import logging
import re
import time
import subprocess
import pyperclip
import Quartz
from AppKit import NSWorkspace, NSRunningApplication

logger = logging.getLogger("verbal.injector")

VK_V = 0x09
VK_RETURN = 0x24

# An '@name.ext' file tag produced by app.filetags.tag(). Used to drive Cursor's
# @-mention picker so the reference becomes a real chip, not literal text. The
# lookbehind requires the '@' to start a word (as tags always do) so an email
# like 'foo@gmail.com' is NOT mistaken for a file tag.
_MENTION_RE = re.compile(r'(?<![\w@])@[A-Za-z0-9_.\-]+\.[A-Za-z0-9]+')

# Store the app the user was in before recording
_previous_app_pid    = None
_previous_app_name   = ""
_previous_app_bundle = ""


def save_focused_app():
    """Call this BEFORE recording starts to remember where user was."""
    global _previous_app_pid, _previous_app_name, _previous_app_bundle
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app and app.bundleIdentifier() != "com.verbal.app":
            _previous_app_pid    = app.processIdentifier()
            _previous_app_name   = app.localizedName() or ""
            _previous_app_bundle = app.bundleIdentifier() or ""
            logger.info(f"Saved focused app: {_previous_app_name} (PID {_previous_app_pid})")
    except Exception as e:
        logger.warning(f"Could not save focused app: {e}")


def get_focused_app_name() -> str:
    """Return the name of the app that was focused when recording started."""
    return _previous_app_name


def get_focused_app_pid():
    """PID of the app focused when recording started (None if unknown). This is
    the dictation TARGET — use it (not the live frontmost app, which may be the
    overlay by transcription time) for file-tagging AX reads."""
    return _previous_app_pid


def get_focused_app_bundle() -> str:
    """Bundle id of the app focused when recording started ('' if unknown)."""
    return _previous_app_bundle


def restore_focused_app():
    """Restore focus to the app the user was in before recording."""
    global _previous_app_pid
    if _previous_app_pid is None:
        return
    try:
        apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_("")
        # Get all running apps and find ours
        ws = NSWorkspace.sharedWorkspace()
        for app in ws.runningApplications():
            if app.processIdentifier() == _previous_app_pid:
                app.activateWithOptions_(1 << 1)  # NSApplicationActivateIgnoringOtherApps
                logger.info(f"Restored focus to: {app.localizedName()}")
                return
    except Exception as e:
        logger.warning(f"Could not restore focused app: {e}")


def _paste_via_cgevent():
    """Simulate Cmd+V using Quartz CGEvents."""
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    cmd_down = Quartz.CGEventCreateKeyboardEvent(src, VK_V, True)
    Quartz.CGEventSetFlags(cmd_down, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, cmd_down)
    time.sleep(0.05)
    cmd_up = Quartz.CGEventCreateKeyboardEvent(src, VK_V, False)
    Quartz.CGEventSetFlags(cmd_up, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, cmd_up)


def _event_source():
    return Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)


def _type_unicode(src, s, per_char=0.012):
    """Type a string as real keyboard input via unicode events (layout-agnostic)."""
    tap = Quartz.kCGAnnotatedSessionEventTap
    for ch in s:
        down = Quartz.CGEventCreateKeyboardEvent(src, 0, True)
        Quartz.CGEventKeyboardSetUnicodeString(down, len(ch), ch)
        Quartz.CGEventPost(tap, down)
        up = Quartz.CGEventCreateKeyboardEvent(src, 0, False)
        Quartz.CGEventKeyboardSetUnicodeString(up, len(ch), ch)
        Quartz.CGEventPost(tap, up)
        time.sleep(per_char)


def _tap_key(src, vk):
    tap = Quartz.kCGAnnotatedSessionEventTap
    down = Quartz.CGEventCreateKeyboardEvent(src, vk, True)
    Quartz.CGEventPost(tap, down)
    time.sleep(0.02)
    up = Quartz.CGEventCreateKeyboardEvent(src, vk, False)
    Quartz.CGEventPost(tap, up)


def _paste_chunk(text: str):
    """Clipboard-paste a plain text chunk (fast, reliable for arbitrary text)."""
    if not text:
        return
    pyperclip.copy(text)
    time.sleep(0.04)
    _paste_via_cgevent()
    time.sleep(0.06)


def _inject_with_mentions(text: str) -> bool:
    """Inject `text` into Cursor/Windsurf so each '@name.ext' becomes a REAL
    file reference: plain chunks are pasted; each tag is TYPED ('@' + filename)
    to open the editor's file-picker, then Enter selects the highlighted match.
    """
    restore_focused_app()
    time.sleep(0.25)
    src = _event_source()

    plain_parts = _MENTION_RE.split(text)      # N+1 plain chunks
    mentions = _MENTION_RE.findall(text)       # N '@name.ext' tokens

    for i, chunk in enumerate(plain_parts):
        _paste_chunk(chunk)
        if i < len(mentions):
            query = mentions[i][1:]            # drop leading '@'
            _type_unicode(src, "@")            # open the mention picker
            time.sleep(0.18)
            _type_unicode(src, query)          # filter to the file
            time.sleep(0.35)                   # let the picker populate/highlight
            _tap_key(src, VK_RETURN)           # accept the top match -> real chip
            time.sleep(0.14)
    logger.info(f"Injected with {len(mentions)} mention(s): '{text[:40]}...'")
    return True


def inject_text(text: str, allow_mentions: bool = False) -> bool:
    # When file-tagging is on and the dictation target is Cursor/Windsurf, drive
    # the @-mention picker so tags become real references. Any failure falls back
    # to a plain paste so a recording is never lost.
    if allow_mentions and _MENTION_RE.search(text or ""):
        try:
            from app import filetags
            ide = filetags.supported_ide(_previous_app_bundle, _previous_app_name)
        except Exception:
            ide = None
        if ide in ("cursor", "windsurf"):
            try:
                return _inject_with_mentions(text)
            except Exception as e:
                logger.error(f"Mention injection failed, falling back to paste: {e}")

    try:
        pyperclip.copy(text)
        time.sleep(0.05)

        # Restore focus to the app user was typing in
        restore_focused_app()
        time.sleep(0.2)

        # Paste via CGEvent
        _paste_via_cgevent()
        logger.info(f"Pasted: '{text[:40]}...'")
        return True

    except Exception as e:
        logger.error(f"Paste failed (text in clipboard): {e}")
        return False


def request_accessibility():
    """Prompt user for accessibility permission."""
    from ApplicationServices import AXIsProcessTrustedWithOptions
    AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True})
