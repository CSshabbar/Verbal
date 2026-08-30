# W6 — Meetings: `win_system_audio.py` (WASAPI loopback) + full wiring

**Goal:** bring Meetings to Windows. Create `app/win_system_audio.py` that mirrors the **public
interface** of `app/system_audio.py` but captures system audio via **WASAPI loopback** instead of
ScreenCaptureKit. Wire `MeetingManager` into `VerbalWinApp`, host the meeting window + HUD as pywebview
windows, and add a Windows `permissions.py` variant. The cross-platform `app/meetings.py` is reused
**unchanged**.

## `meetings.py` is cross-platform — confirmed

`app/meetings.py` (`MeetingSession`, `MeetingManager`) has **no macOS imports at module load** — top
imports are `json/logging/os/threading/time/uuid/wave/numpy` + `app.config`. It captures:

- **mic** → its own `sounddevice.InputStream` (`_start`, line ~515: `import sounddevice as sd`) — this
  already works on Windows.
- **system audio** → lazily: inside `MeetingSession._start` (~line 600):
  ```python
  from app.system_audio import SystemAudioCapture, is_supported
  if is_supported():
      self._sys_cap = SystemAudioCapture(sys_cb)
  ```

**Problem:** that hardcodes `app.system_audio` (the ScreenCaptureKit module, which imports
ScreenCaptureKit and returns `is_supported()=False` on Windows → meetings run mic-only). To capture
the call audio on Windows, make that import **platform-aware**. Preferred approach — a tiny shim so
`meetings.py` stays clean:

- Option A (minimal edit to `meetings.py`, behind a platform check): change the lazy import to select
  the module by platform, e.g. `system_audio = win_system_audio if sys.platform=='win32' else system_audio`.
- Option B (no `meetings.py` edit): make `app/system_audio.py` re-export the Windows implementation
  when `sys.platform == 'win32'` (a top-of-file branch: `if win32: from app.win_system_audio import *`).

Option A is cleaner and is the documented Mac↔Win pairing convention. Whichever you pick, the
`SystemAudioCapture` / `is_supported` / `run_capture_test` **names and shapes must be identical** so
`meetings.py` calls them without further change.

## The exact public interface to mirror (from `system_audio.py`)

Constants: `SAMPLE_RATE = 16000`, `CHANNELS = 1`. Capture directly at **16 kHz mono float32** (no
resample step downstream) — WASAPI loopback typically hands you 44.1/48 kHz stereo int/float, so you
**must resample to 16 kHz + downmix to mono** inside the capture before calling the callback.

```python
# module-level
def is_supported() -> bool: ...
    # True when a WASAPI loopback path is importable/usable on this machine. Fail-closed.

class SystemAudioCapture:
    def __init__(self, on_audio):        # on_audio(np.float32 ndarray @16k mono)
    @property
    def level(self) -> float: ...        # rolling peak 0..1 for the UI meter
    @property
    def error(self): ...                 # last error string or None
    @property
    def running(self) -> bool: ...
    def start(self, timeout=6.0) -> bool: ...  # True on success, False = fail closed
    def stop(self): ...

def run_capture_test(app=None, seconds=3.0) -> dict: ...
    # {"ok": True, "buffers": n, "peak": p, "silent": bool} | {"ok": False, "error": str}
    # emit live level to the meeting window meter: app.meeting_window.emit("testLevel", {"level": cap.level})
```

The **sample-callback contract** the rest of the system depends on: `on_audio` receives a **1-D
`np.float32` ndarray, mono, 16 kHz**, and must be called with a **copy** (`audio.copy()`), never
raising into the capture thread (swallow all exceptions — see `system_audio.py::_consume`).
`run_capture_test` must gate on `permissions.check_system_audio()` and `is_supported()` and report
whether any buffers arrived, exactly like the Mac version (used by the "Test capture" button).

## WASAPI loopback implementation

Primary path — **sounddevice WASAPI loopback**:

```python
import sounddevice as sd
was = sd.WasapiSettings(loopback=True)
# open an InputStream on the default OUTPUT device with loopback=True — this
# captures what the speakers are PLAYING (the far side of the call).
stream = sd.InputStream(device=<default output device index>, channels=..., samplerate=<device rate>,
                        dtype="float32", extra_settings=was, callback=cb)
```

In the callback: downmix to mono (`frames.mean(axis=1)`), resample device-rate → 16 kHz (use
`scipy.signal.resample_poly` — `scipy` is already bundled), update `self._level` (peak), then
`self._on_audio(mono16k.copy())`. Pick the **default render (output) device** via
`sd.query_devices(kind='output')` / `sd.default.device`.

**Fallbacks** (already in `requirements-win.txt`): `soundcard` (`soundcard.get_microphone(id=<speaker
id>, include_loopback=True)`), and if that proves unreliable, `PyAudioWPatch` (WASAPI-loopback fork of
PyAudio — noted in `requirements-win.txt`). Try sounddevice first; on failure fall to soundcard;
`is_supported()` returns True if any backend can open a loopback stream. **Exclude our own process
audio** if the backend supports it (WASAPI loopback captures the whole endpoint mix, so our start/stop
cues may leak in — the Mac uses `setExcludesCurrentProcessAudio_(True)`; on Windows, prefer capturing
before playing cues or accept minor leakage and note it).

## Wire `MeetingManager` into `VerbalWinApp`

Mirror the Mac wiring in `main.py` (lines ~122–127, ~475–496). In `win_main.py`:

```python
# __init__
self.meetings = None
self.meeting_window = None
self.meeting_hud = None
try:
    from app.meetings import MeetingManager
    self.meetings = MeetingManager(self)
except Exception as e:
    logger.error("MeetingManager init failed: %s", e)   # fail closed → meetings unavailable

def _meeting_win(self):     # lazy, like main.py
    if self.meeting_window is None:
        from app.win_meeting_window import WinMeetingWindow
        self.meeting_window = WinMeetingWindow(self)
    return self.meeting_window

def _meeting_hud(self):
    if self.meeting_hud is None:
        from app.win_meeting_hud import WinMeetingHud
        self.meeting_hud = WinMeetingHud(self)
    return self.meeting_hud

def _toggle_meeting(self, _=None):
    ...  # port main.py::_toggle_meeting: permission checklist vs pre-meeting modal, start/stop
```

`DashboardApi.open_meeting_launcher` already calls `self.app._toggle_meeting` (guarded), and
`_meeting_mode`/`open_meeting`/`close_meeting_window`/`expand_meeting_window`/`collapse_meeting_window`
already call `getattr(self.app, "meeting_window", None)` methods. So once `self.meetings` and
`self.meeting_window`/`_meeting_win()` exist on the Windows app, most meeting `DashboardApi` methods
light up with no further backend change.

## Meeting window + HUD as pywebview windows

- **Create `app/win_meeting_window.py`** (`WinMeetingWindow`) hosting `app/meeting_html.py::meeting_html()`.
  Mirror the Mac `MeetingWindow` (`app/meeting_window.py`) **public interface** the backend calls:
  `show(mode="premeeting")`, `hide()`, `set_mode(mode)`, `expand()`, `collapse()`,
  `emit(event, payload)`, `page_ready()`. On Mac these animate between a compact **bar** layout and a
  full **window** layout; on Windows, implement `expand`/`collapse` by resizing/repositioning the
  pywebview window (WebView2 won't do the fluid frame morph — a resize is acceptable parity).
  `emit` = `window.evaluate_js("window.VerbalNative(<event>,<payload>)")`. The bridge (`js_api`) must
  expose the meeting methods the page calls (they're all on `DashboardApi`, so pass a `DashboardApi`
  or delegate to it). Honor the `meeting_page_ready` handshake (`DashboardApi.meeting_page_ready` →
  `dashboard.page_ready()` flushes queued events) — queue `emit`s until the page signals ready.
- **Create `app/win_meeting_hud.py`** (`WinMeetingHud`) hosting `app/meeting_hud_html.py::meeting_hud_html()`
  as a small **non-activating always-on-top** window (same `WS_EX_NOACTIVATE` technique as W3 — it
  floats during a call and must not steal focus). Mirror `app/meeting_hud.py::MeetingHud`:
  `show()`, `hide()`, `visible`, `push(event, payload)`, and bridge actions `hud_star`, `hud_pause`,
  `hud_return`.

## Windows `permissions.py` variant

`app/permissions.py` is macOS-only (TCC/AVFoundation/Quartz). Add a **Windows branch** (top-of-file
`if sys.platform == 'win32'` returning the Windows implementations, or a paired module the macOS file
imports). Windows meeting semantics:

- `check_system_audio()` → **`"granted"`** always. WASAPI loopback needs no OS permission (there is no
  screen-recording gate like macOS). So `meeting_permissions()` step `system_audio` is always done.
- `check_microphone()` → best-effort: on Win10/11 mic access is gated by a privacy setting, but there's
  no synchronous API. Return `"granted"` optimistically (or `"unknown"`); `request_microphone()`
  opens the Settings deep-link **`ms-settings:privacy-microphone`** (via `os.startfile` /
  `subprocess.Popen(["cmd","/c","start","ms-settings:privacy-microphone"])`).
- `check_accessibility()` → `"granted"` (Windows needs no accessibility grant to paste; matches
  `win_injector.request_accessibility()` which is a no-op).
- `system_audio_capture_supported()` → `bool(win_system_audio.is_supported())`.
- `meeting_permissions()` → same shape as the Mac (`supported`, `system_audio`, `microphone`, `ready`,
  `steps[]`) so the PermissionChecklistModal renders identically. With system-audio always granted,
  the checklist is effectively just mic + capture-support.
- Keep `all_status()`, `request(which)`, and the `check_*`/`request_*` names identical so
  `DashboardApi.get_permissions/request_permission/get_meeting_permissions` work unchanged.

## DashboardApi meeting methods that must go live on Windows

All of these currently return `{"ok": False, "error": "unavailable"}` (or "…unavailable on this
platform.") because `self._meetings()` / `self.app.meeting_window` are `None` on Windows. They become
live automatically once `self.meetings` (MeetingManager) and the meeting window/HUD exist — verify
each:

- `start_meeting(title, use_mic, use_system)` — "Meetings unavailable on this platform." → live.
- `stop_meeting()`, `pause_meeting()`, `mark_moment(label)`.
- `open_meeting_launcher()`, `open_meeting(meeting_id)`, `delete_meeting(meeting_id)`.
- `list_meetings()`, `get_meeting(meeting_id)`, `export_meeting(meeting_id, fmt)`,
  `get_meeting_audio(meeting_id)`.
- `retry_meeting_summary(meeting_id)`, `ask_meetings(question)`.
- `set_action_item_done/text`, `delete_action_item`, `set_transcript_text`,
  `delete_marked_moment`, `set_mark_note`, `regenerate_hybrid`, `set_meeting_pinned`,
  `set_speaker_name`, `rename_speaker`, `set_meeting_title`, `save_meeting_scratchpad`.
- `get_meeting_settings()`, `set_meeting_setting(key, value)` (these already work — no MeetingManager
  needed).
- `test_meeting_capture()` — imports `run_capture_test` from `app.system_audio`; make it resolve to
  the Windows capture (see the platform shim above).
- Window-control methods (`meeting_permissions_skipped/done`, `_meeting_mode`, `close_meeting_window`,
  `meeting_page_ready`, `expand_meeting_window`, `collapse_meeting_window`) — go live once
  `self.app.meeting_window` (via `_meeting_win()`) exists.

## Acceptance

- [ ] `win_system_audio.is_supported()` is True on a machine with audio output; `run_capture_test()`
      returns `ok:True` with `silent:False` while audio plays.
- [ ] Callback delivers 16 kHz mono float32 (assert `dtype`, 1-D, and rate downstream).
- [ ] Start a real meeting (Zoom/Meet/Teams): both **your mic** and the **far-side audio** appear in
      the live transcript; summary + action items generate; meeting saves to Supabase.
- [ ] Meeting window renders `meeting_html()` (pre-meeting → recording bar → summary) matching Mac;
      HUD renders `meeting_hud_html()` and does not steal focus.
- [ ] PermissionChecklistModal shows system-audio granted, mic step, and "Test capture" works.
- [ ] With loopback unavailable, meeting still runs **mic-only** and dictation is unaffected (Rule #1).
