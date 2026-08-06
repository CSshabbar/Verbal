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

        self._menu_items = pystray.Menu(
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
        self.overlay.setup()
        self._start_hotkey()
        threading.Thread(target=self._check_update, daemon=True).start()
        threading.Thread(target=self._presence_loop, daemon=True).start()

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

    def _keys_match(self, pressed_key, target_key):
        """Check if pressed key matches target, treating alt_r/alt_gr as equivalent on Windows."""
        if pressed_key == target_key:
            return True
        from pynput import keyboard
        # On Windows, right Alt can emit either alt_r or alt_gr depending on keyboard layout
        alt_keys = {keyboard.Key.alt_r, keyboard.Key.alt_gr}
        if pressed_key in alt_keys and target_key in alt_keys:
            return True
        return False

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

        # Start periodic cleanup timer
        self._cleanup_timer = None
        self._start_cleanup_timer()

    def _on_key_press(self, key):
        try:
            from pynput import keyboard

            hold_key = self._parsed_hold_key
            toggle_key = self._parsed_toggle_key

            # Case 1: Same key for both
            if hold_key == toggle_key and self._keys_match(key, hold_key):
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
            if self._keys_match(key, hold_key):
                if not self._is_recording:
                    self._on_record_start()

            if self._keys_match(key, toggle_key):
                now = time.time()
                if now - self._last_toggle_time > 0.3:
                    self._last_toggle_time = now
                    self._toggle_recording()

            if key == keyboard.Key.esc:
                self._on_esc_pressed()
        except Exception as e:
            logger.error(f"Key press error: {e}", exc_info=True)

    def _on_key_release(self, key):
        try:
            # Only handle release if we are in Hold mode or if it's explicitly the hold key
            if self._keys_match(key, self._parsed_hold_key):
                if self._parsed_hold_key == self._parsed_toggle_key:
                    if self._mode == MODE_HOLD and self._is_recording:
                        self._on_record_stop()
                else:
                    if self._is_recording:
                        self._on_record_stop()
        except Exception:
            pass

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

            # Phase-0 context grounding (MER-44): pass the target window title
            # (Windows has no bundle id) so the cleanup LLM grounds on it + the
            # user's dictionary terms.
            result = process_text(text, self.config, active_app=get_focused_app_name())
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
            success = inject_text(result)
            _play_sound("done")

            # Push to other devices if sync is enabled
            if self._sync:
                target = self.dashboard._target_device_id if self.dashboard else "__all__"
                if target not in (None, "__none__"):
                    # "__all__" = broadcast (None), else = specific device_id
                    push_target = None if target == "__all__" else target
                    threading.Thread(
                        target=self._sync.push, args=(result, push_target), daemon=True
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

    def _reset_to_ready(self):
        self._processing = False
        self._is_recording = False
        self._cancel_flag.clear()
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
                    device_id = (self._sync.device_id if self._sync
                                 else platform.node())
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


def main():
    import time
    sys._verbal_start_time = time.time()
    app = VerbalWinApp()
    app.start()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
