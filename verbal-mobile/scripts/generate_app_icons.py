#!/usr/bin/env python3
"""Generate the real Flume mobile app icons — was Expo's default placeholder
template (grid lines + guide circles) the whole time, never replaced.

Follows Expo's actual asset conventions, not a single reused image:
- icon.png: full-bleed 1024x1024 SQUARE, no pre-rounded corners, no
  transparency (iOS applies its own squircle mask; a pre-rounded icon fights
  that mask instead of matching it).
- adaptive-icon.png: Android adaptive icon FOREGROUND layer only — just the
  mark on a transparent background, kept inside the ~66% center safe zone,
  since Android supplies the background color/shape (app.json's
  android.adaptiveIcon.backgroundColor) and crops the foreground to its own
  shape (circle/squircle/rounded-square depending on launcher).
- splash-icon.png: same transparent-mark treatment, shown centered over
  app.json's splash backgroundColor.
"""

from PIL import Image, ImageDraw, ImageFont
import os

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
FONT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "whisperflow", "app", "assets", "fonts", "Geist_700Bold.ttf"
)

TERRACOTTA = (200, 90, 62, 255)
CREAM = (242, 242, 242, 255)


def _find_font():
    if os.path.exists(FONT_PATH):
        return FONT_PATH
    raise FileNotFoundError(f"Geist Bold font not found at {FONT_PATH}")


def draw_f(draw, size, color, font_size_ratio=0.56, y_nudge_ratio=0.015):
    font = ImageFont.truetype(_find_font(), int(size * font_size_ratio))
    text = "F"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0]
    y = (size - th) / 2 - bbox[1] - size * y_nudge_ratio
    draw.text((x, y), text, font=font, fill=color)


def generate_icon_square(size=1024):
    """Full-bleed square, solid terracotta, no transparency — for iOS/general."""
    img = Image.new("RGBA", (size, size), TERRACOTTA)
    draw = ImageDraw.Draw(img)
    draw_f(draw, size, CREAM)
    return img.convert("RGB")  # no alpha — iOS icons must be fully opaque


def generate_foreground_mark(size=1024):
    """Transparent background, mark only, sized within Android's safe zone."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Shrink the glyph so it sits within the ~66% center safe zone Android
    # adaptive icons require (foreground can get cropped near the edges).
    draw_f(draw, size, CREAM, font_size_ratio=0.40, y_nudge_ratio=0.01)
    return img


def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)

    icon = generate_icon_square(1024)
    icon.save(os.path.join(ASSETS_DIR, "icon.png"))
    print("Generated icon.png (full-bleed square)")

    adaptive = generate_foreground_mark(1024)
    adaptive.save(os.path.join(ASSETS_DIR, "adaptive-icon.png"))
    print("Generated adaptive-icon.png (transparent foreground)")

    splash = generate_foreground_mark(1024)
    splash.save(os.path.join(ASSETS_DIR, "splash-icon.png"))
    print("Generated splash-icon.png (transparent mark)")

    favicon = icon.resize((196, 196), Image.LANCZOS)
    favicon.save(os.path.join(ASSETS_DIR, "favicon.png"))
    print("Generated favicon.png")


if __name__ == "__main__":
    main()
