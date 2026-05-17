"""Verbal for Windows — system tray app with global hotkey dictation."""

import logging
import os
import sys
import time
import threading
import traceback

# Fix for PyInstaller "console=False" builds where sys.stderr/stdout are None
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')  # type: ignore[assignment]
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')  # type: ignore[assignment]

import faulthandler
faulthandler.enable()

from app.config import (
    load_config, save_config, add_to_history, update_daily_words,
    add_gemini_key, remove_gemini_key,
    _entry_text, _entry_app, LOG_DIR, ensure_dirs, APP_VERSION, PLATFORM,
)
from app.recorder import Recorder
from app.transcriber import transcribe
from app.ai_cleanup import process_text

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
        from app.shared_dashboard import SharedDashboard

        self.overlay = WinOverlay()
        self.dashboard = SharedDashboard(self)

        history = self.config.get("history", [])
        self._total_transcriptions = len(history)
        self._total_words = sum(len(_entry_text(h).split()) for h in history)

        self._init_sync()

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

        self._menu_items = pystray.Menu(
            self._menu_status,
            self._menu_record,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Verbal", self._tray_open_dashboard),
            pystray.MenuItem("Open Canvas", self._tray_open_canvas),
            pystray.MenuItem("Recording Mode", mode_menu),
            pystray.MenuItem("Whisper Model", model_menu),
            pystray.MenuItem("Groq API Key...", self._tray_manage_groq),
            pystray.MenuItem("Gemini API Key...", self._tray_manage_gemini),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: f"Verbal v{APP_VERSION}", self._tray_about),
            pystray.MenuItem("Quit", self._tray_quit),
        )

        return self._menu_items

    def start(self):
        logger.info(f"=== VERBAL v{APP_VERSION} STARTING (Windows) ===")
        self.overlay.setup()
        self._start_hotkey()
        threading.Thread(target=self._check_update, daemon=True).start()

        import pystray
        from PIL import Image, ImageDraw

        icon_image = self._create_icon_image(False)
        self._tray_icon = pystray.Icon(
            "Verbal", icon_image,
            f"Verbal v{APP_VERSION}",
            menu=self._build_tray_menu(),
        )
        self._tray_icon.run()

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

    def _tray_open_dashboard(self, icon=None, item=None):
        self.dashboard.show()

    def _tray_open_canvas(self, icon=None, item=None):
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

    def _tray_manage_groq(self, icon=None, item=None):
        import tkinter as tk
        from tkinter import simpledialog
        keys = self.config.get("groq_api_keys", [])
        if keys:
            key_list = "\n".join(f"  {i+1}. ...{k[-8:]}" for i, k in enumerate(keys))
            msg = f"Groq keys (for transcription):\n{key_list}\n\nPaste a new key, or 'remove N':"
        else:
            msg = "No Groq API key set.\n\nGet a FREE key at console.groq.com\nPaste it here:"
        root = tk.Tk()
        root.withdraw()
        text = simpledialog.askstring("Verbal - Groq API Key", msg, parent=root)
        root.destroy()
        if text:
            text = text.strip()
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

    def _tray_manage_gemini(self, icon=None, item=None):
        import tkinter as tk
        from tkinter import simpledialog
        keys = self.config.get("gemini_api_keys", [])
        active_idx = self.config.get("active_gemini_key_index", 0)
        if keys:
            key_list = "\n".join(
                f"{'> ' if i == active_idx else '  '}{i+1}. ...{k[-8:]}"
                for i, k in enumerate(keys)
            )
            msg = f"Current keys:\n{key_list}\n\nPaste a new key, or 'remove N':"
        else:
            msg = "No Gemini API keys configured.\n\nPaste a key to add:"
        root = tk.Tk()
        root.withdraw()
        text = simpledialog.askstring("Verbal - Gemini API Keys", msg, parent=root)
        root.destroy()
        if text:
            text = text.strip()
            if text.lower().startswith("remove "):
                try:
                    idx = int(text.split()[1]) - 1
                    self.config = remove_gemini_key(self.config, idx)
                except (ValueError, IndexError):
                    pass
            else:
                self.config = add_gemini_key(self.config, text)

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

    # ── Hotkey (pynput) ──────────────────────────────────────────────────
    def _parse_key(self, key_name):
        from pynput import keyboard
        if not key_name: return None
        try:
            if hasattr(keyboard.Key, str(key_name).replace("Key.", "")):
                return getattr(keyboard.Key, str(key_name).replace("Key.", ""))
            return keyboard.KeyCode.from_char(key_name)
        except Exception:
            return None

    def _start_hotkey(self):
        from pynput import keyboard
        self._parsed_hold_key = self._parse_key(self.config.get("hotkey_hold", "alt_r"))
        self._parsed_toggle_key = self._parse_key(self.config.get("hotkey_toggle", "alt_r"))
        
        self._hotkey_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()
        logger.info(f"Hotkey listener started (Hold={self.config.get('hotkey_hold')}, Toggle={self.config.get('hotkey_toggle')})")

    def _on_key_press(self, key):
        try:
            from pynput import keyboard
            
            hold_key = self._parsed_hold_key
            toggle_key = self._parsed_toggle_key
            
            # Case 1: Same key for both
            if hold_key == toggle_key and key == hold_key:
                if self._mode == MODE_HOLD:
                    if not self._is_recording:
                        self._on_record_start()
                else: # MODE_TOGGLE
                    now = time.time()
                    if now - self._last_toggle_time > 0.3:
                        self._last_toggle_time = now
                        self._toggle_recording()
                return

            # Case 2: Different keys
            if key == hold_key:
                if not self._is_recording:
                    self._on_record_start()
            
            if key == toggle_key:
                now = time.time()
                if now - self._last_toggle_time > 0.3:
                    self._last_toggle_time = now
                    self._toggle_recording()

            if key == keyboard.Key.esc:
                self._on_esc_pressed()
        except Exception as e:
            logger.debug(f"Key press error: {e}")

    def _on_key_release(self, key):
        try:
            # Only handle release if we are in Hold mode or if it's explicitly the hold key
            if key == self._parsed_hold_key:
                if self._parsed_hold_key == self._parsed_toggle_key:
                    if self._mode == MODE_HOLD and self._is_recording:
                        self._on_record_stop()
                else:
                    if self._is_recording:
                        self._on_record_stop()
        except Exception:
            pass

    def _update_hotkeys(self):
        try:
            if hasattr(self, "_hotkey_listener") and self._hotkey_listener:
                self._hotkey_listener.stop()
            self._start_hotkey()
        except Exception as e:
            logger.error(f"Failed to update hotkeys: {e}")

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
            from app.win_injector import save_focused_app
            save_focused_app()
        except Exception:
            pass
        self._is_recording = True
        self._cancel_flag.clear()
        self.recorder.start()
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

        if audio is None or len(audio) < 8000: # 0.5s at 16kHz
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

    def _process_audio(self, audio):
        try:
            if self._cancel_flag.is_set():
                return

            text = transcribe(audio, self.config, self.recorder.sample_rate)
            if self._cancel_flag.is_set():
                return
            if not text:
                self.overlay.hide()
                return

            result = process_text(text, self.config)
            if self._cancel_flag.is_set():
                return

            from app.win_injector import get_focused_app_name
            self.config = add_to_history(self.config, result, get_focused_app_name())
            word_count = len(result.split())
            self._total_transcriptions += 1
            self._total_words += word_count
            self.config = update_daily_words(self.config, word_count)
            self._update_tray_menu()

            self.overlay.hide()
            time.sleep(0.3)

            if self._cancel_flag.is_set():
                return

            from app.win_injector import inject_text
            success = inject_text(result)
            _play_sound("done")

            if self._sync:
                target = self.dashboard._target_device_id if self.dashboard else "__all__"
                if target not in (None, "__none__"):
                    # "__all__" = broadcast (None), else = specific device_id
                    push_target = None if target == "__all__" else target
                    threading.Thread(
                        target=self._sync.push, args=(result, push_target), daemon=True
                    ).start()

            brief = f"Pasted | {word_count}w" if success else f"Copied | {word_count}w"
            self.overlay.show_briefly(brief, duration=2.0)
            self.dashboard.show_result(result)

        except Exception as e:
            logger.critical(f"PROCESS CRASH: {e}\n{traceback.format_exc()}")
            self.overlay.hide()
        finally:
            self._processing = False

    def _reset_to_ready(self):
        self._processing = False
        self._is_recording = False
        self._cancel_flag.clear()
        self.overlay.hide()
        self._update_tray_icon(False)
        self._update_tray_menu()
        self.dashboard.update_recording_state(False)

    # ── Sync ──────────────────────────────────────────────────────────────
    def _init_sync(self):
        if not self.config.get("sync_enabled"):
            return
        user_id = self.config.get("sync_user_id", "").strip()
        if not user_id:
            return
        try:
            from app.sync import SyncClient
            device_name = self.config.get("sync_device_name", "Windows")
            self._sync = SyncClient(
                user_id=user_id,
                device_name=device_name,
                on_receive=self._on_sync_receive,
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

    def _on_sync_receive(self, text: str, device_name: str):
        import pyperclip
        pyperclip.copy(text)
        logger.info(f"Sync received from {device_name}: '{text[:40]}'")
        try:
            from app.win_injector import inject_text
            success = inject_text(text)
        except Exception as e:
            logger.error(f"Sync paste failed: {e}")
            success = False
        action = "pasted" if success else "copied"
        brief = f"From {device_name} | {len(text.split())}w - {action}"
        self.overlay.show_briefly(brief, duration=2.5)

    # ── Update check ──────────────────────────────────────────────────────
    def _check_update(self):
        from app.updater import check_for_update, download_update, install_update
        update = check_for_update()
        if not update:
            return
        try:
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
            logger.error(f"Update prompt failed: {e}")


def main():
    app = VerbalWinApp()
    app.start()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
