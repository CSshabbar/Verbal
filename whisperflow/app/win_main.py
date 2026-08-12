"""Verbal for Windows — system tray app with global hotkey dictation."""

import logging
import os
import sys
import time
import threading
import traceback

# WebView2's GPU compositor rasterizes to a DirectX surface that bypasses
# the WS_EX_LAYERED / SetLayeredWindowAttributes(LWA_COLORKEY) pathway we
# use to give the overlay/HUD/autolearn pills a floating-sticker look
# (WebView2 doesn't do real per-pixel alpha on Windows). Force the CPU
# compositor before pywebview boots WebView2 so the chroma-key pixels
# actually reach Windows for it to mask out.
os.environ.setdefault(
    "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
    "--disable-gpu --disable-features=UseGpuMemoryBufferVideoFrames",
)

# Fix for PyInstaller "console=False" builds where sys.stderr/stdout are None
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')  # type: ignore[assignment]
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')  # type: ignore[assignment]

import faulthandler
faulthandler.enable()

from app.config import (
    load_config, save_config, add_to_history, update_history_entry,
    update_daily_words,
    _entry_text, _entry_app, LOG_DIR, ensure_dirs, APP_VERSION, PLATFORM,
)
from app.recorder import Recorder
from app.transcriber import transcribe, transcribe_with_status
from app.ai_cleanup import process_text
from app import recordings
from app import auth

ensure_dirs()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "app.log"),
    ],
)
logger = logging.getLogger("verbal")

MODE_HOLD = "hold"
MODE_TOGGLE = "toggle"


def _play_sound(name: str):
    try:
        import winsound
        # Resolve the assets path whether running from source or frozen (PyInstaller)
        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        sound_path = os.path.join(base_dir, "assets", "sounds", f"{name}.wav")

        if os.path.exists(sound_path):
            winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            # Fallback to beep if file missing
            freq_map = {"start": 800, "stop": 600, "done": 1000}
            winsound.Beep(freq_map.get(name, 800), 120)
    except Exception as e:
        logger.debug(f"Sound error: {e}")


class VerbalWinApp:
    def __init__(self):
        self.config = load_config()
        # Config defaults ship with the Mac glyph in `hotkey_label`
        # ("Right ⌘"). On Windows that Command symbol is meaningless —
        # migrate it once to a Windows-appropriate label so the Settings
        # UI doesn't display a Mac icon on a Windows box.
        if self.config.get("hotkey_label", "").strip() in ("Right ⌘", "⌘", ""):
            self.config["hotkey_label"] = "Right Alt"
            try:
                save_config(self.config)
            except Exception:
                pass
        self.recorder = Recorder()
        self._is_recording = False
        self._mode = self.config.get("recording_mode", MODE_TOGGLE)
        self._processing = False
        self._cancel_flag = threading.Event()
        self._last_toggle_time = 0.0
        self._sync = None
        self._tray_icon = None

        # Menu item references for dynamic updates
        self._menu_status = None
        self._menu_record = None
        self._menu_mode_hold = None
        self._menu_mode_toggle = None
        self._menu_model_items = {}

        from app.win_overlay import WinOverlay
        from app.win_popover import WinPopover
        from app.win_autolearn_widget import WinAutoLearnWidget
        from app.shared_dashboard import SharedDashboard

        self.overlay = WinOverlay(self)
        self.dashboard = SharedDashboard(self)
        self.popover = WinPopover(self)
        self.autolearn_widget = WinAutoLearnWidget(self)
        self._edit_watcher = None

        # MER-41: Transform Mode B (selection). Lazy — the pill is only
        # built when the Ctrl+Shift+T hotkey fires the first time.
        self.transform_widget = None

        # W6: MeetingManager wiring. Same shape as Mac main.py:122–127 —
        # fail-closed to None so `record → transcribe → inject` continues
        # unaffected if meetings can't spin up.
        self.meetings = None
        self.meeting_window = None
        self.meeting_hud = None
        try:
            from app.meetings import MeetingManager
            self.meetings = MeetingManager(self)
        except Exception as e:
            logger.error("MeetingManager init failed: %s", e)

        history = self.config.get("history", [])
        self._total_transcriptions = len(history)
        self._total_words = sum(len(_entry_text(h).split()) for h in history)

        self._init_sync()

    def _on_main(self, fn):
        """Run `fn` off the hot path — the Windows analogue of the Mac app's
        main-thread marshaller.

        On macOS the app owns a Cocoa run loop and marshals UI work onto the
        main thread because WKWebView/AppKit are main-thread-only. Windows has
        no such run loop here: the pywebview window and pystray tray run their
        own loops, and none of them require callers to hop to a specific thread.

        So we simply run `fn` on a short-lived daemon thread, fully guarded so a
        failing callback can never propagate into (or block) whatever invoked it.
        This is fire-and-forget / non-blocking by design — nothing in the
        record → transcribe → inject hot path depends on _on_main running
        synchronously (the pipeline updates state inline and only uses _on_main
        for peripheral UI refreshes)."""
        def _run():
            try:
                fn()
            except Exception as e:
                logger.error(f"_on_main callback failed: {e}", exc_info=True)
        try:
            threading.Thread(target=_run, daemon=True).start()
        except Exception as e:
            logger.error(f"_on_main dispatch failed: {e}")

    def _build_tray_menu(self):
        import pystray

        # Dynamic status text
        self._menu_status = pystray.MenuItem(
            lambda item: self._status_text(), None, enabled=False
        )

        # Dynamic record button text
        self._menu_record = pystray.MenuItem(
            lambda item: "Stop Recording" if self._is_recording else "Start Recording",
            self._tray_toggle_record,
        )

        # Recording Mode submenu
        mode_menu = pystray.Menu(
            pystray.MenuItem("Hold Key to Record", self._tray_set_mode_hold, checked=lambda item: self._mode == MODE_HOLD),
            pystray.MenuItem("Toggle On/Off", self._tray_set_mode_toggle, checked=lambda item: self._mode == MODE_TOGGLE),
        )

        # Whisper Model submenu
        model_menu = pystray.Menu(
            *[pystray.MenuItem(m, self._tray_change_model, checked=lambda item, mn=m: self.config.get("whisper_model", "base") == mn) for m in ["tiny", "base", "small", "medium"]]
        )

        # default=True routes the tray icon's LEFT-click to this item's
        # callback instead of opening the right-click menu. It's still shown
        # at the top of the menu so users can also invoke it via right-click.
        self._menu_open_popover = pystray.MenuItem(
            "Open Flume", self._tray_open_popover, default=True,
        )

        self._menu_items = pystray.Menu(
            self._menu_open_popover,
            self._menu_status,
            self._menu_record,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Verbal", self._tray_open_dashboard),
            pystray.MenuItem("Open Canvas", self._tray_open_canvas),
            pystray.MenuItem("Open Notes", self._tray_open_notes),
            pystray.MenuItem("Settings...", self._tray_open_settings),
            pystray.MenuItem("Recording Mode", mode_menu),
            pystray.MenuItem("Whisper Model", model_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: self._auth_menu_label(), self._tray_toggle_auth),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: f"Verbal v{APP_VERSION}", self._tray_about),
            pystray.MenuItem("Quit", self._tray_quit),
        )

        return self._menu_items

    def start(self):
        logger.info(f"=== VERBAL v{APP_VERSION} STARTING (Windows) ===")
        self._start_hotkey()
        threading.Thread(target=self._check_update, daemon=True).start()
        threading.Thread(target=self._presence_loop, daemon=True).start()

        import pystray

        icon_image = self._create_icon_image(False)
        self._tray_icon = pystray.Icon(
            "Verbal", icon_image,
            f"Verbal v{APP_VERSION}",
            menu=self._build_tray_menu(),
        )

        # W3: pywebview must own the process main thread (its guard is a
        # thread-name check — webview/__init__.py:168 rejects any thread
        # not named "MainThread"). So the tray runs on a background thread
        # and pywebview blocks on main. The recording overlay is now
        # tkinter (real transparency; WebView2 can't do per-pixel alpha),
        # so it owns its own tk mainloop on another thread — that means
        # we need a hidden pywebview anchor window here to keep the
        # webview loop alive until a real user-visible window (dashboard,
        # popover, meeting) is created.
        tray_thread = threading.Thread(
            target=self._tray_icon.run, name="tray", daemon=True)
        tray_thread.start()

        # Tkinter overlay on its own thread.
        self.overlay.setup()
        # Autolearn confirm pill is also tkinter-hosted now (real
        # transparency, no WebView2 canvas). Start its mainloop up-front
        # so show() has a live tk.Tk to talk to.
        try:
            self.autolearn_widget.setup()
        except Exception as e:
            logger.debug(f"autolearn_widget.setup failed: {e}")

        # Hidden pywebview anchor so webview.start() has at least one
        # window (its hard requirement) and the loop keeps running for
        # later create_window() calls from the tray callbacks.
        try:
            import webview
            self._webview_anchor = webview.create_window(
                "VerbalAnchor", html="<html><body></body></html>",
                width=1, height=1, x=-32000, y=-32000,
                frameless=True, on_top=False, hidden=True,
            )
        except Exception as e:
            logger.error(f"webview anchor create failed: {e}", exc_info=True)
            self._webview_anchor = None

        # Auto-open the dashboard shortly after the webview loop is running
        # so Verbal shows up as a normal taskbar app (not just tray-only).
        # Users can close/minimize it like any Windows app; the tray icon
        # stays so it can be re-opened later. Skipped if the user has
        # explicitly opted out via config.
        def _open_dashboard_on_start():
            try:
                if self.config.get("open_dashboard_on_launch", True):
                    self.dashboard.show()
            except Exception as e:
                logger.debug(f"auto-open dashboard failed: {e}")

        try:
            import webview
            webview._verbal_started = True
            # pywebview runs `func` on a background thread once the GUI loop
            # is up — perfect place to trigger the first create_window() so
            # the taskbar entry appears at launch.
            webview.start(func=_open_dashboard_on_start, debug=False)
        except Exception as e:
            logger.error(f"webview.start failed on main thread: {e}", exc_info=True)
            # Fail-closed: if the GUI loop can't run, keep the tray alive so
            # dictation still works. Block until the tray exits.
            tray_thread.join()

    def _create_icon_image(self, recording: bool):
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        color = (232, 82, 42, 255) if recording else (242, 239, 233, 255)
        draw.ellipse([4, 4, 28, 28], fill=color)
        draw.ellipse([10, 8, 22, 20], fill=(26, 25, 23, 255))
        draw.rectangle([14, 20, 18, 26], fill=(26, 25, 23, 255))
        return img

    def _status_text(self):
        return f"{self._total_transcriptions} transcriptions | {self._total_words} words"

    def _update_tray_menu(self):
        try:
            if self._tray_icon and self._menu_status:
                self._tray_icon.update_menu()
        except Exception:
            pass

    def _update_tray_icon(self, recording: bool):
        try:
            if self._tray_icon:
                self._tray_icon.icon = self._create_icon_image(recording)
                self._tray_icon.title = "Verbal - Recording..." if recording else f"Verbal v{APP_VERSION}"
        except Exception:
            pass

    # ── Tray menu callbacks ─────────────────────────────────────────────
    def _tray_toggle_record(self, icon=None, item=None):
        self._toggle_recording()

    def _tray_open_popover(self, icon=None, item=None):
        """Left-click default: open the compact Flume popover.

        Marked as pystray's default menu item so a left-click on the tray icon
        invokes this instead of showing the right-click menu. Right-click still
        shows the full menu."""
        try:
            self.popover.toggle()
        except Exception as e:
            logger.error(f"popover toggle failed: {e}", exc_info=True)

    def _tray_open_dashboard(self, icon=None, item=None):
        self.dashboard.show()

    def _tray_open_canvas(self, icon=None, item=None):
        self.dashboard.show()
        self.dashboard._on_tab_select(3)

    def _tray_open_notes(self, icon=None, item=None):
        self.dashboard.show()
        self.dashboard._on_tab_select(5)

    def _tray_open_settings(self, icon=None, item=None):
        self.dashboard.show()
        self.dashboard._on_tab_select(4)

    def _tray_set_mode_hold(self, icon=None, item=None):
        self._mode = MODE_HOLD
        self.config["recording_mode"] = MODE_HOLD
        save_config(self.config)
        self._update_tray_menu()

    def _tray_set_mode_toggle(self, icon=None, item=None):
        self._mode = MODE_TOGGLE
        self.config["recording_mode"] = MODE_TOGGLE
        save_config(self.config)
        self._update_tray_menu()

    def _tray_change_model(self, icon=None, item=None):
        if item is None:
            return
        model_name = str(item.text if hasattr(item, 'text') else item)
        self.config["whisper_model"] = model_name
        save_config(self.config)
        self._update_tray_menu()

    def _tray_quit(self, icon=None, item=None):
        if self._tray_icon:
            self._tray_icon.stop()
        sys.exit(0)

    def _tray_about(self, icon=None, item=None):
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            f"Verbal v{APP_VERSION}",
            "Voice to text, instantly.\n\n"
            "Hold Right Alt to record (Hold mode)\n"
            "or press once to start/stop (Toggle mode).\n"
            "Press ESC to cancel anytime.\n\n"
            "Powered by Whisper + Gemini"
        )
        root.destroy()

    # ── Google auth ───────────────────────────────────────────────────────
    def _auth_menu_label(self):
        """Dynamic tray label reflecting the current sign-in state."""
        try:
            u = auth.current_user()
            if u:
                return f"Sign out ({u.get('email', 'account')})"
        except Exception:
            pass
        return "Sign in with Google"

    def _update_auth_menu(self):
        """Refresh the tray so the auth item picks up the new state."""
        self._update_tray_menu()

    def _tray_toggle_auth(self, icon=None, item=None):
        try:
            if auth.current_user():
                self._sign_out()
            else:
                self._sign_in()
        except Exception as e:
            logger.error(f"Auth toggle failed: {e}")

    def _sign_in(self, _=None):
        """Kick off Google sign-in. The PKCE loopback server blocks, so the whole
        flow runs on a daemon thread — the tray/GUI never freezes. Fail-closed."""
        def work():
            try:
                a = auth.sign_in_with_google()
                self._on_main(lambda: self._after_sign_in(a))
            except Exception as e:
                logger.error(f"Sign-in failed: {e}")
        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception as e:
            logger.error(f"Sign-in dispatch failed: {e}")

    def _after_sign_in(self, auth_info):
        try:
            self.config = load_config()  # picks up sync_user_id set during sign-in
        except Exception as e:
            logger.error(f"Reload config after sign-in failed: {e}")
        self._update_auth_menu()
        # Detect other signed-in devices off the UI path, then finish.
        def detect():
            others = []
            try:
                import platform
                from app.sync import fetch_devices
                others = fetch_devices(auth_info.get("user_id", ""), platform.node()) or []
            except Exception as e:
                logger.debug(f"device detect failed: {e}")
            self._on_main(lambda: self._finish_sign_in(others))
        try:
            threading.Thread(target=detect, daemon=True).start()
        except Exception as e:
            logger.error(f"device detect dispatch failed: {e}")
            self._finish_sign_in([])

    def _finish_sign_in(self, others):
        """Enable + (re)start sync after sign-in, then refresh the dashboard.

        Unlike the Mac app (which pops a modal asking whether to sync when other
        devices exist) we default sync ON — the tray has no clean modal moment —
        while still logging any detected devices. Fully fail-closed."""
        try:
            if others:
                names = ", ".join(d.get("device_name", "a device") for d in others[:3])
                logger.info(f"Account already signed in on: {names}")
            self.config["sync_enabled"] = True
            save_config(self.config)
        except Exception as e:
            logger.error(f"finish_sign_in config write failed: {e}")
        try:
            self._restart_sync()
        except Exception as e:
            logger.error(f"finish_sign_in sync restart failed: {e}")
        self._update_auth_menu()
        try:
            self.dashboard.show()  # bring Flume to the front after sign-in
            self.dashboard._refresh()
        except Exception as e:
            logger.debug(f"dashboard refresh after sign-in skipped: {e}")

    def _sign_out(self, _=None):
        try:
            # Stop ACTIVE work first (IDI-170) — mirrors main._sign_out. The
            # Windows build has no MeetingManager yet (meetings are a macOS
            # feature, see WINDOWS_PARITY_PLAN.md W6), so this is a guarded
            # no-op here and becomes live the moment `self.meetings` exists.
            try:
                meetings = getattr(self, "meetings", None)
                if meetings and meetings.active:
                    meetings.stop_async()
            except Exception as e:
                logger.debug(f"meeting stop on sign-out skipped: {e}")
            if self._sync:
                try:
                    self._sync.stop()
                except Exception:
                    pass
                self._sync = None
            auth.sign_out()   # clears sync_user_id + deletes our devices row
            self.config = load_config()
        except Exception as e:
            logger.error(f"Sign-out failed: {e}")
        self._update_auth_menu()
        try:
            self.dashboard._refresh()
        except Exception as e:
            logger.debug(f"dashboard refresh after sign-out skipped: {e}")

    # ── Hotkey ─────────────────────────────────────────────────────────
    def _start_hotkey(self):
        """MER-41: replace the inline pynput.Listener with WinHotkeyListener
        so `hotkey_listener.set_transform(...)` (used by
        shared_dashboard.set_transform_hotkey) has a real seat, and the
        Transform chord (Ctrl+Shift+T) is detected without touching the
        dictation path."""
        from app.win_hotkey import WinHotkeyListener

        # `MODE_TOGGLE` matches the value the pill uses; WinHotkeyListener
        # takes the exact same strings the Mac HotkeyListener does.
        self.hotkey_listener = WinHotkeyListener(
            on_start=self._on_record_start,
            on_stop=self._on_record_stop,
            on_toggle=self._toggle_recording,
            on_esc=self._on_esc_pressed,
            hold_key=self.config.get("hotkey_hold", "alt_r"),
            toggle_key=self.config.get("hotkey_toggle", "alt_r"),
            mode=self._mode,
            on_transform=self._on_transform_hotkey,
            transform_key=self.config.get("transform_hotkey_label", "T"),
        )
        self.hotkey_listener.start()
        # Keep the legacy private name in sync so other call sites that
        # still reference `_hotkey_listener` don't break.
        self._hotkey_listener = self.hotkey_listener

        # Start periodic cleanup timer
        self._cleanup_timer = None
        self._start_cleanup_timer()

    def _start_cleanup_timer(self):
        """Start a periodic cleanup timer to prevent resource accumulation"""
        try:
            if self._cleanup_timer:
                self._cleanup_timer.cancel()
        except:
            pass

        def cleanup_callback():
            try:
                # Perform periodic cleanup
                import gc
                gc.collect()
                logger.debug("Periodic cleanup completed")
            except Exception as e:
                logger.debug(f"Periodic cleanup error: {e}")
            finally:
                # Schedule next cleanup
                self._start_cleanup_timer()

        # Schedule cleanup every 5 minutes
        import threading
        self._cleanup_timer = threading.Timer(300.0, cleanup_callback)
        self._cleanup_timer.daemon = True
        self._cleanup_timer.start()

    def _update_hotkeys(self):
        try:
            if getattr(self, "hotkey_listener", None) is not None:
                self.hotkey_listener.stop()
            self._start_hotkey()
        except Exception as e:
            logger.error(f"Failed to update hotkeys: {e}")

    def capture_next_key(self, timeout=20.0, allow_modifiers=True):
        """MER-41: Windows equivalent of main.py::capture_next_key. Blocks
        until the user presses a single key (or times out) and returns
        {'keycode': <pynput-key-name>, 'label': <display>, 'modifier': bool}.
        Used by shared_dashboard's Transform / dictation hotkey picker.

        The running WinHotkeyListener is suspended while we capture so the
        current dictation key doesn't fire the recorder while the user is
        just picking a replacement."""
        import threading as _t
        try:
            from pynput import keyboard
        except Exception as e:
            logger.error("capture_next_key: pynput import failed: %s", e)
            return None

        result = {}
        done = _t.Event()
        self._capturing_key = True

        # Suspend the running listener so its dictation-key handlers don't
        # fire during capture.
        running = getattr(self, "hotkey_listener", None)
        was_running = running is not None
        if was_running:
            try:
                running.stop()
            except Exception:
                pass

        def key_name(key):
            """Best-effort persistable name that _parse_key round-trips."""
            try:
                if hasattr(key, "name") and key.name:
                    return key.name              # e.g. 'alt_r', 'space'
                ch = getattr(key, "char", None)
                if ch:
                    return ch
            except Exception:
                pass
            return None

        def display_label(key, name):
            """Short human label for the settings pill."""
            if name is None:
                return "?"
            if len(name) == 1:
                return name.upper()
            return name.replace("_", " ").title()

        modifier_keys = {
            keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r,
            keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
            keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r,
            keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
        }
        # alt_gr exists on Windows layouts.
        for opt in ("alt_gr",):
            k = getattr(keyboard.Key, opt, None)
            if k is not None:
                modifier_keys.add(k)

        def on_press(key):
            try:
                if key == keyboard.Key.esc:
                    done.set()
                    return False
                is_mod = key in modifier_keys
                if is_mod and not allow_modifiers:
                    return                       # keep listening
                name = key_name(key)
                if not name:
                    return
                result.update(keycode=name,
                              label=display_label(key, name),
                              modifier=is_mod)
                done.set()
                return False
            except Exception:
                done.set()
                return False

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()
        logger.info("capture_next_key armed (timeout %.0fs, allow_modifiers=%s)",
                    timeout, allow_modifiers)
        done.wait(timeout)
        try:
            listener.stop()
        except Exception:
            pass

        # Restart the normal hotkey listener so dictation resumes.
        if was_running:
            try:
                self._start_hotkey()
            except Exception as e:
                logger.error("capture_next_key: hotkey restart failed: %s", e)

        # Small grace so the captured keypress can't double-fire the new binding.
        _t.Timer(0.4,
                 lambda: setattr(self, "_capturing_key", False)).start()

        logger.info("capture_next_key result: %s", result or "none")
        return result if result.get("keycode") is not None else None

    def _on_transform_hotkey(self):
        """MER-41 Mode B — Ctrl+Shift+T on Windows. Captures the current
        selection off-thread (clipboard swap), then shows the Transform
        pill. Never enters the dictation core, always fails closed to a
        silent no-op."""
        try:
            if not self.config.get("transform_enabled"):
                # Silent no-op is confusing — flash a brief hint on the
                # overlay so the user knows the hotkey was received but
                # Transform is off in Settings.
                logger.info("Transform hotkey fired but transform_enabled=False")
                try:
                    self.overlay.show_briefly(
                        "Turn on Transform in Settings first", duration=2.0)
                except Exception:
                    pass
                return
            if not self.config.get("transform_selection_enabled", True):
                logger.info("Transform hotkey fired but selection mode disabled")
                try:
                    self.overlay.show_briefly(
                        "Selection Transform is off in Settings", duration=2.0)
                except Exception:
                    pass
                return
            if self._is_recording:
                return
            widget = self.transform_widget
            if widget is not None and widget.visible:
                self._on_main(widget.hide)
                return
            # One capture at a time — overlapping captures each clear the
            # clipboard while another is polling it, so they destroy each
            # other's results (the "inconsistent" first-try failures).
            if getattr(self, "_tf_capture_inflight", False):
                return
            self._tf_capture_inflight = True

            def bg():
                try:
                    from app import transform as _tf
                    sel = _tf.capture_selection()
                    if not sel:
                        # No text selected — silent no-op is confusing; hint
                        # so the user knows what's needed.
                        logger.info("Transform: capture_selection returned empty (nothing selected?)")
                        try:
                            self.overlay.show_briefly(
                                "Select text first, then press Ctrl+Shift+T",
                                duration=2.0)
                        except Exception:
                            pass
                        return
                    logger.info("Transform: captured %d chars, opening pill", len(sel))
                    def ui():
                        try:
                            if self.transform_widget is None:
                                from app.win_transform_widget import (
                                    WinTransformWidget)
                                self.transform_widget = WinTransformWidget(self)
                            self.transform_widget.show(sel)
                        except Exception as e:
                            logger.error(f"transform pill failed: {e}", exc_info=True)
                    self._on_main(ui)
                except Exception as e:
                    logger.error(f"transform capture failed: {e}", exc_info=True)
                finally:
                    self._tf_capture_inflight = False
            threading.Thread(target=bg, daemon=True).start()
        except Exception as e:
            self._tf_capture_inflight = False
            logger.debug(f"_on_transform_hotkey failed closed: {e}")

    # ── Recording pipeline ────────────────────────────────────────────────
    def _toggle_recording(self):
        if self._is_recording:
            self._on_record_stop()
        else:
            self._on_record_start()

    def _on_esc_pressed(self):
        if self._processing:
            self._cancel_flag.set()
            self._reset_to_ready()
        elif self._is_recording:
            self._cancel_recording()

    def _on_record_start(self):
        if self._processing:
            return
        try:
            from app.win_injector import save_focused_app, get_focused_app_pid
            save_focused_app()
        except Exception:
            pass
        # Kick off the UIA harvest off-thread if file-tagging is on. Runs
        # WHILE the user speaks so seen-files memory is populated by the
        # time we build the Whisper prompt. Fail-closed: any exception here
        # must not block the recorder.
        try:
            if self.config.get("filetag_enabled", False):
                from app import win_ax
                from app.win_injector import get_focused_app_bundle, get_focused_app_name
                if win_ax.supported_ide(
                        get_focused_app_bundle(), get_focused_app_name()):
                    pid = get_focused_app_pid()
                    if pid:
                        win_ax.harvest_async(pid, self.config, save_config)
        except Exception as e:
            logger.debug(f"filetag harvest kickoff skipped: {e}")
        self._cancel_flag.clear()
        try:
            self.recorder.start()
        except Exception as e:
            logger.error(f"Failed to start recording: {e}", exc_info=True)
            return
        self._is_recording = True
        _play_sound("start")
        self._update_tray_icon(True)
        self._update_tray_menu()
        self.overlay.show("Listening...")
        self.dashboard.update_recording_state(True)

    def _on_record_stop(self):
        if not self._is_recording:
            return
        self._is_recording = False
        audio = self.recorder.stop()
        _play_sound("stop")
        self._update_tray_icon(False)
        self._update_tray_menu()
        self.dashboard.update_recording_state(False)

        # Minimum ~1.0s of audio to avoid accidental clicks / hallucinations —
        # matches the Mac semantics. The shared Recorder captures at the mic's
        # NATIVE rate (typically 48kHz), not 16kHz, so derive the sample count
        # from the actual sample_rate rather than a hard-coded 16k constant.
        min_samples = int(self.recorder.sample_rate * 1.0)
        if audio is None or len(audio) < min_samples:
            self.overlay.hide()
            return

        self._processing = True
        self.overlay.update_status("Transcribing...")
        threading.Thread(target=self._process_audio, args=(audio,), daemon=True).start()

    def _cancel_recording(self):
        self._is_recording = False
        self.recorder.stop()
        _play_sound("stop")
        self._reset_to_ready()

    def _transcribe_with_retry(self, audio, attempts=3):
        """Transcribe, auto-retrying on 'failed' (transient network/API) with a
        short backoff. Returns (text, status). Silence returns immediately.
        Mirrors main.py:_transcribe_with_retry."""
        text, status = "", "failed"
        for i in range(attempts):
            if self._cancel_flag.is_set():
                return "", "silent"
            try:
                text, status = transcribe_with_status(
                    audio, self.config, self.recorder.sample_rate)
            except Exception as e:
                logger.error(f"Transcription attempt {i+1} raised: {e}")
                text, status = "", "failed"
            if status in ("ok", "silent"):
                return text, status
            if i < attempts - 1:
                logger.warning(f"Transcription failed (attempt {i+1}) — retrying…")
                time.sleep(1.5 * (i + 1))
        return text, status

    def _refresh_dashboards(self):
        try:
            self.dashboard._refresh()
        except Exception:
            pass

    def _history_entry(self, entry_id):
        for e in self.config.get("history", []):
            if isinstance(e, dict) and e.get("id") == entry_id:
                return e
        return None

    def _upload_recording_async(self, rec_id, local_path):
        """Upload the WAV to the cloud + attach its URL to the history entry.
        Fail-closed peripheral — never blocks or breaks the pipeline."""
        def work():
            try:
                user_id = self.config.get("sync_user_id", "")
                # Capture artifact → gated on being signed in (cloud_allowed),
                # not on the `sync_enabled` toggle (IDI-170/171).
                if not user_id or not local_path or not auth.cloud_allowed(self.config):
                    return
                url = recordings.upload_cloud(local_path, user_id, rec_id)
                if url:
                    self.config = update_history_entry(self.config, rec_id, audio_url=url)
                    # IDI-172: patch the already-pushed row so other devices get
                    # the audio too.
                    try:
                        entry = self._history_entry(rec_id) or {}
                        if self._sync and entry.get("sync_id"):
                            self._sync.update_pushed_audio_url(entry["sync_id"], url)
                    except Exception as e:
                        logger.debug(f"audio_url sync patch skipped: {e}")
                    self._on_main(self._refresh_dashboards)
            except Exception as e:
                logger.debug(f"recording upload failed: {e}")
        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception as e:
            logger.debug(f"recording upload dispatch failed: {e}")

    def _process_audio(self, audio):
        # Save the recording locally FIRST (playback backup + retry cache), same
        # as the Mac app. Fail-closed: a save failure leaves audio_path=None and
        # never blocks transcription/injection.
        rec_id = recordings.new_id()
        try:
            audio_path = recordings.save_wav(audio, self.recorder.sample_rate, rec_id)
            logger.info(f"Recording saved: {audio_path} (id={rec_id})")
        except Exception as e:
            logger.error(f"save_wav failed: {e}")
            audio_path = None

        try:
            if self._cancel_flag.is_set():
                return

            from app.win_injector import get_focused_app_name

            text, status = self._transcribe_with_retry(audio)
            if self._cancel_flag.is_set():
                return

            # "silent" — empty/too-short audio. Discard the WAV, tell the user.
            if status == "silent":
                logger.warning("No speech detected — discarding recording")
                if audio_path:
                    try:
                        os.remove(audio_path)
                    except Exception:
                        pass
                try:
                    self.overlay.show_briefly("No speech detected. Speak louder!", duration=1.5)
                except Exception:
                    pass
                self._reset_to_ready()
                return

            # "failed" — network/API down. Keep the audio + a retryable entry.
            if status == "failed":
                logger.error("Transcription failed after retries — saved for retry")
                try:
                    self.config = add_to_history(
                        self.config, "", get_focused_app_name(),
                        entry_id=rec_id, audio=audio_path or "", status="failed")
                except Exception as e:
                    logger.error(f"failed-entry write failed: {e}")
                self._upload_recording_async(rec_id, audio_path)
                try:
                    self.overlay.show_briefly("Transcription failed — retry from History", duration=2.0)
                except Exception:
                    pass
                self._reset_to_ready()
                self._refresh_dashboards()
                return

            # MER-41 Transform Mode A (inline): a trailing "…so Flume,
            # <instruction>" transforms the dictated body instead of
            # formatting it. Fully guarded — any miss/failure falls through
            # to the normal process_text path so a Transform hiccup never
            # blocks record → transcribe → inject.
            result = None
            transform_note = None
            try:
                if (self.config.get("transform_enabled")
                        and self.config.get("transform_inline_enabled", True)):
                    from app import transform as _tf
                    det = _tf.detect_trailing_instruction(
                        text, self.config.get("transform_trigger_words"))
                    if det:
                        body, instruction = det
                        rewritten = _tf.apply_instruction(body, instruction, self.config)
                        if rewritten:
                            result = rewritten
                            transform_note = instruction
                            logger.info(
                                "transform inline applied: %r", instruction[:60])
            except Exception as e:
                logger.debug(f"transform inline skipped: {e}")

            if result is None:
                # Phase-0 context grounding (MER-44): pass the target window title
                # (Windows has no bundle id) so the cleanup LLM grounds on it + the
                # user's dictionary terms. Only the formatting path takes it — a
                # Transform rewrite carries its own instruction.
                result = process_text(text, self.config,
                                      active_app=get_focused_app_name())
            if self._cancel_flag.is_set():
                return

            # Expand spoken snippet triggers into their saved text. Runs AFTER AI
            # cleanup and immediately BEFORE injection — the same point the Mac
            # app applies it. Fully guarded / fail-closed: any error leaves the
            # transcription untouched and never breaks the pipeline.
            try:
                from app import dictionary
                result = dictionary.apply_snippets(result, self.config, save_config)
            except Exception as e:
                logger.debug(f"apply_snippets skipped: {e}")

            try:
                self.config = add_to_history(
                    self.config, result, get_focused_app_name(),
                    entry_id=rec_id, audio=audio_path or "", status="done")
            except Exception as e:
                logger.error(f"history write failed: {e}")
            word_count = len(result.split())
            self._total_transcriptions += 1
            self._total_words += word_count
            try:
                self.config = update_daily_words(self.config, word_count)
            except Exception:
                pass
            self._update_tray_menu()

            self.overlay.hide()
            time.sleep(0.3)

            if self._cancel_flag.is_set():
                return

            from app.win_injector import inject_text
            success = inject_text(
                result,
                allow_mentions=self.config.get("filetag_enabled", False),
            )
            _play_sound("done")

            # Show the split (TRANSFORM_SWARM.md P1.3): surface what was
            # read as the instruction so a wrong split is catchable and
            # retryable. Only fires on the inline-transform path.
            if transform_note:
                note = (transform_note if len(transform_note) <= 44
                        else transform_note[:41] + "…")
                try:
                    self.overlay.show_briefly("✦ Transformed · " + note, 2.5)
                except Exception:
                    pass

            # W7: arm the UIA edit-watcher AFTER injection so a user
            # correction to the just-pasted text triggers the autolearn
            # confirm pill. Guarded end-to-end — if UIA can't read the
            # target field, or the classification decides against offering,
            # the watcher silently drops the event. Never blocks the
            # pipeline (watch runs on its own daemon thread).
            try:
                if success and self.config.get("autolearn_enabled", True):
                    from app.win_editwatch import EditWatcher
                    from app.win_injector import (
                        get_focused_app_pid, get_focused_app_bundle)
                    self._edit_watcher = EditWatcher()
                    self._edit_watcher.arm(
                        pid=get_focused_app_pid(),
                        bundle=get_focused_app_bundle(),
                        inserted_text=result,
                        on_decision_callback=self._on_autolearn_decision,
                    )
            except Exception as e:
                logger.debug(f"autolearn arm failed: {e}")

            # Push to other devices if sync is enabled
            if self._sync:
                target = self.dashboard._target_device_id if self.dashboard else "__all__"
                if target not in (None, "__none__"):
                    # "__all__" = broadcast (None), else = specific device_id
                    push_target = None if target == "__all__" else target
                    # Full push shape (IDI-172) — audio_url normally lands later
                    # via _upload_recording_async's patch.
                    entry = self._history_entry(rec_id) or {}
                    threading.Thread(
                        target=self._sync.push,
                        args=(result, push_target, entry.get("audio_url") or "",
                              "done", rec_id),
                        daemon=True,
                    ).start()

            # Upload the audio to the cloud + attach its URL (async, fail-closed).
            self._upload_recording_async(rec_id, audio_path)

            # TODO (Windows parity, later workstreams): AX file-tagging, autolearn
            # edit-watch, and meeting mic-tap sharing are intentionally not wired
            # here yet (macOS-only for now).

            brief = f"Pasted | {word_count}w" if success else f"Copied | {word_count}w"
            self.overlay.show_briefly(brief, duration=2.0)
            self.dashboard.show_result(result)

        except Exception as e:
            logger.critical(f"PROCESS CRASH: {e}\n{traceback.format_exc()}")
            try:
                self.overlay.show_briefly("Error occurred", duration=2.0)
            except:
                pass
            self._reset_to_ready()
        finally:
            self._processing = False

    # ── Meetings (W6) ────────────────────────────────────────────────────
    def _meeting_win(self):
        """Lazy meeting window; fails closed to None (mirrors main.py::_meeting_win)."""
        if self.meeting_window is None:
            try:
                from app.win_meeting_window import WinMeetingWindow
                self.meeting_window = WinMeetingWindow(self)
            except Exception as e:
                logger.warning("meeting window unavailable (%s)", e)
        return self.meeting_window

    def _meeting_hud(self):
        """Lazy meeting HUD; fails closed to None."""
        if self.meeting_hud is None:
            try:
                from app.win_meeting_hud import WinMeetingHud
                self.meeting_hud = WinMeetingHud(self)
            except Exception as e:
                logger.warning("meeting HUD unavailable (%s)", e)
                self.meeting_hud = None
        return self.meeting_hud

    def _toggle_meeting(self, _=None):
        """Open the meeting checklist or pre-meeting modal (parity with
        main.py::_toggle_meeting). Called by DashboardApi.open_meeting_launcher."""
        try:
            if not self.meetings:
                return
            if self.meetings.active:
                win = self._meeting_win()
                if win:
                    self._on_main(lambda: win.show("live"))
                return

            def bg():
                try:
                    from app import permissions
                    ready = bool(permissions.meeting_permissions().get("ready"))
                except Exception:
                    ready = False
                skipped = bool(self.config.get("meetings_skipped_system_audio"))
                logger.info("meeting open: ready=%s skipped=%s", ready, skipped)
                if not ready and skipped:
                    ready = True

                def ui():
                    try:
                        win = self._meeting_win()
                        if win:
                            win.show("premeeting" if ready else "permissions")
                    except Exception as e:
                        logger.error("meeting show failed: %s", e)
                self._on_main(ui)
            threading.Thread(target=bg, daemon=True).start()
        except Exception as e:
            logger.error("start meeting failed: %s", e)

    # ── Autolearn (W7) ────────────────────────────────────────────────────
    def _on_autolearn_decision(self, decision):
        """Callback from EditWatcher — decision has already passed classify()
        + apply_observation_guard(). Show the confirm pill only when the
        Decision asks us to offer."""
        try:
            if not decision:
                return
            # The Decision dict shape is set by autolearn.classify; the Mac
            # side reads `action` == "offer" and pulls old/new. Anything else
            # (ignore/reject) is silently dropped.
            if decision.get("action") != "offer":
                return
            old = decision.get("old")
            new = decision.get("new")
            if not old or not new or old == new:
                return
            self._on_main(lambda: self.autolearn_widget.show(old, new))
        except Exception as e:
            logger.debug(f"autolearn decision handler failed: {e}")

    def _autolearn_result(self, old, new, added):
        """Widget callback — user clicked Add or dismissed. Record either
        way so we never nag again (autolearn F9); on Add, persist the
        dictionary rule and refresh dashboards."""
        try:
            from app import autolearn, dictionary
            cfg = self.config
            autolearn.record_offered(cfg, new, save_config)
            if added:
                dictionary.add_replacement(cfg, old, new, save_config, auto=True)
                self.config = cfg
                _play_sound("added") if False else _play_sound("done")
                # Refresh dashboards / popover so the new rule appears live.
                try:
                    self.dashboard.update_recording_state(self._is_recording)
                except Exception:
                    pass
                try:
                    self.popover._refresh()
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"autolearn result failed: {e}")

    def _reset_to_ready(self):
        self._processing = False
        self._is_recording = False
        # Must NOT clear `_cancel_flag` — `_on_esc_pressed` sets it and then
        # calls this, which used to wipe the cancel before the transcription
        # worker's next `is_set()` check and let the text paste anyway. Cleared
        # at recording start instead (IDI-178; mirrors main.py).
        try:
            self.recorder.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up recorder: {e}")
        self.overlay.hide()
        self._update_tray_icon(False)
        self._update_tray_menu()
        self.dashboard.update_recording_state(False)

    # ── Sync ──────────────────────────────────────────────────────────────
    PRESENCE_INTERVAL = 30

    def _presence_loop(self):
        """App-level device heartbeat (IDI-177) — see main._presence_loop.
        On Windows the presence upsert used to ride `SharedDashboard`'s
        `_device_refresh_loop`, which is only started by `dashboard.show()`,
        so a tray-only session never reported itself online at all. Fail-closed."""
        import platform
        while True:
            try:
                user = auth.current_user()
                if user:
                    from app.sync import register_device_presence
                    from app.config import get_device_id
                    device_id = (self._sync.device_id if self._sync
                                 else get_device_id(self.config))
                    register_device_presence(
                        user.get("user_id", ""), device_id,
                        self.config.get("sync_device_name") or platform.node())
            except Exception as e:
                logger.debug(f"presence heartbeat skipped: {e}")
            time.sleep(self.PRESENCE_INTERVAL)

    def _init_sync(self):
        if not self.config.get("sync_enabled"):
            return
        # IDI-170/171: never open a channel on an ex-account's user_id.
        if not auth.cloud_allowed(self.config):
            return
        user_id = self.config.get("sync_user_id", "").strip()
        if not user_id:
            return
        try:
            from app.sync import SyncClient
            device_name = self.config.get("sync_device_name", "Windows")
            from app.config import get_device_id
            self._sync = SyncClient(
                user_id=user_id,
                device_name=device_name,
                on_receive=self._on_sync_receive,
                on_tombstone=self._on_sync_tombstone,
                on_pushed=self._on_sync_pushed,
                device_id=get_device_id(self.config),
            )
            logger.info(f"Sync started for user {user_id[:8]}...")
        except Exception as e:
            logger.error(f"Sync init failed: {e}")

    def _restart_sync(self):
        if self._sync:
            try:
                self._sync.stop()
            except Exception:
                pass
            self._sync = None
        self._init_sync()

    def _this_device_id(self) -> str:
        import platform
        return self._sync.device_id if self._sync else platform.node()

    def _on_sync_receive(self, text: str, device_name: str, record: dict | None = None):
        """Mirrors main._on_sync_receive (IDI-172): ALWAYS append to local
        history + clipboard; auto-paste ONLY when this device was the explicit
        target. A broadcast must not type into whatever window has focus."""
        record = record or {}
        logger.info(f"Sync received from {device_name}: '{text[:40]}'")
        try:
            import pyperclip
            pyperclip.copy(text)
        except Exception as e:
            logger.debug(f"clipboard copy failed: {e}")

        try:
            entry_id = recordings.new_id()
            self.config = add_to_history(
                self.config, text, device_name or "Synced",
                entry_id=entry_id,
                audio_url=record.get("audio_url") or "",
                status=record.get("status") or "done")
            fields = {"device_name": device_name or "",
                      "created_at": record.get("created_at") or "",
                      "source": "sync"}
            if record.get("id"):
                fields["sync_id"] = record["id"]
            self.config = update_history_entry(self.config, entry_id, **fields)
            self._total_transcriptions += 1
            self._total_words += len(text.split())
            self._refresh_dashboards()
        except Exception as e:
            logger.error(f"Sync receive: could not save to history: {e}")

        target = record.get("target_device_id")
        if target and target == self._this_device_id():
            try:
                from app.win_injector import inject_text
                success = inject_text(text)
            except Exception as e:
                logger.error(f"Sync paste failed: {e}")
                success = False
            action = "pasted" if success else "copied"
            brief = f"From {device_name} | {len(text.split())}w - {action}"
        else:
            brief = f"From {device_name} | {len(text.split())}w - in History"
        try:
            self.overlay.show_briefly(brief, duration=2.5)
        except Exception:
            pass

    def _on_sync_tombstone(self, record: dict):
        """Another device deleted a history row — drop our copy (IDI-172)."""
        try:
            from app.sync import prune_local_history
            rid = (record or {}).get("id")
            if not rid:
                return
            history = self.config.get("history", [])
            pruned = prune_local_history(history, [rid])
            if len(pruned) != len(history):
                self.config["history"] = pruned
                save_config(self.config)
                self._total_transcriptions = len(pruned)
                self._refresh_dashboards()
        except Exception as e:
            logger.debug(f"tombstone prune failed: {e}")

    def _on_sync_pushed(self, entry_id: str, row_id: str):
        try:
            self.config = update_history_entry(self.config, entry_id, sync_id=row_id)
        except Exception as e:
            logger.debug(f"sync_id record failed: {e}")

    # ── Update check ──────────────────────────────────────────────────────
    def _check_update(self):
        # Only check for updates once per session to prevent resource exhaustion
        if hasattr(self, '_update_checked') and self._update_checked:
            return

        from app.updater import check_for_update, download_update, install_update
        update = check_for_update()
        self._update_checked = True  # Mark that we've checked

        if not update:
            return
        try:
            auto_update = self.config.get("auto_update", True)
            if auto_update:
                logger.info(f"Auto-update: downloading {update['version']}")
                self.overlay.show_briefly(f"Updating to v{update['version']}...", duration=3.0)
                path = download_update(update)
                if path:
                    install_update(path, silent=True)
                return

            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            changelog = update.get("changelog", "Bug fixes and improvements")
            resp = messagebox.askyesno(
                f"Verbal {update['version']} available",
                f"{changelog}\n\nDownload and install now?",
            )
            root.destroy()
            if resp:
                path = download_update(update)
                if path:
                    install_update(path)
        except Exception as e:
            logger.error(f"Update failed: {e}")


def _acquire_single_instance_mutex():
    """Prevent a second Verbal from running — the second instance stacks
    every window (tray icons, overlay pills) and steals the hotkey.

    Uses a Windows named mutex; the handle stays alive for the whole
    process lifetime (stashed on the sys module) so Windows releases it
    on exit. Returns True if we acquired the singleton, False if another
    Verbal is already running.

    NOTE: Must call kernel32.GetLastError() directly — `ctypes.get_last_error`
    only returns non-zero when the DLL was loaded with `use_last_error=True`,
    which `ctypes.windll.kernel32` is not."""
    import ctypes
    from ctypes import wintypes
    ERROR_ALREADY_EXISTS = 183
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.GetLastError.restype = wintypes.DWORD
    kernel32.GetLastError.argtypes = []
    handle = kernel32.CreateMutexW(None, False, "VerbalSingletonMutex_v1")
    if not handle:
        return True  # can't tell; let it run — mutex failure isn't fatal
    # CreateMutexW succeeds either way when the name pre-exists; the "already
    # running" signal is only in the LAST-ERROR field, so we MUST read it
    # BEFORE any other Win32 call has a chance to overwrite it.
    err = kernel32.GetLastError()
    if err == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    sys._verbal_singleton_mutex = handle
    return True


def main():
    import time
    sys._verbal_start_time = time.time()
    if not _acquire_single_instance_mutex():
        logger.info("Another Verbal instance is already running — exiting")
        return
    app = VerbalWinApp()
    app.start()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
