# Flume brand masters

The two mascot images (user-chosen, 2026-08-25) every shipped icon derives from:

- `flume-mascot-head.png` — head close-up ("4a") → the macOS menu-bar template
  pair (`assets/icon.png` idle, `assets/icon_active.png` recording).
- `flume-mascot-head-chest.png` — head + chest ("4b") → the app icon on every
  platform (`assets/app_icon.png` for mac/Windows, and the four
  `verbal-mobile/assets/` files).

Regenerate all derived icons with:

    .venv/bin/python scripts/generate_brand_icons.py

Never hand-edit the derived PNGs, and never let CI regenerate them — CI only
converts `app_icon.png` into `.icns`/`.ico` (see conventions #61 and the
"Generate icons" step comments in `.github/workflows/build-release.yml`; a CI
step that regenerated art shipped the retired mic menu-bar icon in v1.0.29).

Both masters carry a baked rounded-rect + drop shadow — they are app-store
style previews, which is why the generator recomposes from a color-distance
cutout of the bird instead of flattening the master.
