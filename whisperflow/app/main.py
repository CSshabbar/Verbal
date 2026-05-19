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
    add_to_history, update_daily_words, get_daily_words,
    _entry_text, _entry_app, LOG_DIR, ensure_dirs,
)
from app.recorder import Recorder
from app.transcriber import transcribe
from app.ai_cleanup import process_text
from app.injector import inject_text, save_focused_app, get_focused_app_name
from app.hotkey import HotkeyListener
from app.overlay import OverlayBar
from app.sounds import play_start, play_stop, play_done
from app.dashboard import DashboardWindow
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

        self.overlay = OverlayBar()
        self.dashboard = DashboardWindow(self)
        self.canvas    = CanvasWindow(self.config)

        history = self.config.get("history", [])
        self._total_transcriptions = len(history)
        self._total_words = sum(len(_entry_text(h).split()) for h in history)

        # Sync client — starts if sync is enabled in config
        self._sync = None
        self._init_sync()

        self.status_item = rumps.MenuItem(self._status_text(), callback=None)
        self.status_item.set_callback(None)

        self.record_btn = rumps.MenuItem("Start Recording", callback=self._toggle_recording)

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

        self.menu = [
            self.status_item,
            self.record_btn,
            None,
            rumps.MenuItem("Open Verbal", callback=self._open_dashboard),
            rumps.MenuItem("Open Canvas", callback=self._open_canvas),
            rumps.MenuItem("Open Notes", callback=self._open_notes),
            mode_menu,
            rumps.MenuItem("Groq API Key (Transcription)...", callback=self._manage_groq_keys),
            rumps.MenuItem("Gemini API Key (AI Cleanup)...", callback=self._manage_keys),
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
        )

        self._ui_timer = rumps.Timer(self._drain_ui_queue, 0.1)

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

    def _start_app(self, _=None):
        logger.info("Starting Verbal")
        self.overlay.setup()
        self.hotkey_listener.start()
        self._ui_timer.start()
        threading.Thread(target=self._preload_model, daemon=True).start()
        threading.Thread(target=self._check_update, daemon=True).start()

        # Request accessibility permission on first launch
        from app.injector import request_accessibility
        try:
            request_accessibility()
        except Exception as e:
            logger.warning(f"Accessibility check: {e}")

        self.dashboard.show()
        from AppKit import NSApplication
        NSApplication.sharedApplication().setActivationPolicy_(0)

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

    def _open_dashboard(self, _=None):
        self.dashboard.show()

    def _open_canvas(self, _=None):
        self.dashboard.show()
        self.dashboard._on_tab_select(4)

    def _open_notes(self, _=None):
        self.dashboard.show()
        self.dashboard._on_tab_select(5)

    def _set_mode_hold(self, _):
        self._mode = MODE_HOLD
        self.mode_hold.state = 1
        self.mode_toggle.state = 0
        self.config["recording_mode"] = MODE_HOLD
        save_config(self.config)

    def _set_mode_toggle(self, _):
        self._mode = MODE_TOGGLE
        self.mode_hold.state = 0
        self.mode_toggle.state = 1
        self.config["recording_mode"] = MODE_TOGGLE
        save_config(self.config)

    def _on_hotkey_press(self):
        """Called by HotkeyListener for Hold Key Down."""
        if not self._is_recording:
            self._on_main(self._on_record_start)

    def _on_hotkey_release(self):
        """Called by HotkeyListener for Hold Key Up."""
        if self._is_recording:
            self._on_main(self._on_record_stop)

    def _on_hotkey_toggle(self):
        """Called by HotkeyListener for Toggle Key Down."""
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
            self._is_recording = True
            self._cancel_flag.clear()
            self.recorder.start()
            play_start()

            if os.path.exists(ICON_ACTIVE_PATH):
                self.icon = ICON_ACTIVE_PATH
            self.status_item.title = "Recording... (ESC to cancel)"
            self.record_btn.title = "Stop Recording"
            self.overlay.show("Listening…")
            self.dashboard.update_recording_state(True)
        except Exception as e:
            self._is_recording = False
            logger.error(f"Record start failed: {e}\n{traceback.format_exc()}")

    def _on_record_stop(self):
        if not self._is_recording:
            return
        try:
            self._is_recording = False
            audio = self.recorder.stop()
            play_stop()

            if os.path.exists(ICON_PATH):
                self.icon = ICON_PATH
            self.record_btn.title = "Start Recording"
            self.dashboard.update_recording_state(False)

            # Minimum 0.5s of audio to avoid accidental clicks / hallucinations
            if audio is None or len(audio) < 8000:
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
        play_stop()
        self._reset_to_ready()

    def _process_audio(self, audio):
        try:
            if self._cancel_flag.is_set():
                return

            text = transcribe(audio, self.config, self.recorder.sample_rate)

            if self._cancel_flag.is_set():
                return
            if not text:
                self._on_main(self._reset_to_ready)
                return

            result = process_text(text, self.config)
            if self._cancel_flag.is_set():
                return

            self.config = add_to_history(self.config, result, get_focused_app_name())
            word_count = len(result.split())
            self._total_transcriptions += 1
            self._total_words += word_count
            self.config = update_daily_words(self.config, word_count)

            self._on_main(lambda: self.overlay.hide())
            time.sleep(0.3)

            if self._cancel_flag.is_set():
                return

            success = inject_text(result)
            play_done()

            # Push to other devices if sync is enabled
            if self._sync:
                target = self.dashboard._target_device_id if self.dashboard else "__all__"
                if target not in (None, "__none__"):
                    # "__all__" = broadcast (None), else = specific device_id
                    push_target = None if target == "__all__" else target
                    threading.Thread(
                        target=self._sync.push, args=(result, push_target), daemon=True
                    ).start()

            preview = result[:30] + "..." if len(result) > 30 else result
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
        except Exception as e:
            logger.error(f"_show_result error: {e}\n{traceback.format_exc()}")

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
