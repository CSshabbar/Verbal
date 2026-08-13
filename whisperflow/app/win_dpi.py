"""Shared DPI scaling for the Windows tkinter+PIL "sticker" widgets.

The process declares PER_MONITOR_AWARE_V2 in `win_main.py` before any window
exists, so Windows does NOT bitmap-stretch us: tkinter geometry and PIL drawing
land in REAL DEVICE PIXELS. A widget whose layout constants are plain 96-DPI
design numbers therefore renders at 1/scale of its intended physical size —
half on a 200% display, a third on a 300% one. That is why the transform pill,
the auto-learn pill and the meeting HUD came up tiny on a 200% VM while the
overlay (which scales itself) looked right.

Each widget owns a `_DESIGN` dict of 96-DPI numbers and an `_apply_scale()` that
restates them in device pixels; this module supplies the two things they must
agree on — how the monitor's scale is measured, and the taste multiplier applied
on top of it. Keep USER_SCALE in step with `win_overlay.py`, which carries its
own copy so the overlay can be tuned independently while it is being reworked.

macOS never imports this: the Mac widgets are AppKit/WKWebView and Cocoa handles
backing-scale itself.
"""
import ctypes
import logging

logger = logging.getLogger("verbal.win.dpi")

# Taste multiplier applied on top of the measured DPI scale. 1.0 is exact Mac
# parity; lower values shrink a widget's proportions, fonts and hit-boxes
# together. Mirrors win_overlay.USER_SCALE — change both or they drift apart.
USER_SCALE = 0.85


def probe_scale():
    """Device pixels per 96-DPI unit on the primary monitor.

    Returns 1.0 when the process is DPI-unaware (Windows then scales our output
    itself, so scaling again would double it) and on any failure — the widget
    stays its 96-DPI size, which is the pre-existing behaviour rather than a
    crash on the dictation path.
    """
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
    except AttributeError:                       # pre-1607
        try:
            hdc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)   # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(0, hdc)
        except Exception as e:
            logger.debug("dpi probe failed: %s", e)
            return 1.0
    except Exception as e:                       # not Windows, or no user32
        logger.debug("dpi probe failed: %s", e)
        return 1.0
    return (dpi / 96.0) if dpi else 1.0


def widget_scale():
    """The scale a sticker widget should lay itself out at."""
    return probe_scale() * USER_SCALE
