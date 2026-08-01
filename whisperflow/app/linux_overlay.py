"""Linux status overlay — modern floating pill rendered with PIL."""

import logging
import math
import tkinter as tk
import threading
import time
from PIL import Image, ImageDraw, ImageTk, ImageFont, ImageFilter

logger = logging.getLogger("verbal.overlay")

# ── Brand colors ──────────────────────────────────────────────────────
BG         = (26, 25, 23)
BG_HEX     = "#1A1917"
TEXT       = (242, 239, 233)
ACCENT     = (224, 90, 43)
BLUE       = (74, 144, 226)
GREEN      = (76, 175, 125)
MUTED      = (122, 117, 112)
BORDER     = (42, 40, 37)
SHADOW     = (0, 0, 0, 60)

# ── Layout ────────────────────────────────────────────────────────────
PILL_W    = 190
PILL_H    = 38
RADIUS    = 19
BAR_COUNT = 10
BAR_W     = 2.5
BAR_GAP   = 3.0
BAR_MAX_H = 20


class LinuxOverlay:
    def __init__(self):
        self._root       = None
        self._canvas     = None
        self._photo_img  = None
        self._canvas_img = None
        self._status_text = ""
        self._phase      = 0.0
        self._amplitude  = 0.0
        self._active     = False
        self._fade_alpha = 0.0
        # Three INDEPENDENT timer slots. They used to share one field, so scheduling the
        # hide cancelled the in-flight fade-in and every show_briefly() pill rendered at
        # 5% opacity (i.e. invisibly) for its whole duration.
        self._fade_timer = None   # fade in/out chain
        self._anim_timer = None   # recording waveform loop
        self._hide_timer = None   # pending auto-hide
        self._loop_running = False
        self._show_time  = 0
        self._font       = None

    def setup(self):
        t = threading.Thread(target=self._run_tk, daemon=True)
        t.start()

    def _target_monitor(self):
        """Return (x, y, w, h) of the monitor to place the pill on.

        Tk's winfo_screenwidth/height report the UNION bounding box of all monitors, so
        centering on them puts the pill in the middle of the virtual desktop — on a
        multi-monitor setup that is somewhere near a bezel, or on the wrong screen
        entirely. xrandr is queried rather than Gdk because it reports the same X11
        coordinate space Tk positions windows in (Gdk under Wayland may not).
        """
        import re
        import subprocess
        try:
            out = subprocess.run(
                ["xrandr", "--listmonitors"], capture_output=True, text=True, timeout=3
            ).stdout
            # e.g. " 0: +*eDP-1 3072/310x1728/170+0+432  eDP-1"   ('*' marks primary)
            monitors = []
            for line in out.splitlines():
                m = re.search(r"(\d+)/\d+x(\d+)/\d+\+(-?\d+)\+(-?\d+)", line)
                if m:
                    w, h, x, y = (int(g) for g in m.groups())
                    monitors.append((x, y, w, h, "*" in line.split(":", 1)[-1][:4]))
            if monitors:
                for x, y, w, h, primary in monitors:
                    if primary:
                        return (x, y, w, h)
                x, y, w, h, _ = monitors[0]
                return (x, y, w, h)
        except Exception as e:
            logger.debug(f"xrandr monitor query failed: {e}")
        return (0, 0, self._root.winfo_screenwidth(), self._root.winfo_screenheight())

    def _run_tk(self):
        try:
            self._root = tk.Tk()
            self._root.overrideredirect(True)
            self._root.attributes("-topmost", True)
            try:
                self._root.wm_attributes("-type", "splash")
            except Exception:
                pass
            
            self._root.attributes("-alpha", 0.0)
            self._root.withdraw()
            
            self._root.configure(bg=BG_HEX)

            mx, my, mw, mh = self._target_monitor()
            x = mx + (mw - PILL_W) // 2
            y = my + mh - PILL_H - 80
            self._root.geometry(f"{PILL_W}x{PILL_H}+{x}+{y}")

            self._canvas = tk.Canvas(
                self._root,
                width=PILL_W,
                height=PILL_H,
                bg=BG_HEX,
                highlightthickness=0,
            )
            self._canvas.pack()

            # Load font — try standard Linux fonts, then default
            try:
                self._font = ImageFont.truetype("DejaVuSans.ttf", 13)
            except Exception:
                try:
                    self._font = ImageFont.truetype("LiberationSans-Regular.ttf", 13)
                except Exception:
                    self._font = ImageFont.load_default()

            self._loop_running = True
            self._root.mainloop()
        except Exception as e:
            logger.error(f"Overlay thread crashed: {e}", exc_info=True)
        finally:
            # Without this, a crashed setup leaves _root non-None forever and every later
            # _safe() call blocks the CALLER for ~1s in Tcl's WaitForMainloop before
            # failing - which would put seconds of latency on the dictation hot path.
            self._loop_running = False

    def show(self, status="Listening..."):
        self._status_text = status
        self._active = True
        self._amplitude = 1.0
        self._show_time = time.time()
        self._safe(lambda: self._show_internal())

    def update_status(self, status):
        self._status_text = status
        self._safe(lambda: self._update_internal())

    def hide(self):
        self._active = False
        self._safe(lambda: self._fade_out())

    def show_briefly(self, status, duration=2.0):
        self.show(status)
        self._safe(lambda: self._schedule_hide(duration))

    def _cancel_one(self, attr):
        tid = getattr(self, attr, None)
        if tid:
            try:
                self._root.after_cancel(tid)
            except Exception:
                pass
            setattr(self, attr, None)

    def _cancel_animation(self):
        """Cancel fade/waveform chains only — leaves a pending auto-hide alone."""
        self._cancel_one("_fade_timer")
        self._cancel_one("_anim_timer")

    def _cancel_timers(self):
        self._cancel_animation()
        self._cancel_one("_hide_timer")

    def _schedule_hide(self, duration):
        # Only touch the hide slot. Cancelling the fade here is what made brief pills
        # invisible: show_briefly() queues _show_internal (starts the fade) then
        # _schedule_hide, so this ran one frame into the fade-in and killed it.
        self._cancel_one("_hide_timer")
        self._hide_timer = self._root.after(int(duration * 1000), self._fade_out)

    def _show_internal(self):
        if not self._root:
            return
        self._cancel_timers()
        if self._fade_alpha > 0.3:
            self._render()
        else:
            self._fade_in()

    def _fade_in(self):
        self._cancel_animation()
        self._fade_alpha = 0.0
        self._root.deiconify()
        self._root.lift()
        self._animate_fade_in()

    def _animate_fade_in(self):
        if self._fade_alpha < 0.95:
            self._fade_alpha += 0.05
            self._root.attributes("-alpha", min(self._fade_alpha, 0.95))
            self._render()
            self._fade_timer = self._root.after(16, self._animate_fade_in)
        else:
            self._root.attributes("-alpha", 0.95)
            self._render()
            self._start_animation_loop()

    def _fade_out(self):
        self._hide_timer = None   # we ARE the hide callback; don't cancel ourselves
        self._cancel_timers()
        self._active = False
        self._animate_fade_out()

    def _animate_fade_out(self):
        if self._fade_alpha > 0.0:
            self._fade_alpha = max(0.0, self._fade_alpha - 0.05)
            if self._fade_alpha > 0:
                self._root.attributes("-alpha", self._fade_alpha)
                self._render()
                self._fade_timer = self._root.after(16, self._animate_fade_out)
            else:
                self._root.attributes("-alpha", 0.0)
                self._root.withdraw()
                self._amplitude = 0.0
        else:
            self._root.withdraw()
            self._amplitude = 0.0

    def _update_internal(self):
        if not self._canvas:
            return
        self._render()

    def _start_animation_loop(self):
        if self._active and self._root:
            self._phase += 0.10
            self._render()
            self._anim_timer = self._root.after(33, self._start_animation_loop)

    def _render(self):
        if not self._canvas or not self._root:
            return

        try:
            is_recording  = self._active and ("Listen" in self._status_text or "Record" in self._status_text)
            is_processing = self._active and "Transcrib" in self._status_text
            is_success    = any(w in self._status_text for w in ("Done", "Pasted", "Copied", "clipboard"))

            dot_color = ACCENT if is_recording else (BLUE if is_processing else (GREEN if is_success else MUTED))

            # Create image with solid BG since Linux transparent background trick is tricky with Tkinter
            img = Image.new("RGBA", (PILL_W, PILL_H), (*BG, 255))
            draw = ImageDraw.Draw(img)

            # Main pill with gradient effect
            draw.rounded_rectangle(
                [0, 0, PILL_W - 1, PILL_H - 1],
                radius=RADIUS,
                fill=BG,
                outline=BORDER,
                width=1,
            )

            # Add subtle gradient highlight at top
            highlight = Image.new("RGBA", (PILL_W, PILL_H//3), (255, 255, 255, 10))
            img.paste(highlight, (0, 0), highlight)
            draw = ImageDraw.Draw(img)

            # ── Enhanced glow behind dot ───────────────────────────────────────
            if is_recording and self._amplitude > 0.01:
                glow_r = 12 + 8 * self._amplitude * abs(math.sin(self._phase * 2.0))
                cx, cy = 14, PILL_H // 2
                glow = Image.new("RGBA", (PILL_W, PILL_H), (0, 0, 0, 0))
                gd = ImageDraw.Draw(glow)
                for i in range(5):
                    r = glow_r - i * 2
                    alpha = 40 - i * 8
                    if r > 0 and alpha > 0:
                        gd.ellipse(
                            [cx - r, cy - r, cx + r, cy + r],
                            fill=(*ACCENT, alpha),
                        )
                glow = glow.filter(ImageFilter.GaussianBlur(radius=6))
                img = Image.alpha_composite(img, glow)
                draw = ImageDraw.Draw(img)

            # ── Status dot with enhanced visual effect ───────────────────────────────────────────
            dot_r = 4.0
            dot_pulse = 0.7 + 0.3 * abs(math.sin(self._phase * 2.0)) if is_recording else 1.0
            dr = int(dot_r * dot_pulse)
            if dr < 3:
                dr = 3
            cx, cy = 14, PILL_H // 2
            
            draw.ellipse(
                [cx - dr, cy - dr, cx + dr, cy + dr],
                fill=(*dot_color, int(255 * dot_pulse)),
            )
            
            outer_r = dr + 2
            draw.ellipse(
                [cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r],
                outline=(*dot_color, int(80 * dot_pulse)),
                width=1,
            )
            
            highlight_r = max(1, dr // 2)
            draw.ellipse(
                [cx - highlight_r, cy - highlight_r, cx + highlight_r, cy + highlight_r],
                fill=(255, 255, 255, int(100 * dot_pulse)),
            )

            # ── Smooth waveform bars (recording only) ───────────────────────
            if is_recording and self._amplitude > 0.01:
                total_w = BAR_COUNT * BAR_W + (BAR_COUNT - 1) * BAR_GAP
                sx = 24
                sy = PILL_H // 2
                
                for i in range(BAR_COUNT):
                    frac = 1.0 - abs(i - (BAR_COUNT - 1) / 2.0) / ((BAR_COUNT - 1) / 2.0)
                    wave = abs(math.sin(self._phase * 3.0 + i * 0.6))
                    bh = max(2.5, BAR_MAX_H * (0.3 + 0.7 * frac) * wave * self._amplitude)
                    bx = sx + i * (BAR_W + BAR_GAP)
                    by = sy - bh / 2
                    
                    alpha = int(255 * (0.5 + 0.5 * frac * self._amplitude))
                    
                    draw.rounded_rectangle(
                        [bx, by, bx + BAR_W, by + bh],
                        radius=BAR_W/2,
                        fill=(*ACCENT, alpha),
                    )
                    
                    if bh > 4:
                        highlight_h = max(1, int(bh * 0.3))
                        draw.rounded_rectangle(
                            [bx, by, bx + BAR_W, by + highlight_h],
                            radius=BAR_W/4,
                            fill=(255, 255, 255, int(alpha * 0.3)),
                        )
                
                text_x = sx + total_w + 8
            else:
                text_x = 24

            # ── Status text with better positioning ──────────────────────────────────────────
            text = self._status_text
            try:
                bbox = draw.textbbox((0, 0), text, font=self._font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            except Exception:
                text_w, text_h = 100, 16
            text_y = (PILL_H - text_h) // 2 - 1

            if text_x + text_w > PILL_W - 16:
                text_x = PILL_W - 16 - text_w
                if text_x < 24:
                    text_x = 24

            draw.text(
                (text_x + 1, text_y + 1),
                text,
                font=self._font,
                fill=(*TEXT, 80),
            )
            
            draw.text(
                (text_x, text_y),
                text,
                font=self._font,
                fill=TEXT,
            )

            # ── Display on canvas ───────────────────────────────────
            try:
                self._photo_img = ImageTk.PhotoImage(img)
            except Exception as e:
                logger.error(f"ImageTk.PhotoImage failed: {e}")
                rgb_img = img.convert("RGB")
                self._photo_img = ImageTk.PhotoImage(rgb_img)

            if self._canvas_img:
                self._canvas.delete(self._canvas_img)
            self._canvas_img = self._canvas.create_image(
                PILL_W // 2, PILL_H // 2,
                image=self._photo_img,
                anchor="center",
            )
        except Exception as e:
            logger.error(f"Overlay render error: {e}", exc_info=True)

    def _safe(self, fn):
        if not self._loop_running:
            # Tk isn't dispatching (still starting up, or the thread died). Dropping the
            # update is correct: after() would block this caller - often the hotkey
            # listener or the dictation worker - for a second and then fail anyway.
            logger.debug("Overlay not running; dropped UI update")
            return
        try:
            self._root.after(0, fn)
        except Exception as e:
            logger.debug(f"Overlay safe call failed: {e}")

    def destroy(self):
        """Tear down the Tk loop so the process can actually exit."""
        if not self._loop_running or not self._root:
            return
        try:
            self._root.after(0, self._root.quit)
        except Exception as e:
            logger.debug(f"Overlay destroy failed: {e}")

    @property
    def visible(self):
        return self._root is not None and self._fade_alpha > 0.0
