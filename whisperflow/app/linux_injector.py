"""Linux text injection — copy to clipboard + simulate Ctrl+V."""

import logging
import os
import subprocess
import threading
import time
from collections import namedtuple

logger = logging.getLogger("verbal.injector")

# (copied, paste_sent) — deliberately two booleans. X11/XTEST cannot tell us whether a
# client actually consumed the keystroke, so `paste_sent` means "we sent it", never
# "the text landed". Callers must not report a confident "Pasted" off `paste_sent` alone.
InjectResult = namedtuple("InjectResult", "copied paste_sent")

_previous_app_name = ""

# Serializes ALL injection. The core dictation path and inbound sync pushes both paste,
# and two interleaved clipboard-write + Ctrl+V pairs would paste each other's text.
_inject_lock = threading.Lock()

IS_WAYLAND = (
    bool(os.environ.get("WAYLAND_DISPLAY"))
    or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
)


def save_focused_app():
    """Call this BEFORE recording starts to remember where user was."""
    global _previous_app_name
    _previous_app_name = ""
    try:
        # NOTE: no check=True. Under Wayland xdotool exits 0 and prints NOTHING (it sees
        # only Xwayland's 1x1 focus proxy), so a raised-exception guard never fires and the
        # failure is invisible. Treat empty output as the failure it is.
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=2,
        )
        name = (result.stdout or "").strip()
        if name:
            _previous_app_name = name
            logger.info(f"Saved focused app: {_previous_app_name}")
        elif IS_WAYLAND:
            logger.warning(
                "Focused-app capture is unavailable on Wayland - history entries will have "
                "no app attribution. Needs a GNOME Shell extension exposing the focused "
                "window over D-Bus."
            )
        else:
            logger.warning(
                f"xdotool reported no active window name (rc={result.returncode})"
            )
    except FileNotFoundError:
        logger.warning("xdotool is not installed - no app attribution")
    except Exception as e:
        logger.warning(f"Could not save focused app: {e}")


def get_focused_app_name() -> str:
    """Return the name of the app that was focused when recording started."""
    return _previous_app_name


def restore_focused_app():
    """On Linux we typically don't lose focus to our overlay since it's unmanaged (override_redirect)."""
    pass


def copy_to_clipboard(text: str) -> bool:
    """Put text on the clipboard. This is the part we can actually verify."""
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception as e:
        logger.error(f"Clipboard copy failed: {e}")
        return False


def send_paste() -> bool:
    """Send Ctrl+V. Returns whether the keystroke was SENT, not whether it was received."""
    try:
        import pyautogui
        pyautogui.hotkey("ctrl", "v")
        return True
    except Exception as e:
        logger.warning(f"pyautogui hotkey failed, trying xdotool: {e}")
    try:
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", "ctrl+v"], check=True, timeout=5
        )
        return True
    except Exception as e:
        logger.error(f"xdotool paste failed: {e}")
        return False


def inject_text(text: str, should_cancel=None) -> InjectResult:
    """Copy `text` and paste it into the focused window.

    `should_cancel` is polled immediately before the keystroke so ESC can abort a paste
    that hasn't happened yet. Once the keystroke is sent it cannot be recalled.
    """
    with _inject_lock:
        if not copy_to_clipboard(text):
            return InjectResult(False, False)

        time.sleep(0.05)
        restore_focused_app()
        time.sleep(0.15)

        if should_cancel is not None:
            try:
                if should_cancel():
                    logger.info("Injection cancelled before paste - text left on clipboard")
                    return InjectResult(True, False)
            except Exception:
                pass

        sent = send_paste()
        if sent:
            logger.info(f"Paste sent: '{text[:40]}...'")
        return InjectResult(True, sent)


def request_accessibility():
    """Linux doesn't need a separate accessibility prompt (handled by X11/Wayland context)."""
    pass
