"""Windows status overlay — modern floating pill with animations."""

import logging
import math
import tkinter as tk
import threading
import time

logger = logging.getLogger("verbal.overlay")

# Brand colors
BG       = "#1A1917"
BG_RGBA  = (26, 25, 23)
TEXT     = "#F2EFE9"
ACCENT   = "#E05A2B"
BLUE     = "#4A90E2"
GREEN    = "#4CAF7D"
MUTED    = "#7A7570"
WHITE    = "#FFFFFF"

PILL_W = 260
PILL_H = 52
RADIUS = 26

BAR_COUNT = 12
BAR_W = 3
BAR_GAP = 3
BAR_MAX_H = 28


class WinOverlay:
    def __init__(self):
        self._root = None
        self._canvas = None
        self._status_text = ""
        self._phase = 0.0
        self._amplitude = 0.0
        self._active = False
        self._fade_alpha = 0.0
        self._timer = None
        self._fade_timer = None
        self._show_time = 0

    def setup(self):
        t = threading.Thread(target=self._run_tk, daemon=True)
        t.start()

    def _run_tk(self):
        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.0)
        self._root.withdraw()

        screen_w = self._root.winfo_screenwidth()
        x = (screen_w - PILL_W) // 2
        y = 80
        self._root.geometry(f"{PILL_W}x{PILL_H}+{x}+{y}")
        self._root.configure(bg=BG)

        self._canvas = tk.Canvas(
            self._root,
            width=PILL_W,
            height=PILL_H,
            bg=BG,
            highlightthickness=0,
        )
        self._canvas.pack()

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
            self._fade_alpha += 0.08
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
            self._fade_alpha -= 0.08
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
            if not self._active:
                self._amplitude = max(0.0, self._amplitude - 0.05)
            self._render()
            self._fade_timer = self._root.after(50, self._start_animation_loop)

    def _render(self):
        if not self._canvas or not self._root:
            return

        c = self._canvas
        c.delete("all")

        is_recording = self._active and ("Listen" in self._status_text or "Record" in self._status_text)
        is_processing = self._active and "Transcrib" in self._status_text
        is_success = any(w in self._status_text for w in ("Done", "Pasted", "Copied", "clipboard"))

        dot_color = ACCENT if is_recording else (BLUE if is_processing else (GREEN if is_success else MUTED))

        # Draw pill background
        self._draw_rounded_rect(c, 0, 0, PILL_W, PILL_H, RADIUS, BG)

        # Draw subtle inner border
        self._draw_rounded_rect_outline(c, 0.5, 0.5, PILL_W-1, PILL_H-1, RADIUS, "#2A2825", 1.0)

        # Glow effect behind dot
        if is_recording and self._amplitude > 0.01:
            glow_r = 8 + 4 * self._amplitude * abs(math.sin(self._phase * 2.0))
            cx = 26
            cy = PILL_H // 2
            for i in range(3):
                r = glow_r - i * 2
                alpha = 0.15 - i * 0.04
                color = self._fade_color(ACCENT, alpha)
                c.create_oval(cx-r, cy-r, cx+r, cy+r, fill=color, outline="")

        # Status dot
        dot_r = 5
        dot_pulse = 0.7 + 0.3 * abs(math.sin(self._phase * 2.0)) if is_recording else 1.0
        dot_color_faded = self._fade_color(dot_color, dot_pulse)
        c.create_oval(26-dot_r, PILL_H//2-dot_r, 26+dot_r, PILL_H//2+dot_r, fill=dot_color_faded, outline="")

        # Waveform bars (recording only)
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
                alpha = 0.5 + 0.4 * frac * self._amplitude
                color = self._fade_color(ACCENT, alpha)
                c.create_oval(bx, by, bx + BAR_W, by + bh, fill=color, outline="")

        # Status text
        text_x = 48 + (BAR_COUNT * BAR_W + (BAR_COUNT - 1) * BAR_GAP + 10) if is_recording else 48
        text_x = min(text_x, PILL_W - 10)

        c.create_text(
            text_x,
            PILL_H // 2 + 1,
            text=self._status_text,
            fill=TEXT,
            font=("Segoe UI Variable", 12, "normal"),
            anchor="w",
        )

    def _draw_rounded_rect(self, canvas, x, y, w, h, r, fill):
        """Draw a rounded rectangle on canvas."""
        canvas.create_oval(x, y, x + r*2, y + r*2, fill=fill, outline="")
        canvas.create_oval(x + w - r*2, y, x + w, y + r*2, fill=fill, outline="")
        canvas.create_oval(x, y + h - r*2, x + r*2, y + h, fill=fill, outline="")
        canvas.create_oval(x + w - r*2, y + h - r*2, x + w, y + h, fill=fill, outline="")
        canvas.create_rectangle(x + r, y, x + w - r, y + h, fill=fill, outline="")
        canvas.create_rectangle(x, y + r, x + w, y + h - r, fill=fill, outline="")

    def _draw_rounded_rect_outline(self, canvas, x, y, w, h, r, color, width):
        """Draw a rounded rectangle outline."""
        canvas.create_arc(x, y, x + r*2, y + r*2, start=90, extent=90, style="arc", outline=color, width=width)
        canvas.create_arc(x + w - r*2, y, x + w, y + r*2, start=0, extent=90, style="arc", outline=color, width=width)
        canvas.create_arc(x, y + h - r*2, x + r*2, y + h, start=180, extent=90, style="arc", outline=color, width=width)
        canvas.create_arc(x + w - r*2, y + h - r*2, x + w, y + h, start=270, extent=90, style="arc", outline=color, width=width)
        canvas.create_line(x + r, y, x + w - r, y, fill=color, width=width)
        canvas.create_line(x + r, y + h, x + w - r, y + h, fill=color, width=width)
        canvas.create_line(x, y + r, x, y + h - r, fill=color, width=width)
        canvas.create_line(x + w, y + r, x + w, y + h - r, fill=color, width=width)

    def _fade_color(self, hex_color, alpha):
        """Convert hex color to RGB with alpha for tkinter."""
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        # Blend with background
        bg_r, bg_g, bg_b = BG_RGBA
        r = int(bg_r + (r - bg_r) * alpha)
        g = int(bg_g + (g - bg_g) * alpha)
        b = int(bg_b + (b - bg_b) * alpha)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _safe(self, fn):
        if self._root:
            try:
                self._root.after(0, fn)
            except Exception:
                pass

    @property
    def visible(self):
        return self._root is not None and self._fade_alpha > 0.0
