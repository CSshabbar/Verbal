"""
@font-face CSS with Geist + JetBrains Mono embedded as base64 data-URIs.

The WKWebView-hosted UIs (dashboard, popover, overlay) can't rely on the
process-registered fonts being resolved by family name, so we inline the fonts
directly. This guarantees the app renders in the design's typefaces instead of
the system fallback. Built once and cached.
"""
import base64
import functools
import os
import sys

# (file, family, weight)
_FONTS = [
    ("Geist_400Regular.ttf", "Geist", 400),
    ("Geist_500Medium.ttf", "Geist", 500),
    ("Geist_600SemiBold.ttf", "Geist", 600),
    ("Geist_700Bold.ttf", "Geist", 700),
    ("JetBrainsMono_500Medium.ttf", "JetBrains Mono", 500),
    ("JetBrainsMono_600SemiBold.ttf", "JetBrains Mono", 600),
]


def _fonts_dir():
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, "app", "assets", "fonts")
    return os.path.join(os.path.dirname(__file__), "assets", "fonts")


@functools.lru_cache(maxsize=1)
def web_font_css():
    d = _fonts_dir()
    rules = []
    for fname, family, weight in _FONTS:
        try:
            with open(os.path.join(d, fname), "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
        except Exception:
            continue
        rules.append(
            "@font-face{font-family:'%s';font-weight:%d;font-style:normal;"
            "font-display:block;src:url(data:font/ttf;base64,%s) format('truetype')}"
            % (family, weight, b64)
        )
    return "".join(rules)
