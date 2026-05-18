"""Windows status overlay — a small tkinter pill at the top of the screen."""

import logging
import tkinter as tk
import threading

logger = logging.getLogger("verbal.overlay")

PILL_W = 200
PILL_H = 40
BG = "#1A1917"
TEXT_COL = "#F2EFE9"
ACCENT = "#E0522A"
BLUE = "#4A90E2"
GREEN = "#3DAA6E"


class WinOverlay:
    def __init__(self):
        self._root = None
        self._label = None
        self._dot_canvas = None
        self._dot_id = None

    def setup(self):
        t = threading.Thread(target=self._run_tk, daemon=True)
        t.start()

    def _run_tk(self):
        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.95)
        self._root.withdraw()

        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        x = (screen_w - PILL_W) // 2
        y = screen_h - PILL_H - 60
        self._root.geometry(f"{PILL_W}x{PILL_H}+{x}+{y}")

        frame = tk.Frame(self._root, bg=BG, padx=10, pady=6)
        frame.pack(fill="both", expand=True)

        self._dot_canvas = tk.Canvas(
            frame, width=8, height=8, bg=BG, highlightthickness=0
        )
        self._dot_canvas.pack(side="left", padx=(0, 8))
        self._dot_id = self._dot_canvas.create_oval(0, 0, 8, 8, fill=ACCENT, outline="")

        self._label = tk.Label(
            self._frame_text(frame), text="Listening...", fg=TEXT_COL, bg=BG,
            font=("Segoe UI", 11),
        )
        self._label.pack(side="left")

        self._root.mainloop()

    def _frame_text(self, parent):
        # Helper — the dot and label share the same frame
        return parent

    def show(self, status="Listening..."):
        self._safe(lambda: self._show_internal(status))

    def update_status(self, status):
        self._safe(lambda: self._update_internal(status))

    def hide(self):
        self._safe(lambda: self._root.withdraw() if self._root else None)

    def show_briefly(self, status, duration=2.0):
        self._safe(lambda: self._show_internal(status))
        self._safe(lambda: self._root.after(int(duration * 1000), self.hide) if self._root else None)

    def _show_internal(self, status):
        if not self._root:
            return
        self._update_internal(status)
        self._root.deiconify()
        self._root.lift()

    def _update_internal(self, status):
        if not self._label:
            return
        self._label.config(text=status)
        color = ACCENT
        if "Transcrib" in status:
            color = BLUE
        elif any(w in status for w in ("Done", "Pasted", "Copied", "clipboard", "Synced")):
            color = GREEN
        if self._dot_canvas:
            self._dot_canvas.itemconfig(self._dot_id, fill=color)

    def _safe(self, fn):
        if self._root:
            try:
                self._root.after(0, fn)
            except Exception:
                pass

    @property
    def visible(self):
        return self._root is not None
