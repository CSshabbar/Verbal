import logging
import os
import sys
import time
import threading
import queue
import traceback
import faulthandler

faulthandler.enable()

import rumps

from app.config import (
    load_config, save_config, add_gemini_key, remove_gemini_key,
    add_to_history, update_history_entry, update_daily_words, get_daily_words,
    _entry_text, _entry_app, LOG_DIR, ensure_dirs,
)
from app.recorder import Recorder
from app.transcriber import transcribe, transcribe_with_status
from app import recordings
from app import auth
from app.ai_cleanup import process_text
from app.injector import (
    inject_text, save_focused_app, get_focused_app_name,
    get_focused_app_pid, get_focused_app_bundle,
)
from app.hotkey import HotkeyListener
from app.overlay import OverlayBar
from app.autolearn_widget import AutoLearnWidget
from app.sounds import play_start, play_stop, play_done, play_added
from app.dashboard import DashboardWindow           # legacy AppKit dashboard (fallback)
from app.flume_web_dashboard import FlumeWebDashboard
from app.flume_popover import FlumePopover
from app.canvas_window import CanvasWindow

ensure_dirs()  # ensure ~/.verbal/logs/ exists before FileHandler is created

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "app.log"),
    ],
)
logger = logging.getLogger("verbal")


def _exception_handler(exc_type, exc_value, exc_tb):
    logger.critical(f"UNHANDLED: {exc_type.__name__}: {exc_value}")
    logger.critical("".join(traceback.format_tb(exc_tb)))

sys.excepthook = _exception_handler


def _asset_path(filename):
    if getattr(sys, '_MEIPASS', None):
        return os.path.join(sys._MEIPASS, "assets", filename)
    return os.path.join(os.path.dirname(__file__), "..", "assets", filename)


ICON_PATH = _asset_path("icon.png")
ICON_ACTIVE_PATH = _asset_path("icon_active.png")

MODE_HOLD = "hold"
MODE_TOGGLE = "toggle"


class VerbalApp(rumps.App):
    def __init__(self):
        super().__init__("Verbal", icon=ICON_PATH, template=True)

        self.config = load_config()
        self.recorder = Recorder()
        self._is_recording = False
        self._mode = self.config.get("recording_mode", MODE_TOGGLE)
        self._ui_queue = queue.Queue()
        self._processing = False
        self._cancel_flag = threading.Event()
        self._last_toggle_time = 0.0

        self.overlay = OverlayBar(self)
        self.autolearn_widget = AutoLearnWidget(self)
        self._last_result_text = ""
        # Flume desktop dashboard (WKWebView). Falls back to the legacy AppKit
        # dashboard if the web view can't be created.
        try:
            self.dashboard = FlumeWebDashboard(self)
        except Exception as _e:
            logging.getLogger("verbal").warning("Flume web dashboard unavailable (%s); using AppKit", _e)
            self.dashboard = DashboardWindow(self)
        self.canvas    = CanvasWindow(self.config)

        # Flume menubar popover (WKWebView in an NSPopover). Optional — if it
        # can't be created the classic rumps menu is used unchanged.
        try:
            self.popover = FlumePopover(self)
        except Exception as _e:
            logging.getLogger("verbal").warning("Flume popover unavailable (%s)", _e)
            self.popover = None
        self._popover_hook_tries = 0

        history = self.config.get("history", [])
        self._total_transcriptions = len(history)
        self._total_words = sum(len(_entry_text(h).split()) for h in history)

        # Sync client — starts if sync is enabled in config
        self._sync = None
        self._init_sync()

        self.status_item = rumps.MenuItem(self._status_text(), callback=None)
        self.status_item.set_callback(None)

        self.record_btn = rumps.MenuItem("Start Recording", callback=self._toggle_recording)
        self.meeting_btn = rumps.MenuItem("Start Meeting", callback=self._toggle_meeting)
        self.signin_item = rumps.MenuItem("Sign in with Google", callback=self._sign_in)

        # Meetings (MEETINGS_DESIGN_HANDOFF.md) — manager + lazy window. Fails
        # closed: if construction fails, meetings are simply unavailable and
        # dictation is untouched (Rule #1).
        self.meetings = None
        self.meeting_window = None
        self.meeting_hud = None
        try:
            from app.meetings import MeetingManager
            self.meetings = MeetingManager(self)
            # Pre-warm the ScreenCaptureKit import off the critical path — its
            # cold import costs ~1 s and used to freeze the first "Start
            # Meeting" click.
            import threading as _threading

            def _warm():
                try:
                    from app import system_audio
                    system_audio.is_supported()
                except Exception:
                    pass
            _threading.Thread(target=_warm, daemon=True).start()
        except Exception as _e:
            logging.getLogger("verbal").warning("meetings unavailable (%s)", _e)
        self.reset_onb_item = rumps.MenuItem("Reset Onboarding (dev)", callback=self._reset_onboarding)

        mode_menu = rumps.MenuItem("Recording Mode")
        self.mode_hold = rumps.MenuItem("Hold Key to Record", callback=self._set_mode_hold)
        self.mode_toggle = rumps.MenuItem("Toggle On/Off", callback=self._set_mode_toggle)
        self.mode_hold.state = 1 if self._mode == MODE_HOLD else 0
        self.mode_toggle.state = 1 if self._mode == MODE_TOGGLE else 0
        mode_menu.add(self.mode_hold)
        mode_menu.add(self.mode_toggle)

        model_menu = rumps.MenuItem("Whisper Model")
        self.model_items = {}
        for m in ["tiny", "base", "small", "medium"]:
            item = rumps.MenuItem(m, callback=self._change_model)
            item.state = 1 if m == self.config.get("whisper_model", "medium.en") else 0
            self.model_items[m] = item
            model_menu.add(item)

        self.autodetect_item = rumps.MenuItem(
            "Auto-detect meetings", callback=self._toggle_meeting_autodetect)
        self.autodetect_item.state = 1 if self.config.get("meeting_autodetect", True) else 0

        self.menu = [
            self.status_item,
            self.record_btn,
            self.meeting_btn,
            self.autodetect_item,
            None,
            self.signin_item,
            self.reset_onb_item,
            None,
            rumps.MenuItem("Open Verbal", callback=self._open_dashboard),
            rumps.MenuItem("Open Canvas", callback=self._open_canvas),
            rumps.MenuItem("Open Notes", callback=self._open_notes),
            mode_menu,
            model_menu,
            None,
            rumps.MenuItem("About Verbal", callback=self._about),
        ]

        self.hotkey_listener = HotkeyListener(
            on_start=self._on_hotkey_press,
            on_stop=self._on_hotkey_release,
            on_toggle=self._on_hotkey_toggle,
            on_esc=self._on_esc_pressed,
            hold_key=self.config.get("hotkey_hold", 54),
            toggle_key=self.config.get("hotkey_toggle", 54),
            mode=self._mode,
            on_transform=self._on_transform_hotkey,
            transform_key=self.config.get("transform_hotkey", 17),
        )
        self.transform_widget = None      # lazy (TRANSFORM_SWARM.md Mode B)

        # Granola-style meeting auto-detection (macOS only). A window-scan poll pops
        # a non-activating "Meeting detected · <source>" pill; state tracks the call
        # currently being prompted so we ask once per call and reset when it ends.
        self.meeting_prompt = None        # lazy MeetingPrompt
        self._md_active_key = None        # the call key currently on screen
        self._md_handled = set()          # call keys already prompted/dismissed
        self._md_empty = 0                # consecutive polls with no call detected
        self._md_source = ""              # last detected source label
        self._md_scanning = False         # a background window scan is in flight
        self._meeting_detect_timer = rumps.Timer(self._detect_meeting_tick, 5.0)

        self._ui_timer = rumps.Timer(self._drain_ui_queue, 0.1)
        # attaches the popover to the status item once rumps has created it
        self._popover_hook_timer = rumps.Timer(self._install_popover_hook, 0.5)

    def _on_hotkey_toggle(self):
        """Called by HotkeyListener when the toggle key is pressed."""
        self._ui_queue.put(self._toggle_recording)

    def _update_hotkeys(self):
        """Update the hotkey listener with new keys from config."""
        if self.hotkey_listener:
            self.hotkey_listener.update_keys(
                self.config.get("hotkey_hold", 54),
                self.config.get("hotkey_toggle", 54)
            )

    def _status_text(self):
        return f"{self._total_transcriptions} transcriptions | {self._total_words} words"

    def _install_edit_menu(self):
        """rumps/menubar apps ship no standard Edit menu, so the system paste
        shortcut (Cmd+V — and Cmd+C/X/A/Z) never reaches the focused field: those
        shortcuts are delivered via the Edit menu's key equivalents down the
        responder chain. Without it, Cmd+V silently does nothing inside Verbal's
        own windows (dashboard/canvas/notes) even though right-click → Paste works.
        Build a minimal Edit menu so the shortcuts route to the WKWebView / text
        fields normally."""
        try:
            from AppKit import NSApplication, NSMenu, NSMenuItem
            app = NSApplication.sharedApplication()
            main_menu = app.mainMenu()
            if main_menu is None:
                main_menu = NSMenu.alloc().init()
                app.setMainMenu_(main_menu)
            # Don't add twice.
            for i in range(main_menu.numberOfItems()):
                sub = main_menu.itemAtIndex_(i).submenu()
                if sub and sub.title() == "Edit":
                    return
            edit_item = NSMenuItem.alloc().init()
            main_menu.addItem_(edit_item)
            edit_menu = NSMenu.alloc().initWithTitle_("Edit")
            edit_item.setSubmenu_(edit_menu)
            for title, action, key in (
                ("Undo", "undo:", "z"),
                ("Redo", "redo:", "Z"),
                (None, None, None),           # separator
                ("Cut", "cut:", "x"),
                ("Copy", "copy:", "c"),
                ("Paste", "paste:", "v"),
                ("Select All", "selectAll:", "a"),
            ):
                if title is None:
                    edit_menu.addItem_(NSMenuItem.separatorItem())
                    continue
                it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
                edit_menu.addItem_(it)
            logger.info("Edit menu installed (Cmd+C/V/X/A/Z)")
        except Exception as e:
            logger.warning(f"Could not install Edit menu: {e}")

    def _start_app(self, _=None):
        logger.info("Starting Verbal")
        self.overlay.setup()
        self.hotkey_listener.start()
        self._ui_timer.start()
        if self.popover:
            self._popover_hook_timer.start()
        # Poll for calls in progress (Granola-style prompt). Meetings-only, macOS-only;
        # fails closed — a detection error never touches dictation/capture.
        if self.meetings:
            self._meeting_detect_timer.start()
        threading.Thread(target=self._preload_model, daemon=True).start()
        threading.Thread(target=self._check_update, daemon=True).start()
        threading.Thread(target=self._load_dictionary_once, daemon=True).start()

        # Request accessibility permission on first launch
        from app.injector import request_accessibility
        try:
            request_accessibility()
        except Exception as e:
            logger.warning(f"Accessibility check: {e}")

        self.dashboard.show()
        from AppKit import NSApplication
        NSApplication.sharedApplication().setActivationPolicy_(0)
        self._install_edit_menu()

        # Reflect sign-in state + offer sign-in once on first run.
        self._update_auth_menu()
        if not auth.current_user() and not self.config.get("welcomed"):
            self.config["welcomed"] = True
            save_config(self.config)
            r = rumps.alert(
                title="Welcome to Verbal",
                message=("Sign in with Google to save your dictation, notes and canvas "
                         "to the cloud and sync them across your devices."),
                ok="Sign in with Google", cancel="Later")
            if r == 1:
                self._sign_in()

    def _load_dictionary_once(self):
        """Pull the custom dictionary from the cloud once at startup (best-effort)."""
        try:
            from app import dictionary
            dictionary.fetch_remote(self.config, save_config)
        except Exception as e:
            logger.debug(f"dictionary load failed: {e}")

    def _preload_model(self):
        # Cloud transcription is primary — local model loads on first fallback use
        logger.info("Transcription: Groq (primary) -> Gemini (fallback) -> Local Whisper")

    def _init_sync(self):
        """Start sync client if enabled in config."""
        if not self.config.get("sync_enabled"):
            return
        user_id = self.config.get("sync_user_id", "").strip()
        if not user_id:
            logger.info("Sync: no user_id configured, skipping")
            return
        try:
            from app.sync import SyncClient
            device_name = self.config.get("sync_device_name", "") or "Mac"
            self._sync = SyncClient(
                user_id=user_id,
                device_name=device_name,
                on_receive=self._on_sync_receive,
            )
            logger.info(f"Sync started for user {user_id[:8]}...")
        except Exception as e:
            logger.error(f"Sync init failed: {e}")

    def _on_sync_receive(self, text: str, device_name: str):
        """Called when another device pushes a transcription."""
        import pyperclip
        pyperclip.copy(text)
        logger.info(f"Sync received from {device_name}: '{text[:40]}'")
        brief = f"📱 {device_name} · {len(text.split())}w"
        self._on_main(lambda: self._paste_synced(text, brief))

    def _paste_synced(self, text: str, brief: str):
        """Paste synced text into the currently focused app."""
        try:
            from app.injector import inject_text
            inject_text(text)
            self.overlay.show_briefly(brief, duration=2.5)
        except Exception as e:
            logger.error(f"Sync paste failed: {e}")

    def _drain_ui_queue(self, _):
        for _ in range(20):
            try:
                fn = self._ui_queue.get_nowait()
                fn()
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"UI queue error: {e}\n{traceback.format_exc()}")

    def _on_main(self, fn):
        self._ui_queue.put(fn)

    def _install_popover_hook(self, timer):
        """Attach the Flume popover to the status-bar button once rumps has
        created it. Retries a few times, then stops the timer."""
        self._popover_hook_tries += 1
        done = False
        try:
            if self.popover and self.popover.install_status_hook():
                done = True
        except Exception as e:
            logger.warning(f"popover hook attempt failed: {e}")
        if done or self._popover_hook_tries >= 10:
            try:
                timer.stop()
            except Exception:
                pass

    # ── Google auth ───────────────────────────────────────────────────────────
    def _update_auth_menu(self):
        u = auth.current_user()
        if u:
            self.signin_item.title = f"Sign out ({u.get('email', 'account')})"
            self.signin_item.set_callback(self._sign_out)
        else:
            self.signin_item.title = "Sign in with Google"
            self.signin_item.set_callback(self._sign_in)

    def _sign_in(self, _=None):
        def work():
            try:
                a = auth.sign_in_with_google()
                self._on_main(lambda: self._after_sign_in(a))
            except Exception as e:
                logger.error(f"Sign-in failed: {e}")
                self._on_main(lambda: rumps.alert("Sign-in failed", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _after_sign_in(self, auth_info):
        self.config = load_config()  # picks up sync_user_id set during sign-in
        self._update_auth_menu()
        threading.Thread(target=self._detect_and_prompt, args=(auth_info,), daemon=True).start()

    def _detect_and_prompt(self, auth_info):
        others = []
        try:
            import platform
            from app.sync import fetch_devices
            others = fetch_devices(auth_info.get("user_id", ""), platform.node()) or []
        except Exception as e:
            logger.debug(f"device detect failed: {e}")
        self._on_main(lambda: self._finish_sign_in(others))

    def _finish_sign_in(self, others):
        enable = True
        if others:
            names = ", ".join(d.get("device_name", "a device") for d in others[:3])
            r = rumps.alert(
                title="New device detected",
                message=(f"Your account is already signed in on: {names}.\n\n"
                         "Sync your dictation, notes and canvas across your devices?"),
                ok="Sync", cancel="Not now")
            enable = (r == 1)
        self.config["sync_enabled"] = enable
        save_config(self.config)
        if self._sync:
            try:
                self._sync.stop()
            except Exception:
                pass
            self._sync = None
        if enable:
            self._init_sync()
        try:
            self.dashboard.show()  # bring Flume to the front after sign-in
            self.dashboard._refresh()
            if self.popover:
                self.popover._refresh()
        except Exception:
            pass

    def _sign_out(self, _=None):
        if self._sync:
            try:
                self._sync.stop()
            except Exception:
                pass
            self._sync = None
        auth.sign_out()
        self.config = load_config()
        self._update_auth_menu()
        try:
            self.dashboard._refresh()
            if self.popover:
                self.popover._refresh()
        except Exception:
            pass

    def _reset_onboarding(self, _=None):
        """Dev helper — clears auth + onboarding so the flow replays from sign-in."""
        for k in ("auth", "onboarded", "welcomed"):
            self.config.pop(k, None)
        self.config["sync_enabled"] = False
        self.config["sync_user_id"] = ""
        save_config(self.config)
        if self._sync:
            try:
                self._sync.stop()
            except Exception:
                pass
            self._sync = None
        self._update_auth_menu()
        try:
            self.dashboard.show()
            if hasattr(self.dashboard, "_eval"):
                self.dashboard._eval("if(window.__resetOnboarding)window.__resetOnboarding();")
        except Exception:
            pass

    def _open_dashboard(self, _=None):
        self.dashboard.show()

    def _open_canvas(self, _=None):
        self.dashboard.show()
        self.dashboard._on_tab_select(4)

    def _open_notes(self, _=None):
        self.dashboard.show()
        self.dashboard._on_tab_select(5)

    # ── Meetings ─────────────────────────────────────────────────────────────
    def _meeting_win(self):
        """Lazy meeting window; fails closed to None."""
        if self.meeting_window is None:
            try:
                from app.meeting_window import MeetingWindow
                self.meeting_window = MeetingWindow(self)
            except Exception as e:
                logging.getLogger("verbal").warning("meeting window unavailable (%s)", e)
        return self.meeting_window

    _MOD_KEY_LABELS = {54: "Right ⌘", 55: "⌘", 56: "⇧", 57: "⇪", 58: "⌥",
                       59: "⌃", 60: "Right ⇧", 61: "Right ⌥", 62: "Right ⌃", 63: "fn"}

    def capture_next_key(self, timeout=20.0, allow_modifiers=True):
        """Hotkey picker: block (on the CALLER's thread) until the user presses
        one key anywhere, and return {'keycode', 'label', 'modifier'} or None.
        While capturing, the normal hotkey handlers are suppressed so pressing
        the current dictation key doesn't start a recording."""
        import threading
        result = {}
        done = threading.Event()
        state = {"monitors": []}
        self._capturing_key = True

        def install():
            try:
                from AppKit import NSEvent
                import Quartz
                mask = Quartz.NSEventMaskKeyDown | Quartz.NSEventMaskFlagsChanged

                def grab(event):
                    try:
                        et = event.type()
                        kc = int(event.keyCode())
                        if et == 10:                       # KeyDown
                            if kc == 53:                   # ESC cancels capture
                                done.set()
                                return
                            ch = ""
                            try:
                                ch = str(event.charactersIgnoringModifiers() or "")
                            except Exception:
                                pass
                            label = ch.upper() if ch.strip() else f"key {kc}"
                            result.update(keycode=kc, label=label, modifier=False)
                            done.set()
                        elif et == 12 and allow_modifiers:  # FlagsChanged (modifier down)
                            flags = event.modifierFlags()
                            if flags & 0xFFFF0000:          # only the DOWN transition
                                label = self._MOD_KEY_LABELS.get(kc, f"mod {kc}")
                                result.update(keycode=kc, label=label, modifier=True)
                                done.set()
                    except Exception:
                        done.set()

                def local(event):
                    grab(event)
                    return None                            # swallow it locally
                m1 = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(mask, grab)
                m2 = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(mask, local)
                state["monitors"] = [m for m in (m1, m2) if m]
            except Exception as e:
                logging.getLogger("verbal").error("hotkey capture install failed: %s", e)
                done.set()
        self._on_main(install)
        logging.getLogger("verbal").info("hotkey capture armed (timeout %.0fs)", timeout)
        done.wait(timeout)
        logging.getLogger("verbal").info("hotkey capture result: %s", result or "none")

        def cleanup():
            from AppKit import NSEvent
            for m in state["monitors"]:
                try:
                    NSEvent.removeMonitor_(m)
                except Exception:
                    pass
        self._on_main(cleanup)
        # small grace so the captured keypress can't double-fire the new binding
        import threading as _t
        _t.Timer(0.4, lambda: setattr(self, "_capturing_key", False)).start()
        return result if result.get("keycode") is not None else None

    def _on_transform_hotkey(self):
        if getattr(self, "_capturing_key", False):
            return
        """Cmd+Shift+T — Transform Mode B (TRANSFORM_SWARM.md). Never enters the
        dictation core: capture the selection on a worker thread, then show the
        pill on the main thread. Everything fails closed to a silent no-op."""
        try:
            if not (self.config.get("transform_enabled")
                    and self.config.get("transform_selection_enabled", True)):
                return
            if self._is_recording:
                return
            if self.transform_widget and self.transform_widget.visible:
                self._on_main(self.transform_widget.hide)
                return

            def bg():
                try:
                    from app import transform as _tf
                    # Remember the app that holds the selection BEFORE anything
                    # else, while it's still frontmost. Mode B never entered the
                    # dictation core, so injector._previous_app_pid was stale/None
                    # and Replace's inject_text→restore_focused_app() re-activated
                    # the wrong app (or nothing) — the paste landed nowhere. This
                    # is the "Replace does nothing" bug. Mirrors the dictation
                    # path's save_focused_app() at record start.
                    save_focused_app()
                    sel = _tf.capture_selection()
                    if not sel:
                        return                      # nothing selected → silent no-op

                    def ui():
                        try:
                            if self.transform_widget is None:
                                from app.transform_widget import TransformWidget
                                self.transform_widget = TransformWidget(self)
                            self.transform_widget.show(sel)
                        except Exception as e:
                            logging.getLogger("verbal").debug("transform pill failed: %s", e)
                    self._on_main(ui)
                except Exception as e:
                    logging.getLogger("verbal").debug("transform capture failed: %s", e)
            import threading
            threading.Thread(target=bg, daemon=True).start()
        except Exception:
            pass

    def _meeting_hud(self):
        """Lazy meeting HUD; fails closed to None."""
        if getattr(self, "meeting_hud", None) is None:
            try:
                from app.meeting_hud import MeetingHud
                self.meeting_hud = MeetingHud(self)
            except Exception as e:
                logging.getLogger("verbal").warning("meeting HUD unavailable (%s)", e)
                self.meeting_hud = None
        return self.meeting_hud

    def _toggle_meeting(self, _=None):
        """Menubar 'Start Meeting' — opens the permission checklist when setup
        is incomplete, otherwise the pre-meeting modal. When a meeting is
        already running, focuses its window.

        The permission check cold-imports ScreenCaptureKit (~1 s) — it runs on
        a background thread so the menubar/dashboard never freezes; only the
        window show hops back to the main thread."""
        try:
            if not self.meetings:
                return
            if self.meetings.active:
                win = self._meeting_win()
                if win:
                    win.show("live")
                return

            import threading

            def bg():
                try:
                    from app import permissions
                    ready = bool(permissions.meeting_permissions().get("ready"))
                except Exception:
                    ready = False
                # "Skip for now" is a durable choice — don't re-show the
                # checklist on every open (capture fails closed to mic-only).
                skipped = bool(self.config.get("meetings_skipped_system_audio"))
                logging.getLogger("verbal").info(
                    "meeting open: ready=%s skipped=%s", ready, skipped)
                if not ready and skipped:
                    ready = True

                def ui():
                    try:
                        win = self._meeting_win()
                        if win:
                            win.show("premeeting" if ready else "permissions")
                        self._refresh_meeting_menu()
                    except Exception as e:
                        logging.getLogger("verbal").error("meeting show failed: %s", e)
                self._on_main(ui)
            threading.Thread(target=bg, daemon=True).start()
        except Exception as e:
            logging.getLogger("verbal").error("start meeting failed: %s", e)

    def _refresh_meeting_menu(self):
        try:
            active = bool(self.meetings and self.meetings.active)
            self.meeting_btn.title = "Return to Meeting" if active else "Start Meeting"
        except Exception:
            pass

    # ── Granola-style meeting auto-detection ─────────────────────────────────
    def _detect_meeting_tick(self, _=None):
        """Timer (main thread): cheap guards, then run the window scan on a
        background thread (SCShareableContent can block ~1s) and apply the result
        back on the main thread. Best-effort — never raises into the timer."""
        try:
            if not self.meetings:
                return
            # Master switch (default on) + never nag while already capturing.
            if not self.config.get("meeting_autodetect", True):
                if self.meeting_prompt and self.meeting_prompt.visible:
                    self.meeting_prompt.hide()
                return
            if self.meetings.active:
                if self.meeting_prompt and self.meeting_prompt.visible:
                    self.meeting_prompt.hide()
                return
            if getattr(self, "_md_scanning", False):
                return  # a previous scan is still in flight

            self._md_scanning = True

            def work():
                info = None
                try:
                    from app import meeting_detect
                    info = meeting_detect.detect()
                except Exception as e:
                    logger.debug("meeting detect scan failed: %s", e)
                self._on_main(lambda: self._md_apply(info))
            threading.Thread(target=work, daemon=True).start()
        except Exception as e:
            logger.debug("meeting detect tick failed: %s", e)

    def _md_apply(self, info):
        """Main thread: fold a scan result into the prompt state machine."""
        self._md_scanning = False
        try:
            # State may have changed while the scan ran.
            if self.meetings and self.meetings.active:
                return
            if not self.config.get("meeting_autodetect", True):
                return
            if not info:
                # A couple of empty polls = the call ended → forget it so the NEXT
                # call gets a fresh prompt, and drop any stale pill.
                self._md_empty += 1
                if self._md_empty >= 2:
                    self._md_active_key = None
                    self._md_handled.clear()
                    if self.meeting_prompt and self.meeting_prompt.visible:
                        self.meeting_prompt.hide()
                return
            self._md_empty = 0
            key = info.get("key") or ""
            if key in self._md_handled:
                return  # already asked (or dismissed) for this call
            self._md_active_key = key
            self._md_source = info.get("source") or ""
            self._md_handled.add(key)   # ask once per call
            logger.info("meeting detected (auto): source=%s key=%s",
                        self._md_source, key)
            self._show_meeting_prompt(self._md_source)
        except Exception as e:
            logger.debug("meeting detect apply failed: %s", e)

    def _show_meeting_prompt(self, source):
        try:
            if self.meeting_prompt is None:
                from app.meeting_prompt import MeetingPrompt
                self.meeting_prompt = MeetingPrompt(self)
            self.meeting_prompt.show(source)
        except Exception as e:
            logger.debug("meeting prompt show failed: %s", e)

    def _meeting_detect_result(self, take: bool):
        """Pill button result: True = start capturing this call now."""
        if not take:
            return
        try:
            source = self._md_source or ""
            lang = self.config.get("spoken_language", "") or ""
            res = self.meetings.start(title="", use_mic=True, use_system=True,
                                      language=lang) if self.meetings else None
            if res and res.get("ok"):
                logger.info("meeting auto-started from detection (%s)", source)
                self._refresh_meeting_menu()
                win = self._meeting_win()
                if win:
                    win.show("live")
            else:
                # Not ready (e.g. Screen-Recording permission) → fall back to the
                # normal launcher, which walks the permission/pre-meeting flow.
                logger.info("auto-start not ready (%s) — opening launcher",
                            res.get("error") if res else "no manager")
                self._toggle_meeting()
        except Exception as e:
            logger.error("meeting auto-start failed: %s", e)

    def _toggle_meeting_autodetect(self, sender=None):
        try:
            on = not self.config.get("meeting_autodetect", True)
            self.config["meeting_autodetect"] = on
            save_config(self.config)
            if sender is not None:
                sender.state = 1 if on else 0
            if not on and self.meeting_prompt and self.meeting_prompt.visible:
                self.meeting_prompt.hide()
            logger.info("meeting auto-detect %s", "on" if on else "off")
        except Exception as e:
            logger.warning("toggle auto-detect failed: %s", e)

    def _set_mode_hold(self, _):
        self._mode = MODE_HOLD
        self.mode_hold.state = 1
        self.mode_toggle.state = 0
        self.config["recording_mode"] = MODE_HOLD
        save_config(self.config)
        if self.hotkey_listener:
            self.hotkey_listener.set_mode(MODE_HOLD)

    def _set_mode_toggle(self, _):
        self._mode = MODE_TOGGLE
        self.mode_hold.state = 0
        self.mode_toggle.state = 1
        self.config["recording_mode"] = MODE_TOGGLE
        save_config(self.config)
        if self.hotkey_listener:
            self.hotkey_listener.set_mode(MODE_TOGGLE)

    def _on_hotkey_press(self):
        """Called by HotkeyListener for Hold Key Down."""
        if getattr(self, "_capturing_key", False):
            return
        if not self._is_recording:
            self._on_main(self._on_record_start)

    def _on_hotkey_release(self):
        """Called by HotkeyListener for Hold Key Up."""
        if getattr(self, "_capturing_key", False):
            return
        if self._is_recording:
            self._on_main(self._on_record_stop)

    def _on_hotkey_toggle(self):
        """Called by HotkeyListener for Toggle Key Down."""
        if getattr(self, "_capturing_key", False):
            return
        self._on_main(lambda: self._toggle_recording(None))

    def _on_esc_pressed(self):
        if self._processing:
            logger.info("ESC - cancelling transcription")
            self._cancel_flag.set()
            self._on_main(self._reset_to_ready)
        elif self._is_recording:
            logger.info("ESC - cancelling recording")
            self._on_main(self._cancel_recording)

    def _toggle_recording(self, _):
        if self._is_recording:
            self._on_record_stop()
        else:
            self._on_record_start()

    def _on_record_start(self):
        if self._processing:
            return
        try:
            save_focused_app()  # Remember where user was typing
            # File tagging: start a deep AX harvest of the IDE's open files NOW,
            # in the background, so it finishes while the user speaks (Cursor's
            # tree is too slow to walk on the transcription critical path).
            if self.config.get("filetag_enabled", False):
                try:
                    from app import filetags as _ft
                    from app.injector import get_focused_app_pid, get_focused_app_bundle, get_focused_app_name
                    from app.config import save_config as _save_config
                    if _ft.supported_ide(get_focused_app_bundle(), get_focused_app_name()):
                        _ft.harvest_async(get_focused_app_pid(), self.config, _save_config)
                except Exception as e:
                    logger.debug(f"filetag harvest kickoff skipped: {e}")
            self._is_recording = True
            self._cancel_flag.clear()
            # During a meeting, dictation SHARES the meeting's mic stream via a
            # tap — opening a second InputStream on the same device makes
            # CoreAudio drop one of them, and a failed second open used to nuke
            # the meeting's stream through PortAudio reinit.
            mt = self.meetings.active if self.meetings else None
            if mt is not None and mt.mic_running:
                self._meeting_mic_tap = self.recorder.feed_external
                mt.add_mic_tap(self._meeting_mic_tap)
                self.recorder.start_external(16000)
            else:
                self._meeting_mic_tap = None
                self.recorder.start()
            play_start()

            if os.path.exists(ICON_ACTIVE_PATH):
                self.icon = ICON_ACTIVE_PATH
            self.status_item.title = "Recording... (ESC to cancel)"
            self.record_btn.title = "Stop Recording"
            self.overlay.show("Listening…")
            self.dashboard.update_recording_state(True)
            if self.popover:
                self.popover.update_recording_state(True)
        except Exception as e:
            self._is_recording = False
            logger.error(f"Record start failed: {e}\n{traceback.format_exc()}")

    def _detach_meeting_tap(self):
        try:
            tap = getattr(self, "_meeting_mic_tap", None)
            if tap and self.meetings and self.meetings.session:
                self.meetings.session.remove_mic_tap(tap)
            self._meeting_mic_tap = None
        except Exception:
            pass

    def _on_record_stop(self):
        if not self._is_recording:
            return
        try:
            self._is_recording = False
            audio = self.recorder.stop()
            self._detach_meeting_tap()
            play_stop()

            if os.path.exists(ICON_PATH):
                self.icon = ICON_PATH
            self.record_btn.title = "Start Recording"
            self.dashboard.update_recording_state(False)
            if self.popover:
                self.popover.update_recording_state(False)

            # Minimum 1.0s of audio to avoid accidental clicks / hallucinations
            # At 48kHz, we need at least 48000 samples for 1 second
            if audio is None or len(audio) < 48000:
                duration = len(audio) / self.recorder.sample_rate if audio is not None else 0
                logger.warning(f"Audio too short: {duration:.2f}s (< 1.0s minimum)")
                self.status_item.title = self._status_text()
                self.overlay.hide()
                return

            self._processing = True
            self.status_item.title = "Transcribing... (ESC to cancel)"
            self.overlay.update_status("Transcribing…")
            threading.Thread(target=self._process_audio, args=(audio,), daemon=True).start()
        except Exception as e:
            logger.error(f"Record stop failed: {e}\n{traceback.format_exc()}")
            self._on_main(self._reset_to_ready)

    def _cancel_recording(self):
        self._is_recording = False
        self.recorder.stop()
        self._detach_meeting_tap()
        play_stop()
        self._reset_to_ready()

    def _transcribe_with_retry(self, audio, attempts=3):
        """Transcribe, auto-retrying on 'failed' (transient network/API) with a
        short backoff. Returns (text, status). Silence returns immediately."""
        text, status = "", "failed"
        for i in range(attempts):
            if self._cancel_flag.is_set():
                return "", "silent"
            text, status = transcribe_with_status(audio, self.config, self.recorder.sample_rate)
            if status in ("ok", "silent"):
                return text, status
            if i < attempts - 1:
                logger.warning(f"Transcription failed (attempt {i+1}) — retrying…")
                time.sleep(1.5 * (i + 1))
        return text, status

    def _upload_recording_async(self, rec_id, local_path):
        """Upload the WAV to the cloud and attach its URL to the history entry."""
        def work():
            try:
                user_id = self.config.get("sync_user_id", "")
                if not user_id or not local_path:
                    return
                url = recordings.upload_cloud(local_path, user_id, rec_id)
                if url:
                    self.config = update_history_entry(self.config, rec_id, audio_url=url)
                    self._on_main(self._refresh_dashboards)
            except Exception as e:
                logger.debug(f"recording upload failed: {e}")
        threading.Thread(target=work, daemon=True).start()

    def _refresh_dashboards(self):
        try:
            self.dashboard._refresh()
        except Exception:
            pass
        if self.popover:
            try:
                self.popover._refresh()
            except Exception:
                pass

    def _process_audio(self, audio):
        rec_id = recordings.new_id()
        audio_path = recordings.save_wav(audio, self.recorder.sample_rate, rec_id)
        logger.info(f"Recording saved: {audio_path} (id={rec_id})")
        try:
            if self._cancel_flag.is_set():
                return

            text, status = self._transcribe_with_retry(audio)

            if self._cancel_flag.is_set():
                return

            if status == "silent":
                logger.warning("No speech detected — discarding recording")
                if audio_path:
                    try:
                        os.remove(audio_path)
                    except Exception:
                        pass
                self._on_main(lambda: self.overlay.update_status("⚠️ No speech detected. Speak louder!"))
                time.sleep(1.5)
                self._on_main(self._reset_to_ready)
                return

            if status == "failed":
                # Network/API down — keep the audio and save a retryable entry.
                logger.error("Transcription failed after retries — saved for retry")
                self.config = add_to_history(
                    self.config, "", get_focused_app_name(),
                    entry_id=rec_id, audio=audio_path or "", status="failed")
                self._upload_recording_async(rec_id, audio_path)
                self._on_main(lambda: self.overlay.update_status(
                    "⚠️ Transcription failed — retry from History"))
                time.sleep(2.0)
                self._on_main(self._reset_to_ready)
                self._on_main(self._refresh_dashboards)
                return

            # Transform Mode A (TRANSFORM_SWARM.md): a trailing "…so Flume, <instruction>"
            # transforms the dictated body instead of formatting it. Fully guarded —
            # any miss/failure falls through to the normal process_text path.
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
                            logger.info("transform inline applied: %r", instruction[:60])
            except Exception as e:
                logger.debug("transform inline skipped: %s", e)
            if result is None:
                # Phase-0 context grounding (MER-44): pass the target app so the
                # cleanup LLM grounds on it + the user's dictionary terms.
                result = process_text(text, self.config, active_app=get_focused_app_name())
            if self._cancel_flag.is_set():
                return

            # Expand spoken snippet triggers into their saved text. Runs AFTER AI
            # cleanup and immediately BEFORE injection. Fully guarded / fail-closed:
            # any error leaves the transcription untouched and never breaks the
            # record → transcribe → inject pipeline.
            try:
                from app import dictionary
                result = dictionary.apply_snippets(result, self.config, save_config)
            except Exception as e:
                logger.debug("apply_snippets skipped: %s", e)

            self._last_result_text = result
            self.config = add_to_history(
                self.config, result, get_focused_app_name(),
                entry_id=rec_id, audio=audio_path or "", status="done")
            word_count = len(result.split())
            self._total_transcriptions += 1
            self._total_words += word_count
            self.config = update_daily_words(self.config, word_count)

            self._on_main(lambda: self.overlay.hide())
            time.sleep(0.3)

            if self._cancel_flag.is_set():
                return

            success = inject_text(result, allow_mentions=self.config.get("filetag_enabled", False))
            play_done()

            # Show the split (TRANSFORM_SWARM.md P1.3): surface what was read as
            # the instruction so a wrong split is catchable + retryable.
            if transform_note:
                note = transform_note if len(transform_note) <= 44 else transform_note[:41] + "…"
                self._on_main(lambda: self.overlay.show_briefly("✦ Transformed · " + note, 2.5))

            # Auto-learn: watch the target field for a manual correction, off the
            # recording/injection critical path. Fully guarded — any failure is a
            # silent no-op that never affects transcription.
            try:
                if success and self.config.get("autolearn_enabled"):
                    self._arm_autolearn(result)
            except Exception as e:
                logger.debug("autolearn arm skipped: %s", e)

            # Push to other devices if sync is enabled
            if self._sync:
                target = self.dashboard._target_device_id if self.dashboard else "__all__"
                if target not in (None, "__none__"):
                    # "__all__" = broadcast (None), else = specific device_id
                    push_target = None if target == "__all__" else target
                    threading.Thread(
                        target=self._sync.push, args=(result, push_target), daemon=True
                    ).start()

            # Upload the audio to the cloud + attach its URL (async)
            self._upload_recording_async(rec_id, audio_path)

            status = self._status_text()
            if success:
                brief = f"Pasted · {word_count}w"
            else:
                brief = "In clipboard · paste with ⌘V"

            self._on_main(lambda: self._show_result(status, brief))

        except Exception as e:
            logger.critical(f"PROCESS CRASH: {e}\n{traceback.format_exc()}")
            self._on_main(self._reset_to_ready)
        finally:
            self._processing = False

    def _show_result(self, status, brief):
        try:
            self.status_item.title = status
            self.overlay.show_briefly(brief, duration=2.0)
            self.dashboard._refresh()
            if self.popover:
                self.popover._refresh()
        except Exception as e:
            logger.error(f"_show_result error: {e}\n{traceback.format_exc()}")

    def _arm_autolearn(self, inserted_text):
        """Arm the EditWatcher on the dictation target (daemon thread). On a
        confident single-word correction, offer to add it to the dictionary."""
        from app import autolearn
        pid = get_focused_app_pid()
        bundle = get_focused_app_bundle()
        if not pid or not inserted_text:
            return
        watcher = getattr(self, "_edit_watcher", None)
        if watcher is None:
            watcher = self._edit_watcher = autolearn.EditWatcher()
        watcher.arm(
            pid=pid,
            bundle=bundle,
            inserted_text=inserted_text,
            on_decision_callback=lambda decision: self._on_main(
                lambda: self._offer_autolearn(decision)),
        )

    def _offer_autolearn(self, decision):
        """Show the styled, non-activating auto-learn widget for a correction
        (never steals focus from the app being dictated into). Respects the
        declined/offered memory so it never nags."""
        try:
            if not decision or decision.get("action") != "offer":
                return
            old = (decision.get("old") or "").strip()
            new = (decision.get("new") or "").strip()
            if not old or not new:
                return
            from app import autolearn
            if autolearn.is_declined(self.config, new):
                logger.info("[autolearn] not offering %r — already offered/declined", new)
                return
            logger.info("[autolearn] showing widget: %r -> %r", old, new)
            self.autolearn_widget.show(old, new)
        except Exception as e:
            logger.debug("autolearn offer failed: %s", e)

    def _autolearn_result(self, old, new, added):
        """Widget callback (main thread): user clicked Add or closed. Record the
        word either way so we never nag again (F9); on Add, persist the rule and
        refresh the dashboards so the ✨ entry shows up."""
        try:
            from app import autolearn, dictionary
            cfg = self.config
            autolearn.record_offered(cfg, new, save_config)
            if added:
                dictionary.add_replacement(cfg, old, new, save_config, auto=True)
                self.config = cfg
                play_added()  # satisfying confirmation chime
                self._refresh_dashboards()
                # Force the Dictionary screen to re-fetch so the new ✨ rule shows
                # immediately (it's cached behind DICT_LOADED otherwise).
                try:
                    self.dashboard._eval("try{ if(window.loadDict) loadDict(); }catch(e){}")
                except Exception:
                    pass
        except Exception as e:
            logger.debug("autolearn result failed: %s", e)

    def _reset_to_ready(self):
        try:
            self._processing = False
            self._is_recording = False
            self._cancel_flag.clear()
            self.status_item.title = self._status_text()
            self.overlay.hide()
            if os.path.exists(ICON_PATH):
                self.icon = ICON_PATH
            self.record_btn.title = "Start Recording"
            self.dashboard.update_recording_state(False)
            if self.popover:
                self.popover.update_recording_state(False)
        except Exception as e:
            logger.error(f"Reset error: {e}")

    def _manage_groq_keys(self, _):
        keys = self.config.get("groq_api_keys", [])
        if keys:
            key_list = "\n".join(f"  {i+1}. ...{k[-8:]}" for i, k in enumerate(keys))
            msg = f"Groq keys (for transcription):\n{key_list}\n\nPaste a new key, or 'remove N':"
        else:
            msg = "No Groq API key set.\n\nGet a FREE key at console.groq.com\nPaste it here:"

        response = rumps.Window(
            message=msg,
            title="Verbal - Groq API Key",
            default_text="",
            ok="Save",
            cancel="Cancel",
            dimensions=(400, 80),
        ).run()

        if response.clicked:
            text = response.text.strip()
            if not text:
                return
            if text.lower().startswith("remove "):
                try:
                    idx = int(text.split()[1]) - 1
                    if 0 <= idx < len(keys):
                        keys.pop(idx)
                        self.config["groq_api_keys"] = keys
                        save_config(self.config)
                except (ValueError, IndexError):
                    pass
            else:
                if text not in keys:
                    keys.append(text)
                    self.config["groq_api_keys"] = keys
                    save_config(self.config)

    def _manage_keys(self, _):
        keys = self.config.get("gemini_api_keys", [])
        active_idx = self.config.get("active_gemini_key_index", 0)

        if keys:
            key_list = "\n".join(
                f"{'> ' if i == active_idx else '  '}{i+1}. ...{k[-8:]}"
                for i, k in enumerate(keys)
            )
            msg = f"Current keys:\n{key_list}\n\nPaste a new key to add, or type 'remove N' to delete key N:"
        else:
            msg = "No Gemini API keys configured.\n\nPaste a key to add:"

        response = rumps.Window(
            message=msg,
            title="Verbal - Gemini API Keys",
            default_text="",
            ok="Save",
            cancel="Cancel",
            dimensions=(400, 100),
        ).run()

        if response.clicked:
            text = response.text.strip()
            if not text:
                return
            if text.lower().startswith("remove "):
                try:
                    idx = int(text.split()[1]) - 1
                    self.config = remove_gemini_key(self.config, idx)
                except (ValueError, IndexError):
                    rumps.alert("Invalid key number")
            else:
                self.config = add_gemini_key(self.config, text)

    def _change_model(self, sender):
        model_name = sender.title
        for name, item in self.model_items.items():
            item.state = 1 if name == model_name else 0
        self.config["whisper_model"] = model_name
        save_config(self.config)

    def _check_update(self):
        from app.updater import check_for_update, download_update, install_update
        update = check_for_update()
        if update:
            self._on_main(lambda: self._show_update_prompt(update))

    def _show_update_prompt(self, update):
        changelog = update.get('changelog', 'Bug fixes and improvements')
        resp = rumps.alert(
            f"Verbal {update['version']} available",
            f"{changelog}\n\nDownload and install now?",
            ok="Update",
            cancel="Later",
        )
        if resp == 1:
            self.status_item.title = "Downloading update..."
            threading.Thread(target=self._do_update, args=(update,), daemon=True).start()

    def _do_update(self, update):
        from app.updater import download_update, install_update
        path = download_update(update)
        if path:
            install_update(path)
        else:
            self._on_main(lambda: rumps.alert("Update failed", "Could not download the update. Try again later."))
            self._on_main(lambda: setattr(self.status_item, 'title', self._status_text()))

    def _about(self, _):
        from app.config import APP_VERSION
        rumps.alert(
            f"Verbal v{APP_VERSION}",
            "Voice to text, instantly.\n\n"
            "Hold Right Command to record (Hold mode)\n"
            "or press once to start/stop (Toggle mode).\n"
            "Press ESC to cancel anytime.\n\n"
            "Say 'at file main.py' to insert @main.py\n\n"
            "Powered by Whisper + Gemini"
        )


def main():
    logger.info("=== VERBAL STARTING ===")
    app = VerbalApp()
    app._start_app()
    app.run()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
