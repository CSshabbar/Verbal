"""
Meeting auto-detection (Granola-style) — desktop only.

Every few seconds we scan the ON-SCREEN window list for the tell-tale window of a
call actually IN PROGRESS (not merely a conferencing app sitting idle), and return
the human name of the app it's happening in (e.g. "Chrome", "Zoom"). main.py /
win_main.py poll `detect()` on a timer and pop the "Meeting detected · <source> —
Take notes" pill.

Why window titles:
  • macOS: ScreenCaptureKit (`SCShareableContent`) is the reliable title source —
    Flume already holds Screen Recording for capture. `CGWindowListCopyWindowInfo`
    is a fallback (recent macOS leaves `kCGWindowName` empty except the frontmost
    window). Missing permission → empty titles → detect nothing (fail closed).
  • Windows: `EnumWindows` + `GetWindowTextW` (no extra permission). Process exe
    names are mapped to the same owner strings the Mac matchers already use
    (`chrome.exe` → `Google Chrome`) so `_match` stays one table.

Signals are deliberately conservative (an in-call window, not just an open app) so the
prompt doesn't cry wolf:
  • Zoom native  → a window titled "Zoom Meeting" / "Zoom Webinar"
  • Google Meet  → a browser window whose title carries a Meet call (code xxx-yyyy-zzz
                   or the "Meet - " prefix / meet.google.com)
  • Zoom web     → a browser window titled "… Zoom Meeting"
  • Teams native → a Teams window titled with an active "Meeting"/"Call"
  • Webex        → a Webex "Meeting" window
The table is easy to extend — add a row to `_PROVIDERS`.
"""
import logging
import os
import re
import sys

logger = logging.getLogger("verbal.meeting_detect")

# owner-app name (as macOS reports it) → friendly source label shown in the pill
# Windows EnumWindows reports the process *exe*, not a friendly app name.
# Map onto the macOS owner strings `_BROWSERS` / `_native_app` already know so
# the matchers stay one table (and so meeting_detect_fixtures.py can pin both).
_WIN_EXE = {
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Firefox",
    "brave.exe": "Brave Browser",
    "vivaldi.exe": "Vivaldi",
    "arc.exe": "Arc",
    "chromium.exe": "Chromium",
    "zoom.exe": "Zoom",
    "cpthost.exe": "Zoom",          # Zoom's in-call host process
    "ms-teams.exe": "Microsoft Teams",
    "teams.exe": "Microsoft Teams",
    "msteams.exe": "Microsoft Teams",
}

# Our own windows must never count as a call. WebView2 is a *different* PID
# from flume.exe (dashboard / meeting / popover) — skip it so a Flume page
# titled with "Meeting" is not mistaken for a live call.
_SKIP_TITLES = {
    "flume", "flume meeting", "flume popover", "verbalanchor",
}
_SKIP_EXES = {"flume.exe", "verbal.exe", "msedgewebview2.exe"}

# Bound once — mutating windll.user32.argtypes on every 5s scan races other ctypes callers.
_WIN_ENUM = None  # (ctypes, wintypes, user32, kernel32) or False if unavailable


def _canonical_owner(owner: str) -> str:
    """Windows exe basename → macOS-style owner; otherwise leave unchanged."""
    if not owner:
        return owner
    mapped = _WIN_EXE.get(owner.lower())
    return mapped if mapped else owner


_BROWSERS = {
    "Google Chrome": "Chrome",
    "Google Chrome Canary": "Chrome",
    "Chromium": "Chromium",
    "Safari": "Safari",
    "Safari Technology Preview": "Safari",
    "Arc": "Arc",
    "Brave Browser": "Brave",
    "Microsoft Edge": "Edge",
    "Firefox": "Firefox",
    "Firefox Developer Edition": "Firefox",
    "Vivaldi": "Vivaldi",
    "Dia": "Dia",
}

# A Google-Meet call code looks like abc-defg-hij.
#
# The boundaries are load-bearing. Without them this matched any 3-4-3 letter run
# INSIDE a longer hyphenated string, and since it was searched against EVERY
# on-screen browser window title, an ordinary Chrome tab containing
# "…axo-data-and…" was reported as a live Google Meet call — 7 "Take notes"
# prompts in one evening with no meeting anywhere (2026-08-19, key
# `gmeet:axo-data-and` in app.log). A real code is a standalone token, so reject a
# neighbouring letter, digit or hyphen on either side.
_MEET_CODE = re.compile(r"(?<![a-z0-9-])[a-z]{3}-[a-z]{4}-[a-z]{3}(?![a-z0-9-])", re.I)

# "meet" as its own word. A bare code is WEAK evidence even when well-delimited —
# three short hyphenated words are common in article titles and slugs — so it now
# needs this corroboration. Google Meet always carries "Meet" in the tab title,
# which is why requiring it costs no real detection.
_MEET_WORD = re.compile(r"\bmeet\b", re.I)

# "… — Google Meet" as the TRAILING site name, which is how a named call renders
# ("Weekly standup - Google Meet") — a case the old code missed entirely, since it
# has no call code and doesn't start with "Meet". Anchored to the end after a
# separator so an article *about* Meet ("How to use Google Meet - YouTube", which
# ends in the site's own name) is not mistaken for being in one.
_MEET_SITE = re.compile(r"(?:^|[|\-–—]\s*)google meet\s*$", re.I)


def _meet_in_browser(owner: str, title: str):
    """A browser window that is in a Google Meet or Zoom web call → (provider, key)."""
    browser = _BROWSERS.get(owner)
    if not browser:
        return None
    low = title.lower()
    # Google Meet: strongest signal is the call code; else the "Meet - <name>" prefix
    # or the bare host. Guard the prefix with a code/host so a doc named "Meet ..."
    # doesn't trigger.
    m = _MEET_CODE.search(title)
    # Ordered by strength: the host itself is proof; a call code counts only when
    # the title also says "Meet"; the "Meet - <name>" prefix stands on its own.
    if ("meet.google.com" in low
            or (m and _MEET_WORD.search(title))
            or _MEET_SITE.search(title)
            or re.match(r"\s*meet\s*[-–]\s+\S", low)):
        code = m.group(0).lower() if m else "meet"
        return (browser, f"gmeet:{code}")
    # Zoom in the browser
    if "zoom meeting" in low or "zoom.us/j/" in low or "zoom.us/wc/" in low:
        return (browser, f"zoomweb:{owner}")
    return None


def _native_app(owner: str, title: str):
    """A native conferencing app whose IN-CALL window is open → (provider, key)."""
    low = title.lower()
    if owner in ("zoom.us", "us.zoom.xos", "Zoom"):
        if "zoom meeting" in low or "zoom webinar" in low:
            return ("Zoom", "zoom")
        return None
    if owner in ("Microsoft Teams", "Microsoft Teams (work or school)", "MSTeams",
                 "Teams", "com.microsoft.teams2"):
        # Teams keeps a main window open always; only flag when a call/meeting window
        # is present.
        if "meeting" in low or "call with" in low or low.startswith("meeting in"):
            return ("Teams", "teams")
        return None
    if "webex" in owner.lower():
        # `or "webex" in low` used to be here, which made EVERY Webex window a
        # detected call — the owner check above already guarantees it's Webex, and
        # its windows carry the product name whether or not you're in a call. The
        # module's whole premise is "an in-call window, not just an open app".
        if "meeting" in low:
            return ("Webex", "webex")
        return None
    if owner == "FaceTime" and "facetime" in low:
        # FaceTime's window exists only during/near a call.
        return ("FaceTime", "facetime")
    return None


def _match(owner: str, title: str):
    if not owner:
        return None
    owner = _canonical_owner(owner)
    hit = _native_app(owner, title) or _meet_in_browser(owner, title)
    if not hit:
        return None
    source, key = hit
    return {"source": source, "key": key, "app": owner}


def _scan_via_sck(timeout=1.5):
    """All on-screen windows as (owner, title) via ScreenCaptureKit. This is the
    reliable title source: with Screen-Recording permission (which Flume holds for
    capture) SCShareableContent returns EVERY window's title — including background
    windows — unlike CGWindowList's kCGWindowName, which recent macOS only fills in
    for the frontmost window. Returns None if SCK/permission is unavailable so the
    caller can fall back. Async API → wait on an Event (call this OFF the main thread)."""
    try:
        from ScreenCaptureKit import SCShareableContent
    except Exception:
        return None
    import threading
    box = {}
    got = threading.Event()

    def _handler(content, error):
        box["content"] = content
        box["error"] = error
        got.set()

    try:
        SCShareableContent.getShareableContentWithCompletionHandler_(_handler)
    except Exception as e:
        logger.debug("meeting detect: SCK request failed: %s", e)
        return None
    if not got.wait(timeout) or box.get("error") is not None or box.get("content") is None:
        return None
    out = []
    try:
        for w in (box["content"].windows() or []):
            try:
                if not w.isOnScreen():
                    continue
                app = w.owningApplication()
                owner = str(app.applicationName()) if app else ""
                title = str(w.title() or "")
                if owner and title:
                    out.append((owner, title))
            except Exception:
                continue
    except Exception as e:
        logger.debug("meeting detect: SCK window walk failed: %s", e)
        return None
    return out


def _scan_via_cgwindow():
    """Fallback window list via Quartz (only the frontmost window carries a title on
    recent macOS, but better than nothing when SCK is unavailable)."""
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID,
        )
    except Exception:
        return []
    out = []
    try:
        for w in (CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []):
            try:
                if int(w.get("kCGWindowLayer") or 0) != 0:
                    continue
            except Exception:
                continue
            owner = str(w.get("kCGWindowOwnerName") or "")
            title = str(w.get("kCGWindowName") or "")
            if owner and title:
                out.append((owner, title))
    except Exception as e:
        logger.debug("meeting detect: CGWindow scan failed: %s", e)
    return out


def _win_enum_api():
    """ctypes + bound user32/kernel32, prepared once. None if unavailable."""
    global _WIN_ENUM
    if _WIN_ENUM is False:
        return None
    if _WIN_ENUM is not None:
        return _WIN_ENUM
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD)]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        _WIN_ENUM = (ctypes, wintypes, user32, kernel32)
        return _WIN_ENUM
    except Exception:
        _WIN_ENUM = False
        return None


def _scan_via_enumwindows():
    """Top-level visible windows as (owner, title) via EnumWindows.

    Windows has no ScreenCaptureKit. Titles of visible top-level windows need
    no extra permission. Cloaked / empty-title windows are skipped (fail
    closed). Never raises.
    """
    api = _win_enum_api()
    if api is None:
        return []
    ctypes, wintypes, user32, kernel32 = api
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    our_pid = os.getpid()
    out = []

    def _exe_for_pid(pid):
        h = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return ""
        try:
            n = wintypes.DWORD(32768)
            buf = ctypes.create_unicode_buffer(n.value)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                return os.path.basename(buf.value or "")
        finally:
            kernel32.CloseHandle(h)
        return ""

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = (buf.value or "").strip()
            if not title or title.lower() in _SKIP_TITLES:
                return True
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == our_pid:
                return True
            exe = _exe_for_pid(pid.value)
            if (exe or "").lower() in _SKIP_EXES:
                return True
            if exe and title:
                out.append((exe, title))
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(_cb, 0)
    except Exception as e:
        logger.debug("meeting detect: EnumWindows failed: %s", e)
    return out


def detect():
    """Return {"source","key","app"} for a call in progress, or None. Never raises.
    Call OFF the main thread — the SCK path waits on a completion handler."""
    try:
        if sys.platform == "win32":
            windows = _scan_via_enumwindows()
            via = "enumwindows"
        else:
            windows = _scan_via_sck()
            via = "sck"
            if windows is None:
                windows = _scan_via_cgwindow()
                via = "cgwindow"
        logger.debug("meeting detect: scanned %d windows (%s)", len(windows), via)
        for owner, title in windows:
            hit = _match(owner, title)
            if hit:
                return hit
    except Exception as e:
        logger.debug("meeting detect scan failed: %s", e)
    return None
