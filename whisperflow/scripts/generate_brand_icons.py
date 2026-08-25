#!/usr/bin/env python3
"""Regenerate every Flume brand icon from the two mascot masters.

Masters (checked in, the single source of truth — 2026-08-25, user-chosen):
    assets/brand/flume-mascot-head.png        (4a) → menu-bar/tray icons
    assets/brand/flume-mascot-head-chest.png  (4b) → app icons, all platforms

Outputs:
    whisperflow/assets/app_icon.png      1024×1024 full-bleed square (CI derives
                                         the mac .icns and Windows .ico from it —
                                         see conventions #61: never assets/icon.png)
    whisperflow/assets/icon.png          44×44 macOS TEMPLATE menu-bar icon: black
                                         bird-head silhouette; the eye/beak (the
                                         near-black feature pixels) are knocked out
                                         as HOLES, because template rendering only
                                         uses the alpha channel and a solid fill
                                         reads as a flame blob at 22-44px.
    whisperflow/assets/icon_active.png   44×44 recording state: solid disc with the
                                         head knocked out — shape-distinct under
                                         template rendering, same convention the old
                                         disc-with-mic active icon relied on.
    verbal-mobile/assets/icon.png        1024 RGB full-bleed (iOS masks its own
                                         corners — never bake rounding, Expo rule)
    verbal-mobile/assets/adaptive-icon.png  1024 RGBA, bird only, ~62% safe zone
    verbal-mobile/assets/splash-icon.png    1024 RGBA, bird only, centred at 50%
    verbal-mobile/assets/favicon.png        196 RGB

The masters carry a baked rounded-rect + drop shadow (they're app-store style
previews). Everything here therefore starts from a color-distance CUTOUT of the
bird and recomposes onto fresh flat beige / transparency, so no shadow or corner
ever leaks into a square icon.
"""
import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
WF_ASSETS = os.path.join(HERE, "..", "assets")
MOBILE_ASSETS = os.path.join(HERE, "..", "..", "verbal-mobile", "assets")
BG = (232, 222, 209)          # the mascot art's flat beige background


def bird_cutout(path, t0=30.0, t1=70.0):
    """Bird pixels on transparency — soft alpha by color distance from beige."""
    im = Image.open(path).convert("RGBA")
    px = im.load()
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    po = out.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            d = math.sqrt((r - BG[0]) ** 2 + (g - BG[1]) ** 2 + (b - BG[2]) ** 2)
            k = max(0.0, min(1.0, (d - t0) / (t1 - t0)))
            if k:
                po[x, y] = (r, g, b, int(a * k))
    return out


def flat_square(cutout, size):
    canvas = Image.new("RGBA", (size, size), BG + (255,))
    canvas.alpha_composite(cutout.resize((size, size), Image.LANCZOS))
    return canvas


def head_silhouette(cutout):
    """Black silhouette with the near-black features (eye, beak) as holes."""
    px = cutout.load()
    sil = Image.new("RGBA", cutout.size, (0, 0, 0, 0))
    po = sil.load()
    for y in range(cutout.height):
        for x in range(cutout.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            if 0.299 * r + 0.587 * g + 0.114 * b < 80:
                continue                      # feature pixel → hole
            po[x, y] = (0, 0, 0, a)
    sil = sil.crop(sil.getbbox())
    side = max(sil.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.alpha_composite(sil, ((side - sil.width) // 2, (side - sil.height) // 2))
    return sq


def main():
    head = bird_cutout(os.path.join(WF_ASSETS, "brand", "flume-mascot-head.png"))
    body = bird_cutout(os.path.join(WF_ASSETS, "brand", "flume-mascot-head-chest.png"))

    # Desktop app icon (CI: sips→icns on mac, PIL→ico on Windows).
    app1024 = flat_square(body, 1024)
    app1024.save(os.path.join(WF_ASSETS, "app_icon.png"))

    # macOS menu-bar template pair.
    sq = head_silhouette(head)
    idle = Image.new("RGBA", (44, 44), (0, 0, 0, 0))
    idle.alpha_composite(sq.resize((40, 40), Image.LANCZOS), (2, 2))
    idle.save(os.path.join(WF_ASSETS, "icon.png"))

    disc = Image.new("L", (44, 44), 0)
    ImageDraw.Draw(disc).ellipse((1, 1, 43, 43), fill=255)
    hole = Image.new("L", (44, 44), 0)
    hole.paste(sq.resize((30, 30), Image.LANCZOS).split()[3], (7, 7))
    active = Image.new("RGBA", (44, 44), (0, 0, 0, 255))
    active.putalpha(Image.composite(Image.new("L", (44, 44), 0), disc, hole))
    active.save(os.path.join(WF_ASSETS, "icon_active.png"))

    # Mobile (Expo conventions — see verbal-mobile/scripts/generate_app_icons.py's
    # notes: iOS icon full-bleed opaque, Android adaptive foreground-only).
    app1024.convert("RGB").save(os.path.join(MOBILE_ASSETS, "icon.png"))
    fg = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    w = int(1024 * 0.62)
    fg.alpha_composite(body.resize((w, w), Image.LANCZOS), ((1024 - w) // 2, (1024 - w) // 2))
    fg.save(os.path.join(MOBILE_ASSETS, "adaptive-icon.png"))
    sp = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    w = int(1024 * 0.5)
    sp.alpha_composite(body.resize((w, w), Image.LANCZOS), ((1024 - w) // 2, (1024 - w) // 2))
    sp.save(os.path.join(MOBILE_ASSETS, "splash-icon.png"))
    app1024.convert("RGB").resize((196, 196), Image.LANCZOS).save(
        os.path.join(MOBILE_ASSETS, "favicon.png"))
    print("regenerated: app_icon.png, icon.png, icon_active.png + 4 mobile assets")


if __name__ == "__main__":
    main()
