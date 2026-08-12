"""Windows recording overlay — tkinter + PIL sticker pill.

Real per-pixel transparency: tkinter's `-transparentcolor` window attribute
tells DWM to mask out one specific RGB color, and unlike WebView2's
DirectComposition surface this DOES survive through the compositor, so the
pill floats on the desktop with no surrounding rectangle.

Public interface matches OverlayBar (app/overlay.py):
    setup(), show(status), update_status(status),
    show_briefly(status, duration), hide(), .visible

Rendered visual approximates the Mac Flume pill:
  * dark rounded pill background
  * left dot (accent when recording / blue when transcribing / green when done)
  * timer while recording, elapsed 'Xs' while transcribing
  * animated waveform bars while recording
  * device name suffix

No clickable buttons yet — the Right-Alt hotkey still starts/stops recording,
so buttons on the pill are cosmetic for now. Adding them later means binding
canvas click regions to app methods.

Fail-closed: setup() is wrapped by the caller; if the tkinter window can't
build, the recording pipeline runs without a visible overlay.
"""

import logging
import math
import re
import threading
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageTk

logger = logging.getLogger("verbal.overlay")

# ── Layout ──────────────────────────────────────────────────────────────
PILL_W = 470
PILL_H = 44
RADIUS = 22
PANEL_W = PILL_W                # window IS the pill — no surrounding canvas
PANEL_H = PILL_H
PADDING_LEFT  = 12
PADDING_RIGHT = 10

BAR_COUNT   = 10
BAR_W       = 2.5
BAR_GAP     = 3.0
BAR_MAX_H   = 22

# Button geometry (recording-mode right cluster).
BTN_R       = 11                # ctrl-button radius
BTN_GAP     = 6                 # spacing between buttons

# ── Colors (mirroring overlay_html.py CSS vars) ─────────────────────────
BG_RGB     = (26, 25, 23)             # --pill (rgba(22,20,18,.96) opaqued)
BORDER_RGB = (60, 55, 50)             # --bd
TEXT_RGB   = (240, 240, 240)          # --tx
MUTED_RGB  = (140, 140, 140)          # --mut
ACC_RGB    = (232, 82, 42)            # --acc (orange)
BLUE_RGB   = (74, 144, 226)
GREEN_RGB  = (74, 209, 90)            # --green

# tkinter's -transparentcolor makes pixels of ONE exact color invisible.
# Any color works, but PIL antialiases the pill's rounded corners against
# whatever fills the surrounding pixels — with a bright chroma (magenta)
# those blended edge pixels aren't the exact key color, so they stay
# visible as a colored halo around the pill. Using a dark near-black key
# lets the antialias blend from pill-dark → near-black, which reads as a
# faint dark shadow instead of a pink fringe. `#0a0a0a` is dark enough to
# be effectively invisible on most desktops and is not used anywhere in
# the pill (BG=#1a1917, TEXT=#f0f0f0, ACCENT=#e85 2a, GREEN=#4ad15a).
CHROMA_TK  = "#0a0a0a"


class WinOverlay:
    """Public interface matches OverlayBar. Runs the tk mainloop on its own
    daemon thread so nothing here needs to touch the pywebview main-thread
    contract used by the other windows."""

    def __init__(self, app=None):
        self.app = app
        self._root = None
        self._canvas = None
        self._photo = None
        self._font_ui = None
        self._font_num = None

        self._status_text = ""
        self._device = "WIN"
        self._src = "WIN"
        self._dst = "WIN"
        self._done_label = ""
        self._done_meta = ""
        self._mode = "hidden"          # 'recording' | 'transcribing' | 'done' | 'hidden'

        self._t0 = 0.0                 # record start
        self._phase = 0.0              # waveform animation phase
        self._paused = False           # local paused-state hint for the icon
        self._active = False
        self._visible = False
        self._alpha = 0.0
        self._hide_timer = None
        self._anim_timer = None
        self._show_time = 0
        self._done_token = 0
        # Hit-boxes for right-cluster buttons — rebuilt each render:
        # list of (x1, y1, x2, y2, action_name).
        self._hits = []

    # ── device-name helpers (parity with overlay.py) ─────────────────────
    def _this_device(self):
        try:
            return (self.app.config.get("sync_device_name") or "").strip() or "WIN"
        except Exception:
            return "WIN"

    def _target_device(self):
        try:
            dash = getattr(self.app, "dashboard", None)
            tid = getattr(dash, "_target_device_id", "__all__") if dash else "__all__"
            if tid in (None, "", "__all__", "__none__"):
                return self._this_device()
            for d in getattr(dash, "_known_devices", []) or []:
                if d.get("device_id") == tid:
                    return d.get("device_name") or self._this_device()
        except Exception:
            pass
        return self._this_device()

    # ── setup: spawn the tk mainloop on a daemon thread ─────────────────
    def setup(self):
        t = threading.Thread(target=self._run_tk, name="overlay-tk", daemon=True)
        t.start()

    def _run_tk(self):
        try:
            self._root = tk.Tk()
            self._root.overrideredirect(True)                     # no titlebar/frame
            self._root.attributes("-topmost", True)               # float above apps
            self._root.attributes("-alpha", 0.0)                  # start invisible
            self._root.attributes("-transparentcolor", CHROMA_TK) # sticker key
            self._root.configure(bg=CHROMA_TK)
            self._root.withdraw()

            # Bottom-center of the primary work area — matches Mac overlay.py.
            screen_w = self._root.winfo_screenwidth()
            screen_h = self._root.winfo_screenheight()
            x = (screen_w - PANEL_W) // 2
            y = screen_h - PANEL_H - 100
            self._root.geometry(f"{PANEL_W}x{PANEL_H}+{x}+{y}")

            self._canvas = tk.Canvas(
                self._root,
                width=PANEL_W,
                height=PANEL_H,
                bg=CHROMA_TK,
                highlightthickness=0,
                borderwidth=0,
            )
            self._canvas.pack()
            self._canvas.bind("<Button-1>", self._on_click)

            self._load_fonts()

            self._root.mainloop()
        except Exception as e:
            logger.error("overlay tk thread crashed: %s", e, exc_info=True)

    def _load_fonts(self):
        # Try Windows-native fonts; fall back to defaults if the font files
        # are missing. Sizes chosen to fit a 44-px-tall pill comfortably.
        self._font_ui = None
        self._font_num = None
        for face in ("segoeui.ttf", "arial.ttf"):
            try:
                self._font_ui = ImageFont.truetype(face, 12)
                break
            except Exception:
                continue
        for face in ("Consola.ttf", "consola.ttf", "cour.ttf"):
            try:
                self._font_num = ImageFont.truetype(face, 13)
                break
            except Exception:
                continue
        if self._font_ui is None:
            self._font_ui = ImageFont.load_default()
        if self._font_num is None:
            self._font_num = self._font_ui

    # ── OverlayBar-shaped public interface ──────────────────────────────
    def _cancel_hide(self):
        self._done_token += 1
        if self._hide_timer is not None and self._root is not None:
            try:
                self._root.after_cancel(self._hide_timer)
            except Exception:
                pass
            self._hide_timer = None

    def show(self, status="Listening..."):
        self._status_text = status
        self._device = self._this_device()
        self._src = self._this_device()
        self._dst = self._target_device()
        self._mode = "recording"
        self._t0 = time.time()
        self._paused = False
        self._active = True
        self._show_time = time.time()
        self._safe(self._show_internal)

    def update_status(self, status):
        if not status:
            return
        self._status_text = status
        if "Transcrib" in status:
            self._mode = "transcribing"
            self._src = self._this_device()
            self._dst = self._target_device()
        else:
            self._mode = "done"
            self._done_label = status
            self._done_meta = ""
        self._safe(self._render)

    def show_briefly(self, status, duration=2.0):
        self._mode = "done"
        s = status or ""
        low = s.lower()
        if low.startswith("pasted"):
            self._done_label = f"Pasted to {self._this_device()}"
        elif "clipboard" in low:
            self._done_label = "Copied to clipboard"
        else:
            self._done_label = s or "Done"
        secs = int(max(0, time.time() - self._t0)) if self._t0 else 0
        m = re.search(r"(\d+)\s*w", s, re.I)
        words = m.group(1) if m else ""
        self._done_meta = (f"{words}W · {secs}S" if words else (f"{secs}S" if secs else ""))
        self._active = True
        self._safe(lambda: (self._show_internal(), self._schedule_hide(duration)))

    def hide(self):
        self._active = False
        self._mode = "hidden"
        self._safe(self._fade_out)

    @property
    def visible(self):
        return self._visible

    # ── internals ───────────────────────────────────────────────────────
    def _safe(self, fn):
        if self._root is None:
            return
        try:
            self._root.after(0, fn)
        except Exception as e:
            logger.debug("overlay _safe schedule failed: %s", e)

    def _show_internal(self):
        self._cancel_hide()
        if self._root is None:
            return
        if self._alpha < 0.3:
            self._alpha = 0.0
            self._root.deiconify()
            self._fade_in()
        else:
            self._render()
        self._visible = True
        if self._anim_timer is None:
            self._start_animation_loop()

    def _fade_in(self):
        if self._root is None:
            return
        self._alpha = min(0.98, self._alpha + 0.08)
        self._root.attributes("-alpha", self._alpha)
        self._render()
        if self._alpha < 0.95:
            self._hide_timer = self._root.after(16, self._fade_in)

    def _fade_out(self):
        if self._root is None:
            return
        self._alpha = max(0.0, self._alpha - 0.08)
        try:
            self._root.attributes("-alpha", self._alpha)
        except Exception:
            pass
        if self._alpha <= 0.0:
            try:
                self._root.withdraw()
            except Exception:
                pass
            self._visible = False
            return
        self._hide_timer = self._root.after(16, self._fade_out)

    def _schedule_hide(self, duration):
        token = self._done_token = self._done_token + 1

        def _auto():
            if self._done_token != token:
                return
            self.hide()
        self._hide_timer = self._root.after(int(max(0.4, duration) * 1000), _auto)

    def _start_animation_loop(self):
        if not self._active or self._root is None:
            self._anim_timer = None
            return
        self._phase += 0.10
        self._render()
        self._anim_timer = self._root.after(33, self._start_animation_loop)

    # ── rendering ───────────────────────────────────────────────────────
    def _render(self):
        if self._canvas is None:
            return
        try:
            # Base transparent-chroma canvas the pill sits on. Anything
            # outside the pill outline is CHROMA_TK → tkinter masks it out.
            img = Image.new("RGBA", (PANEL_W, PANEL_H),
                            _hex_to_rgba(CHROMA_TK))
            draw = ImageDraw.Draw(img)

            # Pill background — a filled rounded rectangle covering the
            # whole window minus 1px so the border reads crisp.
            border_color = ACC_RGB if self._mode == "recording" else BORDER_RGB
            draw.rounded_rectangle(
                (0, 0, PANEL_W - 1, PANEL_H - 1),
                radius=RADIUS,
                fill=BG_RGB + (255,),
                outline=border_color + (200,),
                width=1,
            )

            if self._mode == "recording":
                self._draw_recording(draw, img)
            elif self._mode == "transcribing":
                self._draw_transcribing(draw, img)
            elif self._mode == "done":
                self._draw_done(draw, img)

            # Blit to tk. Pass `master=self._canvas` — with several tk.Tk()
            # roots in this app (overlay / autolearn / HUD / transform each
            # own one), ImageTk's implicit default root can be the wrong one
            # and Tcl loses the image handle ("pyimage### doesn't exist").
            self._canvas.delete("all")
            self._photo = ImageTk.PhotoImage(img, master=self._canvas)
            self._canvas.create_image(0, 0, image=self._photo, anchor="nw")
        except Exception as e:
            logger.error("overlay render error: %s", e, exc_info=True)

    def _draw_recording(self, draw, img):
        cy = PANEL_H // 2
        x = PADDING_LEFT
        self._hits = []

        # Left "mute" glyph — small circle with accent ring and minus mark.
        r = 9
        draw.ellipse((x, cy - r, x + 2 * r, cy + r),
                     outline=ACC_RGB + (255,), width=2)
        draw.line((x + 5, cy, x + 2 * r - 5, cy),
                  fill=ACC_RGB + (255,), width=2)
        x += 2 * r + 8

        # Timer (MM:SS) in a numeric-monospace font.
        secs = int(max(0, time.time() - self._t0)) if self._t0 else 0
        timer_text = f"{secs // 60:02d}:{secs % 60:02d}"
        tw = _text_width(draw, timer_text, self._font_num)
        draw.text((x, cy - 8), timer_text, fill=TEXT_RGB + (255,),
                  font=self._font_num)
        x += tw + 10

        # Vertical separator bar.
        draw.line((x, cy - 8, x, cy + 8), fill=(80, 80, 80, 255), width=1)
        x += 8

        # Waveform bars — animated sine over time.
        for i in range(BAR_COUNT):
            frac = 1.0 - abs(i - (BAR_COUNT - 1) / 2.0) / ((BAR_COUNT - 1) / 2.0)
            wave = abs(math.sin(self._phase * 3.0 + i * 0.6))
            bh = max(3, BAR_MAX_H * (0.35 + 0.65 * frac) * wave)
            bx = x + i * (BAR_W + BAR_GAP)
            draw.rounded_rectangle(
                (bx, cy - bh / 2, bx + BAR_W, cy + bh / 2),
                radius=BAR_W / 2,
                fill=TEXT_RGB + (int(180 + 60 * frac),),
            )
        x += int(BAR_COUNT * (BAR_W + BAR_GAP)) + 10

        # Device name (uppercase, muted).
        dev_text = (self._device or "WIN").upper()
        draw.text((x, cy - 7), dev_text, fill=MUTED_RGB + (255,),
                  font=self._font_ui)

        # Right-cluster: pause, cancel, stop. Laid out right-to-left so the
        # stop button always sits at the pill's tail.
        rx = PANEL_W - PADDING_RIGHT - BTN_R
        # Stop button (orange with white square) — ends recording.
        self._draw_stop(draw, rx, cy)
        rx -= 2 * BTN_R + BTN_GAP
        # Cancel button (dark ring, ×) — discards recording.
        self._draw_ctrl(draw, rx, cy, glyph="x")
        rx -= 2 * BTN_R + BTN_GAP
        # Pause button (dark ring, ‖ or ►) — toggles paused state.
        self._draw_ctrl(draw, rx, cy,
                        glyph="play" if self._paused else "pause")

    def _draw_stop(self, draw, cx, cy):
        r = BTN_R
        draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                     fill=ACC_RGB + (255,))
        sq = 5
        draw.rounded_rectangle(
            (cx - sq, cy - sq, cx + sq, cy + sq),
            radius=2, fill=(255, 255, 255, 255))
        self._hits.append((cx - r, cy - r, cx + r, cy + r, "overlay_stop"))

    def _draw_ctrl(self, draw, cx, cy, glyph):
        r = BTN_R
        # Dark filled circle with faint outline (subtle button chip).
        draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                     fill=(240, 240, 240, 24),
                     outline=(240, 240, 240, 40), width=1)
        col = TEXT_RGB + (230,)
        if glyph == "x":
            # X marks — two crossing lines.
            k = 4
            draw.line((cx - k, cy - k, cx + k, cy + k), fill=col, width=2)
            draw.line((cx - k, cy + k, cx + k, cy - k), fill=col, width=2)
            action = "overlay_cancel"
        elif glyph == "pause":
            # Two vertical bars.
            draw.rectangle((cx - 3, cy - 4, cx - 1, cy + 4), fill=col)
            draw.rectangle((cx + 1, cy - 4, cx + 3, cy + 4), fill=col)
            action = "overlay_pause"
        elif glyph == "play":
            # Filled right-pointing triangle (paused → resume).
            draw.polygon(
                [(cx - 3, cy - 5), (cx - 3, cy + 5), (cx + 4, cy)],
                fill=col)
            action = "overlay_pause"
        else:
            action = None
        if action:
            self._hits.append((cx - r, cy - r, cx + r, cy + r, action))

    def _draw_transcribing(self, draw, img):
        cy = PANEL_H // 2
        x = PADDING_LEFT

        # Spinner: an accent arc that rotates with self._phase.
        r = 9
        start = int((self._phase * 90) % 360)
        end = (start + 270) % 360
        draw.arc((x, cy - r, x + 2 * r, cy + r),
                 start=start, end=end,
                 fill=ACC_RGB + (255,), width=2)
        x += 2 * r + 10

        # Elapsed seconds since the start of recording (same clock as
        # the recording pill so the number carries over smoothly).
        secs = int(max(0, time.time() - self._t0)) if self._t0 else 0
        label = f"Transcribing {secs}s"
        draw.text((x, cy - 8), label, fill=TEXT_RGB + (255,),
                  font=self._font_ui)
        tw = _text_width(draw, label, self._font_ui)
        x += tw + 12

        # Route: SRC → DST in muted small text, right-aligned to available
        # room.
        route = f"{(self._src or 'WIN').upper()}  →  {(self._dst or 'WIN').upper()}"
        route_w = _text_width(draw, route, self._font_ui)
        rx = PANEL_W - PADDING_RIGHT - route_w
        if rx > x:
            draw.text((rx, cy - 7), route, fill=MUTED_RGB + (255,),
                      font=self._font_ui)

    # ── click dispatch ──────────────────────────────────────────────────
    def _on_click(self, event):
        # Only recording mode currently has interactive buttons.
        if self._mode != "recording":
            return
        x, y = event.x, event.y
        for (x1, y1, x2, y2, action) in self._hits:
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._action(action)
                return

    def _action(self, name):
        try:
            if name == "overlay_stop":
                if self.app and hasattr(self.app, "_toggle_recording"):
                    self.app._on_main(self.app._toggle_recording)
            elif name == "overlay_cancel":
                if self.app and hasattr(self.app, "_cancel_recording"):
                    self.app._on_main(self.app._cancel_recording)
                else:
                    self.hide()
            elif name == "overlay_pause":
                rec = getattr(self.app, "recorder", None) if self.app else None
                if rec and hasattr(rec, "toggle_pause"):
                    try:
                        rec.toggle_pause()
                        self._paused = not self._paused
                        self._safe(self._render)
                    except Exception as e:
                        logger.debug("overlay pause failed: %s", e)
        except Exception as e:
            logger.error("overlay action %s failed: %s", name, e)

    def _draw_done(self, draw, img):
        cy = PANEL_H // 2
        x = PADDING_LEFT

        # Green check dot on the left.
        r = 6
        draw.ellipse((x, cy - r, x + 2 * r, cy + r),
                     fill=GREEN_RGB + (255,))
        x += 2 * r + 10

        # Label + meta.
        label = self._done_label or "Done"
        draw.text((x, cy - 8), label, fill=TEXT_RGB + (255,),
                  font=self._font_ui)

        if self._done_meta:
            meta_w = _text_width(draw, self._done_meta, self._font_ui)
            mx = PANEL_W - PADDING_RIGHT - meta_w
            draw.text((mx, cy - 7), self._done_meta,
                      fill=MUTED_RGB + (255,), font=self._font_ui)


def _hex_to_rgba(hexstr):
    h = hexstr.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r, g, b, 255)


def _text_width(draw, text, font):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    except Exception:
        return int(len(text) * 6.5)
