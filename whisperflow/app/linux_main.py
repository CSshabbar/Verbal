"""Verbal for Linux — system tray app with global hotkey dictation."""

import logging
import os
import signal
import socket
import sys
import time
import threading
import traceback
import faulthandler

faulthandler.enable()

from app.config import (
    load_config, save_config, add_to_history, update_daily_words,
    _entry_text, CONFIG_DIR, LOG_DIR, ensure_dirs, APP_VERSION,
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

# ── IPC control socket ────────────────────────────────────────────────────────
# Wayland forbids an unfocused client from observing global keys, so the in-process
# pynput listener cannot work there. The supported route is to let the DESKTOP own the
# hotkey and have it run `verbal --toggle`, which pokes this socket. See --install-hotkey.
SOCKET_PATH = CONFIG_DIR / "verbal.sock"
LOCK_PATH = CONFIG_DIR / "verbal.lock"

IPC_COMMANDS = ("toggle", "start", "stop", "cancel", "show", "quit", "ping")

# GNOME custom-keybinding slot we install into.
GNOME_KEYBIND_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/verbal/"
DEFAULT_HOTKEY = "<Control><Alt>space"


def _acquire_single_instance():
    """flock a file for the process lifetime. Returns the fd, or None if already running.

    Two instances would both bind hotkeys, both answer the IPC socket, and race on
    config.json — so refuse to start rather than corrupt state.
    """
    import fcntl
    try:
        fd = os.open(str(LOCK_PATH), os.O_RDWR | os.O_CREAT, 0o600)
    except Exception as e:
        logger.warning(f"Could not open lock file: {e}")
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    try:
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
    except Exception:
        pass
    return fd


def send_ipc_command(command: str, timeout: float = 2.0) -> bool:
    """Client side: deliver a command to a running instance. True if it was accepted."""
    if command not in IPC_COMMANDS:
        print(f"verbal: unknown command '{command}'", file=sys.stderr)
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(SOCKET_PATH))
            s.sendall(command.encode())
            s.shutdown(socket.SHUT_WR)
            reply = s.recv(64).decode().strip()
        if reply == "ok":
            return True
        print(f"verbal: {reply or 'no reply'}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print("verbal: not running (no control socket)", file=sys.stderr)
        return False
    except ConnectionRefusedError:
        print("verbal: stale control socket - is Verbal running?", file=sys.stderr)
        return False
    except Exception as e:
        print(f"verbal: could not reach Verbal ({e})", file=sys.stderr)
        return False


def install_gnome_hotkey(binding: str = DEFAULT_HOTKEY, command: str = None) -> bool:
    """Register a GNOME custom keybinding that runs `verbal --toggle`.

    The compositor owns the key, so this works on Wayland where in-process capture cannot.
    Note GNOME keybindings are press-only: this gives toggle mode, not hold-to-talk.
    """
    import shlex
    import subprocess

    if command is None:
        if getattr(sys, "frozen", False):
            command = f"{shlex.quote(sys.executable)} --toggle"
        else:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            command = f"{shlex.quote(sys.executable)} -m app.linux_main --toggle"
            command = f"sh -c {shlex.quote(f'cd {shlex.quote(root)} && {command}')}"

    schema = "org.gnome.settings-daemon.plugins.media-keys"
    kb_schema = f"{schema}.custom-keybinding:{GNOME_KEYBIND_PATH}"
    try:
        existing = subprocess.run(
            ["gsettings", "get", schema, "custom-keybindings"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        # existing is a GVariant array literal, e.g. "@as []" or "['/path/', ...]"
        paths = []
        if existing.startswith("["):
            paths = [p.strip().strip("'\"") for p in existing[1:-1].split(",") if p.strip()]
        if GNOME_KEYBIND_PATH not in paths:
            paths.append(GNOME_KEYBIND_PATH)
        new_value = "[" + ", ".join(f"'{p}'" for p in paths) + "]"

        for args in (
            ["gsettings", "set", schema, "custom-keybindings", new_value],
            ["gsettings", "set", kb_schema, "name", "Verbal: toggle dictation"],
            ["gsettings", "set", kb_schema, "command", command],
            ["gsettings", "set", kb_schema, "binding", binding],
        ):
            subprocess.run(args, check=True, capture_output=True, text=True)

        print(f"Installed GNOME hotkey {binding} -> {command}")
        print("Verify under Settings > Keyboard > View and Customize Shortcuts > Custom.")
        return True
    except FileNotFoundError:
        print("verbal: gsettings not found - not a GNOME session?", file=sys.stderr)
        return False
    except subprocess.CalledProcessError as e:
        print(f"verbal: gsettings failed: {e.stderr or e}", file=sys.stderr)
        return False


def uninstall_gnome_hotkey() -> bool:
    import subprocess
    schema = "org.gnome.settings-daemon.plugins.media-keys"
    try:
        existing = subprocess.run(
            ["gsettings", "get", schema, "custom-keybindings"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        paths = []
        if existing.startswith("["):
            paths = [p.strip().strip("'\"") for p in existing[1:-1].split(",") if p.strip()]
        paths = [p for p in paths if p != GNOME_KEYBIND_PATH]
        new_value = "@as []" if not paths else "[" + ", ".join(f"'{p}'" for p in paths) + "]"
        subprocess.run(
            ["gsettings", "set", schema, "custom-keybindings", new_value],
            check=True, capture_output=True, text=True,
        )
        print("Removed Verbal GNOME hotkey.")
        return True
    except Exception as e:
        print(f"verbal: could not remove hotkey ({e})", file=sys.stderr)
        return False

# Audio players in preference order, as (binary, args-before-file). Distros vary wildly:
# paplay ships with pulseaudio-utils, pw-play with PipeWire, aplay with alsa-utils.
# Probed once at first use — never assume any single one exists.
_SOUND_PLAYERS = (
    ("pw-play", []),
    ("paplay", []),
    ("aplay", ["-q"]),
    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
    ("canberra-gtk-play", ["-f"]),
)

_sound_player = None      # None = not yet probed, False = none available
_sound_procs = []


def _find_sound_player():
    """Resolve a usable audio player once. Returns (binary, args) or False."""
    import shutil
    for binary, args in _SOUND_PLAYERS:
        path = shutil.which(binary)
        if path:
            logger.info(f"Sound player: {path}")
            return (path, args)
    logger.warning(
        "No audio player found (tried: %s) - dictation cues will be silent. "
        "Install pipewire-utils, pulseaudio-utils or alsa-utils.",
        ", ".join(b for b, _ in _SOUND_PLAYERS),
    )
    return False


def _play_sound(name: str):
    global _sound_player
    import subprocess
    try:
        if _sound_player is None:
            _sound_player = _find_sound_player()
        if not _sound_player:
            return

        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sound_path = os.path.join(base_dir, "assets", "sounds", f"{name}.wav")

        if not os.path.exists(sound_path):
            logger.debug(f"Sound file missing: {sound_path}")
            return

        # Reap any finished players so they don't linger as zombies.
        _sound_procs[:] = [p for p in _sound_procs if p.poll() is None]

        binary, args = _sound_player
        # non-blocking
        _sound_procs.append(subprocess.Popen(
            [binary, *args, sound_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        ))
    except Exception as e:
        logger.debug(f"Sound error: {e}")

class VerbalLinuxApp:
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
        self._lock_fd = None
        self._ipc_server = None
        self._shutting_down = False
        self._shutdown_done = False
        self._shutdown_lock = threading.Lock()
        self._exited = threading.Event()

        # Guards the whole recording state machine. Start/stop can arrive concurrently from
        # the hotkey listener, a tray callback, the IPC socket and the dashboard JS bridge;
        # without this two starts both reach recorder.start() and the first InputStream is
        # orphaned with the mic still open.
        self._state_lock = threading.RLock()

        self._menu_status = None
        self._menu_record = None

        from app.linux_overlay import LinuxOverlay
        from app.shared_dashboard import SharedDashboard

        self.overlay = LinuxOverlay()
        self.dashboard = SharedDashboard(self)

        history = self.config.get("history", [])
        self._total_transcriptions = len(history)
        self._total_words = sum(len(_entry_text(h).split()) for h in history)

        self._init_sync()

    def _build_tray_menu(self):
        import pystray

        self._menu_status = pystray.MenuItem(
            lambda item: self._status_text(), None, enabled=False
        )
        # default=True so backends that expose no menu at all (pystray._xorg) still do
        # something useful on a plain click instead of raising StopIteration.
        self._menu_record = pystray.MenuItem(
            lambda item: "Stop Recording" if self._is_recording else "Start Recording",
            self._tray_toggle_record,
            default=True,
        )

        mode_menu = pystray.Menu(
            pystray.MenuItem("Hold Key to Record", self._tray_set_mode_hold, checked=lambda item: self._mode == MODE_HOLD),
            pystray.MenuItem("Toggle On/Off", self._tray_set_mode_toggle, checked=lambda item: self._mode == MODE_TOGGLE),
        )

        model_menu = pystray.Menu(
            *[pystray.MenuItem(m, self._tray_change_model, checked=lambda item, mn=m: self.config.get("whisper_model", "base") == mn) for m in ["tiny", "base", "small", "medium"]]
        )

        # NOTE: no "Groq API Key..." item. Client-side key entry was deliberately removed
        # from every platform (Hard rule #15 / MER-34) — keys live server-side. Do not
        # re-add it here.
        self._menu_items = pystray.Menu(
            self._menu_status,
            self._menu_record,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Verbal", self._tray_open_dashboard),
            pystray.MenuItem("Settings...", self._tray_open_settings),
            pystray.MenuItem("Recording Mode", mode_menu),
            pystray.MenuItem("Whisper Model", model_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: f"Verbal v{APP_VERSION}", self._tray_about),
            pystray.MenuItem("Quit", self._tray_quit),
        )

        return self._menu_items

    def start(self):
        logger.info(f"=== VERBAL v{APP_VERSION} STARTING (Linux) ===")
        self._lock_fd = _acquire_single_instance()
        if self._lock_fd is None:
            logger.error("Verbal is already running - refusing to start a second instance.")
            print("Verbal is already running.", file=sys.stderr)
            return 1

        self.overlay.setup()
        self._start_hotkey()
        self._start_ipc_server()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._on_signal)
            except Exception:
                pass

        import pystray
        icon_image = self._create_icon_image(False)
        self._tray_icon = pystray.Icon(
            "Verbal", icon_image,
            f"Verbal v{APP_VERSION}",
            menu=self._build_tray_menu(),
        )

        backend = type(self._tray_icon).__module__
        if not getattr(type(self._tray_icon), "HAS_MENU", False):
            # pystray._xorg has HAS_MENU=False and won't dock on GNOME/Wayland — the app
            # would run with no icon, no menu and no way to quit. Say so loudly.
            logger.error(
                "Tray backend %s exposes NO MENU - Verbal will have no usable UI. "
                "Install PyGObject (python3-gi) + gir1.2-ayatanaappindicator3-0.1 and make "
                "them visible to this interpreter (venv needs --system-site-packages).",
                backend,
            )
        else:
            logger.info(f"Tray backend: {backend}")

        try:
            self._tray_icon.run()
        finally:
            # run() returns when stop() is called (tray Quit, or a signal) — do the real
            # teardown here on the MAIN thread, not from the callback thread.
            self._shutdown()
        return 0

    def _on_signal(self, signum, frame):
        logger.info(f"Received signal {signum} - shutting down")
        self._request_quit()

    def _request_quit(self):
        """Ask the main loop to exit. Safe to call from any thread."""
        self._shutting_down = True
        try:
            if self._tray_icon:
                self._tray_icon.stop()
        except Exception as e:
            logger.debug(f"Tray stop failed: {e}")
        threading.Thread(target=self._force_exit_watchdog, daemon=True).start()

    def _force_exit_watchdog(self):
        """Guarantee the process actually dies after a quit request.

        pystray's stop() does not reliably unwind Gtk.main() when called from a non-main
        thread (observed: main thread stayed parked in GTK's poll, run() never returned,
        _shutdown() never ran). Without this the process lingers holding the mic and the
        single-instance lock with no tray and no IPC — un-quittable except by kill.
        """
        if self._exited.wait(5.0):
            return
        logger.warning("Tray loop did not exit within 5s - forcing shutdown")
        try:
            self._shutdown()
        except Exception as e:
            logger.error(f"Forced shutdown failed: {e}")
        os._exit(0)

    def _shutdown(self):
        """Release everything. Must be idempotent — signals, Quit and the watchdog can all land."""
        with self._shutdown_lock:
            if self._shutdown_done:
                return
            self._shutdown_done = True
        logger.info("Shutting down...")
        try:
            with self._state_lock:
                if self._is_recording:
                    self._is_recording = False
                    self.recorder.stop()
        except Exception as e:
            logger.debug(f"Recorder stop failed: {e}")
        for label, fn in (
            ("recorder cleanup", lambda: self.recorder.cleanup()),
            ("hotkey listener", lambda: self._hotkey_listener.stop()),
            ("ipc server", self._stop_ipc_server),
            ("sync client", lambda: self._sync.stop()),
            ("overlay", lambda: self.overlay.destroy()),
        ):
            try:
                fn()
            except Exception as e:
                logger.debug(f"{label} teardown failed: {e}")
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)
            except Exception:
                pass
            self._lock_fd = None
        logger.info("Shutdown complete")
        self._exited.set()

    # ── IPC control socket ────────────────────────────────────────────────────
    def _start_ipc_server(self):
        try:
            if SOCKET_PATH.exists():
                SOCKET_PATH.unlink()   # safe: we hold the single-instance lock
        except Exception as e:
            logger.warning(f"Could not clear stale socket: {e}")
        try:
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(str(SOCKET_PATH))
            os.chmod(str(SOCKET_PATH), 0o600)
            srv.listen(4)
            self._ipc_server = srv
            threading.Thread(target=self._ipc_loop, daemon=True).start()
            logger.info(f"IPC socket listening at {SOCKET_PATH}")
        except Exception as e:
            # Peripheral: the tray and (on X11) the hotkey still work without it.
            logger.error(f"Could not start IPC socket: {e}")
            self._ipc_server = None

    def _stop_ipc_server(self):
        srv, self._ipc_server = self._ipc_server, None
        if srv:
            try:
                srv.close()
            except Exception:
                pass
        try:
            if SOCKET_PATH.exists():
                SOCKET_PATH.unlink()
        except Exception:
            pass

    def _ipc_loop(self):
        # Loop only on the socket's liveness, NOT on _shutting_down: exiting the moment a
        # quit is *requested* left the socket bound but unserviced, so if the tray loop
        # failed to unwind the app became unreachable AND un-quittable. _stop_ipc_server()
        # closes the socket, which breaks accept() with OSError below.
        while self._ipc_server is not None:
            try:
                conn, _ = self._ipc_server.accept()
            except OSError:
                return   # socket closed during shutdown
            except Exception as e:
                logger.debug(f"IPC accept failed: {e}")
                continue
            with conn:
                try:
                    conn.settimeout(2.0)
                    command = conn.recv(64).decode().strip().lower()
                    reply = self._handle_ipc_command(command)
                    conn.sendall(reply.encode())
                except Exception as e:
                    logger.debug(f"IPC command failed: {e}")

    def _handle_ipc_command(self, command: str) -> str:
        if command not in IPC_COMMANDS:
            return f"unknown command '{command}'"
        logger.info(f"IPC command: {command}")
        try:
            if command == "ping":
                pass
            elif command == "toggle":
                self._toggle_recording()
            elif command == "start":
                self._on_record_start()
            elif command == "stop":
                self._on_record_stop()
            elif command == "cancel":
                self._on_esc_pressed()
            elif command == "show":
                self._tray_open_dashboard()
            elif command == "quit":
                self._request_quit()
            return "ok"
        except Exception as e:
            logger.error(f"IPC command '{command}' failed: {e}", exc_info=True)
            return f"error: {e}"

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

    def _tray_toggle_record(self, icon=None, item=None):
        self._toggle_recording()

    def _tray_open_dashboard(self, icon=None, item=None):
        """Open the dashboard, from ANY thread.

        pywebview hard-refuses to start off the MainThread. Tray clicks are fine —
        appindicator dispatches them from the GTK main loop, which IS the main thread — but
        `verbal --show` arrives on the IPC socket thread, where webview.start() raised
        "pywebview must be run on a main thread" and the dashboard never opened. Marshal
        those onto the GTK loop instead. A nested webview.start() inside the running loop
        is fine (GTK supports nested main loops and the tray stays responsive).
        """
        if threading.current_thread().name != "MainThread":
            try:
                from gi.repository import GLib
                GLib.idle_add(self._open_dashboard)
                return
            except Exception as e:
                logger.error(f"Could not reach the main thread to open the dashboard: {e}")
                self.overlay.show_briefly("Dashboard unavailable", duration=2.5)
                return
        self._open_dashboard()

    def _open_dashboard(self):
        # SharedDashboard.show() only try/excepts `import webview`; on Linux the import
        # succeeds and the GTK/Qt backend resolution fails later inside webview.start(),
        # so the exception escapes into the caller. Contain it here.
        try:
            self.dashboard.show()
        except Exception as e:
            logger.error(f"Could not open dashboard: {e}")
            self.overlay.show_briefly("Dashboard unavailable", duration=2.5)
        return False   # GLib.idle_add: run once, then remove the source

    def _tray_open_settings(self, icon=None, item=None):
        # dashboard.show() blocks inside webview.start() until the window closes, so
        # selecting the tab inline would only fire after it was already gone. Wait for the
        # window to exist on a helper thread instead.
        def _select_settings_when_ready():
            for _ in range(100):          # ~10s ceiling
                if getattr(self.dashboard, "_window", None):
                    time.sleep(0.4)       # let pywebviewready wire up window.VerbalNative
                    try:
                        self.dashboard._on_tab_select(4)
                    except Exception as e:
                        logger.debug(f"Could not preselect settings tab: {e}")
                    return
                time.sleep(0.1)

        threading.Thread(target=_select_settings_when_ready, daemon=True).start()
        self._tray_open_dashboard()

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
        if item is None: return
        model_name = str(item.text if hasattr(item, 'text') else item)
        self.config["whisper_model"] = model_name
        save_config(self.config)
        self._update_tray_menu()


    def _tray_quit(self, icon=None, item=None):
        # sys.exit() here would only raise SystemExit in this callback thread and leave the
        # process alive. Stop the icon so run() returns on the main thread, which then runs
        # _shutdown() and releases the mic, listener, socket and lock.
        self._request_quit()

    def _tray_about(self, icon=None, item=None):
        # Deliberately NOT a tkinter messagebox: a parentless dialog binds to
        # tkinter._default_root, which is the OVERLAY's interpreter (it is created first),
        # so its modal loop would freeze the recording pill.
        self.overlay.show_briefly(f"Verbal v{APP_VERSION}", duration=2.5)

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
        if pressed_key == target_key:
            return True
        from pynput import keyboard
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
        logger.info(f"Hotkey listener started on Linux")

    def _on_key_press(self, key):
        try:
            from pynput import keyboard
            hold_key = self._parsed_hold_key
            toggle_key = self._parsed_toggle_key

            if hold_key == toggle_key and self._keys_match(key, hold_key):
                if self._mode == MODE_HOLD:
                    if not self._is_recording:
                        self._on_record_start()
                else:
                    now = time.time()
                    if now - self._last_toggle_time > 0.3:
                        self._last_toggle_time = now
                        self._toggle_recording()
                return

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
            if self._keys_match(key, self._parsed_hold_key):
                if self._parsed_hold_key == self._parsed_toggle_key:
                    if self._mode == MODE_HOLD and self._is_recording:
                        self._on_record_stop()
                else:
                    if self._is_recording:
                        self._on_record_stop()
        except Exception:
            pass

    def _toggle_recording(self):
        with self._state_lock:
            if self._is_recording:
                self._on_record_stop()
            else:
                self._on_record_start()

    def _on_esc_pressed(self):
        with self._state_lock:
            if self._processing:
                self._cancel_flag.set()
                self._reset_to_ready(preserve_processing=True)
            elif self._is_recording:
                self._cancel_recording()

    def _on_record_start(self):
        with self._state_lock:
            if self._processing:
                return
            # Without this, two concurrent starts (hotkey + tray + IPC + dashboard all
            # reach here) both call recorder.start(), which overwrites _stream and orphans
            # the first InputStream with the mic still open.
            if self._is_recording:
                return
            try:
                from app.linux_injector import save_focused_app
                save_focused_app()
            except Exception as e:
                logger.debug(f"save_focused_app failed: {e}")
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
        with self._state_lock:
            if not self._is_recording:
                return
            self._is_recording = False
            audio = self.recorder.stop()
            # Minimum viable clip. Recorder captures at the device's NATIVE rate (often
            # 44.1/48kHz), not 16kHz, so a hardcoded 8000 was really a ~0.17s gate.
            min_samples = int(0.5 * self.recorder.sample_rate)
            too_short = audio is None or len(audio) < min_samples
            if not too_short:
                self._processing = True

        _play_sound("stop")
        self._update_tray_icon(False)
        self._update_tray_menu()
        self.dashboard.update_recording_state(False)

        if too_short:
            self.overlay.hide()
            return

        self.overlay.update_status("Transcribing...")
        try:
            threading.Thread(target=self._process_audio, args=(audio,), daemon=True).start()
        except Exception as e:
            # Otherwise _processing stays True forever and the app goes permanently deaf.
            logger.error(f"Could not start processing thread: {e}", exc_info=True)
            self._reset_to_ready()

    def _cancel_recording(self):
        with self._state_lock:
            self._is_recording = False
            self.recorder.stop()
        _play_sound("stop")
        self._reset_to_ready()

    def _process_audio(self, audio):
        try:
            if self._cancel_flag.is_set(): return
            text = transcribe(audio, self.config, self.recorder.sample_rate)
            if self._cancel_flag.is_set(): return
            if not text:
                self.overlay.hide()
                return

            result = process_text(text, self.config)
            if self._cancel_flag.is_set(): return

            from app.linux_injector import get_focused_app_name, inject_text
            self.config = add_to_history(self.config, result, get_focused_app_name())
            word_count = len(result.split())
            self._total_transcriptions += 1
            self._total_words += word_count
            self.config = update_daily_words(self.config, word_count)
            self._update_tray_menu()

            self.overlay.hide()
            time.sleep(0.3)

            if self._cancel_flag.is_set(): return

            # Pass the cancel flag DOWN: inject_text polls it immediately before the
            # keystroke, so ESC during the ~200ms injection window actually stops the paste
            # instead of the text landing anyway.
            outcome = inject_text(result, should_cancel=self._cancel_flag.is_set)
            _play_sound("done")

            if self._sync:
                target = self.dashboard._target_device_id if self.dashboard else "__all__"
                if target not in (None, "__none__"):
                    push_target = None if target == "__all__" else target
                    threading.Thread(
                        target=self._sync.push, args=(result, push_target), daemon=True
                    ).start()

            if outcome.paste_sent:
                brief = f"Pasted | {word_count}w"
            elif outcome.copied:
                # Honest: the keystroke never went out, but the text IS on the clipboard.
                brief = f"Copied - press Ctrl+V | {word_count}w"
            else:
                brief = f"Clipboard failed | {word_count}w"
            self.overlay.show_briefly(brief, duration=2.0)
            self.dashboard.show_result(result)

        except Exception as e:
            logger.critical(f"PROCESS CRASH: {e}\n{traceback.format_exc()}")
            try:
                self.overlay.show_briefly("Error occurred", duration=2.0)
            except Exception:
                pass
            self._reset_to_ready()
        finally:
            self._processing = False

    def _reset_to_ready(self, preserve_processing=False):
        with self._state_lock:
            if not preserve_processing:
                self._processing = False
            self._is_recording = False
        # Do not clear a processing cancellation here. The worker checks this flag at
        # several boundaries (after transcription/cleanup and immediately before paste),
        # and clearing it from the UI thread lets an ESC race continue all the way to
        # injection. A new recording owns the reset and clears the flag in
        # _on_record_start(), after the previous worker has observed the cancellation.
        # preserve_processing blocks a rapid restart until that worker's finally runs.
        try:
            self.recorder.cleanup()
        except Exception:
            pass
        self.overlay.hide()
        self._update_tray_icon(False)
        self._update_tray_menu()
        self.dashboard.update_recording_state(False)

    def _init_sync(self):
        if not self.config.get("sync_enabled"): return
        user_id = self.config.get("sync_user_id", "").strip()
        if not user_id: return
        try:
            from app.sync import SyncClient
            device_name = self.config.get("sync_device_name", "Linux")
            self._sync = SyncClient(
                user_id=user_id,
                device_name=device_name,
                on_receive=self._on_sync_receive,
            )
        except Exception as e:
            logger.error(f"Sync init failed: {e}")

    def _on_sync_receive(self, text: str, device_name: str):
        # Never paste over an in-flight dictation: the two would interleave clipboard writes
        # and Ctrl+V pairs and paste each other's text. inject_text() also holds a lock.
        if self._is_recording or self._processing:
            logger.info(f"Deferring sync text from {device_name} - busy dictating")
            self.overlay.show_briefly(f"From {device_name} - on clipboard", duration=2.5)
            try:
                from app.linux_injector import copy_to_clipboard
                copy_to_clipboard(text)
            except Exception as e:
                logger.error(f"Sync clipboard copy failed: {e}")
            return
        try:
            from app.linux_injector import inject_text
            outcome = inject_text(text)
            action = "pasted" if outcome.paste_sent else ("on clipboard" if outcome.copied else "failed")
        except Exception as e:
            logger.error(f"Sync inject failed: {e}")
            action = "failed"
        brief = f"From {device_name} | {len(text.split())}w - {action}"
        self.overlay.show_briefly(brief, duration=2.5)


def _print_usage():
    print(
        "Verbal for Linux\n"
        "\n"
        "  verbal                      run the tray app\n"
        "  verbal --toggle             start/stop dictation in the running app\n"
        "  verbal --start | --stop     explicit start/stop\n"
        "  verbal --cancel             cancel the current recording/processing\n"
        "  verbal --show               open the dashboard\n"
        "  verbal --quit               shut the running app down\n"
        "  verbal --ping               check whether the app is running\n"
        "\n"
        "  verbal --install-hotkey [BINDING]   bind a GNOME shortcut to --toggle\n"
        f"                                      (default {DEFAULT_HOTKEY})\n"
        "  verbal --uninstall-hotkey           remove that shortcut\n"
        "\n"
        "Wayland note: the in-process global hotkey cannot see keys while another window is\n"
        "focused, so --install-hotkey (the compositor owns the key) is the supported path.\n"
    )


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv:
        arg = argv[0]
        if arg in ("-h", "--help"):
            _print_usage()
            return 0
        if arg == "--install-hotkey":
            binding = argv[1] if len(argv) > 1 else DEFAULT_HOTKEY
            return 0 if install_gnome_hotkey(binding) else 1
        if arg == "--uninstall-hotkey":
            return 0 if uninstall_gnome_hotkey() else 1
        if arg.startswith("--"):
            command = arg[2:]
            if command in IPC_COMMANDS:
                return 0 if send_ipc_command(command) else 1
        _print_usage()
        return 2

    app = VerbalLinuxApp()
    return app.start() or 0


if __name__ == "__main__":
    sys.exit(main())
