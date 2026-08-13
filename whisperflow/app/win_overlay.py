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

import ctypes
import ctypes.wintypes as wintypes
import logging
import math
import re
import threading
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageTk

logger = logging.getLogger("verbal.overlay")

# ── DPI scaling ─────────────────────────────────────────────────────────
# This process runs DPI-AWARE: pywebview flips it to per-monitor awareness
# when WebView2 creates its first window, so tkinter geometry and PIL drawing
# are in real device pixels. An unscaled 470x44 pill therefore renders at half
# its intended physical size on a 200%-scaled display (and a third at 300%).
# Every layout value below is a 96-DPI design number; `_apply_scale()` restates
# them in device pixels once the primary monitor's DPI is known.
SCALE = 1.0

# 96-DPI design values — the source of truth for the pill's proportions.
# Capsule (IDI-184). The WINDOW stays at PILL_W — wide enough for the widest
# state — but the pill is now drawn only as wide as the current state needs,
# centred inside it. Everything outside the drawn pill is CHROMA_TK, which
# tkinter masks out AND which is click-through, so the surplus window costs
# nothing. Doing it this way avoids resizing the window on hover, which would
# make Enter/Leave flap as the frame moved out from under the cursor.
_DESIGN = {
    "PILL_W": 340, "PILL_H": 40, "RADIUS": 20, "BOTTOM_MARGIN": 40,
    "PADDING_LEFT": 12, "PADDING_RIGHT": 10,
    "BAR_W": 2.5, "BAR_GAP": 3.0, "BAR_MAX_H": 18,
    "BTN_R": 10, "BTN_GAP": 6,
    "FONT_UI": 12, "FONT_NUM": 12,
    # Per-state pill widths: (resting, revealed). Resting carries only what is
    # live; the control cluster appears on hover, as on the Mac.
    "W_REC": 150, "W_REC_OPEN": 250,
    "W_TRANS": 175, "W_TRANS_OPEN": 215,
    "W_DONE": 235, "W_DONE_OPEN": 250,
}

# Taste multiplier applied on top of the DPI scale. 1.0 is exact Mac parity;
# lower values shrink the whole pill (proportions, fonts and hit-boxes together).
# Tune this rather than editing _DESIGN, which mirrors the Mac pill.
USER_SCALE = 0.85

BAR_COUNT = 11                  # a count, never scaled (matches the Mac capsule)


def _s(v):
    """Scale a 96-DPI design length to device pixels (float)."""
    return v * SCALE


def _i(v):
    """Scale a 96-DPI stroke width / small offset to whole device pixels."""
    return max(1, int(round(v * SCALE)))


def _apply_scale(scale):
    """Restate every layout constant in device pixels for `scale`."""
    global SCALE, PILL_W, PILL_H, RADIUS, PANEL_W, PANEL_H, BOTTOM_MARGIN
    global PADDING_LEFT, PADDING_RIGHT, BAR_W, BAR_GAP, BAR_MAX_H
    global W_REC, W_REC_OPEN, W_TRANS, W_TRANS_OPEN, W_DONE, W_DONE_OPEN
    global BTN_R, BTN_GAP, FONT_UI, FONT_NUM
    SCALE = scale
    d = _DESIGN
    PILL_W = int(round(d["PILL_W"] * scale))
    PILL_H = int(round(d["PILL_H"] * scale))
    RADIUS = int(round(d["RADIUS"] * scale))
    PANEL_W = PILL_W            # window IS the pill — no surrounding canvas
    PANEL_H = PILL_H
    BOTTOM_MARGIN = int(round(d["BOTTOM_MARGIN"] * scale))
    PADDING_LEFT = int(round(d["PADDING_LEFT"] * scale))
    PADDING_RIGHT = int(round(d["PADDING_RIGHT"] * scale))
    W_REC = int(round(d["W_REC"] * scale))
    W_REC_OPEN = int(round(d["W_REC_OPEN"] * scale))
    W_TRANS = int(round(d["W_TRANS"] * scale))
    W_TRANS_OPEN = int(round(d["W_TRANS_OPEN"] * scale))
    W_DONE = int(round(d["W_DONE"] * scale))
    W_DONE_OPEN = int(round(d["W_DONE_OPEN"] * scale))
    BAR_W = d["BAR_W"] * scale
    BAR_GAP = d["BAR_GAP"] * scale
    BAR_MAX_H = d["BAR_MAX_H"] * scale
    BTN_R = int(round(d["BTN_R"] * scale))
    BTN_GAP = int(round(d["BTN_GAP"] * scale))
    FONT_UI = max(1, int(round(d["FONT_UI"] * scale)))
    FONT_NUM = max(1, int(round(d["FONT_NUM"] * scale)))


_apply_scale(1.0)               # sane defaults before setup() probes the DPI

# ── Colors (mirroring overlay_html.py CSS vars) ─────────────────────────
BG_RGB     = (26, 25, 23)             # --pill (rgba(22,20,18,.96) opaqued)
BORDER_RGB = (60, 55, 50)             # --bd
TEXT_RGB   = (240, 240, 240)          # --tx
MUTED_RGB  = (140, 140, 140)          # --mut
ACC_RGB    = (200, 90, 62)            # --acc #C85A3E terracotta. NOT #E8522A
                                      # (232,82,42) — that orange is retired,
                                      # 05-conventions Rule #16. Found during IDI-184.
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
        self._phase = 0.0              # spinner / fallback-waveform phase
        # Live waveform: a scrolling history of the recorder's 0..1 mic level,
        # newest sample at the right. Empty until the first level is sampled,
        # which is what makes the fallback sine kick in (see _draw_recording).
        self._wave = []
        self._wave_step = 0
        self._paused = False
        self._hover = False          # pointer over the drawn pill (Capsule)
        self._px0 = 0                # drawn pill's left/right edges, set by
        self._px1 = PANEL_W          # _render, used for hit-testing
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

    def _probe_scale(self):
        """Device pixels per 96-DPI unit on the primary monitor.

        Returns 1.0 when the process is DPI-unaware (Windows then scales our
        output itself), so this is self-adjusting rather than double-scaling.
        """
        try:
            dpi = ctypes.windll.user32.GetDpiForSystem()
        except AttributeError:                      # pre-1607 fallback
            try:
                hdc = ctypes.windll.user32.GetDC(0)
                dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
                ctypes.windll.user32.ReleaseDC(0, hdc)
            except Exception as e:
                logger.debug("overlay dpi probe failed: %s", e)
                return 1.0
        except Exception as e:
            logger.debug("overlay dpi probe failed: %s", e)
            return 1.0
        return (dpi / 96.0) if dpi else 1.0

    def _run_tk(self):
        try:
            dpi_scale = self._probe_scale()
            scale = dpi_scale * USER_SCALE
            _apply_scale(scale)
            logger.info("overlay: dpi=%.2f user=%.2f -> scale=%.2f pill=%dx%d",
                        dpi_scale, USER_SCALE, scale, PANEL_W, PANEL_H)
            self._root = tk.Tk()
            self._root.overrideredirect(True)                     # no titlebar/frame
            self._root.attributes("-topmost", True)               # float above apps
            self._root.attributes("-alpha", 0.0)                  # start invisible
            self._root.attributes("-transparentcolor", CHROMA_TK) # sticker key
            self._root.configure(bg=CHROMA_TK)
            self._root.withdraw()

            self._reposition()

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
            # Hover reveal. <Enter>/<Leave> fire for the whole WINDOW, most of
            # which is masked-out chroma, so <Motion> does the precise work:
            # only a pointer actually over the drawn pill counts.
            self._canvas.bind("<Motion>", self._on_motion)
            self._canvas.bind("<Leave>", self._on_leave)

            self._load_fonts()

            self._root.mainloop()
        except Exception as e:
            logger.error("overlay tk thread crashed: %s", e, exc_info=True)

    # ── geometry ────────────────────────────────────────────────────────
    def _work_area(self):
        """Primary monitor's work area (screen minus taskbar), or None."""
        try:
            r = wintypes.RECT()
            # SPI_GETWORKAREA = 0x0030
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):
                return (r.left, r.top, r.right, r.bottom)
        except Exception as e:
            logger.debug("overlay work-area probe failed: %s", e)
        return None

    def _reposition(self):
        """Park the pill bottom-center of the work area.

        Recomputed on every show, not only at setup: the desktop can be
        resized under a running app (VM/RDP auto-fit, docking, a resolution
        change), and a y computed once at startup then strands the pill
        mid-screen. Uses the work area so we sit above the taskbar rather
        than behind it — `winfo_screenheight()` doesn't know about it.
        """
        if self._root is None:
            return
        try:
            wa = self._work_area()
            if wa:
                left, top, right, bottom = wa
            else:
                left, top = 0, 0
                right = self._root.winfo_screenwidth()
                bottom = self._root.winfo_screenheight()
            x = left + (right - left - PANEL_W) // 2
            y = bottom - PANEL_H - BOTTOM_MARGIN
            self._root.geometry(f"{PANEL_W}x{PANEL_H}+{x}+{y}")
        except Exception as e:
            logger.debug("overlay reposition failed: %s", e)

    def _load_fonts(self):
        # Try Windows-native fonts; fall back to defaults if the font files
        # are missing. Sizes chosen to fit a 44-px-tall pill comfortably.
        self._font_ui = None
        self._font_num = None
        for face in ("segoeui.ttf", "arial.ttf"):
            try:
                self._font_ui = ImageFont.truetype(face, FONT_UI)
                break
            except Exception:
                continue
        for face in ("Consola.ttf", "consola.ttf", "cour.ttf"):
            try:
                self._font_num = ImageFont.truetype(face, FONT_NUM)
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
        self._hover = False   # a stale hover must not open the new capsule
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
        self._reposition()
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
        self._sample_level()
        self._poll_hover()      # before _render, so this frame shows the result
        self._render()
        self._anim_timer = self._root.after(33, self._start_animation_loop)

    def _sample_level(self):
        """Scroll one mic-level sample into the waveform history (~15 Hz).

        Every other 33 ms frame, so the 10 bars span ~0.7 s of audio — slow
        enough to read as speech, fast enough to feel immediate. The history
        stays empty (→ fallback sine) if the recorder can't be reached.
        """
        if self._mode != "recording":
            self._wave = []
            return
        self._wave_step += 1
        if self._wave_step % 2:
            return
        try:
            rec = getattr(self.app, "recorder", None) if self.app else None
            if rec is None:
                return
            lvl = float(getattr(rec, "level", 0.0) or 0.0)
        except Exception:
            return
        lvl = min(1.0, max(0.0, lvl))
        if not self._wave:
            self._wave = [0.0] * BAR_COUNT
        self._wave.append(lvl)
        del self._wave[:-BAR_COUNT]

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

            # Pill background — content-sized and centred, not the whole window.
            # `_px0`/`_px1` are the drawn pill's edges; every draw helper and the
            # hover hit-test works off them.
            pw = self._pill_width()
            self._px0 = max(0, (PANEL_W - pw) // 2)
            self._px1 = self._px0 + pw
            border_color = ACC_RGB if self._mode == "recording" else BORDER_RGB
            if self._mode == "recording" and self._paused:
                border_color = BORDER_RGB
            draw.rounded_rectangle(
                (self._px0, 0, self._px1 - _i(1), PANEL_H - _i(1)),
                radius=RADIUS,
                fill=BG_RGB + (255,),
                outline=border_color + (200,),
                width=_i(1),
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
        x = self._px0 + PADDING_LEFT
        self._hits = []
        # The old left-hand "mute" disc is gone: nothing in the app ever set a
        # mute state, so it was decoration occupying the pill's most valuable
        # position. Same for the device tag that used to sit before the buttons —
        # the Done pill already names where the text landed.

        # Waveform bars — driven by the real mic level, scrolling left. Falls
        # back to the old sine animation whenever no level history exists (the
        # recorder isn't reachable), so the pill is never blank.
        for i in range(BAR_COUNT):
            frac = 1.0 - abs(i - (BAR_COUNT - 1) / 2.0) / ((BAR_COUNT - 1) / 2.0)
            if self._wave:
                lvl = self._wave[i]
                # A little level-scaled shimmer so a steady tone still breathes
                # while silence stays flat.
                lvl *= 1.0 + 0.12 * math.sin(self._phase * 3.0 + i * 1.7) * min(1.0, self._wave[i] * 3.0)
                bh = max(3, BAR_MAX_H * min(1.0, lvl))
            else:
                wave = abs(math.sin(self._phase * 3.0 + i * 0.6))
                bh = max(3, BAR_MAX_H * (0.35 + 0.65 * frac) * wave)
            bx = x + i * (BAR_W + BAR_GAP)
            # Plain rectangle, NOT rounded_rectangle: Pillow derives its own
            # inner radius and builds (y0 + r + 1 .. y1 - r - 1), which inverts
            # and raises ValueError for a band of short bars (3.5-4.4px fail
            # while 3.0 and 4.4 pass — it isn't monotonic, and clamping the
            # radius we pass doesn't avoid it). That hit ~2.6% of animation
            # frames, and since _render wraps the whole repaint in try/except,
            # one bad bar dropped the entire pill frame. Corner rounding on a
            # 2.5px-wide bar is invisible anyway.
            draw.rectangle(
                (bx, cy - bh / 2, bx + BAR_W, cy + bh / 2),
                fill=TEXT_RGB + (int(180 + 60 * frac),),
            )
        x += int(BAR_COUNT * (BAR_W + BAR_GAP)) + _s(9)

        # Timer (MM:SS) in a numeric-monospace font — the second and last thing
        # in the resting capsule.
        secs = int(max(0, time.time() - self._t0)) if self._t0 else 0
        timer_text = f"{secs // 60:02d}:{secs % 60:02d}"
        draw.text((x, cy - _s(7)), timer_text, fill=TEXT_RGB + (255,),
                  font=self._font_num)

        # Everything below is the revealed cluster. Collapsed, it is not drawn
        # and registers no hit-boxes, so a click on the resting capsule can only
        # expand it (see _on_click) — it can never hit an invisible button.
        if not self._revealed():
            return

        # Right-cluster: pause, cancel, stop. Laid out right-to-left so the
        # stop button always sits at the pill's tail.
        rx = self._px1 - PADDING_RIGHT - BTN_R
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
        sq = _s(5)
        draw.rounded_rectangle(
            (cx - sq, cy - sq, cx + sq, cy + sq),
            radius=_s(2), fill=(255, 255, 255, 255))
        self._hits.append((cx - r, cy - r, cx + r, cy + r, "overlay_stop"))

    def _draw_ctrl(self, draw, cx, cy, glyph):
        r = BTN_R
        # Dark filled circle with faint outline (subtle button chip).
        draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                     fill=_over(TEXT_RGB, 24) + (255,),
                     outline=_over(TEXT_RGB, 40) + (255,), width=_i(1))
        col = TEXT_RGB + (230,)
        if glyph == "x":
            # X marks — two crossing lines.
            k = _s(4)
            draw.line((cx - k, cy - k, cx + k, cy + k), fill=col, width=_i(2))
            draw.line((cx - k, cy + k, cx + k, cy - k), fill=col, width=_i(2))
            action = "overlay_cancel"
        elif glyph == "pause":
            # Two vertical bars.
            draw.rectangle((cx - _s(3), cy - _s(4), cx - _s(1), cy + _s(4)), fill=col)
            draw.rectangle((cx + _s(1), cy - _s(4), cx + _s(3), cy + _s(4)), fill=col)
            action = "overlay_pause"
        elif glyph == "play":
            # Filled right-pointing triangle (paused → resume).
            draw.polygon(
                [(cx - _s(3), cy - _s(5)), (cx - _s(3), cy + _s(5)), (cx + _s(4), cy)],
                fill=col)
            action = "overlay_pause"
        else:
            action = None
        if action:
            self._hits.append((cx - r, cy - r, cx + r, cy + r, action))

    def _draw_transcribing(self, draw, img):
        cy = PANEL_H // 2
        x = self._px0 + PADDING_LEFT
        self._hits = []

        # Spinner: an accent arc that rotates with self._phase.
        r = _s(9)
        start = int((self._phase * 90) % 360)
        end = (start + 270) % 360
        draw.arc((x, cy - r, x + 2 * r, cy + r),
                 start=start, end=end,
                 fill=ACC_RGB + (255,), width=_i(2))
        x += 2 * r + _s(10)

        # Elapsed seconds since the start of recording (same clock as
        # the recording pill so the number carries over smoothly).
        secs = int(max(0, time.time() - self._t0)) if self._t0 else 0
        label = f"Transcribing {secs}s"
        draw.text((x, cy - _s(8)), label, fill=TEXT_RGB + (255,),
                  font=self._font_ui)
        tw = _text_width(draw, label, self._font_ui)
        x += tw + _s(12)

        # The SRC → DST route used to sit here. It is dropped for the same
        # reason as the recording device tag: the Done pill states the
        # destination, which is the moment it is news. Cancel appears on hover.
        if not self._revealed():
            return
        rx = self._px1 - PADDING_RIGHT - BTN_R
        self._draw_ctrl(draw, rx, cy, glyph="x")

    # ── capsule geometry / hover ─────────────────────────────────────────
    def _revealed(self):
        """True when the control cluster should be drawn.

        Hover reveals it; a paused recording forces it, because with no state
        caption the resume button is the only thing that says "paused" — it must
        not be hidden behind a hover.
        """
        if self._mode == "recording" and self._paused:
            return True
        return bool(getattr(self, "_hover", False))

    def _pill_width(self):
        """Width of the drawn pill for the current mode + reveal state."""
        try:
            if self._mode == "recording":
                return W_REC_OPEN if self._revealed() else W_REC
            if self._mode == "transcribing":
                return W_TRANS_OPEN if self._revealed() else W_TRANS
            if self._mode == "done":
                return W_DONE_OPEN if self._revealed() else W_DONE
        except Exception:
            pass
        return PANEL_W

    def _poll_hover(self):
        """Derive hover from where the pointer IS, not from <Motion> events.

        Events are the wrong foundation here. The window is colour-keyed, so most
        of it is masked and click-through, and it never holds focus — <Motion>
        arrives only over live pixels of a window taking input, which is exactly
        the case we cannot rely on. Polling the pointer against the drawn pill's
        rect always works, and it is free: this runs inside the 33 ms loop that
        already repaints the waveform.
        """
        try:
            if self._root is None:
                return
            px = self._root.winfo_pointerx() - self._root.winfo_rootx()
            py = self._root.winfo_pointery() - self._root.winfo_rooty()
            inside = (self._px0 <= px <= self._px1) and (0 <= py <= PANEL_H)
            self._hover = bool(inside)
        except Exception:
            pass    # a hover glitch must never disturb the pill

    def _on_motion(self, event):
        """Accelerator only — _poll_hover is the real mechanism, but reacting to
        a Motion event we DO get removes up to 33 ms of lag."""
        inside = (getattr(self, "_px0", 0) <= event.x <= getattr(self, "_px1", PANEL_W))
        if inside != bool(getattr(self, "_hover", False)):
            self._hover = inside
            self._safe(self._render)

    def _on_leave(self, event=None):
        # Also just an accelerator; the poll would catch it on the next frame.
        if getattr(self, "_hover", False):
            self._hover = False
            self._safe(self._render)

    # ── click dispatch ──────────────────────────────────────────────────
    def _on_click(self, event):
        x, y = event.x, event.y
        # Collapsed, there are no hit-boxes: a click on the capsule reveals the
        # controls instead of guessing at an invisible one. (Also the only way in
        # for a touchscreen, which never hovers.)
        if not self._revealed():
            if getattr(self, "_px0", 0) <= x <= getattr(self, "_px1", PANEL_W):
                self._hover = True
                self._safe(self._render)
            return
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
        x = self._px0 + PADDING_LEFT
        self._hits = []

        # Green check dot on the left.
        r = _s(6)
        draw.ellipse((x, cy - r, x + 2 * r, cy + r),
                     fill=GREEN_RGB + (255,))
        x += 2 * r + _s(10)

        # Label + meta.
        label = self._done_label or "Done"
        draw.text((x, cy - _s(8)), label, fill=TEXT_RGB + (255,),
                  font=self._font_ui)

        if self._done_meta:
            meta_w = _text_width(draw, self._done_meta, self._font_ui)
            mx = self._px1 - PADDING_RIGHT - meta_w
            if self._revealed():
                mx -= 2 * BTN_R + BTN_GAP
            draw.text((mx, cy - _s(7)), self._done_meta,
                      fill=MUTED_RGB + (255,), font=self._font_ui)
        if self._revealed():
            rx = self._px1 - PADDING_RIGHT - BTN_R
            self._draw_ctrl(draw, rx, cy, glyph="x")


def _over(fg, alpha, bg=None):
    """fg over bg at `alpha` (0-255), returned opaque.

    Needed because ImageDraw writes pixels verbatim — it never blends — and the
    layered window keys on colour, not alpha. Anything that wanted to be a faint
    tint has to be pre-composited here or it lands at full strength.
    """
    if bg is None:
        bg = BG_RGB
    a = max(0.0, min(1.0, alpha / 255.0))
    return tuple(int(round(f * a + b * (1.0 - a))) for f, b in zip(fg, bg))


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
