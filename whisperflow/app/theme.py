"""
Flume design system — desktop (macOS/AppKit).

Single source of truth for colors, fonts, type scale, spacing and radii on the
Mac app, mirroring DESIGN_SYSTEM.md. Import this and use `colors`, `geist()`,
`mono()`, `TYPE`, `space`, `radius` instead of hardcoding values.

Fonts (Geist + JetBrains Mono) are registered at import from ./assets/fonts.
Every font helper falls back to the system font if a face fails to resolve, so
the app never crashes on a missing font.
"""
import os
import sys
import logging

from AppKit import NSColor, NSFont
from Foundation import NSURL

logger = logging.getLogger("verbal.theme")

# Font weight constants (fallback numbers if the symbol isn't exported).
try:
    from AppKit import (
        NSFontWeightRegular, NSFontWeightMedium,
        NSFontWeightSemibold, NSFontWeightBold,
    )
except Exception:  # pragma: no cover
    NSFontWeightRegular, NSFontWeightMedium, NSFontWeightSemibold, NSFontWeightBold = 0.0, 0.23, 0.3, 0.4

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    # PyInstaller bundle — fonts are added via the .spec datas.
    _FONT_DIR = os.path.join(sys._MEIPASS, "app", "assets", "fonts")
else:
    _FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")


def _register_fonts():
    # CTFontManager lives in CoreText; import path varies across PyObjC versions.
    reg = scope = None
    for modname in ("CoreText", "Quartz.CoreText", "Quartz"):
        try:
            mod = __import__(modname, fromlist=["CTFontManagerRegisterFontsForURL"])
            reg = getattr(mod, "CTFontManagerRegisterFontsForURL")
            scope = getattr(mod, "kCTFontManagerScopeProcess", 1)
            break
        except Exception:
            continue
    if reg is None:
        logger.warning("theme: CTFontManagerRegisterFontsForURL unavailable — using system font")
        return
    if not os.path.isdir(_FONT_DIR):
        logger.warning("theme: font dir missing: %s", _FONT_DIR)
        return
    for fn in sorted(os.listdir(_FONT_DIR)):
        if fn.lower().endswith((".ttf", ".otf")):
            try:
                url = NSURL.fileURLWithPath_(os.path.join(_FONT_DIR, fn))
                reg(url, scope, None)
            except Exception as e:  # pragma: no cover
                logger.info("theme: font register skipped %s (%s)", fn, e)


_register_fonts()

# ── Colors (DESIGN_SYSTEM §2) ──────────────────────────────────────────────────
def _c(r, g, b, a=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, a)

def _hex(h, a=1.0):
    h = h.lstrip("#")
    return _c(int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0, a)

def _w(a):  # near-white (240,240,240) at alpha a
    return _c(240 / 255.0, 240 / 255.0, 240 / 255.0, a)


colors = {
    "bgCanvas":      _hex("#14110f"),
    "bgScreen":      _hex("#0e1012"),
    "bgChrome":      _hex("#0a0c0e"),
    "surface1":      _hex("#17191c"),
    "surface2":      _w(0.06),
    "surface3":      _w(0.08),
    "scrim":         _c(0, 0, 0, 0.55),

    "borderSubtle":  _w(0.05),
    "borderDefault": _w(0.08),
    "borderStrong":  _w(0.12),
    "borderDashed":  _w(0.16),

    "textPrimary":   _hex("#f2f2f2"),
    "textSecondary": _w(0.65),
    "textMuted":     _w(0.55),
    "textSubtle":    _w(0.45),
    "textDisabled":  _w(0.30),

    "primary":       _hex("#C85A3E"),
    "primaryInk":    _hex("#0e1012"),
    "primarySoft":   _c(200 / 255.0, 90 / 255.0, 62 / 255.0, 0.14),
    "primarySofter": _c(200 / 255.0, 90 / 255.0, 62 / 255.0, 0.06),
    "primaryBorder": _c(200 / 255.0, 90 / 255.0, 62 / 255.0, 0.35),
    "primaryDashed": _c(200 / 255.0, 90 / 255.0, 62 / 255.0, 0.32),
    "primaryAccent": _hex("#f0b39a"),
    "primaryInkAlt": _hex("#fff5ea"),

    "cream":         _hex("#EADFCE"),
    "creamInk":      _hex("#2a1f18"),
    "creamDisc":     _hex("#1a1512"),
    "sage":          _hex("#DDE4D3"),
    "sageInk":       _hex("#1e2418"),
    "sageDisc":      _hex("#1e2418"),
    "plum":          _hex("#e6dae4"),
    "plumInk":       _hex("#221820"),
    "plumDisc":      _hex("#221820"),

    "online":        _hex("#4ad15a"),
    "onlineSoft":    _c(74 / 255.0, 209 / 255.0, 90 / 255.0, 0.10),
    "onlineBorder":  _c(74 / 255.0, 209 / 255.0, 90 / 255.0, 0.32),
    "onlineAccent":  _hex("#8ee69a"),
    "offline":       _w(0.30),
    "recording":     _hex("#C85A3E"),

    "tagIPhone":     _hex("#C85A3E"),
    "tagIPhoneInk":  _hex("#fff5ea"),
    "tagIPad":       _hex("#4a6494"),
    "tagIPadInk":    _hex("#eaf1ff"),
    "tagWorkPC":     _hex("#4a6494"),
    "tagWorkPCInk":  _hex("#eaf1ff"),
}


def color(name):
    """Look up a token; falls back to textPrimary if unknown."""
    return colors.get(name, colors["textPrimary"])


# ── Fonts (DESIGN_SYSTEM §3) ───────────────────────────────────────────────────
_GEIST = {
    "regular":  "Geist-Regular",
    "medium":   "Geist-Medium",
    "semibold": "Geist-SemiBold",
    "bold":     "Geist-Bold",
}
_MONO = {
    "medium":   "JetBrainsMono-Medium",
    "semibold": "JetBrainsMono-SemiBold",
}
_SYS_WEIGHT = {
    "regular":  NSFontWeightRegular,
    "medium":   NSFontWeightMedium,
    "semibold": NSFontWeightSemibold,
    "bold":     NSFontWeightBold,
}


def geist(size, weight="regular"):
    """Geist at `size`/`weight`; falls back to the system font if unavailable."""
    f = NSFont.fontWithName_size_(_GEIST.get(weight, "Geist-Regular"), size)
    if f is None:
        try:
            f = NSFont.systemFontOfSize_weight_(size, _SYS_WEIGHT.get(weight, NSFontWeightRegular))
        except Exception:
            f = NSFont.systemFontOfSize_(size)
    return f


def mono(size, weight="medium"):
    """JetBrains Mono at `size`/`weight`; falls back to the monospaced system font."""
    f = NSFont.fontWithName_size_(_MONO.get(weight, "JetBrainsMono-Medium"), size)
    if f is None:
        try:
            f = NSFont.monospacedSystemFontOfSize_weight_(size, _SYS_WEIGHT.get(weight, NSFontWeightMedium))
        except Exception:
            f = NSFont.systemFontOfSize_(size)
    return f


# ── Desktop type scale (DESIGN_SYSTEM §3.2) ────────────────────────────────────
# Each entry: (family fn, size, weight). Build NSFont via TYPE[name].
def _mk(fn, size, weight):
    return fn(size, weight)


TYPE = {
    "pageTitle":     geist(22, "semibold"),
    "pageEyebrow":   geist(11, "regular"),
    "sectionTitle":  geist(12.5, "semibold"),
    "sectionSub":    geist(11, "regular"),
    "navHeading":    mono(10, "medium"),
    "navItem":       geist(12, "medium"),
    "navItemActive": geist(12, "semibold"),
    "featureNum":    geist(20, "semibold"),
    "featureLabel":  geist(12, "semibold"),
    "featureSub":    geist(11, "regular"),
    "listTitle":     geist(14, "semibold"),
    "listItem":      geist(11.5, "regular"),
    "listTime":      mono(10.5, "medium"),
    "tagPill":       geist(9.5, "semibold"),
    "statusPill":    geist(10.5, "semibold"),
    "kbd":           mono(10.5, "medium"),
    "titleBar":      geist(11.5, "medium"),
    "version":       mono(10, "medium"),
}


# ── Spacing + radius (DESIGN_SYSTEM §4 — identical across platforms) ────────────
space = {
    "px": 1, "xs": 4, "s": 8, "m": 12, "base": 16, "l": 18, "lg": 22,
    "xl": 28, "xxl": 36, "xxxl": 48,
}
radius = {
    "xs": 6, "sm": 8, "md": 10, "lg": 12, "xl": 14, "xxl": 18, "pill": 999,
}

# Desktop layout tokens (DESIGN_SYSTEM §6.2)
layout = {
    "titleBarH": 36,
    "sidebarW": 196,
    "sidebarPadX": 16,
    "sidebarPadY": 10,
    "mainPadX": 26,
    "mainPadY": 24,
    "minW": 720, "minH": 480,
    "defW": 900, "defH": 600,
}
