"""Windows DPI geometry helpers for the pywebview shells (dashboard, meeting
window, popover).

Why this exists (2026-08-28, verified on a 200 % display): the Windows build
pins **pywebview 5.3**, whose WinForms backend is inconsistent about units —
`create_window(width, height, min_size)` and `Window.resize()` apply the
numbers as PHYSICAL pixels (raw `Size`/`SetWindowPos`), while `Window.move()`
multiplies by the scale factor (logical). The app's constants are logical
(CSS) pixels, so at 200 % every pywebview window came out at half its
intended size: the 880x620 meeting window rendered a 440x310 CSS viewport
("the meeting-name popup is square, options don't fit") and the 560x54 bar a
280x27 one (only dot + timer visible). pywebview >= 6 scales everything
itself, so these helpers become identity there — detected via the installed
version, never by guessing.
"""
import ctypes
import logging
import sys

logger = logging.getLogger("verbal.win.geometry")

_PYWEBVIEW_MAJOR = None


def pywebview_major() -> int:
    global _PYWEBVIEW_MAJOR
    if _PYWEBVIEW_MAJOR is None:
        try:
            from importlib.metadata import version
            _PYWEBVIEW_MAJOR = int(version("pywebview").split(".")[0])
        except Exception as e:
            logger.debug("pywebview version probe failed: %s", e)
            _PYWEBVIEW_MAJOR = 5
    return _PYWEBVIEW_MAJOR


def system_scale() -> float:
    """Primary-monitor DPI scale (1.0 at 96 dpi, 2.0 at 192)."""
    if sys.platform != "win32":
        return 1.0
    try:
        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except Exception:
        return 1.0


def window_scale(hwnd) -> float:
    """DPI scale of the monitor a window is on."""
    if sys.platform != "win32":
        return 1.0
    try:
        return ctypes.windll.user32.GetDpiForWindow(int(hwnd)) / 96.0
    except Exception:
        return system_scale()


def create_size(logical_w: int, logical_h: int):
    """What to pass as create_window width/height so the window really is
    `logical_w x logical_h` CSS px on this pywebview.

    NOT for min_size: on 5.3 the BrowserForm sets MinimumSize BEFORE it turns
    on AutoScaleMode.Dpi, so WinForms scales that one value itself (a scaled
    min_size came out doubled — 2800x1920 at 200 % — and, clamped to the work
    area, pinned the window to full screen; measured 2026-08-28). Pass
    min_size in logical px on every version."""
    s = 1.0 if pywebview_major() >= 6 else system_scale()
    return int(logical_w * s), int(logical_h * s)


def set_window_rect(hwnd, x_phys: int, y_phys: int, w_logical: int, h_logical: int, scale: float = None):
    """Position + size a top-level window in one SetWindowPos, bypassing
    pywebview's unit confusion. x/y are physical (SPI_GETWORKAREA space),
    w/h logical. Safe from any thread (SetWindowPos marshals to the owner).
    Returns the physical size applied."""
    SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
    s = scale if scale else window_scale(hwnd)
    w, h = int(w_logical * s), int(h_logical * s)
    ctypes.windll.user32.SetWindowPos(int(hwnd), None, int(x_phys), int(y_phys), w, h,
                                      SWP_NOZORDER | SWP_NOACTIVATE)
    return w, h


def set_window_pill_region(hwnd, w_phys: int, h_phys: int):
    """Clip a borderless window to a pill (fully rounded rect). WebView2 has
    no per-pixel alpha, so this is how the meeting bar gets its shape: the
    window is exactly the pill's size and the region hides the corners."""
    try:
        gdi, user = ctypes.windll.gdi32, ctypes.windll.user32
        # Inset by one device pixel: the region edge is aliased (no AA on
        # window regions), so keep it just INSIDE the pill's anti-aliased CSS
        # border rather than leaving a jagged fringe of window background
        # around it (zoomed inspection, 2026-08-28).
        w, h = int(w_phys), int(h_phys)
        rgn = gdi.CreateRoundRectRgn(1, 1, w, h, h - 2, h - 2)
        user.SetWindowRgn(int(hwnd), rgn, True)      # the window now owns rgn
    except Exception as e:
        logger.debug("pill region failed: %s", e)


def clear_window_region(hwnd):
    try:
        ctypes.windll.user32.SetWindowRgn(int(hwnd), None, True)
    except Exception as e:
        logger.debug("clear region failed: %s", e)
