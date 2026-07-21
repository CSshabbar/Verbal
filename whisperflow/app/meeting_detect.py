"""
Meeting auto-detection (Granola-style) — desktop only.

Every few seconds we scan the ON-SCREEN window list for the tell-tale window of a
call actually IN PROGRESS (not merely a conferencing app sitting idle), and return
the human name of the app it's happening in (e.g. "Chrome", "Zoom"). main.py polls
`detect()` on a timer and pops the "Meeting detected · <source> — Take notes" pill.

Why window titles: `CGWindowListCopyWindowInfo` gives us each window's owner app and
title with no extra permission beyond Screen Recording, which Flume already holds for
ScreenCaptureKit meeting capture. If that permission is absent, titles come back empty
and we simply detect nothing (fail closed — detection must never break capture).

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
import re

logger = logging.getLogger("verbal.meeting_detect")

# owner-app name (as macOS reports it) → friendly source label shown in the pill
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
_MEET_CODE = re.compile(r"[a-z]{3}-[a-z]{4}-[a-z]{3}", re.I)


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
    if m or "meet.google.com" in low or re.match(r"\s*meet\s*[-–]\s+\S", low):
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
        if "meeting" in low or "webex" in low:
            return ("Webex", "webex")
        return None
    if owner == "FaceTime" and "facetime" in low:
        # FaceTime's window exists only during/near a call.
        return ("FaceTime", "facetime")
    return None


def _match(owner: str, title: str):
    if not owner:
        return None
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


def detect():
    """Return {"source","key","app"} for a call in progress, or None. Never raises.
    Call OFF the main thread — the SCK path waits on a completion handler."""
    try:
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
