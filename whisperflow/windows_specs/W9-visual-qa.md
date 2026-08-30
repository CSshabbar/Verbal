# W9 — Visual QA: pixel-parity checklist across all six Flume surfaces

**Goal:** verify the Windows/WebView2 rendering of every Flume surface matches the macOS/WKWebView
rendering. Because both hosts load the **same HTML** (`app/*_html.py`), parity failures come from the
**host container** (transparency, sizing, DPI) or **font/asset loading** — not the markup. This is a
verification workstream: diff, don't rebuild.

## The six surfaces to verify

| Surface | HTML source | Windows host (workstream) |
|---|---|---|
| 1. Dashboard | `app/flume_dashboard_html.py::flume_html()` | `shared_dashboard.SharedDashboard.show()` (done) |
| 2. Popover | `app/flume_popover_html.py::popover_html()` | `WinPopover` (W4) |
| 3. Overlay | `app/overlay_html.py::overlay_html()` | `WinOverlay` (W3) |
| 4. Meeting window | `app/meeting_html.py::meeting_html()` | `WinMeetingWindow` (W6) |
| 5. Meeting HUD | `app/meeting_hud_html.py::meeting_hud_html()` | `WinMeetingHud` (W6) |
| 6. Autolearn widget | `app/autolearn_widget.py::autolearn_widget_html()` | `WinAutoLearnWidget` (W7) |

## What to check on each surface

### Fonts — Geist (UI) + JetBrains Mono (numerics/meta)

- All six surfaces embed fonts via `app/fonts_css.py::web_font_css()` — base64 `@font-face` data-URIs
  for `Geist` (400/500/600/700) and `JetBrains Mono` (500/600). This is host-independent and is the
  correct path on Windows (**do NOT rely on `app/theme.py` — it's macOS-only / not bundled on Windows**).
- **Verify the fonts actually resolve**, not the system fallback: numerics/timers/meta (e.g. overlay
  timer, `qnum`, `recmeta`, version) must be JetBrains Mono; body text must be Geist. A common WebView2
  failure is the font dir missing from `sys._MEIPASS` — confirm `verbal-win.spec` bundles
  `('app/assets/fonts', 'app/assets/fonts')` (it does) and that `fonts_css._fonts_dir()` finds them in
  the frozen exe.
- Check letter-spacing on the mono eyebrow/label styles (e.g. `.statelabel` `letter-spacing:.24em`,
  `.reclab` `.14em`) — these read wrong if the fallback font substitutes.

### Palette (from `app/theme.py` — the reference values)

The web CSS hardcodes these; confirm they render identically (WebView2 vs WKWebView color management
can differ subtly):

- Screen background **`#0e1012`** (`bgScreen` / popover `--bg`; also the pywebview
  `background_color="#0e1012"` passed in `create_window`).
- Card / surface **`#17191c`** (`surface1` / popover `--card`).
- Accent **`#C85A3E`** (`primary`; note the overlay CSS uses a slightly brighter `--acc:#E8522A` for
  the recording pill — keep as-is, it's intentional in `overlay_html.py`).
- Text primary **`#f2f2f2`**; online/success green **`#4ad15a`**; pastels cream `#EADFCE`,
  sage `#DDE4D3`, plum `#e6dae4`.
- Borders as low-alpha whites (`rgba(240,240,240,.05–.16)`).

### SVG icon set

- Icons are inline SVG strings in the HTML (`_ICONS` in `flume_popover_html.py`; `_X`/`_PAUSE` in
  `overlay_html.py`; icon sets in the dashboard/meeting HTML). They render host-independently — verify
  stroke widths and sizes match (no clipping, correct `stroke:currentColor`).

### Spacing, motion, shadows

- **Spacing/radii** follow `theme.py` `space`/`radius` tokens baked into the CSS — check card padding,
  gaps, pill radii (`border-radius:22px` overlay pill, `12–14px` cards).
- **Motion/keyframes** — verify these animate smoothly on WebView2: overlay `@keyframes pillIn`
  (entrance), `wv` (waveform bars), `spin` (transcribing spinner); dashboard/meeting transitions.
  WebView2 honors CSS animations, but confirm no jank at the overlay's high-frequency waveform.
- **Shadows** — `box-shadow:0 10px 32px rgba(0,0,0,.5)` (overlay pill), card shadows. On a
  transparent overlay window these need the window to actually be transparent (W3); on the solid
  fallback the outer shadow won't show — acceptable, note it.

## Host-specific parity hazards (WebView2)

- **Transparency:** overlay + HUD rely on a transparent window to show rounded corners without a black
  box. If WebView2 transparency fails, W3/W6 ship the solid-background fallback — the corners then read
  against `#0e1012`. Verify the fallback still looks clean (no light-gray box, no hard rectangle).
- **DPI scaling:** WebView2 respects Windows display scaling (125%/150%). Verify surfaces aren't
  blurry or oversized at non-100% scale; set the process DPI awareness if needed
  (`ctypes.windll.shcore.SetProcessDpiAwareness(2)` early in `win_main`) and re-check sizes.
- **Scrollbars:** the CSS styles `::-webkit-scrollbar` (Chromium/WebView2 supports it) — confirm the
  thin dark scrollbar renders (it does on WKWebView; WebView2 is also Chromium so it should match).
- **Default white flash:** ensure `create_window(background_color="#0e1012")` on every surface so
  there's no white flash before the HTML paints.

## How to diff against Mac screenshots

1. On a Mac, capture each of the six surfaces at a known state (e.g. overlay in each of recording/
   transcribing/done; dashboard on each tab; popover main + history + canvas; meeting pre/recording/
   summary; HUD active; autolearn pill showing a correction). Save to a shared `qa/mac/` folder.
2. On the Windows machine, open the same surface in the same state and screenshot to `qa/win/` at the
   **same logical size** (100% display scale for the first pass to remove DPI as a variable).
3. Compare side-by-side (or `Pillow`/`numpy` per-pixel diff for the fixed-size surfaces like the
   overlay and HUD). Flag: wrong font (biggest tell), off palette, spacing drift, missing shadow,
   clipped icon, transparency box.
4. Re-run at 150% scale to catch DPI issues.
5. File any delta as a **host-container** fix (W3/W4/W6/W7) — do **not** edit the shared `*_html.py`
   (that would break Mac parity). The only acceptable HTML-level change is one that improves BOTH
   platforms, applied to the shared file and re-verified on Mac.

## Acceptance

- [ ] All six surfaces render in Geist + JetBrains Mono (not system fallback) on the frozen Windows exe.
- [ ] Palette matches (`#0e1012` / `#17191c` / `#C85A3E` / `#f2f2f2` / `#4ad15a` + pastels).
- [ ] Icons, spacing, radii, shadows visually match Mac at 100% scale.
- [ ] Animations (pillIn, waveform, spinner) run smoothly on WebView2.
- [ ] No white flash on open; scrollbars styled; readable at 125%/150% DPI.
- [ ] Any transparency fallback (overlay/HUD) still reads as a clean rounded surface.
