"""Windows Transform selection pill — tkinter + PIL, styled to match the
Mac design in `transform_widget_html.py`.

Everything except the two text-bearing controls (instruction Entry,
preview Text) is PIL-rendered onto a canvas with click hit-boxes, so no
OS button chrome leaks in. The window IS the pill: `-transparentcolor`
chroma + a rounded PIL background give a true floating sticker with no
surrounding rectangle (WebView2 could not do this — see win_overlay.py).

States, mirroring the Mac widget:

    prompt    eyebrow · excerpt · chars · ×
              [Improvise] (mic) [ instruction input ] [Go]
              hint / error
    listening same as prompt, mic filled + live ●REC timer
    busy      spinner + label
    preview   PREVIEW eyebrow · rewrite box · [Replace] [Cancel]
    done      REPLACED · [Undo]

Bridge-action names match the Mac widget so wiring stays consistent.
Fail-closed throughout; Esc closes.
"""

import logging
import math
import threading
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageTk

logger = logging.getLogger("verbal.transform.widget.win")

# ── Geometry + DPI scaling (the pill IS the window) ─────────────────────
# Every number below is a 96-DPI DESIGN value. The process is DPI-aware (see
# win_dpi), so tkinter/PIL work in real device pixels — drawing these raw made
# the pill render at 59% on the 200% test VM. `_apply_scale()` restates them
# once the monitor's scale is known; every inline offset in the drawing code
# goes through `_i()`/`_s()` for the same reason.
SCALE = 1.0

_DESIGN = {
    "PANEL_W": 660, "RADIUS": 16, "PAD": 18,
    "H_PROMPT": 132, "H_BUSY": 68, "H_PREVIEW": 244, "H_DONE": 64,
    "BOTTOM_MARGIN": 80,
    "ROW_Y": 56,      # control row top
    "ROW_H": 34,
    "MIC_D": 34,      # mic diameter
    # PIL font sizes, and the tk Entry/Text sizes in PIXELS (a negative tk font
    # size means pixels — points would be re-scaled by tk's own 96-DPI factor
    # and come out too small on a scaled monitor).
    "F_EYEBROW": 10, "F_BODY": 12, "F_SMALL": 11, "F_BTN": 12,
    "TK_PX": 13,
}


def _s(v):
    """Scale a 96-DPI design length to device pixels (float)."""
    return v * SCALE


def _i(v):
    """Scale a 96-DPI offset / stroke width to whole device pixels."""
    return max(1, int(round(v * SCALE)))


def _apply_scale(scale):
    """Restate every layout constant in device pixels for `scale`."""
    global SCALE, PANEL_W, RADIUS, PAD, H_PROMPT, H_BUSY, H_PREVIEW, H_DONE
    global BOTTOM_MARGIN, ROW_Y, ROW_H, MIC_D
    global F_EYEBROW, F_BODY, F_SMALL, F_BTN, TK_PX
    SCALE = scale
    d = _DESIGN
    PANEL_W = int(round(d["PANEL_W"] * scale))
    RADIUS = int(round(d["RADIUS"] * scale))
    PAD = int(round(d["PAD"] * scale))
    H_PROMPT = int(round(d["H_PROMPT"] * scale))
    H_BUSY = int(round(d["H_BUSY"] * scale))
    H_PREVIEW = int(round(d["H_PREVIEW"] * scale))
    H_DONE = int(round(d["H_DONE"] * scale))
    BOTTOM_MARGIN = int(round(d["BOTTOM_MARGIN"] * scale))
    ROW_Y = int(round(d["ROW_Y"] * scale))
    ROW_H = int(round(d["ROW_H"] * scale))
    MIC_D = int(round(d["MIC_D"] * scale))
    F_EYEBROW = max(1, int(round(d["F_EYEBROW"] * scale)))
    F_BODY = max(1, int(round(d["F_BODY"] * scale)))
    F_SMALL = max(1, int(round(d["F_SMALL"] * scale)))
    F_BTN = max(1, int(round(d["F_BTN"] * scale)))
    TK_PX = max(1, int(round(d["TK_PX"] * scale)))


_apply_scale(1.0)          # sane defaults before _run_tk probes the monitor

# ── Palette — transform_widget_html CSS flattened over cream ────────────
CREAM      = (234, 223, 206)
INK        = (42, 31, 24)
MUT        = (123, 112, 100)
DARK       = (26, 21, 18)
LINE       = (205, 193, 177)
INPUT_BG   = (241, 235, 224)
PREVIEW_BG = (243, 238, 228)
X_BG       = (216, 205, 189)
ERR        = (154, 61, 46)
REC_RED    = (200, 62, 48)

CREAM_HEX      = "#EADFCE"
INPUT_BG_HEX   = "#F1EBE0"
PREVIEW_BG_HEX = "#F3EEE4"
INK_HEX        = "#2A1F18"
MUT_HEX        = "#7B7064"

CHROMA_TK = "#0a0a0a"


class WinTransformWidget:
    def __init__(self, app=None):
        self.app = app
        self._root = None
        self._canvas = None
        self._photo = None
        self._f_eyebrow = None
        self._f_body = None
        self._f_btn = None
        self._f_small = None

        self._state = "prompt"        # prompt | busy | preview | done
        self._selection = None
        self._rewrite = None
        self._busy = False
        self._speaking = False
        self._transcribing = False
        self._speak_t0 = 0.0
        self._busy_label = "Working…"
        self._error = ""
        self._hint = ""
        self._visible = False
        self._alpha = 0.0
        self._hits = []
        self._panel_h = H_PROMPT
        self._anim_after = None

        self._instr_entry = None
        self._preview_text = None
        # Cached layout so the drawn input box and the real Entry always
        # land on exactly the same rect (a hardcoded guess drifts and can
        # cover neighbouring hit-boxes).
        self._entry_rect = (0, 0, 0, 0)

    # ── public API ──────────────────────────────────────────────────────
    def show(self, selection):
        self._selection = str(selection or "")
        self._rewrite = None
        self._busy = False
        self._speaking = False
        self._transcribing = False
        self._error = ""
        self._hint = ""
        self._state = "prompt"
        if self._root is None:
            self._setup()
        self._safe(self._show_internal)

    def hide(self):
        self._safe(self._fade_out)

    @property
    def visible(self):
        return self._visible

    # ── tk lifecycle ────────────────────────────────────────────────────
    def _setup(self):
        threading.Thread(target=self._run_tk, name="tf-tk", daemon=True).start()
        for _ in range(80):
            if self._root is not None:
                return
            time.sleep(0.02)

    def _run_tk(self):
        try:
            # BEFORE the canvas: it is sized from PANEL_W.
            try:
                from app.win_dpi import widget_scale
                _apply_scale(widget_scale())
                logger.info("transform pill: scale=%.2f -> %dx%d", SCALE, PANEL_W, H_PROMPT)
            except Exception as e:
                logger.debug("transform dpi scale skipped: %s", e)
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.attributes("-alpha", 0.0)
            root.attributes("-transparentcolor", CHROMA_TK)
            root.configure(bg=CHROMA_TK)
            root.withdraw()

            canvas = tk.Canvas(root, width=PANEL_W, height=H_PROMPT,
                               bg=CHROMA_TK, highlightthickness=0,
                               borderwidth=0)
            canvas.pack()
            canvas.bind("<Button-1>", self._on_click)

            self._root = root
            self._canvas = canvas
            self._load_fonts()
            self._build_overlay_widgets()
            root.bind("<Escape>", lambda e: self.tf_cancel())
            self._apply_geometry(H_PROMPT)
            root.mainloop()
        except Exception as e:
            logger.error("transform tk thread crashed: %s", e, exc_info=True)

    def _load_fonts(self):
        for face in ("consola.ttf", "cour.ttf"):
            try:
                self._f_eyebrow = ImageFont.truetype(face, F_EYEBROW)
                break
            except Exception:
                continue
        for face in ("segoeui.ttf", "arial.ttf"):
            try:
                self._f_body = ImageFont.truetype(face, F_BODY)
                self._f_small = ImageFont.truetype(face, F_SMALL)
                break
            except Exception:
                continue
        try:
            self._f_btn = ImageFont.truetype("segoeuib.ttf", F_BTN)
        except Exception:
            self._f_btn = self._f_body
        self._f_eyebrow = self._f_eyebrow or ImageFont.load_default()
        self._f_body = self._f_body or ImageFont.load_default()
        self._f_small = self._f_small or self._f_body
        self._f_btn = self._f_btn or self._f_body

    def _build_overlay_widgets(self):
        self._instr_entry = tk.Entry(
            self._root, bg=INPUT_BG_HEX, fg=INK_HEX,
            insertbackground=INK_HEX, bd=0, relief="flat",
            highlightthickness=0, font=("Segoe UI", -TK_PX))
        self._instr_entry.bind("<Return>", lambda e: self._send_typed_prompt())

        self._preview_text = tk.Text(
            self._root, bg=PREVIEW_BG_HEX, fg=INK_HEX,
            font=("Segoe UI", -TK_PX), wrap="word", bd=0, relief="flat",
            highlightthickness=0, state="disabled", padx=_i(8), pady=_i(6),
            cursor="arrow")

    def _apply_geometry(self, h):
        self._panel_h = h
        try:
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            self._root.geometry(
                f"{PANEL_W}x{h}+{(sw - PANEL_W) // 2}+{sh - h - BOTTOM_MARGIN}")
            self._canvas.config(width=PANEL_W, height=h)
        except Exception:
            pass

    # ── actions ─────────────────────────────────────────────────────────
    def _run_llm(self, fn, label):
        if self._busy:
            return
        if not self._selection:
            self._error = "Selection was lost — press the hotkey again."
            self._set_state("prompt")
            return
        from app import transform as _t
        if len(self._selection) > _t.MAX_SELECTION_CHARS:
            self._error = ("Selection too long (%dk chars, max %dk)."
                           % (len(self._selection) // 1000,
                              _t.MAX_SELECTION_CHARS // 1000))
            self._set_state("prompt")
            return
        self._busy = True
        self._busy_label = label
        self._set_state("busy")
        sel = self._selection

        def work():
            out = None
            try:
                out = fn(sel)
            except Exception as e:
                logger.debug("transform LLM failed: %s", e)

            def ui():
                self._busy = False
                if not self._visible:
                    return
                if out:
                    self._rewrite = out
                    self._error = ""
                    self._set_state("preview")
                else:
                    self._error = "Couldn't transform — try again."
                    self._set_state("prompt")
            self._on_main(ui)
        threading.Thread(target=work, daemon=True).start()

    def tf_improvise(self):
        from app import transform
        self._run_llm(lambda s: transform.improvise(s, self.app.config),
                      "Improvising…")

    def tf_prompt(self, instruction=""):
        instruction = (instruction or "").strip()
        if not instruction:
            return
        from app import transform
        self._run_llm(
            lambda s: transform.apply_instruction(s, instruction, self.app.config),
            "Transforming…")

    def _send_typed_prompt(self):
        try:
            v = self._instr_entry.get().strip() if self._instr_entry else ""
        except Exception:
            v = ""
        if v:
            self.tf_prompt(v)

    # ── mic / spoken instruction ────────────────────────────────────────
    def tf_speak(self):
        """Toggle the spoken-instruction recording.

        `recorder.start()` blocks ~300ms (PortAudio warm-up). Running it
        on the tk thread froze the UI so the 'listening' state never
        painted before the block — the user saw nothing happen, clicked
        again, and that second click stopped-and-transcribed. Start the
        recorder on a worker thread and paint the listening state
        immediately."""
        if self._transcribing:
            logger.info("tf_speak ignored: transcription already in flight")
            return

        if self._speaking:
            logger.info("tf_speak: stopping recording")
            self._speaking = False
            self._transcribing = True
            self._busy_label = "Transcribing…"
            self._set_state("busy")
            threading.Thread(
                target=lambda: self._stop_speak(discard=False),
                daemon=True).start()
            return

        if getattr(self.app, "_is_recording", False):
            self._error = "Finish your dictation first."
            self._set_state("prompt")
            return
        try:
            mt = self.app.meetings.active if getattr(self.app, "meetings", None) else None
        except Exception:
            mt = None
        if mt is not None:
            self._error = "Mic is busy with your meeting — type the instruction."
            self._set_state("prompt")
            return

        # Paint 'listening' FIRST, then warm the mic off-thread.
        self._speaking = True
        self._speak_t0 = time.time()
        self._error = ""
        self._hint = ""
        logger.info("tf_speak: starting recording")
        self._safe(self._render)
        self._safe(self._tick_listening)

        def start_rec():
            try:
                self.app.recorder.start()
                logger.info("tf_speak: recorder started")
            except Exception as e:
                logger.error("tf_speak recorder.start failed: %s", e)
                self._speaking = False
                self._error = "Couldn't open the microphone."
                self._set_state("prompt")
        threading.Thread(target=start_rec, daemon=True).start()

    def _tick_listening(self):
        """Repaint ~8fps while listening so the timer and pulse animate."""
        if not (self._visible and self._speaking and self._state == "prompt"):
            self._anim_after = None
            return
        self._render()
        try:
            self._anim_after = self._root.after(120, self._tick_listening)
        except Exception:
            self._anim_after = None

    def _stop_speak(self, discard):
        try:
            audio = self.app.recorder.stop()
        except Exception as e:
            logger.error("tf_speak recorder.stop failed: %s", e)
            audio = None

        if discard or audio is None or not self._visible:
            self._transcribing = False
            if not discard and self._visible:
                self._error = "Didn't catch that — try again."
                self._set_state("prompt")
            return

        try:
            from app.transcriber import transcribe_with_status
            text, status = transcribe_with_status(
                audio, self.app.config, self.app.recorder.sample_rate)
            instr = (text or "").strip()
            logger.info("tf_speak: heard %r (status=%s)", instr[:60], status)

            def ui():
                self._transcribing = False
                if not self._visible:
                    return
                if status == "ok" and instr:
                    try:
                        self._instr_entry.delete(0, tk.END)
                        self._instr_entry.insert(0, instr)
                    except Exception:
                        pass
                    self.tf_prompt(instr)
                else:
                    self._error = "Didn't catch that — try again."
                    self._set_state("prompt")
            self._on_main(ui)
        except Exception as e:
            logger.error("spoken prompt failed: %s", e, exc_info=True)
            self._transcribing = False
            self._error = "Didn't catch that — try again."
            self._set_state("prompt")

    # ── replace / undo / cancel ─────────────────────────────────────────
    def tf_replace(self):
        rewrite = self._rewrite
        if not rewrite:
            return
        original = self._selection

        def do():
            try:
                from app.win_injector import inject_text
                inject_text(rewrite, allow_mentions=False)
                self._selection = original
                self._rewrite = None
                self._set_state("done")

                def later():
                    if self._visible and self._state == "done":
                        self.hide()
                threading.Timer(6.0, lambda: self._on_main(later)).start()
            except Exception as e:
                logger.error("transform replace failed: %s", e)
                self._error = "Replace failed — text untouched."
                self._set_state("preview")
        self._on_main(do)

    def tf_undo(self):
        from app import transform
        transform.undo_in_target()
        self.hide()

    def tf_cancel(self):
        if self._speaking:
            self._speaking = False
            threading.Thread(
                target=lambda: self._stop_speak(discard=True),
                daemon=True).start()
        self.hide()

    # ── state plumbing ──────────────────────────────────────────────────
    def _set_state(self, state):
        self._state = state
        self._safe(self._render_and_layout)

    def _safe(self, fn):
        if self._root is None:
            return
        try:
            self._root.after(0, fn)
        except Exception:
            pass

    def _on_main(self, fn):
        if self.app is not None and hasattr(self.app, "_on_main"):
            try:
                self.app._on_main(fn)
                return
            except Exception:
                pass
        try:
            threading.Thread(target=fn, daemon=True).start()
        except Exception:
            pass

    def _show_internal(self):
        if self._root is None:
            return
        self._visible = True
        self._alpha = 0.0
        try:
            self._instr_entry.delete(0, tk.END)
        except Exception:
            pass
        self._root.deiconify()
        self._render_and_layout()
        self._fade_in()

    def _fade_in(self):
        if self._root is None:
            return
        self._alpha = min(0.99, self._alpha + 0.12)
        self._root.attributes("-alpha", self._alpha)
        if self._alpha < 0.97:
            self._root.after(16, self._fade_in)

    def _fade_out(self):
        if self._root is None:
            return
        self._alpha = max(0.0, self._alpha - 0.14)
        try:
            self._root.attributes("-alpha", self._alpha)
        except Exception:
            pass
        if self._alpha <= 0.0:
            for w in (self._instr_entry, self._preview_text):
                try:
                    w.place_forget()
                except Exception:
                    pass
            try:
                self._root.withdraw()
            except Exception:
                pass
            self._visible = False
            return
        self._root.after(16, self._fade_out)

    # ── layout ──────────────────────────────────────────────────────────
    def _render_and_layout(self):
        h = {"prompt": H_PROMPT, "busy": H_BUSY,
             "preview": H_PREVIEW, "done": H_DONE}.get(self._state, H_PROMPT)
        if h != self._panel_h:
            self._apply_geometry(h)
        self._render()                 # render first: computes _entry_rect
        self._place_real_widgets()

    def _place_real_widgets(self):
        for w in (self._instr_entry, self._preview_text):
            try:
                w.place_forget()
            except Exception:
                pass
        if self._state == "prompt":
            ex, ey, ew, eh = self._entry_rect
            if ew > 0:
                self._instr_entry.place(x=ex + _i(12), y=ey + _i(9),
                                        width=ew - _i(24), height=eh - _i(18))
        elif self._state == "preview":
            box_y, box_h = _i(46), H_PREVIEW - _i(46) - _i(58)
            rw = self._rewrite or ""
            try:
                self._preview_text.configure(state="normal")
                self._preview_text.delete("1.0", tk.END)
                self._preview_text.insert(
                    "1.0", rw[:4000] + ("\n…" if len(rw) > 4000 else ""))
                self._preview_text.configure(state="disabled")
            except Exception:
                pass
            self._preview_text.place(x=PAD + _i(6), y=box_y + _i(6),
                                     width=PANEL_W - 2 * PAD - _i(12),
                                     height=box_h - _i(12))

    # ── render ──────────────────────────────────────────────────────────
    def _render(self):
        if self._canvas is None:
            return
        try:
            h = self._panel_h
            img = Image.new("RGBA", (PANEL_W, h), _hex_rgba(CHROMA_TK))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle((0, 0, PANEL_W - 1, h - 1),
                                   radius=RADIUS, fill=CREAM + (255,))
            self._hits = []

            if self._state == "prompt":
                self._draw_prompt(draw)
            elif self._state == "busy":
                self._draw_busy(draw)
            elif self._state == "preview":
                self._draw_preview(draw)
            elif self._state == "done":
                self._draw_done(draw)

            self._canvas.delete("all")
            self._photo = ImageTk.PhotoImage(img, master=self._canvas)
            self._canvas.create_image(0, 0, image=self._photo, anchor="nw")
        except Exception as e:
            logger.error("transform render error: %s", e, exc_info=True)

    # ── chip primitives ─────────────────────────────────────────────────
    # Every literal here is a 96-DPI design offset, so each one is scaled: a
    # correctly-sized panel with unscaled internals is worse than an unscaled
    # panel, because the hit-boxes stop matching what is drawn.
    def _chip_dark(self, draw, x, y, label, action, h=None):
        h = ROW_H if h is None else h
        w = _tw(draw, label, self._f_btn) + _i(34)
        draw.rounded_rectangle((x, y, x + w, y + h), radius=_i(11),
                               fill=DARK + (255,))
        draw.text((x + _i(17), y + (h - _i(15)) // 2), label,
                  fill=CREAM + (255,), font=self._f_btn)
        self._hits.append((x, y, x + w, y + h, action))
        return w

    def _chip_outline(self, draw, x, y, label, action, h=None):
        h = ROW_H if h is None else h
        w = _tw(draw, label, self._f_btn) + _i(30)
        draw.rounded_rectangle((x, y, x + w, y + h), radius=_i(11),
                               outline=LINE + (255,), width=_i(1))
        draw.text((x + _i(15), y + (h - _i(15)) // 2), label,
                  fill=INK + (255,), font=self._f_btn)
        self._hits.append((x, y, x + w, y + h, action))
        return w

    def _chip_mic(self, draw, x, y, action, d=None):
        d = MIC_D if d is None else d
        cx, cy, r = x + d // 2, y + d // 2, d // 2
        if self._speaking:
            draw.ellipse((x, y, x + d, y + d), fill=REC_RED + (255,))
            col = (255, 255, 255, 255)
        else:
            draw.ellipse((x, y, x + d, y + d),
                         outline=LINE + (255,), width=_i(1))
            col = INK + (235,)
        draw.rounded_rectangle((cx - _i(3), cy - _i(8), cx + _i(3), cy + _i(1)),
                               radius=_i(3), outline=col, width=_i(2))
        draw.arc((cx - _i(7), cy - _i(5), cx + _i(7), cy + _i(6)),
                 start=0, end=180, fill=col, width=_i(2))
        draw.line((cx, cy + _i(6), cx, cy + _i(9)), fill=col, width=_i(2))
        self._hits.append((x, y, x + d, y + d, action))
        return d

    def _chip_x(self, draw, cx, cy, action, r=None):
        r = _i(14) if r is None else r
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=X_BG + (255,))
        k = _i(4)
        draw.line((cx - k, cy - k, cx + k, cy + k), fill=INK + (230,), width=_i(2))
        draw.line((cx - k, cy + k, cx + k, cy - k), fill=INK + (230,), width=_i(2))
        self._hits.append((cx - r, cy - r, cx + r, cy + r, action))

    # ── state painters ──────────────────────────────────────────────────
    def _draw_prompt(self, draw):
        y1 = _i(20)
        eyebrow_w = _track_text(draw, (PAD, y1), "TRANSFORM SELECTION",
                                self._f_eyebrow, MUT + (255,), _s(1.6))

        x_cx = PANEL_W - PAD - _i(14)
        chars_lbl = f"{len(self._selection or '')} chars"
        chars_w = _tw(draw, chars_lbl, self._f_small)
        draw.text((x_cx - _i(22) - chars_w, y1 - _i(1)), chars_lbl,
                  fill=MUT + (190,), font=self._f_small)
        self._chip_x(draw, x_cx, y1 + _i(5), "tf_cancel")

        ex_x = PAD + eyebrow_w + _i(14)
        ex_max = (x_cx - _i(22) - chars_w) - _i(12) - ex_x
        excerpt = _fit(draw, (self._selection or "").replace("\n", " "),
                       self._f_body, ex_max)
        draw.text((ex_x, y1 - _i(2)), excerpt, fill=MUT + (215,), font=self._f_body)

        # control row
        x = PAD
        x += self._chip_dark(draw, x, ROW_Y, "Improvise", "tf_improvise") + _i(9)
        x += self._chip_mic(draw, x, ROW_Y, "tf_speak") + _i(9)

        go_w = _tw(draw, "Go", self._f_btn) + _i(30)
        input_w = PANEL_W - PAD - x - go_w - _i(9)
        draw.rounded_rectangle((x, ROW_Y, x + input_w, ROW_Y + ROW_H),
                               radius=_i(11), fill=INPUT_BG + (255,),
                               outline=LINE + (255,), width=_i(1))
        self._entry_rect = (x, ROW_Y, input_w, ROW_H)
        try:
            typed = self._instr_entry.get() if self._instr_entry else ""
        except Exception:
            typed = ""
        if not typed:
            draw.text((x + _i(13), ROW_Y + _i(10)),
                      "…or type an instruction",
                      fill=MUT + (160,), font=self._f_body)
        x += input_w + _i(9)
        self._chip_outline(draw, x, ROW_Y, "Go", "tf_go")

        # status line
        y3 = H_PROMPT - _i(30)
        if self._speaking:
            secs = int(max(0, time.time() - self._speak_t0))
            pulse = 0.55 + 0.45 * abs(math.sin(time.time() * 4.0))
            draw.ellipse((PAD, y3 + _i(4), PAD + _i(8), y3 + _i(12)),
                         fill=REC_RED + (int(255 * pulse),))
            draw.text((PAD + _i(15), y3), f"Listening  {secs//60}:{secs%60:02d}",
                      fill=REC_RED + (255,), font=self._f_small)
            w = _tw(draw, f"Listening  {secs//60}:{secs%60:02d}", self._f_small)
            draw.text((PAD + _i(15) + w + _i(10), y3),
                      "— click the mic again when you're done",
                      fill=MUT + (190,), font=self._f_small)
        elif self._error:
            draw.text((PAD, y3), self._error, fill=ERR + (255,),
                      font=self._f_small)
        elif self._hint:
            draw.text((PAD, y3), self._hint, fill=MUT + (220,),
                      font=self._f_small)
        else:
            draw.text((PAD, y3), "Speak or type how to rewrite it  ·  Esc to close",
                      fill=MUT + (160,), font=self._f_small)

    def _draw_busy(self, draw):
        cx, cy, r = PAD + _i(12), H_BUSY // 2, _i(9)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                     outline=LINE + (255,), width=_i(2))
        start = int(math.degrees((time.time() * 4.0) % (2 * math.pi)))
        draw.arc((cx - r, cy - r, cx + r, cy + r),
                 start=start, end=(start + 240) % 360,
                 fill=DARK + (255,), width=_i(2))
        draw.text((cx + r + _i(14), cy - _i(8)), self._busy_label,
                  fill=INK + (235,), font=self._f_body)
        self._chip_x(draw, PANEL_W - PAD - _i(14), cy, "tf_cancel")
        try:
            self._root.after(66, lambda: (
                self._visible and self._state == "busy" and self._render()))
        except Exception:
            pass

    def _draw_preview(self, draw):
        y1 = _i(20)
        w = _track_text(draw, (PAD, y1), "PREVIEW", self._f_eyebrow,
                        MUT + (255,), _s(1.6))
        draw.text((PAD + w + _i(12), y1 - _i(1)), "replaces your selection",
                  fill=MUT + (180,), font=self._f_small)
        self._chip_x(draw, PANEL_W - PAD - _i(14), y1 + _i(5), "tf_cancel")

        box_y, box_h = _i(46), H_PREVIEW - _i(46) - _i(58)
        draw.rounded_rectangle((PAD, box_y, PANEL_W - PAD, box_y + box_h),
                               radius=_i(11), fill=PREVIEW_BG + (255,),
                               outline=LINE + (255,), width=_i(1))

        yb = H_PREVIEW - _i(46)
        x = PAD
        x += self._chip_dark(draw, x, yb, "Replace", "tf_replace") + _i(9)
        x += self._chip_outline(draw, x, yb, "Cancel", "tf_cancel") + _i(14)
        if self._error:
            draw.text((x, yb + _i(10)), self._error, fill=ERR + (255,),
                      font=self._f_small)

    def _draw_done(self, draw):
        cy = H_DONE // 2
        w = _track_text(draw, (PAD, cy - _i(6)), "REPLACED", self._f_eyebrow,
                        MUT + (255,), _s(1.6))
        x = PAD + w + _i(14)
        draw.text((x, cy - _i(8)), "changed your mind?",
                  fill=MUT + (190,), font=self._f_body)
        x += _tw(draw, "changed your mind?", self._f_body) + _i(14)
        self._chip_outline(draw, x, cy - ROW_H // 2, "Undo", "tf_undo")
        self._chip_x(draw, PANEL_W - PAD - _i(14), cy, "tf_cancel")

    # ── clicks ──────────────────────────────────────────────────────────
    def _on_click(self, event):
        for (x1, y1, x2, y2, action) in self._hits:
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self._dispatch(action)
                return

    def _dispatch(self, action):
        try:
            {
                "tf_go":        self._send_typed_prompt,
                "tf_improvise": self.tf_improvise,
                "tf_speak":     self.tf_speak,
                "tf_replace":   self.tf_replace,
                "tf_cancel":    self.tf_cancel,
                "tf_undo":      self.tf_undo,
            }.get(action, lambda: None)()
        except Exception as e:
            logger.error("transform action %s failed: %s", action, e)


# ── helpers ─────────────────────────────────────────────────────────────
def _hex_rgba(hexstr):
    hh = hexstr.lstrip("#")
    return (int(hh[0:2], 16), int(hh[2:4], 16), int(hh[4:6], 16), 255)


def _tw(draw, text, font):
    try:
        b = draw.textbbox((0, 0), text, font=font)
        return b[2] - b[0]
    except Exception:
        return int(len(text) * 6.5)


def _track_text(draw, xy, text, font, fill, spacing):
    """Draw letter-spaced text (PIL has no letter-spacing). Returns the
    total width — the eyebrow labels use .16em tracking in the CSS."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, fill=fill, font=font)
        x += _tw(draw, ch, font) + spacing
    return int(x - xy[0])


def _fit(draw, text, font, max_w):
    if max_w <= 0:
        return ""
    if _tw(draw, text, font) <= max_w:
        return text
    lo, hi, best = 0, len(text), ""
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = text[:mid].rstrip() + "…"
        if _tw(draw, cand, font) <= max_w:
            best, lo = cand, mid + 1
        else:
            hi = mid - 1
    return best or "…"
