"""Meetings — Windows system-audio capture via WASAPI loopback.

Mirrors the PUBLIC interface of `app/system_audio.py` (ScreenCaptureKit on
macOS) so `app/meetings.py` and `DashboardApi.test_meeting_capture` work
unchanged once wired via the platform shim. Captures the audio the Windows
box is PLAYING — i.e. the far side of a Zoom/Meet/Teams call — without any
bot joining.

Contract (same as system_audio.py):
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
and the meeting continues mic-only."""

import logging
import threading
import time

logger = logging.getLogger("verbal.sysaudio.win")

SAMPLE_RATE = 16000    # Whisper's rate — resample here so downstream is a no-op
CHANNELS    = 1


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


class SystemAudioCapture:
    """Streams system-audio float32 mono @16kHz to `on_audio(np.ndarray)`.

    Uses the `soundcard` library's loopback microphone (WASAPI internally):
    `sc.get_microphone(id=<speaker>, include_loopback=True)` opens a stream
    that yields whatever the endpoint is playing. Runs on a dedicated
    daemon thread with a small block size — same shape as the Mac
    SCK-delegate callback contract."""

    def __init__(self, on_audio):
        self._on_audio = on_audio
        self._thread = None
        self._stop = None
        self._running = False
        self._level = 0.0
        self._err = None
        self._device_rate = 48000       # WASAPI mix format is typically 48k
        self._device_ch = 2

    @property
    def level(self):    return self._level
    @property
    def error(self):    return self._err
    @property
    def running(self):  return self._running

    def start(self, timeout=6.0):
        try:
            return self._start(timeout)
        except Exception as e:
            logger.error("sysaudio start failed: %s", e)
            self._err = str(e)
            return False

    def _start(self, timeout):
        import soundcard as sc
        import threading

        sp = sc.default_speaker()
        if sp is None:
            self._err = "no default speaker"
            return False
        # include_loopback=True on the SAME-NAME microphone gives us the
        # endpoint's mix (what the box is playing). This is the WASAPI-
        # loopback path — no bot needed.
        lp = sc.get_microphone(id=str(sp.name), include_loopback=True)
        self._device_ch = max(1, int(getattr(lp, "channels", 2) or 2))

        stop = threading.Event()
        self._stop = stop
        started = threading.Event()

        def _run():
            try:
                # Capture at the device's native rate — soundcard picks one
                # that matches the endpoint. Downstream code resamples to 16k.
                with lp.recorder(samplerate=self._device_rate,
                                 channels=self._device_ch,
                                 blocksize=1024) as rec:
                    self._running = True
                    started.set()
                    while not stop.is_set():
                        try:
                            data = rec.record(numframes=1024)
                        except Exception as e:
                            logger.debug("sysaudio record error: %s", e)
                            break
                        self._consume(data)
            except Exception as e:
                self._err = str(e)
                logger.warning("sysaudio loopback loop failed: %s", e)
            finally:
                self._running = False
                started.set()   # unblock the waiter on error

        self._thread = threading.Thread(
            target=_run, name="sysaudio-loopback", daemon=True)
        self._thread.start()

        if not started.wait(timeout):
            self._err = "capture start timed out"
            return False
        if not self._running:
            # error was set inside _run
            return False
        self._err = None
        logger.info("sysaudio: WASAPI loopback started via soundcard @%dHz ch=%d",
                    self._device_rate, self._device_ch)
        return True

    def stop(self):
        try:
            if self._stop is not None:
                self._stop.set()
            if self._thread is not None:
                self._thread.join(timeout=2.0)
        except Exception as e:
            logger.debug("sysaudio stop: %s", e)
        finally:
            self._thread = None
            self._stop = None
            self._running = False

    # ── PortAudio buffer → 16kHz mono float32 ─────────────────────────────
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
