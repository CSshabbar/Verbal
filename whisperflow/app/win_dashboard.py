"""Windows dashboard — simplified tkinter window with record, history, and settings."""

import logging
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from app.config import load_config, save_config, _entry_text, APP_VERSION

logger = logging.getLogger("verbal.dashboard")

BG = "#1A1917"
SHEET_BG = "#F2EFE9"
CARD_BG = "#FFFFFF"
TEXT_DARK = "#2C2A27"
TEXT_LIGHT = "#F2EFE9"
MUTED = "#7A7570"
ACCENT = "#E05A2B"


class WinDashboard:
    def __init__(self, app):
        self.app = app
        self._window = None
        self._history_list = None
        self._record_btn = None
        self._status_label = None
        self._result_text = None

    def show(self):
        if self._window:
            try:
                self._window.lift()
                return
            except tk.TclError:
                self._window = None

        threading.Thread(target=self._build_and_run, daemon=True).start()

    def _build_and_run(self):
        self._window = tk.Tk()
        self._window.title("Verbal")
        self._window.geometry("640x520")
        self._window.configure(bg=BG)
        self._window.resizable(True, True)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#2A2927", foreground=TEXT_LIGHT,
                         padding=[16, 6], font=("Segoe UI", 10))
        style.map("TNotebook.Tab", background=[("selected", ACCENT)])

        notebook = ttk.Notebook(self._window)
        notebook.pack(fill="both", expand=True)

        record_frame = tk.Frame(notebook, bg=SHEET_BG)
        history_frame = tk.Frame(notebook, bg=SHEET_BG)
        settings_frame = tk.Frame(notebook, bg=SHEET_BG)

        notebook.add(record_frame, text="  Record  ")
        notebook.add(history_frame, text="  History  ")
        notebook.add(settings_frame, text="  Settings  ")

        self._build_record_tab(record_frame)
        self._build_history_tab(history_frame)
        self._build_settings_tab(settings_frame)

        self._window.mainloop()

    # ── Record tab ────────────────────────────────────────────────────────
    def _build_record_tab(self, parent):
        header = tk.Frame(parent, bg=BG, height=100)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text="Verbal", font=("Segoe UI", 22, "normal"),
                 fg=TEXT_LIGHT, bg=BG).pack(pady=(16, 0))

        self._status_label = tk.Label(header, text="Ready", font=("Segoe UI", 11),
                                       fg=MUTED, bg=BG)
        self._status_label.pack()

        body = tk.Frame(parent, bg=SHEET_BG)
        body.pack(fill="both", expand=True, padx=20, pady=20)

        self._record_btn = tk.Button(
            body, text="Start Recording", font=("Segoe UI", 13, "bold"),
            bg=ACCENT, fg="white", activebackground="#C04A22", activeforeground="white",
            relief="flat", cursor="hand2", padx=24, pady=10,
            command=self._toggle_recording,
        )
        self._record_btn.pack(pady=(20, 16))

        self._result_text = scrolledtext.ScrolledText(
            body, height=8, wrap="word", font=("Segoe UI", 12),
            bg=CARD_BG, fg=TEXT_DARK, relief="flat", bd=0,
        )
        self._result_text.pack(fill="both", expand=True, pady=(8, 0))

    def _toggle_recording(self):
        if self.app._is_recording:
            self.app._on_record_stop()
        else:
            self.app._on_record_start()

    def update_recording_state(self, recording: bool):
        if not self._window:
            return
        try:
            if recording:
                self._record_btn.config(text="Stop Recording", bg="#C04A22")
                self._status_label.config(text="Listening...", fg=ACCENT)
            else:
                self._record_btn.config(text="Start Recording", bg=ACCENT)
                self._status_label.config(text="Ready", fg=MUTED)
        except tk.TclError:
            pass

    def show_result(self, text: str):
        if not self._window:
            return
        try:
            self._result_text.delete("1.0", "end")
            self._result_text.insert("1.0", text)
            self._status_label.config(text="Done - pasted", fg="#3DAA6E")
        except tk.TclError:
            pass

    # ── History tab ───────────────────────────────────────────────────────
    def _build_history_tab(self, parent):
        config = load_config()
        history = config.get("history", [])

        header = tk.Frame(parent, bg=BG, height=60)
        header.pack(fill="x")
        header.pack_propagate(False)

        total = len(history)
        words = sum(len(_entry_text(h).split()) for h in history)
        tk.Label(header, text=f"{total} transcriptions  |  {words} words",
                 font=("Segoe UI", 11), fg=MUTED, bg=BG).pack(pady=16)

        body = tk.Frame(parent, bg=SHEET_BG)
        body.pack(fill="both", expand=True, padx=12, pady=8)

        self._history_list = tk.Listbox(
            body, font=("Segoe UI", 11), bg=CARD_BG, fg=TEXT_DARK,
            selectbackground=ACCENT, selectforeground="white",
            relief="flat", bd=0, activestyle="none",
        )
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self._history_list.yview)
        self._history_list.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._history_list.pack(fill="both", expand=True)

        for i, entry in enumerate(history):
            text = _entry_text(entry)[:80]
            self._history_list.insert("end", f"  {i+1}.  {text}")
            self._history_list.itemconfig("end", {"fg": TEXT_DARK})

        btn_frame = tk.Frame(parent, bg=SHEET_BG)
        btn_frame.pack(fill="x", padx=12, pady=8)

        tk.Button(btn_frame, text="Copy selected", command=self._copy_selected,
                  bg=BG, fg=TEXT_LIGHT, relief="flat", padx=12, pady=6,
                  font=("Segoe UI", 10)).pack(side="left")

        tk.Button(btn_frame, text="Refresh", command=self._refresh_history,
                  bg=BG, fg=TEXT_LIGHT, relief="flat", padx=12, pady=6,
                  font=("Segoe UI", 10)).pack(side="left", padx=8)

    def _copy_selected(self):
        if not self._history_list:
            return
        sel = self._history_list.curselection()
        if not sel:
            return
        config = load_config()
        history = config.get("history", [])
        idx = sel[0]
        if idx < len(history):
            import pyperclip
            pyperclip.copy(_entry_text(history[idx]))

    def _refresh_history(self):
        if not self._history_list:
            return
        self._history_list.delete(0, "end")
        config = load_config()
        for i, entry in enumerate(config.get("history", [])):
            text = _entry_text(entry)[:80]
            self._history_list.insert("end", f"  {i+1}.  {text}")

    # ── Settings tab ──────────────────────────────────────────────────────
    def _build_settings_tab(self, parent):
        config = load_config()

        canvas = tk.Canvas(parent, bg=SHEET_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=SHEET_BG)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        pad = {"padx": 20, "pady": 6}
        entry_opts = {"font": ("Consolas", 11), "bg": CARD_BG, "fg": TEXT_DARK,
                       "relief": "flat", "bd": 0, "width": 44}

        # Groq keys
        tk.Label(scroll_frame, text="GROQ API KEY", font=("Segoe UI", 9, "bold"),
                 fg=MUTED, bg=SHEET_BG).pack(**pad, anchor="w")
        groq_keys = config.get("groq_api_keys", [])
        groq_var = tk.StringVar(value=groq_keys[0] if groq_keys else "")
        tk.Entry(scroll_frame, textvariable=groq_var, **entry_opts, show="*").pack(**pad)

        # Gemini keys
        tk.Label(scroll_frame, text="GEMINI API KEY", font=("Segoe UI", 9, "bold"),
                 fg=MUTED, bg=SHEET_BG).pack(**pad, anchor="w")
        gemini_keys = config.get("gemini_api_keys", [])
        gemini_var = tk.StringVar(value=gemini_keys[0] if gemini_keys else "")
        tk.Entry(scroll_frame, textvariable=gemini_var, **entry_opts, show="*").pack(**pad)

        # Whisper model
        tk.Label(scroll_frame, text="WHISPER MODEL (local fallback)", font=("Segoe UI", 9, "bold"),
                 fg=MUTED, bg=SHEET_BG).pack(**pad, anchor="w")
        model_var = tk.StringVar(value=config.get("whisper_model", "base"))
        ttk.Combobox(scroll_frame, textvariable=model_var,
                     values=["tiny", "base", "small", "medium"],
                     state="readonly", width=20, font=("Segoe UI", 11)).pack(**pad, anchor="w")

        # Recording mode
        tk.Label(scroll_frame, text="RECORDING MODE", font=("Segoe UI", 9, "bold"),
                 fg=MUTED, bg=SHEET_BG).pack(**pad, anchor="w")
        mode_var = tk.StringVar(value=config.get("recording_mode", "toggle"))
        ttk.Combobox(scroll_frame, textvariable=mode_var,
                     values=["hold", "toggle"],
                     state="readonly", width=20, font=("Segoe UI", 11)).pack(**pad, anchor="w")

        # Sync
        tk.Label(scroll_frame, text="SYNC", font=("Segoe UI", 9, "bold"),
                 fg=MUTED, bg=SHEET_BG).pack(**pad, anchor="w")

        sync_var = tk.BooleanVar(value=config.get("sync_enabled", False))
        tk.Checkbutton(scroll_frame, text="Enable cross-device sync", variable=sync_var,
                       bg=SHEET_BG, fg=TEXT_DARK, selectcolor=CARD_BG,
                       activebackground=SHEET_BG, font=("Segoe UI", 11)).pack(**pad, anchor="w")

        tk.Label(scroll_frame, text="User ID", font=("Segoe UI", 9), fg=MUTED,
                 bg=SHEET_BG).pack(padx=20, anchor="w")
        uid_var = tk.StringVar(value=config.get("sync_user_id", ""))
        uid_opts = {k: v for k, v in entry_opts.items() if k != "show"}
        tk.Entry(scroll_frame, textvariable=uid_var, **uid_opts).pack(**pad)

        tk.Label(scroll_frame, text="Device Name", font=("Segoe UI", 9), fg=MUTED,
                 bg=SHEET_BG).pack(padx=20, anchor="w")
        dn_var = tk.StringVar(value=config.get("sync_device_name", "Windows"))
        tk.Entry(scroll_frame, textvariable=dn_var, **uid_opts).pack(**pad)

        # Save button
        tk.Button(
            scroll_frame, text="Save Settings", font=("Segoe UI", 11, "bold"),
            bg=ACCENT, fg="white", activebackground="#C04A22", relief="flat",
            cursor="hand2", padx=20, pady=8,
            command=lambda: self._save_settings(
                groq_var, gemini_var, model_var, mode_var, sync_var, uid_var, dn_var
            ),
        ).pack(pady=20)

        # Version
        tk.Label(scroll_frame, text=f"Verbal v{APP_VERSION} | Windows",
                 font=("Segoe UI", 9), fg=MUTED, bg=SHEET_BG).pack(pady=(0, 20))

    def _save_settings(self, groq_var, gemini_var, model_var, mode_var,
                       sync_var, uid_var, dn_var):
        config = load_config()
        gk = groq_var.get().strip()
        if gk:
            config["groq_api_keys"] = [gk]
        gemk = gemini_var.get().strip()
        if gemk:
            config["gemini_api_keys"] = [gemk]
        config["whisper_model"] = model_var.get()
        config["recording_mode"] = mode_var.get()
        config["sync_enabled"] = sync_var.get()
        config["sync_user_id"] = uid_var.get().strip()
        config["sync_device_name"] = dn_var.get().strip() or "Windows"
        save_config(config)
        messagebox.showinfo("Settings", "Saved")

    def _refresh(self):
        self._refresh_history()
