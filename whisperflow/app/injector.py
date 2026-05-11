import logging
import time
import subprocess
import pyperclip
import Quartz
from AppKit import NSWorkspace, NSRunningApplication

logger = logging.getLogger("verbal.injector")

VK_V = 0x09

# Store the app the user was in before recording
_previous_app_pid  = None
_previous_app_name = ""


def save_focused_app():
    """Call this BEFORE recording starts to remember where user was."""
    global _previous_app_pid, _previous_app_name
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app and app.bundleIdentifier() != "com.verbal.app":
            _previous_app_pid  = app.processIdentifier()
            _previous_app_name = app.localizedName() or ""
            logger.info(f"Saved focused app: {_previous_app_name} (PID {_previous_app_pid})")
    except Exception as e:
        logger.warning(f"Could not save focused app: {e}")


def get_focused_app_name() -> str:
    """Return the name of the app that was focused when recording started."""
    return _previous_app_name


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


def inject_text(text: str) -> bool:
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
