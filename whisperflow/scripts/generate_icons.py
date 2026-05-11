#!/usr/bin/env python3
"""Generate icons for Pico - clean Google-inspired neon aesthetic."""

from PIL import Image, ImageDraw, ImageFilter
import os
import math

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")


def generate_menu_icon(size=44):
    """Clean mic icon for menu bar (black on transparent, template image)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = size / 2
    s = size / 44

    # Mic body
    bw, bh = int(6 * s), int(13 * s)
    bt = int(9 * s)
    draw.rounded_rectangle([cx - bw, bt, cx + bw, bt + bh], radius=bw, fill="black")

    # Arc
    aw = int(10 * s)
    at, ab = int(13 * s), int(25 * s)
    draw.arc([cx - aw, at, cx + aw, ab + int(3 * s)], start=0, end=180,
             fill="black", width=max(2, int(2 * s)))

    # Stand
    st = ab + int(2 * s)
    sb = st + int(5 * s)
    lw = max(2, int(2 * s))
    draw.line([cx, st, cx, sb], fill="black", width=lw)
    draw.line([cx - int(5 * s), sb, cx + int(5 * s), sb], fill="black", width=lw)
    return img


def generate_active_icon(size=44):
    """Recording: neon green circle with white mic."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    p = 2
    # Google-green inspired
    draw.ellipse([p, p, size - p, size - p], fill=(52, 168, 83, 255))

    mic = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    md = ImageDraw.Draw(mic)
    cx = size / 2
    s = size / 44 * 0.65
    bw, bh = int(6 * s), int(13 * s)
    bt = int(11 * s)
    md.rounded_rectangle([cx - bw, bt, cx + bw, bt + bh], radius=bw, fill="white")
    aw = int(10 * s)
    at, ab = int(15 * s), int(26 * s)
    md.arc([cx - aw, at, cx + aw, ab + int(2 * s)], start=0, end=180,
           fill="white", width=max(2, int(2 * s)))
    st = ab + int(1 * s)
    sb = st + int(4 * s)
    lw = max(2, int(2 * s))
    md.line([cx, st, cx, sb], fill="white", width=lw)
    md.line([cx - int(4 * s), sb, cx + int(4 * s), sb], fill="white", width=lw)
    img = Image.alpha_composite(img, mic)
    return img


def generate_app_icon(size=512):
    """Dock icon: Google-inspired gradient with white mic and soft glow."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded square background with Google-blue gradient
    margin = int(size * 0.06)
    radius = int(size * 0.22)

    # Base: Google blue
    for y in range(margin, size - margin):
        t = (y - margin) / (size - 2 * margin)
        r = int(66 + (26 - 66) * t)
        g = int(133 + (115 - 133) * t)
        b = int(244 + (232 - 244) * t)
        draw.line([(margin, y), (size - margin, y)], fill=(r, g, b, 255))

    # Mask to rounded rect
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([margin, margin, size - margin, size - margin],
                                radius=radius, fill=255)
    img.putalpha(mask)

    # White mic
    cx, cy = size / 2, size / 2
    s = size / 44

    bw, bh = int(5 * s), int(11 * s)
    bt = int(cy - 8 * s)
    draw.rounded_rectangle([cx - bw, bt, cx + bw, bt + bh], radius=bw, fill="white")

    aw = int(8 * s)
    at = int(cy - 4 * s)
    ab = int(cy + 4 * s)
    draw.arc([cx - aw, at, cx + aw, ab], start=0, end=180,
             fill="white", width=int(2.2 * s))

    st = ab
    sb = st + int(4 * s)
    lw = int(2.2 * s)
    draw.line([cx, st, cx, sb], fill="white", width=lw)
    draw.line([cx - int(4 * s), sb, cx + int(4 * s), sb], fill="white", width=lw)

    return img


def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)

    icon = generate_menu_icon(44)
    icon.save(os.path.join(ASSETS_DIR, "icon.png"))
    print("Generated icon.png")

    active = generate_active_icon(44)
    active.save(os.path.join(ASSETS_DIR, "icon_active.png"))
    print("Generated icon_active.png")

    app_icon = generate_app_icon(512)
    app_icon.save(os.path.join(ASSETS_DIR, "app_icon_512.png"))
    print("Generated app_icon_512.png")


if __name__ == "__main__":
    main()
