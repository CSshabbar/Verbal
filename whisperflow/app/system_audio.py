"""
Meetings — system-audio capture. macOS ScreenCaptureKit lives below; on
Windows the top-of-file shim re-exports the WASAPI loopback implementation
from `app.win_system_audio` so `app.meetings` and DashboardApi.test_meeting_capture
work unchanged (WINDOWS_PARITY_PLAN.md — the paired-module convention).

The one genuinely new subsystem for Meetings (MEETINGS_DESIGN_HANDOFF.md):
captures what the Mac is PLAYING (the other side of a Zoom/Meet/Teams call)
without any bot joining the call. Requires:

  - macOS 13+ (SCStreamConfiguration.capturesAudio)
  - the Screen & System Audio Recording permission (permissions.check_system_audio
    — SCK audio is gated by the Screen Recording TCC class even though we never
    read pixels; we set a 2×2 video box and drop video buffers)
  - pyobjc-framework-ScreenCaptureKit + pyobjc-framework-CoreMedia
    (install with `.venv/bin/python -m pip …` — the venv's `pip` binary is a
    mismatched interpreter; see context/05-conventions.md)

HARD GUARANTEES (Rule #1): nothing in here can break dictation. Every entry
point is try/except'd; failures surface as is_supported()=False or
start()=False and the meeting continues mic-only.
"""
import logging
import sys
import threading
import time

logger = logging.getLogger("verbal.sysaudio")

SAMPLE_RATE = 16000   # capture directly at Whisper's rate — no resample step
CHANNELS = 1


# The SCStreamOutput delegate class must be registered with the ObjC runtime
# exactly ONCE per process — defining it inside start() raised
# "_Output is overriding existing Objective-C class" on the second meeting.
_OUTPUT_CLS = None


def _output_class():
    global _OUTPUT_CLS
    if _OUTPUT_CLS is None:
        import objc

        class _FlumeSCKAudioOutput(objc.lookUpClass("NSObject")):
            def stream_didOutputSampleBuffer_ofType_(self, stream, sbuf, of_type):
                # of_type: 0 = screen (video), 1 = audio, 2 = mic (macOS 15+)
                if of_type != 1:
                    return
                cap = getattr(self, "_capture", None)
                if cap is None:
                    return
                try:
                    cap._consume(sbuf)
                except Exception:
                    pass  # never throw into SCK's queue

        _OUTPUT_CLS = _FlumeSCKAudioOutput
    return _OUTPUT_CLS


def is_supported():
    """True when the SCK audio path is importable and the OS is new enough."""
    try:
        import platform
        major = int(platform.mac_ver()[0].split(".")[0] or 0)
        if major < 13:
            return False
        from ScreenCaptureKit import SCStreamConfiguration
        cfg = SCStreamConfiguration.alloc().init()
        return bool(getattr(cfg, "setCapturesAudio_", None))
    except Exception as e:
        logger.debug("sysaudio unsupported: %s", e)
        return False


class SystemAudioCapture:
    """Streams system-audio float32 mono chunks to `on_audio(np.ndarray)`.

    Lifecycle: start() → callbacks on an SCK internal queue → stop().
    All SCK objects are created lazily inside start() so simply importing this
    module can never fail on an older Mac.
    """

    def __init__(self, on_audio):
        self._on_audio = on_audio          # fn(np.float32 ndarray @16k mono)
        self._stream = None
        self._delegate = None
        self._running = False
        self._level = 0.0                  # rolling peak for UI meters
        self._err = None

    @property
    def level(self):
        return self._level

    @property
    def error(self):
        return self._err

    # ── start / stop ──────────────────────────────────────────────────────────
    def start(self, timeout=6.0):
        """Begin capture. Returns True on success, False otherwise (fail closed)."""
        try:
            return self._start(timeout)
        except Exception as e:
            logger.error("sysaudio start failed: %s", e)
            self._err = str(e)
            return False

    def _start(self, timeout):
        import objc
        from ScreenCaptureKit import (
            SCShareableContent, SCContentFilter, SCStream, SCStreamConfiguration,
        )

        # 1) shareable content (async block API → wait on an Event)
        box = {}
        got = threading.Event()

        def _content_handler(content, error):
            box["content"] = content
            box["error"] = error
            got.set()

        SCShareableContent.getShareableContentWithCompletionHandler_(_content_handler)
        if not got.wait(timeout) or box.get("error") is not None or box.get("content") is None:
            self._err = str(box.get("error") or "no shareable content (permission?)")
            logger.warning("sysaudio: shareable content unavailable: %s", self._err)
            return False

        displays = box["content"].displays()
        if not displays or not len(displays):
            self._err = "no display for content filter"
            return False

        # 2) audio-only filter/config: one display, exclude nothing; video shrunk
        #    to 2×2 and dropped in the delegate — we only consume audio buffers.
        flt = SCContentFilter.alloc().initWithDisplay_excludingWindows_(displays[0], [])
        cfg = SCStreamConfiguration.alloc().init()
        cfg.setCapturesAudio_(True)
        cfg.setExcludesCurrentProcessAudio_(True)   # never re-capture our own cues
        cfg.setSampleRate_(SAMPLE_RATE)
        cfg.setChannelCount_(CHANNELS)
        try:
            from CoreMedia import CMTimeMake
            cfg.setWidth_(2)
            cfg.setHeight_(2)
            cfg.setMinimumFrameInterval_(CMTimeMake(1, 1))  # ≤1 video frame/s (we drop them)
        except Exception:
            pass  # video config is best-effort; we ignore video buffers anyway

        # 3) output delegate (SCStreamOutput protocol) — class registered once
        #    per process; the instance carries a reference back to this capture.
        self._delegate = _output_class().alloc().init()
        self._delegate._capture = self

        # 4) stream — sampleHandlerQueue nil → SCK delivers on an internal queue
        self._stream = SCStream.alloc().initWithFilter_configuration_delegate_(flt, cfg, None)
        ok, err = self._stream.addStreamOutput_type_sampleHandlerQueue_error_(
            self._delegate, 1, None, None)  # 1 = SCStreamOutputTypeAudio
        if not ok:
            self._err = str(err or "addStreamOutput failed")
            return False

        started = threading.Event()
        sbox = {}

        def _start_handler(error):
            sbox["error"] = error
            started.set()

        self._stream.startCaptureWithCompletionHandler_(_start_handler)
        if not started.wait(timeout) or sbox.get("error") is not None:
            self._err = str(sbox.get("error") or "startCapture timed out")
            logger.warning("sysaudio: startCapture failed: %s", self._err)
            self._stream = None
            return False

        self._running = True
        self._err = None
        logger.info("sysaudio: capture started @%dHz", SAMPLE_RATE)
        return True

    def stop(self):
        try:
            if self._stream is not None:
                done = threading.Event()
                self._stream.stopCaptureWithCompletionHandler_(lambda e: done.set())
                done.wait(3.0)
        except Exception as e:
            logger.debug("sysaudio stop: %s", e)
        finally:
            try:
                if self._delegate is not None:
                    self._delegate._capture = None  # break the back-reference
            except Exception:
                pass
            self._stream = None
            self._delegate = None
            self._running = False

    @property
    def running(self):
        return self._running

    # ── CMSampleBuffer → numpy ────────────────────────────────────────────────
    def _consume(self, sbuf):
        import numpy as np
        from CoreMedia import (
            CMSampleBufferGetDataBuffer, CMBlockBufferGetDataLength,
            CMBlockBufferCopyDataBytes,
        )
        block = CMSampleBufferGetDataBuffer(sbuf)
        if block is None:
            return
        length = CMBlockBufferGetDataLength(block)
        if not length:
            return
        # CMBlockBufferCopyDataBytes(theSourceBuffer, offsetToData, dataLength, destination)
        # pyobjc: pass None for the out-buffer and it returns (status, bytes)
        status, data = CMBlockBufferCopyDataBytes(block, 0, length, None)
        if status != 0 or not data:
            return
        audio = np.frombuffer(bytes(data), dtype=np.float32)
        if audio.size == 0:
            return
        try:
            self._level = float(min(1.0, float(abs(audio).max())))
        except Exception:
            self._level = 0.0
        cb = self._on_audio
        if cb is not None:
            cb(audio.copy())


# ── 3-second self-test (PermissionChecklistModal "Test capture") ────────────────
def run_capture_test(app=None, seconds=3.0):
    """Capture briefly and report whether ANY audio arrived. Emits live level
    events to the meeting window meter when `app` is provided."""
    try:
        if not is_supported():
            return {"ok": False, "error": "Needs macOS 13 or later."}
        from app import permissions
        if permissions.check_system_audio() != "granted":
            return {"ok": False,
                    "error": "Screen & System Audio Recording is not granted yet."}

        import numpy as np
        got = {"n": 0, "peak": 0.0}

        def on_audio(chunk):
            got["n"] += 1
            try:
                got["peak"] = max(got["peak"], float(abs(chunk).max()))
            except Exception:
                pass

        cap = SystemAudioCapture(on_audio)
        if not cap.start():
            return {"ok": False, "error": cap.error or "Could not start capture."}
        t0 = time.time()
        while time.time() - t0 < seconds:
            time.sleep(0.12)
            try:
                win = getattr(app, "meeting_window", None) if app else None
                if win:
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


# ── Windows platform shim (W6) ───────────────────────────────────────────
# On Windows the Mac ScreenCaptureKit defs above are unreachable (their
# imports fail at call time on any non-Mac). Override the public symbols
# with the WASAPI-loopback implementation so app.meetings and
# DashboardApi.test_meeting_capture pick up the correct backend without any
# other code change. Placed at the end so it wins the name binding.
if sys.platform == "win32":
    try:
        from app.win_system_audio import (  # noqa: F401
            SAMPLE_RATE, CHANNELS, is_supported,
            SystemAudioCapture, run_capture_test,
        )
    except Exception as _e:  # win_system_audio not built / sounddevice missing
        logger.debug("system_audio: Windows shim not loaded (%s)", _e)
        def is_supported(): return False  # noqa: E301
        def run_capture_test(app=None, seconds=3.0):  # noqa: E301
            return {"ok": False, "error": "system audio unavailable"}
