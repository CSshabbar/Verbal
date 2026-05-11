"""Verbal for Windows — system tray app with global hotkey dictation."""

import logging
import os
import sys
import time
import threading
import traceback

# Fix for PyInstaller "console=False" builds where sys.stderr/stdout are None
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')

import faulthandler
faulthandler.enable()

from app.config import (
    load_config, save_config, add_to_history, update_daily_words,
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
        freq_map = {"start": 800, "stop": 600, "done": 1000}
        winsound.Beep(freq_map.get(name, 800), 120)
    except Exception:
        pass


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

        from app.win_overlay import WinOverlay
        from app.win_dashboard import WinDashboard

        self.overlay = WinOverlay()
        self.dashboard = WinDashboard(self)

        history = self.config.get("history", [])
        self._total_transcriptions = len(history)
        self._total_words = sum(len(_entry_text(h).split()) for h in history)

        self._init_sync()

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
            menu=pystray.Menu(
                pystray.MenuItem("Start Recording", self._tray_toggle_record),
                pystray.MenuItem("Open Dashboard", self._tray_open_dashboard),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(f"Verbal v{APP_VERSION}", None, enabled=False),
                pystray.MenuItem("Quit", self._tray_quit),
            ),
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

    def _update_tray_icon(self, recording: bool):
        try:
            if self._tray_icon:
                self._tray_icon.icon = self._create_icon_image(recording)
                self._tray_icon.title = "Verbal - Recording..." if recording else f"Verbal v{APP_VERSION}"
        except Exception:
            pass

    # ── Hotkey (pynput) ──────────────────────────────────────────────────
    def _start_hotkey(self):
        from pynput import keyboard
        self._hotkey_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()
        logger.info("Hotkey listener started (Right Alt + ESC)")

    def _on_key_press(self, key):
        try:
            from pynput import keyboard
            if key == keyboard.Key.alt_r:
                if self._mode == MODE_HOLD:
                    if not self._is_recording:
                        self._on_record_start()
                else:
                    now = time.time()
                    if now - self._last_toggle_time < 1.0:
                        return
                    self._last_toggle_time = now
                    self._toggle_recording()
            elif key == keyboard.Key.esc:
                self._on_esc_pressed()
        except Exception:
            pass

    def _on_key_release(self, key):
        try:
            from pynput import keyboard
            if key == keyboard.Key.alt_r and self._mode == MODE_HOLD:
                if self._is_recording:
                    self._on_record_stop()
        except Exception:
            pass

    # ── Recording pipeline ────────────────────────────────────────────────
    def _tray_toggle_record(self, icon=None, item=None):
        self._toggle_recording()

    def _tray_open_dashboard(self, icon=None, item=None):
        self.dashboard.show()

    def _tray_quit(self, icon=None, item=None):
        if self._tray_icon:
            self._tray_icon.stop()
        sys.exit(0)

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
        self.overlay.show("Listening...")
        self.dashboard.update_recording_state(True)

    def _on_record_stop(self):
        if not self._is_recording:
            return
        self._is_recording = False
        audio = self.recorder.stop()
        _play_sound("stop")
        self._update_tray_icon(False)
        self.dashboard.update_recording_state(False)

        if audio is None or len(audio) < 1600:
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

            self.overlay.hide()
            time.sleep(0.3)

            if self._cancel_flag.is_set():
                return

            from app.win_injector import inject_text
            success = inject_text(result)
            _play_sound("done")

            if self._sync:
                threading.Thread(
                    target=self._sync.push, args=(result, None), daemon=True
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

    def _on_sync_receive(self, text: str, device_name: str):
        import pyperclip
        pyperclip.copy(text)
        logger.info(f"Sync received from {device_name}: '{text[:40]}'")
        brief = f"From {device_name} | {len(text.split())}w - copied"
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
