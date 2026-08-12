"""Windows file-tags harvest — UI Automation analog of app/filetags.py.

Reuses ALL the pure logic in `app/filetags.py` (regex/stem/ext rewrite, seen-
files memory, prompt fragment, LRU config plumbing) and swaps only the two
platform-specific pieces:

  * `_frontmost_app()` — GetForegroundWindow → PID → exe basename.
  * `read_open_files(pid)` — walk the process's UIA subtree collecting
    `name.ext` strings from tab items / documents / list items instead of the
    macOS AXValue/AXTitle harvest under `AXWebArea`.

Public names match `filetags.py` so shared callers (`win_injector` for
`supported_ide`/`TAGGING_IDES`, the record-start pipeline for
`harvest_async`) don't branch on OS.

HARD GUARANTEES (WINDOWS_PARITY_PLAN.md §1):
  * Nothing here may crash or stall a recording.
  * Every UIA call is wrapped; the tree walk is time-bounded, node-capped,
    and depth-capped.
  * A missing/unresponsive editor tree returns [] — the pipeline continues.
"""

import ctypes
import ctypes.wintypes as wt
import logging
import os
import re
import threading
import time

logger = logging.getLogger("verbal.filetags.win")

# Re-export the portable helpers so shared call-sites can `from app import
# win_ax` uniformly and pick up rewrite/memory/prompt logic unchanged.
from app.filetags import (  # noqa: F401
    TAGGING_IDES,
    tag,
    prompt_fragment,
    get_seen_files,
    remember_files,
    _norm_files,
    _NAME_EXT_RE,
    _FILE_TOKEN_RE,
    _title_to_name,
    _PROMPT_MAX_WORDS,
)

# Walk limits — mirror filetags._AX_* so behavior matches Mac (Chromium/
# Electron trees are DEEP; without bounds a walk can stall).
_UIA_BUDGET_S      = 0.60
_UIA_MAX_NODES     = 4000
_UIA_MAX_DEPTH     = 40
_UIA_MAX_CHILDREN  = 250

# Harvest budget when called from harvest_async (longer than the read-only
# budget — the caller is off the recording critical path).
_HARVEST_SETTLE_S  = 1.3

# Reused Win32 helpers (same as win_injector) — kept private here so this
# module doesn't require win_injector for exe/pid resolution.
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32


def _pid_from_hwnd(hwnd):
    try:
        pid = wt.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) or None
    except Exception:
        return None


def _exe_from_pid(pid):
    if not pid:
        return ""
    handle = _kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf_len = wt.DWORD(1024)
        buf = ctypes.create_unicode_buffer(buf_len.value)
        if not _kernel32.QueryFullProcessImageNameW(
                handle, 0, buf, ctypes.byref(buf_len)):
            return ""
        return os.path.basename(buf.value or "")
    finally:
        _kernel32.CloseHandle(handle)


def _frontmost_app():
    """Return (pid, exe_basename) for the foreground window, or (None, '')."""
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None, ""
        pid = _pid_from_hwnd(hwnd)
        return pid, _exe_from_pid(pid)
    except Exception as e:
        logger.debug("frontmost app lookup failed: %s", e)
        return None, ""


# ── IDE classification (by exe basename) ─────────────────────────────────

def _classify(bundle_or_exe, name=None):
    """Windows classifier: identify supported IDEs by exe basename (with
    window title as a fallback signal).

    `bundle_or_exe` may be either a Windows exe basename (e.g. 'Cursor.exe',
    'code.exe') or, when callers reuse the Mac name of the parameter, a Mac
    bundle id — either way we look at its stem lowercase. Extra safety: also
    check the window title so builds with unusual exe names still classify.
    """
    ident = (bundle_or_exe or "").lower()
    # Drop the '.exe' so 'Cursor.exe' → 'cursor'.
    stem = re.sub(r"\.exe$", "", ident)
    title = (name or "").lower()
    tc = re.sub(r"[\s\-_]+", "", title)

    if "cursor" in stem or "cursor" in title:
        return "cursor"
    if "windsurf" in stem or "codeium" in stem or "windsurf" in title:
        return "windsurf"
    if "antigravity" in stem or "antigravity" in tc:
        return "antigravity"
    if "kiro" in stem or "kiro" in tc:
        return "kiro"
    # VS Code's exe is 'Code.exe'; Insiders is 'Code - Insiders.exe' → 'code'
    # after regex strip, and titles typically include 'Visual Studio Code'.
    if stem == "code" or stem.startswith("code ") or stem == "code-insiders":
        return "vscode"
    if "visual studio code" in title:
        return "vscode"
    return None


def supported_ide(bundle_id=None, name=None):
    """Same signature as filetags.supported_ide — on Windows the first arg is
    an exe basename (win_injector.get_focused_app_bundle() returns the exe),
    with no-args falling back to the live foreground app."""
    if bundle_id is None and name is None:
        pid, exe = _frontmost_app()
        if not exe:
            return None
        # Title lookup for the frontmost window (used as a fallback signal in
        # _classify).
        try:
            hwnd = _user32.GetForegroundWindow()
            length = _user32.GetWindowTextLengthW(hwnd) + 1
            buf = ctypes.create_unicode_buffer(length)
            _user32.GetWindowTextW(hwnd, buf, length)
            name = buf.value
        except Exception:
            name = None
        return _classify(exe, name)
    return _classify(bundle_id, name)


# ── UIA harvest ──────────────────────────────────────────────────────────

_TAB_CONTROL_TYPES = None  # populated lazily after uiautomation import


def _uia_control_types():
    """Return the set of UIA ControlType ids we treat as "file name carriers".

    Cached so we don't rebuild it per walk. Guarded because uiautomation may
    fail to load COM in exotic environments — this stays fail-closed."""
    global _TAB_CONTROL_TYPES
    if _TAB_CONTROL_TYPES is not None:
        return _TAB_CONTROL_TYPES
    try:
        import uiautomation as auto
        _TAB_CONTROL_TYPES = {
            auto.ControlType.TabItemControl,
            auto.ControlType.DocumentControl,
            auto.ControlType.ListItemControl,
            auto.ControlType.TreeItemControl,
        }
    except Exception:
        _TAB_CONTROL_TYPES = set()
    return _TAB_CONTROL_TYPES


def read_open_files(pid=None, budget=None, settle=0.0):
    """Best-effort list of open/visible `name.ext` files under a PID.

    Walks the UIA subtree of the process's top-level windows collecting Name
    properties from tab items / documents / list items / tree items that
    parse as `name.ext`. Bounded by wall-clock + node count + depth exactly
    like the Mac AX harvest, and always returns a list (empty on any
    failure)."""
    if pid is None:
        return []
    wall_budget = float(budget) if budget is not None else _UIA_BUDGET_S
    deadline = time.time() + wall_budget + max(0.0, settle)

    if settle > 0:
        time.sleep(min(settle, wall_budget))

    try:
        import uiautomation as auto
    except Exception as e:
        logger.debug("uiautomation import failed: %s", e)
        return []

    files = []
    seen = set()
    node_count = 0
    control_types = _uia_control_types()

    def try_collect(name_val):
        nonlocal files, seen
        if not name_val:
            return
        parsed = _title_to_name(name_val)
        if parsed and parsed.lower() not in seen:
            seen.add(parsed.lower())
            files.append(parsed)

    def walk(node, depth):
        nonlocal node_count
        if time.time() > deadline:
            return
        if node_count >= _UIA_MAX_NODES:
            return
        if depth > _UIA_MAX_DEPTH:
            return
        node_count += 1

        try:
            ctrl_type = node.ControlType
        except Exception:
            ctrl_type = None
        # Cheap filter — check names of every element (tabs, docs, list items).
        try:
            if ctrl_type in control_types:
                try_collect(node.Name)
        except Exception:
            pass

        # Recurse — cap children per node.
        try:
            children = node.GetChildren()
        except Exception:
            children = []
        for i, ch in enumerate(children[:_UIA_MAX_CHILDREN]):
            if time.time() > deadline or node_count >= _UIA_MAX_NODES:
                return
            walk(ch, depth + 1)

    try:
        root = auto.GetRootControl()
        # Iterate the desktop's top-level windows; harvest only the ones that
        # belong to `pid`.
        top_windows = root.GetChildren()
    except Exception as e:
        logger.debug("uia root walk failed: %s", e)
        return []

    for win in top_windows:
        if time.time() > deadline:
            break
        try:
            win_pid = win.ProcessId
        except Exception:
            win_pid = None
        if win_pid != pid:
            continue
        try:
            walk(win, 0)
        except Exception as e:
            logger.debug("uia subtree walk failed: %s", e)

    return _norm_files(files)


_harvesting = threading.Lock()


def harvest_async(pid, config=None, save_config_fn=None, budget=4.0):
    """Off-thread harvest — same contract as filetags.harvest_async.

    Runs read_open_files(pid) on a daemon thread with a wider budget than the
    inline read, waits for the Chromium tree to build (settle), and merges
    results into `config['filetag_files']` via `remember_files`. Never blocks
    the caller. Never raises. If a harvest is already in flight, no-ops."""
    if pid is None:
        return
    if not _harvesting.acquire(blocking=False):
        return

    def _run():
        try:
            files = read_open_files(pid, budget=budget, settle=_HARVEST_SETTLE_S)
            if files:
                remember_files(config, files, save_config_fn)
        except Exception as e:
            logger.debug("harvest_async failed: %s", e)
        finally:
            _harvesting.release()

    try:
        threading.Thread(target=_run, daemon=True).start()
    except Exception:
        _harvesting.release()


# ── Focus is terminal? ───────────────────────────────────────────────────

_TERMINAL_EXES = {
    "windowsterminal.exe",   # Windows Terminal
    "conhost.exe",           # legacy console host
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "wsl.exe",
    "wt.exe",
}

_TERMINAL_KEYWORDS = ("terminal", "console", "shell")


def focus_is_terminal():
    """Best-effort: is the system's focused control a terminal?

    True → the transcript should NOT be file-tagged (we don't inject `@name`
    tags into a shell prompt). False on any uncertainty — matches Mac
    behavior (`filetags.focus_is_terminal` only skips when confident).
    """
    try:
        # Fast path: foreground process is a known terminal executable.
        pid, exe = _frontmost_app()
        if exe and exe.lower() in _TERMINAL_EXES:
            return True

        # Slower path: check the UIA focused control for terminal-shaped
        # metadata (VS Code / Cursor terminal panel, classname hints).
        try:
            import uiautomation as auto
            focused = auto.GetFocusedControl()
        except Exception:
            focused = None
        if focused is None:
            return False

        # Walk up a couple of ancestors sniffing Name/ClassName/AutomationId
        # for terminal indicators. Bounded to 3 hops.
        node = focused
        for _ in range(3):
            try:
                for attr in ("Name", "ClassName", "AutomationId"):
                    val = getattr(node, attr, None)
                    if val and any(k in str(val).lower() for k in _TERMINAL_KEYWORDS):
                        return True
            except Exception:
                pass
            try:
                parent = node.GetParentControl()
            except Exception:
                parent = None
            if parent is None:
                break
            node = parent
    except Exception as e:
        logger.debug("focus_is_terminal failed: %s", e)
        return False
    return False
