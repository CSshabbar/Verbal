"""Windows autolearn confirm-pill — tkinter + PIL sticker (same technique
as `win_overlay.py`).

WebView2 can't do per-pixel transparency reliably on Windows, so we drop
pywebview here and hand-render the cream pill with PIL onto a tkinter
window whose `-transparentcolor` chroma-key gives a real sticker look
(no surrounding dark rectangle).

Public interface matches the Mac `AutoLearnWidget`:
    setup(), show(old, new), hide(), .visible

Interaction is limited to two hit-boxes (Add / Dismiss) — clicks on the
canvas dispatch back into the app the same way the Mac widget does
(`app._autolearn_result(old, new, added)`)."""

import logging
import math
import threading
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageTk

logger = logging.getLogger("verbal.autolearn.widget.win")

# ── Layout ──────────────────────────────────────────────────────────────
PILL_W = 620
PILL_H = 72
RADIUS = 16
PANEL_W = PILL_W
PANEL_H = PILL_H

PAD_LEFT   = 16
PAD_RIGHT  = 10

# ── Colors (mirror autolearn_widget_html CSS vars) ──────────────────────
CREAM_RGB   = (234, 223, 206)    # --cream #EADFCE
INK_RGB     = (42, 31, 24)       # --ink   #2A1F18
INK_MUT_RGB = (110, 96, 82)      # muted ink
DARK_RGB    = (26, 21, 18)       # --dark  #1A1512 (Add button bg)
LINE_RGB    = (0, 0, 0, 36)      # subtle divider / stroke alpha

# tkinter -transparentcolor chroma. Near-black so anti-aliased pill edges
# blend to a soft dark halo instead of a bright fringe.
CHROMA_TK = "#0a0a0a"


class WinAutoLearnWidget:
    """Same public interface as the Mac widget. Runs its own tk mainloop
    on a daemon thread; every render happens via `.after(0, ...)`."""

    def __init__(self, app=None):
        self.app = app
        self._root = None
        self._canvas = None
        self._photo = None
        self._font_title = None
        self._font_pair = None
        self._font_btn = None

        self._old = ""
        self._new = ""
        self._visible = False
        self._alpha = 0.0
        self._dismiss_token = 0

        # Hit rects rebuilt per render: [(x1,y1,x2,y2,action), ...]
        self._hits = []
        self._fade_timer = None

    # ── setup ───────────────────────────────────────────────────────────
    def setup(self):
        t = threading.Thread(target=self._run_tk, name="autolearn-tk", daemon=True)
        t.start()

    def _run_tk(self):
        try:
            self._root = tk.Tk()
            self._root.overrideredirect(True)
            self._root.attributes("-topmost", True)
            self._root.attributes("-alpha", 0.0)
            self._root.attributes("-transparentcolor", CHROMA_TK)
            self._root.configure(bg=CHROMA_TK)
            self._root.withdraw()

            screen_w = self._root.winfo_screenwidth()
            screen_h = self._root.winfo_screenheight()
            x = (screen_w - PANEL_W) // 2
            y = screen_h - PANEL_H - 100
            self._root.geometry(f"{PANEL_W}x{PANEL_H}+{x}+{y}")

            self._canvas = tk.Canvas(
                self._root, width=PANEL_W, height=PANEL_H,
                bg=CHROMA_TK, highlightthickness=0, borderwidth=0)
            self._canvas.pack()
            self._canvas.bind("<Button-1>", self._on_click)

            self._load_fonts()
            self._root.mainloop()
        except Exception as e:
            logger.error("autolearn tk thread crashed: %s", e, exc_info=True)

    def _load_fonts(self):
        for face in ("segoeui.ttf", "arial.ttf"):
            try:
                self._font_title = ImageFont.truetype(face, 13)
                self._font_pair = ImageFont.truetype(face, 11)
                self._font_btn = ImageFont.truetype(face, 12)
                return
            except Exception:
                continue
        self._font_title = ImageFont.load_default()
        self._font_pair = ImageFont.load_default()
        self._font_btn = ImageFont.load_default()

    # ── public API (parity with AutoLearnWidget) ────────────────────────
    def show(self, old, new):
        self._old = str(old or "")
        self._new = str(new or "")
        self._safe(self._show_internal)
        # Auto-dismiss after 20s untouched, same as Mac.
        self._dismiss_token += 1
        token = self._dismiss_token

        def _auto():
            if self._dismiss_token != token or not self._visible:
                return
            self._action("autolearn_close")
        threading.Timer(20.0, _auto).start()

    def hide(self):
        self._dismiss_token += 1
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
            logger.debug("autolearn _safe failed: %s", e)

    def _show_internal(self):
        if self._root is None:
            return
        self._visible = True
        self._alpha = 0.0
        self._root.deiconify()
        self._fade_in()

    def _fade_in(self):
        if self._root is None:
            return
        self._alpha = min(0.98, self._alpha + 0.08)
        self._root.attributes("-alpha", self._alpha)
        self._render()
        if self._alpha < 0.95:
            self._fade_timer = self._root.after(16, self._fade_in)

    def _fade_out(self):
        if self._root is None:
            return
        self._alpha = max(0.0, self._alpha - 0.10)
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
        self._fade_timer = self._root.after(16, self._fade_out)

    # ── rendering ───────────────────────────────────────────────────────
    def _render(self):
        if self._canvas is None:
            return
        try:
            img = Image.new("RGBA", (PANEL_W, PANEL_H),
                            _hex_to_rgba(CHROMA_TK))
            draw = ImageDraw.Draw(img)

            # Cream pill background (rounded).
            draw.rounded_rectangle(
                (0, 0, PANEL_W - 1, PANEL_H - 1),
                radius=RADIUS,
                fill=CREAM_RGB + (255,))

            self._hits = []
            cy = PANEL_H // 2

            # Right cluster: X (dismiss) at far right, then Add button.
            # Draw right-to-left so the X hugs the edge.
            x_r = PANEL_W - PAD_RIGHT
            # X close button (28x28 with soft ink fill circle).
            x_r_size = 26
            x_left = x_r - x_r_size
            draw.ellipse(
                (x_left, cy - x_r_size // 2,
                 x_left + x_r_size, cy + x_r_size // 2),
                fill=(0, 0, 0, 24))
            k = 5
            cx = x_left + x_r_size // 2
            draw.line((cx - k, cy - k, cx + k, cy + k),
                      fill=INK_RGB + (220,), width=2)
            draw.line((cx - k, cy + k, cx + k, cy - k),
                      fill=INK_RGB + (220,), width=2)
            self._hits.append((x_left, cy - x_r_size // 2,
                               x_left + x_r_size, cy + x_r_size // 2,
                               "autolearn_close"))
            x_r = x_left - 8

            # Add button — dark rounded rect with cream label.
            btn_label = "Add to dictionary"
            btn_w = _text_width(draw, btn_label, self._font_btn) + 28
            btn_h = 34
            btn_left = x_r - btn_w
            btn_top = cy - btn_h // 2
            draw.rounded_rectangle(
                (btn_left, btn_top, btn_left + btn_w, btn_top + btn_h),
                radius=11, fill=DARK_RGB + (255,))
            tw = _text_width(draw, btn_label, self._font_btn)
            draw.text(
                (btn_left + (btn_w - tw) // 2, btn_top + 9),
                btn_label, fill=CREAM_RGB + (255,), font=self._font_btn)
            self._hits.append((btn_left, btn_top,
                               btn_left + btn_w, btn_top + btn_h,
                               "autolearn_add"))
            content_right = btn_left - 12

            # Left side: two-line text stack. Title + pair.
            new_word_disp = f"“{self._new}”"
            old_word_disp = f"“{self._old}”"

            title_prefix = "Add "
            title_suffix = " to your dictionary?"
            # Line 1 pieces so the quoted word renders bold-ish (we fake
            # emphasis via colored contrast).
            _title_max_w = content_right - PAD_LEFT
            title_y = cy - 18
            x_run = PAD_LEFT
            draw.text((x_run, title_y), title_prefix,
                      fill=INK_MUT_RGB + (255,), font=self._font_title)
            x_run += _text_width(draw, title_prefix, self._font_title)
            draw.text((x_run, title_y), new_word_disp,
                      fill=INK_RGB + (255,), font=self._font_title)
            x_run += _text_width(draw, new_word_disp, self._font_title)
            # Suffix; ellipsize if it overflows.
            _suffix = _fit_to_width(draw, title_suffix, self._font_title,
                                    _title_max_w - (x_run - PAD_LEFT))
            draw.text((x_run, title_y), _suffix,
                      fill=INK_MUT_RGB + (255,), font=self._font_title)

            # Line 2 — "Replaces <old> when misheard".
            pair_y = cy + 3
            replaces = "Replaces "
            when = " when misheard"
            x_run = PAD_LEFT
            draw.text((x_run, pair_y), replaces,
                      fill=INK_MUT_RGB + (200,), font=self._font_pair)
            x_run += _text_width(draw, replaces, self._font_pair)
            _old_shown = _fit_to_width(draw, old_word_disp, self._font_pair,
                                       _title_max_w - (x_run - PAD_LEFT) - 90)
            draw.text((x_run, pair_y), _old_shown,
                      fill=INK_RGB + (230,), font=self._font_pair)
            x_run += _text_width(draw, _old_shown, self._font_pair)
            draw.text((x_run, pair_y), when,
                      fill=INK_MUT_RGB + (200,), font=self._font_pair)

            # Blit to tk. `master=self._canvas` is critical — with multiple
            # tk.Tk() roots in the app (overlay / autolearn / HUD / transform
            # each own one), ImageTk defaults to the wrong root and Tcl loses
            # track of the image handle ("pyimage### doesn't exist").
            self._canvas.delete("all")
            self._photo = ImageTk.PhotoImage(img, master=self._canvas)
            self._canvas.create_image(0, 0, image=self._photo, anchor="nw")
        except Exception as e:
            logger.error("autolearn render error: %s", e, exc_info=True)

    # ── clicks ──────────────────────────────────────────────────────────
    def _on_click(self, event):
        x, y = event.x, event.y
        for (x1, y1, x2, y2, action) in self._hits:
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._action(action)
                return

    def _action(self, name):
        try:
            old, new = self._old, self._new
            self.hide()
            if self.app is not None and hasattr(self.app, "_autolearn_result"):
                added = (name == "autolearn_add")
                self.app._on_main(
                    lambda: self.app._autolearn_result(old, new, added))
        except Exception as e:
            logger.error("autolearn action %s failed: %s", name, e)


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


def _fit_to_width(draw, text, font, max_w):
    if _text_width(draw, text, font) <= max_w:
        return text
    ell = "…"
    lo, hi = 0, len(text)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = text[:mid].rstrip() + ell
        if _text_width(draw, cand, font) <= max_w:
            best = cand
            lo = mid + 1
        else:
            hi = mid - 1
    return best or ell
