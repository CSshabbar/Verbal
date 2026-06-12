"""Windows status overlay — modern floating pill rendered with PIL for smooth design."""

import logging
import math
import tkinter as tk
import threading
import time
from PIL import Image, ImageDraw, ImageTk, ImageFont, ImageFilter

logger = logging.getLogger("verbal.overlay")

# ── Brand colors ──────────────────────────────────────────────────────
BG        = (26, 25, 23)
BG_HEX    = "#1A1917"
TEXT      = (242, 239, 233)
TEXT_HEX  = "#F2EFE9"
ACCENT    = (224, 90, 43)
ACCENT_HEX = "#E05A2B"
BLUE      = (74, 144, 226)
GREEN     = (76, 175, 125)
MUTED     = (122, 117, 112)
BORDER    = (42, 40, 37)
SHADOW    = (0, 0, 0, 80)

# ── Layout ────────────────────────────────────────────────────────────
PILL_W    = 280
PILL_H    = 52
RADIUS    = 26
SHADOW_BLUR = 12
SHADOW_OFFSET = 4
CANVAS_W  = PILL_W + SHADOW_BLUR * 4
CANVAS_H  = PILL_H + SHADOW_BLUR * 4
BAR_COUNT = 12
BAR_W     = 3
BAR_GAP   = 3
BAR_MAX_H = 24


class WinOverlay:
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
        self._timer      = None
        self._fade_timer = None
        self._show_time  = 0
        self._font       = None

    def setup(self):
        t = threading.Thread(target=self._run_tk, daemon=True)
        t.start()

    def _run_tk(self):
        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.0)
        self._root.withdraw()
        self._root.configure(bg="black")

        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        x = (screen_w - PILL_W) // 2
        y = screen_h - PILL_H - 80
        self._root.geometry(f"{PILL_W}x{PILL_H}+{x}+{y}")

        self._canvas = tk.Canvas(
            self._root,
            width=PILL_W,
            height=PILL_H,
            bg="black",
            highlightthickness=0,
        )
        self._canvas.pack()

        # Try to load a nice font, fallback to default
        try:
            self._font = ImageFont.truetype("segoeui.ttf", 13)
        except Exception:
            try:
                self._font = ImageFont.truetype("arial.ttf", 13)
            except Exception:
                self._font = ImageFont.load_default()

        self._root.mainloop()

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

    def _schedule_hide(self, duration):
        if self._timer:
            self._root.after_cancel(self._timer)
        self._timer = self._root.after(int(duration * 1000), self._fade_out)

    def _fade_in(self):
        self._fade_alpha = 0.0
        self._root.deiconify()
        self._root.lift()
        self._animate_fade_in()

    def _animate_fade_in(self):
        if self._fade_alpha < 0.95:
            self._fade_alpha += 0.10
            self._root.attributes("-alpha", min(self._fade_alpha, 0.95))
            self._render()
            self._fade_timer = self._root.after(16, self._animate_fade_in)
        else:
            self._root.attributes("-alpha", 0.95)
            self._render()
            self._start_animation_loop()

    def _fade_out(self):
        if self._fade_timer:
            self._root.after_cancel(self._fade_timer)
        self._animate_fade_out()

    def _animate_fade_out(self):
        if self._fade_alpha > 0.0:
            self._fade_alpha -= 0.10
            if self._fade_alpha > 0:
                self._root.attributes("-alpha", self._fade_alpha)
                self._render()
                self._fade_timer = self._root.after(16, self._animate_fade_out)
            else:
                self._root.attributes("-alpha", 0.0)
                self._root.withdraw()
                self._active = False
                self._amplitude = 0.0
        else:
            self._root.withdraw()
            self._active = False

    def _show_internal(self):
        if not self._root:
            return
        self._fade_in()

    def _update_internal(self):
        if not self._canvas:
            return
        self._render()

    def _start_animation_loop(self):
        if self._active and self._root:
            self._phase += 0.12
            self._render()
            self._fade_timer = self._root.after(50, self._start_animation_loop)

    def _render(self):
        if not self._canvas or not self._root:
            return

        is_recording  = self._active and ("Listen" in self._status_text or "Record" in self._status_text)
        is_processing = self._active and "Transcrib" in self._status_text
        is_success    = any(w in self._status_text for w in ("Done", "Pasted", "Copied", "clipboard"))

        dot_color = ACCENT if is_recording else (BLUE if is_processing else (GREEN if is_success else MUTED))

        # Create transparent image for the pill
        img = Image.new("RGBA", (PILL_W, PILL_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # ── Shadow ────────────────────────────────────────────────────
        shadow = Image.new("RGBA", (PILL_W, PILL_H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.rounded_rectangle(
            [SHADOW_OFFSET, SHADOW_OFFSET, PILL_W - SHADOW_OFFSET + 2, PILL_H - SHADOW_OFFSET + 2],
            radius=RADIUS,
            fill=(0, 0, 0, 60),
        )
        # Blur the shadow
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=SHADOW_BLUR))
        # Paste shadow first
        img = Image.alpha_composite(img, shadow)
        draw = ImageDraw.Draw(img)

        # ── Pill background ───────────────────────────────────────────
        draw.rounded_rectangle(
            [0, 0, PILL_W - 1, PILL_H - 1],
            radius=RADIUS,
            fill=BG,
            outline=BORDER,
            width=1,
        )

        # ── Glow behind dot ────────────────────────────────────────────
        if is_recording and self._amplitude > 0.01:
            glow_r = 12 + 6 * self._amplitude * abs(math.sin(self._phase * 2.0))
            cx, cy = 26, PILL_H // 2
            glow = Image.new("RGBA", (PILL_W, PILL_H), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow)
            for i in range(3):
                r = glow_r - i * 3
                alpha = 25 - i * 8
                if r > 0 and alpha > 0:
                    gd.ellipse(
                        [cx - r, cy - r, cx + r, cy + r],
                        fill=(*ACCENT, alpha),
                    )
            glow = glow.filter(ImageFilter.GaussianBlur(radius=4))
            img = Image.alpha_composite(img, glow)
            draw = ImageDraw.Draw(img)

        # ── Status dot ─────────────────────────────────────────────────
        dot_r = 5
        dot_pulse = 0.7 + 0.3 * abs(math.sin(self._phase * 2.0)) if is_recording else 1.0
        dr = int(dot_r * dot_pulse)
        if dr < 2:
            dr = 2
        cx, cy = 26, PILL_H // 2
        draw.ellipse(
            [cx - dr, cy - dr, cx + dr, cy + dr],
            fill=(*dot_color, int(255 * dot_pulse)),
        )
        # Dot border
        draw.ellipse(
            [cx - dr - 1, cy - dr - 1, cx + dr + 1, cy + dr + 1],
            outline=(*dot_color, 80),
            width=1,
        )

        # ── Waveform bars (recording only) ─────────────────────────────
        if is_recording and self._amplitude > 0.01:
            total_w = BAR_COUNT * BAR_W + (BAR_COUNT - 1) * BAR_GAP
            sx = 48
            sy = PILL_H // 2
            for i in range(BAR_COUNT):
                frac = 1.0 - abs(i - (BAR_COUNT - 1) / 2.0) / ((BAR_COUNT - 1) / 2.0)
                wave = abs(math.sin(self._phase * 3.0 + i * 0.6))
                bh = max(3, BAR_MAX_H * (0.3 + 0.7 * frac) * wave * self._amplitude)
                bx = sx + i * (BAR_W + BAR_GAP)
                by = sy - bh / 2
                alpha = int(255 * (0.5 + 0.4 * frac * self._amplitude))
                draw.rounded_rectangle(
                    [bx, by, bx + BAR_W, by + bh],
                    radius=BAR_W // 2,
                    fill=(*ACCENT, alpha),
                )
            text_x = sx + total_w + 14
        else:
            text_x = 48

        # ── Status text ──────────────────────────────────────────────
        text = self._status_text
        bbox = draw.textbbox((0, 0), text, font=self._font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_y = (PILL_H - text_h) // 2 - 1

        # Ensure text fits
        if text_x + text_w > PILL_W - 14:
            text_x = PILL_W - 14 - text_w
            if text_x < 48:
                text_x = 48

        draw.text(
            (text_x, text_y),
            text,
            font=self._font,
            fill=TEXT,
        )

        # Convert to PhotoImage and display
        self._photo_img = ImageTk.PhotoImage(img)
        if self._canvas_img:
            self._canvas.delete(self._canvas_img)
        self._canvas_img = self._canvas.create_image(
            PILL_W // 2, PILL_H // 2,
            image=self._photo_img,
            anchor="center",
        )

    def _safe(self, fn):
        if self._root:
            try:
                self._root.after(0, fn)
            except Exception:
                pass

    @property
    def visible(self):
        return self._root is not None and self._fade_alpha > 0.0
