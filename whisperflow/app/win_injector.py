"""Windows text injection — copy to clipboard + simulate Ctrl+V."""

import logging
import time
import ctypes
import pyperclip

logger = logging.getLogger("verbal.injector")

user32 = ctypes.windll.user32

_previous_hwnd = None
_previous_app_name = ""


def save_focused_app():
    """Call this BEFORE recording starts to remember where user was."""
    global _previous_hwnd, _previous_app_name
    try:
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            _previous_hwnd = hwnd
            length = user32.GetWindowTextLengthW(hwnd) + 1
            buf = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hwnd, buf, length)
            _previous_app_name = buf.value
            logger.info(f"Saved focused app: {_previous_app_name} (hwnd {_previous_hwnd})")
    except Exception as e:
        logger.warning(f"Could not save focused app: {e}")


def get_focused_app_name() -> str:
    """Return the name of the app that was focused when recording started."""
    return _previous_app_name


def restore_focused_app():
    """Restore focus to the app the user was in before recording."""
    global _previous_hwnd
    if _previous_hwnd is None:
        return
    try:
        user32.SetForegroundWindow(_previous_hwnd)
        time.sleep(0.2)
        logger.info(f"Restored focus to hwnd {_previous_hwnd}")
    except Exception as e:
        logger.warning(f"Could not restore focused app: {e}")


def inject_text(text: str) -> bool:
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
    """Windows doesn't need a separate accessibility prompt like Mac."""
    pass
