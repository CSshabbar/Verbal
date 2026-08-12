"""Windows text injection — parity interface with app/injector.py (macOS).

Public surface the shared callers rely on:

    save_focused_app()          # capture PID + window title + exe name
    restore_focused_app()       # SetForegroundWindow the saved HWND
    get_focused_app_name()      # window title (used in history display)
    get_focused_app_pid()       # PID of the dictation target
    get_focused_app_bundle()    # exe basename (e.g. "Cursor.exe") — Windows "bundle"
    inject_text(text, allow_mentions=False)

When `allow_mentions` is True AND the recorded target is a tagging IDE (Cursor,
Windsurf, VS Code — resolved by app.win_ax.supported_ide()), inline `@name.ext`
tokens are TYPED into the editor's mention picker so they become real chips,
matching the Mac `_inject_with_mentions` path. Every failure in that path
falls back to plain clipboard paste — a recording is never lost (peripheral
features must fail closed, per WINDOWS_PARITY_PLAN.md §1).

W8 (app/win_ax.py) has not yet landed at the time this ships — the import is
guarded, so until then `allow_mentions=True` behaves like plain paste (the
tagging check returns False and we fall through).
"""

import ctypes
import ctypes.wintypes as wt
import logging
import os
import re
import time

import pyperclip

logger = logging.getLogger("verbal.injector")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# ── PID → exe resolution (Win32) ─────────────────────────────────────────
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# ── SendInput (layout-safe unicode typing) ───────────────────────────────
INPUT_KEYBOARD    = 1
KEYEVENTF_KEYUP   = 0x0002
KEYEVENTF_UNICODE = 0x0004

ULONG_PTR = ctypes.c_size_t


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk",         wt.WORD),
                ("wScan",       wt.WORD),
                ("dwFlags",     wt.DWORD),
                ("time",        wt.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


# MOUSEINPUT / HARDWAREINPUT are declared purely so the union is sized
# correctly. The INPUT union takes the size of its LARGEST member, and
# SendInput validates the struct size we hand it against the real x64
# layout (40 bytes). Declaring only KEYBDINPUT yields 32 bytes and every
# SendInput call fails with ERROR_INVALID_PARAMETER (87) while appearing
# to succeed — no keystrokes are injected at all.
class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx",          wt.LONG),
                ("dy",          wt.LONG),
                ("mouseData",   wt.DWORD),
                ("dwFlags",     wt.DWORD),
                ("time",        wt.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg",    wt.DWORD),
                ("wParamL", wt.WORD),
                ("wParamH", wt.WORD)]


class _INPUT_U(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT),
                ("mi", _MOUSEINPUT),
                ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD),
                ("u",    _INPUT_U)]


# An '@name.ext' file tag produced by app.filetags.tag(). Same regex as
# injector.py (macOS) — the lookbehind requires '@' to start a word so an
# email like 'foo@gmail.com' is NOT mistaken for a file tag.
_MENTION_RE = re.compile(r'(?<![\w@])@[A-Za-z0-9_.\-]+\.[A-Za-z0-9]+')

# ── Module state (mirrors injector.py) ───────────────────────────────────
_previous_hwnd       = None
_previous_app_pid    = None
_previous_app_name   = ""    # window title (kept for history display)
_previous_app_exe    = ""    # e.g. "Cursor.exe" — the Windows "bundle" identity

_OUR_PID = os.getpid()


# ── PID / exe helpers ────────────────────────────────────────────────────

def _pid_from_hwnd(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value) or None


def _exe_from_pid(pid):
    """Return the process's exe basename (e.g. 'Cursor.exe'), or ''."""
    if not pid:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf_len = wt.DWORD(1024)
        buf = ctypes.create_unicode_buffer(buf_len.value)
        # QueryFullProcessImageNameW(hProcess, dwFlags, lpExeName, lpdwSize)
        ok = kernel32.QueryFullProcessImageNameW(
            handle, 0, buf, ctypes.byref(buf_len))
        if not ok:
            return ""
        return os.path.basename(buf.value or "")
    finally:
        kernel32.CloseHandle(handle)


# ── save / restore focused app ───────────────────────────────────────────

def save_focused_app():
    """Call BEFORE recording starts to remember the dictation target.

    Captures HWND + window title + PID + exe basename. Skips Verbal's own
    windows (e.g. the popover) so we always restore to the app the user
    was actually typing in, not our own surface."""
    global _previous_hwnd, _previous_app_pid, _previous_app_name, _previous_app_exe
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return
        pid = _pid_from_hwnd(hwnd)
        if pid and pid == _OUR_PID:
            # Foreground is Verbal itself (popover, dashboard, overlay). Don't
            # overwrite the saved target — the pipeline will restore to the
            # previous non-Verbal window.
            return

        length = user32.GetWindowTextLengthW(hwnd) + 1
        buf = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buf, length)
        title = buf.value or ""
        exe = _exe_from_pid(pid)

        _previous_hwnd     = hwnd
        _previous_app_pid  = pid
        _previous_app_name = title
        _previous_app_exe  = exe
        logger.info(
            f"Saved focused app: {title!r} ({exe}, PID {pid}, hwnd {hwnd})")
    except Exception as e:
        logger.warning(f"Could not save focused app: {e}")


def get_focused_app_name() -> str:
    """Window title of the app focused when recording started."""
    return _previous_app_name


def get_focused_app_pid():
    """PID of the app focused when recording started (None if unknown).

    This is the dictation TARGET — the shared file-tag / autolearn code uses
    it, not the live frontmost app (which is the overlay by transcription
    time)."""
    return _previous_app_pid


def get_focused_app_bundle() -> str:
    """Exe basename of the app focused when recording started ('' if unknown).

    Named 'bundle' for cross-platform parity with app/injector.py so shared
    callers (filetags / autolearn / injector call sites) don't branch on OS.
    On Windows the exe basename ('Cursor.exe') plays the role the bundle id
    plays on macOS ('com.todesktop.230313mzl4w4u92')."""
    return _previous_app_exe


def restore_focused_app():
    """Bring the previously focused HWND back to the foreground."""
    global _previous_hwnd
    if _previous_hwnd is None:
        return
    try:
        user32.SetForegroundWindow(_previous_hwnd)
        time.sleep(0.2)
        logger.info(f"Restored focus to hwnd {_previous_hwnd}")
    except Exception as e:
        logger.warning(f"Could not restore focused app: {e}")


# ── Low-level typing (layout-safe unicode) ───────────────────────────────

def _send_inputs(inputs):
    n = len(inputs)
    arr = (_INPUT * n)(*inputs)
    return user32.SendInput(n, arr, ctypes.sizeof(_INPUT))


def _unicode_key(ch, key_up=False):
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if key_up else 0)
    inp = _INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = _KEYBDINPUT(wVk=0, wScan=ord(ch), dwFlags=flags,
                         time=0, dwExtraInfo=0)
    return inp


def _type_unicode(s: str, per_char: float = 0.012):
    """Type a string by sending Unicode down/up events via SendInput.

    Bypasses the current keyboard layout — '@' arrives as '@' whether the
    user is on US, DE, FR, etc. This is what makes the mention picker open
    reliably on any layout."""
    for ch in s:
        _send_inputs([_unicode_key(ch, key_up=False)])
        _send_inputs([_unicode_key(ch, key_up=True)])
        time.sleep(per_char)


def _press_return():
    """Send an Enter down+up via SendInput (VK-based, not clipboard/paste)."""
    VK_RETURN = 0x0D
    down = _INPUT(); down.type = INPUT_KEYBOARD
    down.ki = _KEYBDINPUT(wVk=VK_RETURN, wScan=0, dwFlags=0,
                          time=0, dwExtraInfo=0)
    up = _INPUT(); up.type = INPUT_KEYBOARD
    up.ki = _KEYBDINPUT(wVk=VK_RETURN, wScan=0, dwFlags=KEYEVENTF_KEYUP,
                        time=0, dwExtraInfo=0)
    _send_inputs([down])
    time.sleep(0.02)
    _send_inputs([up])


def _paste_chunk(chunk: str):
    """Clipboard-paste a plain text chunk (fast and reliable for arbitrary
    text). Ctrl+V is layout-independent."""
    if not chunk:
        return
    pyperclip.copy(chunk)
    time.sleep(0.04)
    import pyautogui
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.06)


# ── Mention injection (parity with injector._inject_with_mentions) ───────

def _inject_with_mentions(text: str) -> bool:
    """For each '@name.ext' in `text`, TYPE it into the editor's file-mention
    picker so it becomes a real chip. Plain chunks are pasted via Ctrl+V.

    Timings mirror the Mac version (0.18 / 0.35 / 0.14).
    """
    restore_focused_app()
    time.sleep(0.25)

    plain_parts = _MENTION_RE.split(text)   # N+1 plain chunks
    mentions    = _MENTION_RE.findall(text) # N '@name.ext' tokens

    for i, chunk in enumerate(plain_parts):
        _paste_chunk(chunk)
        if i < len(mentions):
            query = mentions[i][1:]         # strip leading '@'
            _type_unicode("@")              # open mention picker (layout-safe)
            time.sleep(0.18)
            _type_unicode(query)            # filter to the file
            time.sleep(0.35)                # let the picker populate/highlight
            _press_return()                 # accept top match → real chip
            time.sleep(0.14)

    logger.info(f"Injected with {len(mentions)} mention(s): '{text[:40]}...'")
    return True


# ── Public entry point ───────────────────────────────────────────────────

def inject_text(text: str, allow_mentions: bool = False) -> bool:
    # When file-tagging is on and the dictation target is a supported IDE,
    # route through the mention path so `@name.ext` becomes a real reference
    # chip. Any failure below the top-level try falls back to plain paste so
    # a recording is never lost.
    if allow_mentions and _MENTION_RE.search(text or ""):
        try:
            from app import win_ax as filetags  # W8 (may not exist yet)
            ide = filetags.supported_ide(_previous_app_exe, _previous_app_name)
            tagging = ide in filetags.TAGGING_IDES
        except Exception:
            # W8 not shipped yet OR classifier failed — treat as non-tagging.
            tagging = False
        if tagging:
            try:
                return _inject_with_mentions(text)
            except Exception as e:
                logger.error(
                    f"Mention injection failed, falling back to paste: {e}")

    try:
        pyperclip.copy(text)
        time.sleep(0.05)
        restore_focused_app()
        time.sleep(0.15)
        import pyautogui
        pyautogui.hotkey("ctrl", "v")
        logger.info(f"Pasted: '{text[:40]}...'")
        return True
    except Exception as e:
        logger.error(f"Paste failed: {e}")
        return False


def request_accessibility():
    """Windows doesn't need a separate accessibility prompt like macOS."""
    pass
