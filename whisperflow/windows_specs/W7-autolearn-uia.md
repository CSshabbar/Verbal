# W7 — Autolearn: `win_editwatch.py` (UI Automation) + confirm pill

**Goal:** replicate `app/autolearn.py::EditWatcher` on Windows using **UI Automation**
(`uiautomation` / `comtypes`) to read the target field's text after injection — instead of macOS
Accessibility (`AXValue` / `AXSelectedTextRange`). **Reuse the entire portable diff/classify core**
from `autolearn.py`; only swap the native text read-back. Render the confirmation pill
(`autolearn_widget.py::autolearn_widget_html()`) as a non-activating pywebview window.

## Files

- **Create:** `app/win_editwatch.py` — `EditWatcher` (same public API as the Mac one).
- **Create:** `app/win_autolearn_widget.py` — `WinAutoLearnWidget` hosting `autolearn_widget_html()`.
- **Reuse (import, do not reimplement):** `app/autolearn.py` — `classify`, `tokenize`, `align`,
  `apply_observation_guard`, `record_declined`, `record_offered`, `is_declined`, and all the phonetic/
  orthographic helpers. These are **pure Python, no AppKit** — import them directly.
- **Reuse (do not edit):** `app/autolearn_widget.py::autolearn_widget_html()`.
- **Reference (Mac hosts):** `app/autolearn_widget.py` (`AutoLearnWidget`).
- **Depends on:** `app/win_injector.py` (W5) for `get_focused_app_pid()` / `get_focused_app_bundle()`.

## Portable core to REUSE vs native layer to REPLACE

`autolearn.py` is cleanly split. **Keep everything except the AX read-back.**

**Reuse as-is (portable, pure):**
- `classify(inserted_text, edited_text, config=None)` — the whole T→E decision pipeline (tokenize →
  align → edit-shape gate → phonetic → orthographic → case/punct → common-word/proper-noun). Returns
  the Decision dict.
- `apply_observation_guard(decision, keystrokes_observed, ms_since_insert)` (F10) — the final guard.
- `align`, `tokenize`, `levenshtein`, `double_metaphone`, `phonetic_match`, declined/offered
  bookkeeping, common-word loading.

**Replace (native read-back) — the only Windows-specific part:**
`EditWatcher._run` reads the focused element's live value and caret via AX:
- `_app_element(pid)` = `AXUIElementCreateApplication(pid)` → **Windows:** UIA element for the process.
- `_focused_element(app_el)` via `AXFocusedUIElement` → **Windows:** the focused control.
- `_read_value(element)` reads `"AXValue"` → **Windows:** `TextPattern` (`DocumentRange.GetText`) or
  `ValuePattern.CurrentValue`.
- `_caret_location` reads `"AXSelectedTextRange"` → **Windows:** `TextPattern.GetSelection()` →
  range start offset.
- `_is_secure(element)` checks secure-text → **Windows:** `ValuePattern.CurrentIsReadOnly` /
  password control (`IsPassword` / ControlType), skip.
- `_set_messaging_timeout` (AX timeout) → **Windows:** no direct equivalent; bound your own polling
  with a deadline (the Mac already uses `_EW_POLL_INTERVAL = 0.15` and an overall deadline).

## Public API `win_editwatch.EditWatcher` MUST expose (same as Mac)

```python
class EditWatcher:
    def __init__(self): ...
    def arm(self, pid, bundle, inserted_text, on_decision_callback) -> bool:
        """Non-blocking. Watches the target field for an edit to inserted_text and
        calls on_decision_callback(decision_dict) AT MOST ONCE. Returns True if a
        watch thread started, else False (bad args → silent no-op). Never raises."""
    def cancel(self): ...
```

Behavior contract (copy from the Mac docstring, lines ~744–812):
- `arm()` returns immediately; all UIA work on an internal **daemon thread**.
- Calling `arm()` again **cancels** any in-flight watch first (no stacking).
- The callback fires **at most once**, with a Decision that has already passed
  `apply_observation_guard`.
- **Fails CLOSED:** unreadable / secure / password / flaky target, or any exception → never calls the
  callback, never raises, never affects transcription.

## UIA read-back implementation notes

- Use `uiautomation` (wraps `comtypes` IUIAutomation). Init COM on the watch thread
  (`comtypes.CoInitialize()` / `CoUninitialize()`).
- Resolve the target element from **PID** (from `win_injector.get_focused_app_pid()`), not the live
  focused control globally — by transcription time the overlay may hold focus. Options:
  `uiautomation.GetFocusedControl()` guarded to the target PID, or walk from the process's top window.
- Read text via `TextPattern` first (`pattern.DocumentRange.GetText(-1)`), fall back to
  `ValuePattern.Value`. Poll on `_EW_POLL_INTERVAL` up to the overall deadline (reuse the Mac's timing
  constants), detect when the value diverges from `inserted_text`, capture the settled edited text,
  then feed `classify(inserted_text, edited_text, config)` + `apply_observation_guard(...)`.
- Skip password/secure fields: `ValuePattern.CurrentIsReadOnly`, or control type = `Edit` with the
  `IsPassword`/protected property set.
- Keep it bounded and guarded exactly like `filetags`/`autolearn` (node caps, deadlines) — a slow UIA
  tree must never stall the pipeline.

## The confirm pill — `WinAutoLearnWidget`

Host `autolearn_widget_html()` in a **borderless, non-activating, always-on-top** pywebview window
(same `WS_EX_NOACTIVATE` technique as W3 — it must never steal focus from the app the user is editing).
Mirror the Mac `AutoLearnWidget` public interface:

```python
class WinAutoLearnWidget:
    def __init__(self, app=None): ...
    def setup(self): ...
    def show(self, old, new): ...   # push window.VerbalAutolearn({old,new}); auto-dismiss ~20s
    def hide(self): ...             # push window.VerbalAutolearnHide(); order out
    @property
    def visible(self) -> bool: ...
```

Bridge (`js_api`) methods the widget's HTML calls: `autolearn_add` (learn the correction →
dictionary), `autolearn_close` (dismiss). Push the payload with
`window.evaluate_js("if(window.VerbalAutolearn)window.VerbalAutolearn(%s)" % json.dumps({"old":old,"new":new}))`
and auto-dismiss after ~20s via a cancel-token timer (see `autolearn_widget.py::show` lines ~119–150).

## Where to arm it in `win_main`

Mirror `main.py` (~lines 799–883). Right **after** `inject_text(result, allow_mentions=...)` in
`win_main.VerbalWinApp._process_audio`, if autolearn is enabled
(`self.config.get("autolearn_enabled", ...)` — check `DashboardApi.get_autolearn_enabled` for the
key/default), arm the watcher on a background thread:

```python
from app import win_editwatch as autolearn_win
from app.win_injector import get_focused_app_pid, get_focused_app_bundle
watcher = self._edit_watcher = autolearn_win.EditWatcher()
watcher.arm(
    pid=get_focused_app_pid(),
    bundle=get_focused_app_bundle(),
    inserted_text=result,
    on_decision_callback=lambda d: self._on_main(
        lambda: self.autolearn_widget.show(d["old"], d["new"])) if d and d.get("should_offer") else None,
)
```

(Use the same Decision keys the Mac callback uses — inspect the Decision dict returned by
`autolearn.classify` / `_decision` for the exact field names, e.g. `old`/`new`/offer flag/`reason`.)
Instantiate `self.autolearn_widget = WinAutoLearnWidget(self)` in `__init__`. Arming and the widget
must be fully try/except'd — a failure here can never affect `record → transcribe → inject`.

## Acceptance

- [ ] Dictate a word into Notepad/Word, then manually correct it → the confirm pill appears offering
      to learn `old → new`; "Add" writes it to the dictionary; "Close"/timeout dismisses.
- [ ] Classification parity: the same T→E pairs that trigger/reject on Mac trigger/reject on Windows
      (because `classify` is shared) — spot-check a phonetic fix, a case-only change (reject), and a
      proper-noun.
- [ ] Password fields and read-only fields never trigger the pill.
- [ ] Pill never steals focus (typing test as in W3).
- [ ] Autolearn disabled, or UIA read failing, or widget failing → dictation unaffected, no exception.
