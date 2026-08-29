"""Windows meeting-detected pill — tkinter + PIL sticker (same technique
as `win_overlay.py` / `win_autolearn_widget.py`).

WebView2 can't do per-pixel transparency on Windows, so the Mac
`meeting_prompt.py` NSPanel+WKWebView recipe is not used here. Public
interface matches the Mac widget:

    setup(), show(source), hide(), .visible

Clicks dispatch `app._meeting_detect_result(True/False)` the same way
the Mac pill posts `md_take` / `md_dismiss`.
"""
import ctypes
import logging
import threading
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageTk

from app.tk_pending import PendingCalls

logger = logging.getLogger("verbal.meeting_prompt.win")

SCALE = 1.0

_DESIGN = {
    "PILL_W": 520, "PILL_H": 72, "RADIUS": 16,
    "PAD_LEFT": 14, "PAD_RIGHT": 10,
    "F_TITLE": 13, "F_SUB": 11, "F_BTN": 12,
}


def _i(v):
    return max(1, int(round(v * SCALE)))


def _apply_scale(scale):
    global SCALE, PILL_W, PILL_H, RADIUS, PANEL_W, PANEL_H
    global PAD_LEFT, PAD_RIGHT, F_TITLE, F_SUB, F_BTN
    SCALE = scale
    d = _DESIGN
    PILL_W = int(round(d["PILL_W"] * scale))
    PILL_H = int(round(d["PILL_H"] * scale))
    RADIUS = int(round(d["RADIUS"] * scale))
    PANEL_W = PILL_W
    PANEL_H = PILL_H
    PAD_LEFT = int(round(d["PAD_LEFT"] * scale))
    PAD_RIGHT = int(round(d["PAD_RIGHT"] * scale))
    F_TITLE = max(1, int(round(d["F_TITLE"] * scale)))
    F_SUB = max(1, int(round(d["F_SUB"] * scale)))
    F_BTN = max(1, int(round(d["F_BTN"] * scale)))


_apply_scale(1.0)

# Near-black Flume pill (meeting_prompt.py CSS: --bg #1b1714, --tx #F5EDE4,
# --sage #A8BD9A, --sage-ink #16201a).
PANEL_RGB = (27, 23, 20)
TX_RGB = (245, 237, 228)
MUT_RGB = (140, 134, 128)
SAGE_RGB = (168, 189, 154)
SAGE_INK_RGB = (22, 32, 26)
MARK_RGB = (50, 50, 41)
X_FILL = (245, 237, 228, 18)

CHROMA_TK = "#0a0a0a"


class WinMeetingPrompt:
    """Same public interface as Mac `MeetingPrompt`. Own tk mainloop."""

    def __init__(self, app=None):
        self.app = app
        self._root = None
        self._canvas = None
        self._photo = None
        self._font_title = None
        self._font_sub = None
        self._font_btn = None

        self._source = ""
        self._visible = False
        self._alpha = 0.0
        self._hits = []
        self._fade_timer = None
        self._pending = PendingCalls(name="meeting-prompt")
        self._setup_started = False

    def setup(self):
        if self._setup_started:
            return
        self._setup_started = True
        t = threading.Thread(target=self._run_tk, name="meeting-prompt-tk",
                             daemon=True)
        t.start()

    def _run_tk(self):
        try:
            try:
                from app.win_dpi import widget_scale
                _apply_scale(widget_scale())
                logger.info("meeting prompt: scale=%.2f -> %dx%d",
                            SCALE, PANEL_W, PANEL_H)
            except Exception as e:
                logger.debug("meeting prompt dpi scale skipped: %s", e)
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
            y = screen_h - PANEL_H - 48
            self._root.geometry(f"{PANEL_W}x{PANEL_H}+{x}+{y}")

            self._canvas = tk.Canvas(
                self._root, width=PANEL_W, height=PANEL_H,
                bg=CHROMA_TK, highlightthickness=0, borderwidth=0)
            self._canvas.pack()
            self._canvas.bind("<Button-1>", self._on_click)

            self._load_fonts()
            self._noactivate()
            self._root.after(0, self._replay_pending)
            self._root.mainloop()
        except Exception as e:
            logger.error("meeting prompt tk thread crashed: %s", e, exc_info=True)
        finally:
            self._pending.close()

    def _replay_pending(self):
        try:
            self._pending.mark_ready(lambda fn: fn())
        except Exception as e:
            logger.debug("meeting prompt pending replay failed: %s", e)

    def _tk_ready(self):
        return self._root is not None and self._pending.ready

    def _noactivate(self):
        """Don't steal focus from Zoom/Meet (Mac NSPanel non-activating).

        `winfo_id()` is the Tk wrapper HWND, not the toplevel — apply the
        style to `GetAncestor(..., GA_ROOT)` or ShowWindow would still activate.
        """
        try:
            hwnd = int(self._root.winfo_id())
            GA_ROOT = 2
            user32 = ctypes.windll.user32
            root = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            style = user32.GetWindowLongW(root, GWL_EXSTYLE)
            user32.SetWindowLongW(root, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)
        except Exception:
            pass

    def cleanup(self):
        self._pending.close()
        root = self._root
        if root is None:
            return
        try:
            root.after(0, root.quit)
        except Exception as e:
            logger.debug("meeting prompt cleanup failed: %s", e)

    def _load_fonts(self):
        for face in ("segoeui.ttf", "arial.ttf"):
            try:
                self._font_title = ImageFont.truetype(face, F_TITLE)
                self._font_sub = ImageFont.truetype(face, F_SUB)
                self._font_btn = ImageFont.truetype(face, F_BTN)
                return
            except Exception:
                continue
        self._font_title = ImageFont.load_default()
        self._font_sub = ImageFont.load_default()
        self._font_btn = ImageFont.load_default()

    def show(self, source):
        self._source = str(source or "")
        self._safe(self._show_internal)

    def hide(self):
        self._safe(self._cancel_fade)
        self._safe(self._fade_out)

    @property
    def visible(self):
        return self._visible

    def _safe(self, fn):
        def _post(f):
            self._root.after(0, f)
        try:
            self._pending.dispatch(fn, _post)
        except Exception as e:
            logger.debug("meeting prompt _safe failed: %s", e)

    def _cancel_fade(self):
        t = getattr(self, "_fade_timer", None)
        if t is not None and self._tk_ready():
            try:
                self._root.after_cancel(t)
            except Exception:
                pass
        self._fade_timer = None

    def _show_internal(self):
        if not self._tk_ready():
            return
        self._cancel_fade()
        self._visible = True
        self._alpha = 0.0
        self._noactivate()
        self._root.deiconify()
        self._noactivate()
        self._fade_in()

    def _fade_in(self):
        if not self._tk_ready():
            return
        self._alpha = min(0.98, self._alpha + 0.08)
        self._root.attributes("-alpha", self._alpha)
        self._render()
        if self._alpha < 0.95:
            self._fade_timer = self._root.after(16, self._fade_in)

    def _fade_out(self):
        if not self._tk_ready():
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

    def _render(self):
        if self._canvas is None:
            return
        try:
            img = Image.new("RGBA", (PANEL_W, PANEL_H),
                            _hex_to_rgba(CHROMA_TK))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle(
                (0, 0, PANEL_W - 1, PANEL_H - 1),
                radius=RADIUS, fill=PANEL_RGB + (255,))

            self._hits = []
            cy = PANEL_H // 2

            x_r = PANEL_W - PAD_RIGHT
            x_size = _i(26)
            x_left = x_r - x_size
            draw.ellipse(
                (x_left, cy - x_size // 2,
                 x_left + x_size, cy + x_size // 2),
                fill=X_FILL)
            k = _i(5)
            cx = x_left + x_size // 2
            draw.line((cx - k, cy - k, cx + k, cy + k),
                      fill=TX_RGB + (220,), width=_i(2))
            draw.line((cx - k, cy + k, cx + k, cy - k),
                      fill=TX_RGB + (220,), width=_i(2))
            self._hits.append((x_left, cy - x_size // 2,
                               x_left + x_size, cy + x_size // 2,
                               "md_dismiss"))
            x_r = x_left - _i(8)

            btn_label = "Take notes"
            btn_w = _text_width(draw, btn_label, self._font_btn) + _i(32)
            btn_h = _i(34)
            btn_left = x_r - btn_w
            btn_top = cy - btn_h // 2
            draw.rounded_rectangle(
                (btn_left, btn_top, btn_left + btn_w, btn_top + btn_h),
                radius=_i(11), fill=SAGE_RGB + (255,))
            tw = _text_width(draw, btn_label, self._font_btn)
            draw.text(
                (btn_left + (btn_w - tw) // 2, btn_top + _i(9)),
                btn_label, fill=SAGE_INK_RGB + (255,), font=self._font_btn)
            self._hits.append((btn_left, btn_top,
                               btn_left + btn_w, btn_top + btn_h,
                               "md_take"))
            content_right = btn_left - _i(12)

            mark = _i(34)
            mark_left = PAD_LEFT
            mark_top = cy - mark // 2
            draw.rounded_rectangle(
                (mark_left, mark_top, mark_left + mark, mark_top + mark),
                radius=_i(10), fill=MARK_RGB + (255,))
            mx = mark_left + mark // 2
            my = mark_top + mark // 2
            # Tiny mic glyph — body + stand.
            bw, bh = _i(6), _i(10)
            draw.rounded_rectangle(
                (mx - bw // 2, my - _i(8), mx + bw // 2, my + _i(2)),
                radius=_i(3), outline=SAGE_RGB + (255,), width=_i(2))
            draw.arc(
                (mx - _i(8), my - _i(4), mx + _i(8), my + _i(10)),
                start=0, end=180, fill=SAGE_RGB + (255,), width=_i(2))
            draw.line((mx, my + _i(10), mx, my + _i(13)),
                      fill=SAGE_RGB + (255,), width=_i(2))

            text_left = mark_left + mark + _i(10)
            max_w = content_right - text_left
            title_y = cy - _i(16)
            draw.text((text_left, title_y), "Meeting detected",
                      fill=TX_RGB + (255,), font=self._font_title)
            sub = ("In " + self._source) if self._source else "Ready to capture"
            sub = _fit_to_width(draw, sub, self._font_sub, max_w)
            draw.text((text_left, cy + _i(4)), sub,
                      fill=MUT_RGB + (255,), font=self._font_sub)

            self._canvas.delete("all")
            self._photo = ImageTk.PhotoImage(img, master=self._canvas)
            self._canvas.create_image(0, 0, image=self._photo, anchor="nw")
        except Exception as e:
            logger.error("meeting prompt render error: %s", e, exc_info=True)

    def _on_click(self, event):
        x, y = event.x, event.y
        for (x1, y1, x2, y2, action) in self._hits:
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._action(action)
                return

    def _action(self, name):
        try:
            self.hide()
            take = name == "md_take"
            if self.app is not None and hasattr(self.app, "_meeting_detect_result"):
                self.app._on_main(
                    lambda: self.app._meeting_detect_result(take))
        except Exception as e:
            logger.error("meeting prompt action %s failed: %s", name, e)


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
