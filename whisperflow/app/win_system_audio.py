"""Meetings — Windows system-audio capture via WASAPI loopback.

Mirrors the PUBLIC interface of `app/system_audio.py` (ScreenCaptureKit on
macOS) so `app/meetings.py` and `DashboardApi.test_meeting_capture` work
unchanged once wired via the platform shim. Captures the audio the Windows
box is PLAYING — i.e. the far side of a Zoom/Meet/Teams call — without any
bot joining.

Contract (same as system_audio.py):
    import warnings as _warnings
# soundcard emits "data discontinuity in recording" as a RuntimeWarning on
# stderr whenever a WASAPI packet is late (routine on a loaded machine / VM).
# It is informational: route it to the logger at debug instead of the console.
try:
    from soundcard import SoundcardRuntimeWarning as _SCWarn
    _warnings.filterwarnings("ignore", category=_SCWarn)
except Exception:
    pass

SAMPLE_RATE = 16000
    CHANNELS    = 1
    def is_supported() -> bool
    def run_capture_test(app=None, seconds=3.0) -> dict
    class SystemAudioCapture:
        __init__(on_audio)                  # on_audio(np.float32 1-D mono @16k)
        .level, .error, .running
        start(timeout=6.0) -> bool
        stop()

HARD GUARANTEES (WINDOWS_PARITY_PLAN.md §1): dictation and the recording
pipeline never fail because of anything here. All entry points are
try/except'd; failures surface as `is_supported()=False` or `start()=False`
and the meeting continues mic-only.

ROBUSTNESS (2026-08-28) — two field bugs fixed here, see
context/05-conventions.md Rule #76:

  (a) WASAPI loopback yields NO frames while the endpoint is silent, so a
      blocking `record()` could outlive `stop()`'s join and leave the
      IAudioClient open until process exit ("device in use" on the next
      start). Fix: a companion `_SilencePlayer` writes zeros into the
      default speaker for as long as capture runs, which keeps the loopback
      stream producing (zero) frames; the record loop also uses a small
      block and re-checks the stop event between calls, and stop() joins
      deterministically (< 2 s) and is idempotent.
  (b) A device change/unplug mid-meeting used to `break` out of the loop
      and set `_running=False` with no `_err` and no retry. Fix: any
      exception from the recorder (WASAPI raises AUDCLNT_E_DEVICE_INVALIDATED
      via soundcard's `_com.check_error`) or a detected default-endpoint
      change re-resolves the default loopback device and restarts capture,
      bounded by `RestartPolicy` (3 attempts, 1 s backoff, reset after a
      healthy stretch). Each hop logs WARNING and sets `.error`; giving up
      leaves `.running=False` + `.error` for meetings.py to surface.

soundcard API relied on (verified against soundcard 0.4.3 == the pin in
requirements-win.txt, and 0.4.6; mediafoundation.py):
  - `default_speaker()` l.123, `get_microphone(id, include_loopback)` l.156
    (substring/fuzzy match on name → IndexError when absent, l.185)
  - `_Speaker.player(samplerate, channels=None, blocksize=None)` l.441 →
    `_Player` context manager; `.play(data)` l.628 queues and returns as
    soon as the data is in the render buffer (1 ms polling loop, l.663-666)
  - `_Microphone.recorder(samplerate, channels=None, blocksize=None)` l.475 →
    `_Recorder`; `.record(numframes)` l.781 blocks until `numframes` are
    available; `_record_chunk` l.736-756 returns zeros after ~4 device
    periods without frames (so a silent card does NOT hang in these
    versions — the silence player is belt-and-braces for cards that keep the
    packet queue empty AND older builds); COM errors surface as
    `RuntimeError('Error 0x...')` from `_com.check_error` l.107
  - `_AudioClient.__init__` l.494 requests SHARED mode with AUTOCONVERTPCM |
    SRC_DEFAULT_QUALITY (l.546), so asking for 48 kHz is safe on any mix format
  - every `_DeviceEnumerator()` CoInitializeEx's the CALLING thread (l.38-49),
    so device re-resolution from the capture thread is legal
"""

import logging
import threading
import time

logger = logging.getLogger("verbal.sysaudio.win")

SAMPLE_RATE = 16000    # Whisper's rate — resample here so downstream is a no-op
CHANNELS    = 1

# Capture geometry. 1024 frames @48k ≈ 21 ms per callback (same as before);
# the small block keeps stop() latency and reconnect detection tight.
_BLOCK_FRAMES = 1024
# How often the loop checks whether the default output endpoint changed
# under us (WASAPI keeps the OLD endpoint's loopback stream alive — silent —
# when the user switches speakers, so an exception alone is not enough).
_DEVICE_POLL_S = 2.0


def is_supported():
    """True when a WASAPI loopback backend is importable and a default
    speaker exists to loop back from."""
    try:
        import soundcard as sc
        sp = sc.default_speaker()
        return sp is not None
    except Exception as e:
        logger.debug("sysaudio unsupported: %s", e)
        return False


# ── Pure-Python restart/backoff decision (unit-tested by win_sysaudio_fixtures.py) ──
class RestartPolicy:
    """Bounded reconnect budget for the capture loop.

    `next_delay()` returns the seconds to wait before the next attempt, or
    `None` once the budget is exhausted. `note_healthy(seconds_running)`
    refunds the budget after capture has run cleanly for `healthy_after`
    seconds, so a 90-minute meeting with two unrelated glitches an hour
    apart never gives up. No I/O, no threads — safe to test anywhere."""

    def __init__(self, max_attempts=3, backoff_s=1.0, healthy_after_s=10.0):
        self.max_attempts = max(0, int(max_attempts))
        self.backoff_s = max(0.0, float(backoff_s))
        self.healthy_after_s = max(0.0, float(healthy_after_s))
        self.attempts = 0

    def next_delay(self):
        if self.attempts >= self.max_attempts:
            return None
        self.attempts += 1
        return self.backoff_s

    def note_healthy(self, seconds_running):
        if seconds_running >= self.healthy_after_s and self.attempts:
            self.attempts = 0
            return True
        return False

    def reset(self):
        self.attempts = 0

    @property
    def exhausted(self):
        return self.attempts >= self.max_attempts


class _DeviceChanged(Exception):
    """Raised inside the record loop when the default speaker is no longer
    the endpoint we opened the loopback on."""


class _SilencePlayer:
    """Plays zeros into `speaker` while running (see module docstring (a)).

    Entirely optional: if the player cannot be opened (no render endpoint,
    exclusive-mode app, COM error) capture still proceeds — we only lose the
    guarantee that a silent endpoint keeps producing loopback frames."""

    def __init__(self, speaker, samplerate, channels, blocksize=480):
        self._speaker = speaker
        self._rate = int(samplerate)
        self._ch = max(1, int(channels))
        self._block = int(blocksize)          # 480 @48k = 10 ms per play()
        self._stop = threading.Event()
        self._thread = None
        self.ok = False

    def start(self):
        self._thread = threading.Thread(target=self._run, name="sysaudio-silence",
                                        daemon=True)
        self._thread.start()

    def _run(self):
        try:
            import numpy as np
            zeros = np.zeros((self._block, self._ch), dtype="float32")
            with self._speaker.player(samplerate=self._rate, channels=self._ch,
                                      blocksize=self._block) as p:
                self.ok = True
                while not self._stop.is_set():
                    # play() returns once the block is queued; when the
                    # render buffer is full it waits ~one block (10 ms) —
                    # so stop latency is bounded by the block length.
                    p.play(zeros)
        except Exception as e:
            # Never fatal — see class docstring.
            logger.debug("sysaudio silence player ended: %s", e)
        finally:
            self.ok = False

    def stop(self, timeout=1.0):
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout)
        self._thread = None


class SystemAudioCapture:
    """Streams system-audio float32 mono @16kHz to `on_audio(np.ndarray)`.

    Uses the `soundcard` library's loopback microphone (WASAPI internally):
    `sc.get_microphone(id=<speaker>, include_loopback=True)` opens a stream
    that yields whatever the endpoint is playing. Runs on a dedicated
    daemon thread with a small block size — same shape as the Mac
    SCK-delegate callback contract — plus a silence-player thread and a
    bounded reconnect loop (module docstring)."""

    RECONNECT_ATTEMPTS = 3
    RECONNECT_BACKOFF_S = 1.0
    RECONNECT_HEALTHY_S = 10.0

    def __init__(self, on_audio):
        self._on_audio = on_audio
        self._thread = None
        self._stop = None
        self._running = False
        self._level = 0.0
        self._err = None
        self._device_rate = 48000       # WASAPI mix format is typically 48k
        self._device_ch = 2
        self._device_id = None          # id of the speaker we looped back on
        self._device_name = None
        self._reconnects = 0            # successful re-opens this session
        self._policy = RestartPolicy(self.RECONNECT_ATTEMPTS,
                                     self.RECONNECT_BACKOFF_S,
                                     self.RECONNECT_HEALTHY_S)
        self._lock = threading.Lock()   # serialises start()/stop()

    @property
    def level(self):    return self._level
    @property
    def error(self):    return self._err
    @property
    def running(self):  return self._running
    @property
    def reconnects(self):
        """Number of successful mid-session re-opens (diagnostics)."""
        return self._reconnects

    # ── start ──────────────────────────────────────────────────────────────
    def start(self, timeout=6.0):
        try:
            with self._lock:
                return self._start(timeout)
        except Exception as e:
            logger.error("sysaudio start failed: %s", e)
            self._err = str(e)
            return False

    def _open_loopback(self, sc):
        """Resolve the CURRENT default speaker and its loopback microphone.
        Called on every (re)connect so a changed default is picked up."""
        sp = sc.default_speaker()
        if sp is None:
            raise RuntimeError("no default speaker")
        # include_loopback=True on the SAME-NAME microphone gives us the
        # endpoint's mix (what the box is playing). This is the WASAPI-
        # loopback path — no bot needed.
        lp = sc.get_microphone(id=str(sp.name), include_loopback=True)
        try:
            ch = int(getattr(lp, "channels", 2) or 2)
        except Exception:
            ch = 2
        self._device_ch = max(1, ch)
        self._device_id = getattr(sp, "id", None)
        self._device_name = getattr(sp, "name", None)
        return sp, lp

    def _start(self, timeout):
        import soundcard as sc

        if self._thread is not None and self._thread.is_alive():
            # already running — idempotent
            return bool(self._running)

        # Resolve once up-front so a missing device fails start() synchronously
        # (meetings.py logs `.error` and goes mic-only).
        sp, lp = self._open_loopback(sc)

        stop = threading.Event()
        self._stop = stop
        started = threading.Event()
        self._policy.reset()
        self._reconnects = 0
        self._err = None

        self._thread = threading.Thread(
            target=self._run, args=(sc, sp, lp, stop, started),
            name="sysaudio-loopback", daemon=True)
        self._thread.start()

        if not started.wait(timeout):
            self._err = "capture start timed out"
            stop.set()
            return False
        if not self._running:
            # error was set inside _run
            if not self._err:
                self._err = "capture did not start"
            return False
        self._err = None
        logger.info("sysaudio: WASAPI loopback started via soundcard @%dHz ch=%d on %r",
                    self._device_rate, self._device_ch, self._device_name)
        return True

    # ── capture thread ─────────────────────────────────────────────────────
    def _run(self, sc, sp, lp, stop, started):
        """Outer supervisor: runs one capture segment at a time and applies
        `RestartPolicy` between failures. NEVER lets an exception escape."""
        ever_ok = False
        try:
            while not stop.is_set():
                t0 = time.monotonic()
                reason = None
                try:
                    reason = self._capture_segment(sc, sp, lp, stop, started, ever_ok)
                except _DeviceChanged as e:
                    reason = str(e) or "default output device changed"
                except Exception as e:
                    reason = "loopback error: %s" % (e,)
                finally:
                    self._running = False
                    self._level = 0.0
                if stop.is_set() or reason is None:
                    break
                if not started.is_set():
                    # The FIRST segment never came up: that is a start()
                    # failure, not a mid-meeting fault. Report it and exit so
                    # start() returns False synchronously and no orphan thread
                    # keeps retrying (and calling back) after meetings.py has
                    # dropped us and gone mic-only.
                    self._err = reason
                    logger.warning("sysaudio: could not open loopback: %s", reason)
                    break
                ever_ok = True

                # A mid-session failure: decide whether to retry.
                ran_for = time.monotonic() - t0
                self._policy.note_healthy(ran_for)
                delay = self._policy.next_delay()
                if delay is None:
                    self._err = ("system audio lost (%s) — gave up after %d reconnect "
                                 "attempts; meeting continues mic-only"
                                 % (reason, self._policy.max_attempts))
                    logger.warning("sysaudio: %s", self._err)
                    started.set()
                    break
                self._err = "system audio interrupted (%s) — reconnecting (%d/%d)" % (
                    reason, self._policy.attempts, self._policy.max_attempts)
                logger.warning("sysaudio: %s", self._err)
                if stop.wait(delay):
                    break
                try:
                    sp, lp = self._open_loopback(sc)
                except Exception as e:
                    # Device still missing — count it as a failed attempt and
                    # loop again (the next iteration's segment will fail fast
                    # too if `lp` is stale, which is fine).
                    logger.warning("sysaudio: re-resolve failed: %s", e)
                    continue
        except Exception as e:
            # Absolute backstop — nothing may propagate off this thread.
            self._err = str(e)
            logger.warning("sysaudio supervisor failed: %s", e)
        finally:
            self._running = False
            self._level = 0.0
            started.set()   # unblock the waiter in every exit path

    def _capture_segment(self, sc, sp, lp, stop, started, is_reconnect=False):
        """One recorder lifetime. Returns None on a clean stop, or a short
        reason string when the segment ended because of a fault."""
        silence = _SilencePlayer(sp, self._device_rate, self._device_ch)
        try:
            with lp.recorder(samplerate=self._device_rate,
                             channels=self._device_ch,
                             blocksize=_BLOCK_FRAMES) as rec:
                silence.start()
                self._running = True
                if is_reconnect:
                    self._reconnects += 1
                    logger.info("sysaudio: loopback re-opened on %r (reconnect #%d)",
                                self._device_name, self._reconnects)
                    self._err = None
                started.set()
                seg_t0 = time.monotonic()
                next_poll = seg_t0 + _DEVICE_POLL_S
                healthy_refunded = False
                while not stop.is_set():
                    data = rec.record(numframes=_BLOCK_FRAMES)
                    if stop.is_set():
                        break
                    self._consume(data)
                    now = time.monotonic()
                    if not healthy_refunded and self._policy.note_healthy(now - seg_t0):
                        healthy_refunded = True
                    if now >= next_poll:
                        next_poll = now + _DEVICE_POLL_S
                        self._check_default_device(sc)
                return None
        finally:
            silence.stop()

    def _check_default_device(self, sc):
        """Raise `_DeviceChanged` if the default speaker is no longer the one
        we opened. Any error while asking is ignored (the recorder itself will
        raise if the device really vanished)."""
        if self._device_id is None:
            return
        try:
            cur = sc.default_speaker()
            cur_id = getattr(cur, "id", None) if cur is not None else None
        except Exception:
            return
        if cur_id is not None and cur_id != self._device_id:
            raise _DeviceChanged("default output changed to %r"
                                 % (getattr(cur, "name", cur_id),))

    # ── stop ───────────────────────────────────────────────────────────────
    def stop(self):
        """Deterministic and idempotent: signals the loop, joins ≤ 2 s, and
        always clears state. The recorder/player context managers close on
        their own threads (`with` blocks) as soon as the loop observes the
        stop event — the silence player guarantees `record()` returns
        within ~one block even on a silent endpoint."""
        try:
            with self._lock:
                stop = self._stop
                t = self._thread
                if stop is not None:
                    stop.set()
                if t is not None and t.is_alive():
                    t.join(timeout=2.0)
                    if t.is_alive():
                        logger.warning("sysaudio stop: capture thread still alive after 2 s "
                                       "(WASAPI record() did not return); handle will "
                                       "close on process exit")
        except Exception as e:
            logger.debug("sysaudio stop: %s", e)
        finally:
            self._thread = None
            self._stop = None
            self._running = False
            self._level = 0.0

    # ── WASAPI buffer → 16kHz mono float32 ────────────────────────────────
    def _consume(self, indata):
        import numpy as np
        if indata is None:
            return
        # `indata` is (frames, channels) float32. Downmix to mono.
        try:
            if indata.ndim == 2 and indata.shape[1] > 1:
                mono = indata.mean(axis=1).astype(np.float32, copy=False)
            elif indata.ndim == 2:
                mono = indata[:, 0].astype(np.float32, copy=False)
            else:
                mono = indata.astype(np.float32, copy=False)
        except Exception:
            return

        # Resample device_rate → 16 kHz using scipy (already bundled).
        if self._device_rate != SAMPLE_RATE:
            try:
                from scipy.signal import resample_poly
                from math import gcd
                g = gcd(self._device_rate, SAMPLE_RATE)
                up = SAMPLE_RATE // g
                down = self._device_rate // g
                mono = resample_poly(mono, up, down).astype("float32", copy=False)
            except Exception as e:
                logger.debug("resample failed (%s), passing native rate", e)

        try:
            self._level = float(min(1.0, float(abs(mono).max())))
        except Exception:
            self._level = 0.0

        cb = self._on_audio
        if cb is not None:
            try:
                cb(mono.copy())
            except Exception:
                pass  # never propagate into the callback thread


# ── 3-second self-test (PermissionChecklistModal "Test capture") ─────────
def run_capture_test(app=None, seconds=3.0):
    """Capture briefly and report whether ANY audio arrived."""
    try:
        if not is_supported():
            return {"ok": False, "error": "WASAPI loopback is not available on this machine."}
        # Windows has no OS-level gate for loopback; skip the permissions
        # check that the Mac version does (see permissions.check_system_audio
        # → always 'granted' on Windows).

        got = {"n": 0, "peak": 0.0}

        def on_audio(chunk):
            got["n"] += 1
            try:
                p = float(abs(chunk).max())
                if p > got["peak"]:
                    got["peak"] = p
            except Exception:
                pass

        cap = SystemAudioCapture(on_audio)
        if not cap.start():
            return {"ok": False, "error": cap.error or "Could not start WASAPI capture."}
        t0 = time.time()
        while time.time() - t0 < seconds:
            time.sleep(0.12)
            try:
                win = getattr(app, "meeting_window", None) if app else None
                if win and hasattr(win, "emit"):
                    win.emit("testLevel", {"level": cap.level})
            except Exception:
                pass
        cap.stop()

        if got["n"] == 0:
            return {"ok": False,
                    "error": "Capture started but no audio buffers arrived. "
                             "Play any sound and retry."}
        return {"ok": True, "buffers": got["n"], "peak": round(got["peak"], 4),
                "silent": got["peak"] < 0.001}
    except Exception as e:
        logger.error("capture test failed: %s", e)
        return {"ok": False, "error": str(e)}
