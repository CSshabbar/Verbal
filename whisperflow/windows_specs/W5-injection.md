# W5 — Injection: PID/process identity + `@-file-tag` mentions

**Goal:** bring `app/win_injector.py` to parity with `app/injector.py`: (1) track the dictation
target's **PID + process identity** (not just the window handle + title), and (2) add an
`allow_mentions` path so `@name.ext` file-tags become **real mention chips** in Cursor/Windsurf/VS
Code (parity with `injector._inject_with_mentions`).

## Files

- **Modify:** `app/win_injector.py`.
- **Reference (Mac):** `app/injector.py`.
- **Depends on:** `app/win_ax.py` (W8) for `supported_ide()` / `TAGGING_IDES` — but W5 can land first
  with a guarded import that fails closed until W8 exists.
- **Caller:** `app/win_main.py` — currently `inject_text(result)` (line ~542). Update it to
  `inject_text(result, allow_mentions=self.config.get("filetag_enabled", False))` to match the Mac
  call in `main.py` (`inject_text(result, allow_mentions=self.config.get("filetag_enabled", False))`).

## The gap (Windows vs Mac)

### Current `win_injector.py` (what exists)

- `save_focused_app()` — stores `GetForegroundWindow()` HWND + window **title** only
  (`_previous_hwnd`, `_previous_app_name`).
- `get_focused_app_name()` — returns the window title.
- `restore_focused_app()` — `SetForegroundWindow(_previous_hwnd)`.
- `inject_text(text)` — `pyperclip.copy` → restore focus → `pyautogui.hotkey("ctrl","v")`.
- **No PID, no bundle/exe identity, no `get_focused_app_pid()`, no `get_focused_app_bundle()`, no
  `allow_mentions`.**

### Mac `injector.py` (the target interface)

- `save_focused_app()` stores **PID + localizedName + bundleIdentifier**
  (`_previous_app_pid/_name/_bundle`).
- `get_focused_app_pid()` and `get_focused_app_bundle()` exist — **these are what W7 (autolearn) and
  W8 (file-tags) key off** to read the *dictation target*, not the live-frontmost app (which is the
  overlay by transcription time).
- `inject_text(text, allow_mentions=False)` — when `allow_mentions` and the target is a tagging IDE,
  routes to `_inject_with_mentions`.

## What to implement in `win_injector.py`

### 1. Capture PID + process identity in `save_focused_app()`

Use `GetForegroundWindow` → `GetWindowThreadProcessId` to get the PID, then resolve the executable
name/path as the Windows analog of the Mac bundle id:

```python
import ctypes
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

_previous_hwnd = None
_previous_app_pid = None
_previous_app_name = ""      # window title (keep for history display)
_previous_app_exe = ""       # e.g. "Cursor.exe" — the Windows "bundle" identity

def save_focused_app():
    hwnd = user32.GetForegroundWindow()
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    # exe name via QueryFullProcessImageNameW (PROCESS_QUERY_LIMITED_INFORMATION = 0x1000)
    # or psutil.Process(pid).name() if psutil is bundled.
    ...
```

Resolve the exe with `OpenProcess(0x1000, False, pid)` + `QueryFullProcessImageNameW`, then
`os.path.basename(...)` → `"Cursor.exe"`. (Optionally read `FileDescription` from the version info
for a friendlier name; the exe basename is enough for IDE detection.) Skip capturing when the
foreground window is Verbal's own (compare against our own PID, like the Mac skips
`com.verbal.app`).

### 2. Add the getters (same names the shared code calls)

```python
def get_focused_app_pid():    return _previous_app_pid
def get_focused_app_bundle(): return _previous_app_exe   # exe name is the Windows "bundle"
def get_focused_app_name():   return _previous_app_name  # (already exists)
```

> **Convention note:** `win_ax.supported_ide()` (W8) will classify by **exe name** (`cursor.exe`,
> `windsurf.exe`, `code.exe`, …) where the Mac `filetags._classify` uses the **bundle id**. Keep the
> `get_focused_app_bundle()` name so the shared callers (`injector`/`autolearn`/`filetags` call
> sites) don't branch on OS — it just returns the exe on Windows.

### 3. Add the `allow_mentions` mention path — parity with `injector._inject_with_mentions`

Mirror `injector.py`:

```python
_MENTION_RE = re.compile(r'(?<![\w@])@[A-Za-z0-9_.\-]+\.[A-Za-z0-9]+')  # same regex as injector.py

def inject_text(text, allow_mentions=False):
    if allow_mentions and _MENTION_RE.search(text or ""):
        try:
            from app import win_ax as filetags
            ide = filetags.supported_ide(_previous_app_exe, _previous_app_name)
            tagging = ide in filetags.TAGGING_IDES
        except Exception:
            tagging = False
        if tagging:
            try:
                return _inject_with_mentions(text)
            except Exception as e:
                logger.error("mention injection failed, falling back to paste: %s", e)
    # ...existing plain clipboard-paste path (fail-closed fallback)...
```

`_inject_with_mentions(text)` mirrors the Mac version but with Windows key simulation:

- Split with `_MENTION_RE.split` (N+1 plain chunks) and `_MENTION_RE.findall` (N `@name.ext` tokens).
- For each plain chunk: `pyperclip.copy(chunk)` → `pyautogui.hotkey("ctrl","v")` (the Windows
  equivalent of the Mac `_paste_chunk`/CGEvent paste).
- For each mention: **type** `@` to open the editor's file-mention picker (`pyautogui.typewrite("@")`
  or `pyautogui.press` per char — type the literal, don't paste, so the picker opens), pause ~0.18s,
  type the filename query, pause ~0.35s to let the picker populate, then `pyautogui.press("enter")`
  to accept the highlighted match → real chip. Match the Mac timing (`0.18 / 0.35 / 0.14`).
- Any failure returns to the plain paste so a recording is never lost (Rule #1).

> **Windows nuance:** `pyautogui.typewrite` uses the current keyboard layout; the `@` glyph position
> varies by layout. If `@` fails to open the picker on non-US layouts, fall back to
> `pyperclip.copy("@") + ctrl+v` for the `@` and `typewrite` for the query, or use
> `keyboard`/`pynput` unicode input. Document what shipped.

## Acceptance

- [ ] `get_focused_app_pid()` returns the target PID; `get_focused_app_bundle()` returns the exe
      (e.g. `Cursor.exe`) — verified by dictating into Cursor and logging both.
- [ ] With file-tagging OFF, `inject_text(text)` behaves exactly as today (plain paste).
- [ ] With file-tagging ON and target = Cursor/VS Code, `@main.py` in the dictated text becomes a
      **real mention chip** (open the mention picker, filter, accept).
- [ ] Non-IDE targets ignore mentions and paste literally.
- [ ] Every mention-path failure falls back to plain paste (kill the picker mid-inject and confirm
      the text still lands).
