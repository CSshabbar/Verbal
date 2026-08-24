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

# Pipeline + model choices, mirroring the macOS Settings pane. Kept as plain tables so
# both platforms offer exactly the same options in the same order.
WIN_PIPELINES = [
    ("hybrid", "Hybrid",          "starts working while you talk"),
    ("one",    "One round trip",  "best all-round, same words sooner"),
    ("two",    "Two round trips", "the older, slower route"),
    ("old",    "Original",        "how Flume used to sound"),
]
# (config value, label). Labels are what the combobox shows and are mapped back on save.
WIN_ASR_MODELS = [
    ("auto",                   "Automatic — fast, good at everything (Groq)"),
    ("whisper-large-v3-turbo", "Whisper turbo — always the fast one (Groq)"),
    ("whisper-large-v3",       "Whisper large — better for other languages (Groq)"),
    ("eleven-scribe-v1",       "Scribe — most accurate on your voice (ElevenLabs)"),
    ("aai-universal-2",        "Universal-2 — best with Urdu mixed in (AssemblyAI)"),
    ("aai-universal-3-5-pro",  "Universal-3.5 — strong English, weak Urdu (AssemblyAI)"),
]


def _derive_pipeline(config):
    """Which pipeline the three flags currently describe. Derived, never stored — the
    dictation path reads the flags, so a separate key could disagree with what runs."""
    if config.get("hybrid_mode"):
        return "hybrid"
    if not config.get("speed_mode"):
        return "old"
    return "one" if config.get("chained_mode") else "two"


def _pipeline_flags(pid):
    """hybrid_mode is written on EVERY choice, not only when enabling it — otherwise
    switching away from Hybrid would leave it set and silently keep streaming."""
    if pid == "old":
        return {"speed_mode": False, "chained_mode": False, "hybrid_mode": False}
    if pid == "two":
        return {"speed_mode": True, "chained_mode": False, "hybrid_mode": False}
    if pid == "hybrid":
        return {"speed_mode": True, "chained_mode": True, "hybrid_mode": True}
    return {"speed_mode": True, "chained_mode": True, "hybrid_mode": False}


def _win_asr_label(config):
    cur = str(config.get("asr_model") or "auto")
    for val, lbl in WIN_ASR_MODELS:
        if val == cur:
            return lbl
    return WIN_ASR_MODELS[0][1]


def _win_asr_value(label):
    for val, lbl in WIN_ASR_MODELS:
        if lbl == label:
            return val
    return "auto"


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
        self._window.title("Flume")
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

        tk.Label(header, text="Flume", font=("Segoe UI", 22, "normal"),
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

        # Speed / pipeline. Same three flags the macOS Settings pane writes, and the
        # same derivation — the radio position is READ from speed_mode/chained_mode/
        # hybrid_mode rather than stored separately, so the two platforms can never
        # disagree about which pipeline is active.
        tk.Label(scroll_frame, text="SPEED", font=("Segoe UI", 9, "bold"),
                 fg=MUTED, bg=SHEET_BG).pack(**pad, anchor="w")
        pipe_var = tk.StringVar(value=_derive_pipeline(config))
        for pid, plabel, pdesc in WIN_PIPELINES:
            tk.Radiobutton(
                scroll_frame, text=f"{plabel} — {pdesc}", value=pid, variable=pipe_var,
                bg=SHEET_BG, fg=TEXT_DARK, selectcolor=CARD_BG, activebackground=SHEET_BG,
                anchor="w", justify="left", font=("Segoe UI", 10),
            ).pack(padx=20, anchor="w")

        # Transcription model
        tk.Label(scroll_frame, text="TRANSCRIPTION MODEL", font=("Segoe UI", 9, "bold"),
                 fg=MUTED, bg=SHEET_BG).pack(**pad, anchor="w")
        asr_var = tk.StringVar(value=_win_asr_label(config))
        ttk.Combobox(scroll_frame, textvariable=asr_var,
                     values=[lbl for _, lbl in WIN_ASR_MODELS],
                     state="readonly", width=44, font=("Segoe UI", 10)).pack(**pad, anchor="w")

        # Recording mode
        tk.Label(scroll_frame, text="RECORDING MODE", font=("Segoe UI", 9, "bold"),
                 fg=MUTED, bg=SHEET_BG).pack(**pad, anchor="w")
        mode_var = tk.StringVar(value=config.get("recording_mode", "toggle"))
        ttk.Combobox(scroll_frame, textvariable=mode_var,
                     values=["hold", "toggle"],
                     state="readonly", width=20, font=("Segoe UI", 11)).pack(**pad, anchor="w")

        # Hotkeys
        tk.Label(scroll_frame, text="HOTKEYS", font=("Segoe UI", 9, "bold"),
                 fg=MUTED, bg=SHEET_BG).pack(**pad, anchor="w")
        
        hold_var = tk.StringVar(value=config.get("hotkey_hold", "alt_r"))
        self._hold_btn = tk.Button(scroll_frame, textvariable=hold_var, **entry_opts,
                                  command=lambda: self._record_hotkey("hold", hold_var))
        self._hold_btn.pack(**pad)
        tk.Label(scroll_frame, text="Push-to-talk Key", font=("Segoe UI", 8), fg=MUTED, bg=SHEET_BG).pack(padx=20, anchor="w")

        toggle_var = tk.StringVar(value=config.get("hotkey_toggle", "alt_r"))
        self._toggle_btn = tk.Button(scroll_frame, textvariable=toggle_var, **entry_opts,
                                    command=lambda: self._record_hotkey("toggle", toggle_var))
        self._toggle_btn.pack(**pad)
        tk.Label(scroll_frame, text="Toggle Key", font=("Segoe UI", 8), fg=MUTED, bg=SHEET_BG).pack(padx=20, anchor="w")

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
                groq_var, gemini_var, model_var, mode_var, sync_var, uid_var, dn_var,
                pipe_var, asr_var
            ),
        ).pack(pady=20)

        # Version
        tk.Label(scroll_frame, text=f"Flume v{APP_VERSION} | Windows",
                 font=("Segoe UI", 9), fg=MUTED, bg=SHEET_BG).pack(pady=(0, 20))

    def _save_settings(self, groq_var, gemini_var, model_var, mode_var,
                       sync_var, uid_var, dn_var, pipe_var=None, asr_var=None):
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
        # Pipeline + model. Validated here rather than trusted: a bad asr_model would
        # be forwarded to the proxy and fail every dictation.
        if pipe_var is not None:
            config.update(_pipeline_flags(pipe_var.get()))
        if asr_var is not None:
            from app.transcriber import ASR_CHOICES
            _m = _win_asr_value(asr_var.get())
            config["asr_model"] = _m if _m in ASR_CHOICES else "auto"
        save_config(config)
        self.app.config = config
        messagebox.showinfo("Settings", "Saved")

    def _record_hotkey(self, mode, var):
        var.set("Press any key...")
        self._window.bind("<Key>", lambda e: self._on_tk_key(e, mode, var))

    def _on_tk_key(self, event, mode, var):
        self._window.unbind("<Key>")
        key = event.keysym.lower()
        if key == "alt_l" or key == "alt_r" or key == "control_l" or key == "control_r":
            pass # Keep it as is
        elif len(key) == 1:
            pass # Keep it as is

        var.set(key)
        config = load_config()
        if mode == "hold":
            config["hotkey_hold"] = key
        else:
            config["hotkey_toggle"] = key
        save_config(config)
        self.app.config = config

    def _refresh(self):

        self._refresh_history()
