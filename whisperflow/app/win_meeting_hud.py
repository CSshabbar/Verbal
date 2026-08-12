"""Windows meeting HUD — tkinter + PIL sticker (same technique as
`win_overlay.py` / `win_autolearn_widget.py`).

Small floating pill shown during a call: red pulse dot · timer · mic
waveform · title · action buttons (star / pause / return). Uses
tkinter's `-transparentcolor` for true see-through around the pill
outline — no WebView2 canvas.

Public interface matches the Mac `MeetingHud`:
    show(), hide(), .visible,
    push(event, payload)   # 'state' | 'elapsed' | ...
Also `cleanup()` for shutdown parity.
"""

import logging
import math
import threading
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageTk

logger = logging.getLogger("verbal.meetinghud.win")

# ── Layout ──────────────────────────────────────────────────────────────
HUD_W = 380
HUD_H = 52
RADIUS = 18

# Colors match meeting_hud_html CSS.
BG_RGB     = (14, 16, 18)         # rgba(14,16,18,.9) as solid
TEXT_RGB   = (242, 242, 242)
MUT_RGB    = (200, 200, 200)
DOT_RGB    = (224, 80, 73)        # #E05049 recording indicator
ACC_RGB    = (200, 90, 62)        # star / accent
BORDER_RGB = (60, 55, 50)

CHROMA_TK = "#0a0a0a"

BAR_COUNT = 5
BAR_W     = 2.5
BAR_GAP   = 3.0
BAR_MAX_H = 20

_HUD_ACTIONS = {"hud_star", "hud_pause", "hud_return"}


class WinMeetingHud:
    def __init__(self, app):
        self.app = app
        self._root = None
        self._canvas = None
        self._photo = None
        self._font = None
        self._font_num = None

        self._visible = False
        self._alpha = 0.0
        self._phase = 0.0
        self._anim_timer = None

        # Live meeting state.
        self._elapsed_secs = 0
        self._mic_level = 0.0
        self._sys_level = 0.0
        self._paused = False
        self._title = "Meeting"

        # Hit rects — rebuilt each render.
        self._hits = []

    # ── setup ───────────────────────────────────────────────────────────
    def _setup(self):
        """Spin up the tk mainloop lazily so we don't cost startup time."""
        if self._root is not None:
            return
        t = threading.Thread(target=self._run_tk, name="hud-tk", daemon=True)
        t.start()
        # Wait briefly for _root to be ready so first show() doesn't race.
        for _ in range(50):
            if self._root is not None:
                return
            time.sleep(0.02)

    def _run_tk(self):
        try:
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.attributes("-alpha", 0.0)
            root.attributes("-transparentcolor", CHROMA_TK)
            root.configure(bg=CHROMA_TK)
            root.withdraw()

            screen_w = root.winfo_screenwidth()
            x = (screen_w - HUD_W) // 2
            y = 14   # top-center
            root.geometry(f"{HUD_W}x{HUD_H}+{x}+{y}")

            canvas = tk.Canvas(
                root, width=HUD_W, height=HUD_H,
                bg=CHROMA_TK, highlightthickness=0, borderwidth=0)
            canvas.pack()
            canvas.bind("<Button-1>", self._on_click)

            self._root = root
            self._canvas = canvas
            self._load_fonts()
            root.mainloop()
        except Exception as e:
            logger.error("HUD tk thread crashed: %s", e, exc_info=True)

    def _load_fonts(self):
        for face in ("segoeui.ttf", "arial.ttf"):
            try:
                self._font = ImageFont.truetype(face, 11)
                break
            except Exception:
                continue
        for face in ("Consola.ttf", "consola.ttf", "cour.ttf"):
            try:
                self._font_num = ImageFont.truetype(face, 12)
                break
            except Exception:
                continue
        if self._font is None:
            self._font = ImageFont.load_default()
        if self._font_num is None:
            self._font_num = self._font

    # ── public API ──────────────────────────────────────────────────────
    def show(self):
        try:
            if self._root is None:
                self._setup()
            self._safe(self._show_internal)
            self._push_state()
        except Exception as e:
            logger.debug("HUD show failed: %s", e)

    def hide(self):
        try:
            self.push("state", {"state": "hidden"})
        except Exception:
            pass
        self._safe(self._fade_out)

    @property
    def visible(self):
        return self._visible

    def push(self, event, payload=None):
        payload = payload or {}
        if event == "state":
            state = payload.get("state") or ""
            title = payload.get("title") or ""
            if state == "hidden":
                self._safe(self._fade_out)
                return
            self._paused = (state == "paused")
            if title:
                self._title = title
        elif event == "elapsed":
            try:
                self._elapsed_secs = int(payload.get("secs") or 0)
                self._mic_level = float(payload.get("mic") or 0.0)
                self._sys_level = float(payload.get("sys") or 0.0)
                self._paused = bool(payload.get("paused"))
            except Exception:
                pass
        # Any push while hidden should NOT surface the HUD — the caller
        # owns visibility.
        if self._visible:
            self._safe(self._render)

    def _push_state(self):
        try:
            s = self.app.meetings.active if getattr(self.app, "meetings", None) else None
            if s is not None:
                self.push("state", {"state": s.state, "title": s.title})
        except Exception:
            pass

    def cleanup(self):
        self.hide()

    # ── internals ───────────────────────────────────────────────────────
    def _safe(self, fn):
        if self._root is None:
            return
        try:
            self._root.after(0, fn)
        except Exception:
            pass

    def _show_internal(self):
        if self._root is None:
            return
        self._visible = True
        self._alpha = 0.0
        self._root.deiconify()
        self._fade_in()
        if self._anim_timer is None:
            self._start_animation_loop()

    def _fade_in(self):
        if self._root is None:
            return
        self._alpha = min(0.95, self._alpha + 0.08)
        self._root.attributes("-alpha", self._alpha)
        self._render()
        if self._alpha < 0.92:
            self._root.after(16, self._fade_in)

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
        self._root.after(16, self._fade_out)

    def _start_animation_loop(self):
        if not self._visible or self._root is None:
            self._anim_timer = None
            return
        self._phase += 0.09
        self._render()
        self._anim_timer = self._root.after(33, self._start_animation_loop)

    # ── rendering ───────────────────────────────────────────────────────
    def _render(self):
        if self._canvas is None:
            return
        try:
            img = Image.new("RGBA", (HUD_W, HUD_H), _hex_to_rgba(CHROMA_TK))
            draw = ImageDraw.Draw(img)

            # Pill background — dark rounded rect.
            draw.rounded_rectangle(
                (0, 0, HUD_W - 1, HUD_H - 1), radius=RADIUS,
                fill=BG_RGB + (230,), outline=BORDER_RGB + (140,), width=1)

            self._hits = []
            cy = HUD_H // 2
            x = 12

            # Red pulse dot (dim & steady when paused).
            r = 5
            if self._paused:
                dot_color = (200, 200, 200, 120)
            else:
                pulse = 0.6 + 0.4 * abs(math.sin(self._phase * 2.0))
                dot_color = DOT_RGB + (int(200 * pulse),)
            draw.ellipse((x, cy - r, x + 2 * r, cy + r), fill=dot_color)
            x += 2 * r + 8

            # Timer (M:SS).
            timer_text = f"{self._elapsed_secs // 60}:{self._elapsed_secs % 60:02d}"
            tw = _text_width(draw, timer_text, self._font_num)
            timer_color = MUT_RGB + (255,) if self._paused else TEXT_RGB + (255,)
            draw.text((x, cy - 7), timer_text,
                      fill=timer_color, font=self._font_num)
            x += tw + 10

            # Waveform bars.
            level = 0.0 if self._paused else max(self._mic_level, self._sys_level)
            for i in range(BAR_COUNT):
                frac = 1.0 - abs(i - (BAR_COUNT - 1) / 2.0) / ((BAR_COUNT - 1) / 2.0)
                wave = abs(math.sin(self._phase * 3.0 + i * 0.7))
                bh = max(3, BAR_MAX_H * (0.35 + 0.65 * frac) * (0.35 + 0.65 * level) * wave)
                bx = x + i * (BAR_W + BAR_GAP)
                draw.rounded_rectangle(
                    (bx, cy - bh / 2, bx + BAR_W, cy + bh / 2),
                    radius=BAR_W / 2,
                    fill=TEXT_RGB + (int(210 * (0.55 + 0.45 * frac)),))
            x += int(BAR_COUNT * (BAR_W + BAR_GAP)) + 12

            # Title — ellipsized to available room before the buttons.
            btn_r = 12
            btn_gap = 6
            buttons_w = 3 * (2 * btn_r) + 2 * btn_gap + 12
            title_max_w = HUD_W - x - buttons_w
            title = _fit_to_width(draw, self._title or "Meeting",
                                  self._font, title_max_w)
            draw.text((x, cy - 7), title,
                      fill=TEXT_RGB + (230,), font=self._font)

            # Right cluster: star / pause / return.
            rx = HUD_W - 10 - btn_r
            self._draw_hud_btn(draw, rx, cy, glyph="return")
            rx -= 2 * btn_r + btn_gap
            self._draw_hud_btn(draw, rx, cy,
                               glyph=("play" if self._paused else "pause"))
            rx -= 2 * btn_r + btn_gap
            self._draw_hud_btn(draw, rx, cy, glyph="star")

            # See win_autolearn_widget for why `master=self._canvas` matters.
            self._canvas.delete("all")
            self._photo = ImageTk.PhotoImage(img, master=self._canvas)
            self._canvas.create_image(0, 0, image=self._photo, anchor="nw")
        except Exception as e:
            logger.error("HUD render error: %s", e, exc_info=True)

    def _draw_hud_btn(self, draw, cx, cy, glyph):
        r = 12
        # Star sits in an accent-tinted circle; others muted.
        bg = (200, 90, 62, 60) if glyph == "star" else (240, 240, 240, 30)
        outline = (240, 240, 240, 60)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                     fill=bg, outline=outline, width=1)
        col = (240, 179, 154, 255) if glyph == "star" else TEXT_RGB + (230,)
        if glyph == "star":
            _draw_star(draw, cx, cy, 4.5, col)
            action = "hud_star"
        elif glyph == "pause":
            draw.rectangle((cx - 3, cy - 4, cx - 1, cy + 4), fill=col)
            draw.rectangle((cx + 1, cy - 4, cx + 3, cy + 4), fill=col)
            action = "hud_pause"
        elif glyph == "play":
            draw.polygon(
                [(cx - 3, cy - 5), (cx - 3, cy + 5), (cx + 4, cy)], fill=col)
            action = "hud_pause"
        elif glyph == "return":
            # Small maximize/return arrow icon (arrow into square).
            draw.rectangle((cx - 4, cy - 4, cx + 4, cy + 4),
                           outline=col, width=1)
            draw.line((cx - 1, cy + 1, cx + 3, cy - 3), fill=col, width=1)
            draw.polygon(
                [(cx + 3, cy - 3), (cx + 3, cy - 1), (cx + 1, cy - 3)],
                fill=col)
            action = "hud_return"
        else:
            action = None
        if action:
            self._hits.append((cx - r, cy - r, cx + r, cy + r, action))

    # ── clicks ──────────────────────────────────────────────────────────
    def _on_click(self, event):
        x, y = event.x, event.y
        for (x1, y1, x2, y2, action) in self._hits:
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._action(action)
                return

    def _action(self, name):
        if name not in _HUD_ACTIONS:
            return
        try:
            if name == "hud_star":
                m = getattr(self.app, "meetings", None)
                if m and m.active:
                    try: m.active.mark_moment("")
                    except Exception: pass
            elif name == "hud_pause":
                m = getattr(self.app, "meetings", None)
                if m and m.active:
                    try:
                        m.active.toggle_pause()
                        self._push_state()
                    except Exception: pass
            elif name == "hud_return":
                def go():
                    try:
                        win = self.app._meeting_win()
                        if win:
                            win.show("live")
                    except Exception:
                        pass
                self.app._on_main(go)
        except Exception as e:
            logger.error("hud action %s failed: %s", name, e)


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
    if max_w <= 0:
        return ""
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


def _draw_star(draw, cx, cy, r, color):
    """Small 5-point star. `r` is the outer radius."""
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=color)
