"""Verbal for Windows — system tray app with global hotkey dictation."""

import ctypes
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

# Windows defaults these streams to cp1252, which can't encode the em dashes,
# arrows and check marks our log messages use throughout (sync.py, transcriber.py,
# recorder.py, meetings.py, ...). logging swallows handler errors, so the line is
# silently dropped and replaced by a UnicodeEncodeError traceback — including on
# the dictation path. Force UTF-8 here rather than policing every f-string.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

# Declare DPI awareness HERE, before any window exists. Windows bitmap-stretches
# DPI-unaware processes, but pywebview flips this one to DPI-aware when WebView2
# builds its first window — which happens AFTER the tkinter overlay has already
# sized itself from a 96-DPI reading. The overlay then stayed at its unscaled
# size and rendered at half its intended dimensions on a 200% display. Declaring
# it up front makes win_overlay's DPI probe see the real value.
try:
    # -4 = DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()    # pre-8.1 fallback
        except Exception:
            pass

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
        logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("verbal")

MODE_HOLD = "hold"
MODE_TOGGLE = "toggle"

# Update-check scheduling (mirrors main.py's UPDATE_CHECK_INTERVAL). The first
# automatic check waits UPDATE_STARTUP_DELAY seconds because
# updater.check_for_update() deliberately returns None for the first 30 s after
# launch (the auto-install-loop guard keyed off sys._verbal_start_time). Before
# 2026-08-26 the Windows app fired its ONLY check of the session at t=0 — inside
# that gate — so a Flume 1.0.33 install never once asked Supabase about 1.0.34.
UPDATE_STARTUP_DELAY = 35
UPDATE_CHECK_INTERVAL = 4 * 60 * 60


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
        # Persistent "update available" state (Task: tray badge + menu item),
        # ported to the same state machine main.py's VerbalApp owns so the
        # cross-platform dashboard bridge (shared_dashboard.DashboardApi.
        # get_update_status / start_update_download / install_ready_update)
        # works identically on Windows. Until 2026-08-26 Windows only had
        # `_pending_update`, so every 30 s dashboard poll logged
        # "'VerbalWinApp' object has no attribute '_update_available'" and the
        # in-app banner / "Check for updates" button were dead here.
        #
        # `_update_available` holds the dict from updater.check_for_update()
        # once a newer version is found and stays set until a still-newer one
        # supersedes it or the app relaunches post-update. None == no known
        # update: the tray icon carries no badge and _menu_update is hidden.
        # `_pending_update` (below, a property) is a read/write alias so the
        # existing tray badge/menu code keeps reading the SAME state.
        #
        # In-dashboard flow — phase: 'idle' | 'downloading' | 'ready' |
        # 'installing' | 'failed'. 'ready' means the installer is on disk at
        # _update_ready_path and nothing has been installed yet: the
        # dashboard's "Update" click parks it there and waits for an explicit
        # "Restart to update" (_install_ready_update). The unattended
        # auto_update path (config default True) drives the same fields so
        # the banner can show what it is doing. (No `_update_dismissed_version`
        # here, unlike main.py: on Windows the dialog only ever shows for an
        # explicit click, so there is no automatic re-nag to suppress, and
        # "is this a new version?" compares against the previously found
        # dict instead — a field nothing reads is a trap for the next port.)
        self._update_available = None
        self._update_phase = "idle"
        self._update_progress = 0.0
        self._update_ready_path = None
        # Serialises download+install so the auto-update path, the tray
        # dialog's "Yes" and the dashboard's "Update" can never run two
        # downloads of the same installer concurrently.
        self._update_download_lock = threading.Lock()
        # Set by _hard_exit (from any thread) the moment a quit begins. Read
        # by SharedDashboard._on_window_closed (no tray hint while quitting)
        # and by _hard_exit itself as its re-entrancy guard, so it must exist
        # from __init__ on — a getattr default alone would hide a typo.
        self._exiting = False

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
        self.meeting_prompt = None
        try:
            from app.win_meeting_prompt import WinMeetingPrompt
            self.meeting_prompt = WinMeetingPrompt(self)
        except Exception as e:
            logger.error("meeting prompt init failed: %s", e)
        self._edit_watcher = None
        # Granola-style auto-detect state (mirrors main.py). Dismissal is
        # session-durable; empty-poll reset does NOT clear `_md_dismissed`.
        self._md_active_key = None
        self._md_handled = set()
        self._md_dismissed = set()
        self._md_empty = 0
        self._md_source = ""
        self._md_scanning = False
        self._meeting_mic_tap = None

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

    @property
    def _pending_update(self):
        """Alias of `_update_available` for the pre-existing tray badge/menu
        code (_menu_update, _create_icon_image, _update_tray_icon,
        _offer_update, _tray_open_update). getattr with a default so a read
        during __init__ — before the backing attr exists — is None, not an
        AttributeError."""
        return getattr(self, "_update_available", None)

    @_pending_update.setter
    def _pending_update(self, value):
        self._update_available = value

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

        # Sign-in gate for appearance: pystray accepts a callable for `enabled`
        # and re-evaluates it every time the menu is shown, which is the tray's
        # equivalent of NSMenuDelegate.menuNeedsUpdate: on macOS. Enforcement
        # does NOT rest on this — every callback below re-checks — so if a
        # pystray build ever ignored the callable, the rows would merely look
        # available while still refusing.
        def gated(item):
            return self._signed_in()

        # Dynamic status text
        self._menu_status = pystray.MenuItem(
            lambda item: self._status_text(), None, enabled=False
        )

        # Dynamic record button text
        self._menu_record = pystray.MenuItem(
            lambda item: ("Stop Recording" if self._is_recording
                          else "Start Recording" if self._signed_in()
                          else "Sign in to dictate"),
            self._tray_toggle_record, enabled=gated,
        )

        # Recording Mode submenu
        mode_menu = pystray.Menu(
            pystray.MenuItem("Hold Key to Record", self._tray_set_mode_hold, checked=lambda item: self._mode == MODE_HOLD, enabled=gated),
            pystray.MenuItem("Toggle On/Off", self._tray_set_mode_toggle, checked=lambda item: self._mode == MODE_TOGGLE, enabled=gated),
        )

        # Offline Model submenu — `whisper_model` feeds ONLY
        # transcriber._transcribe_local, the third-priority fallback after the Groq
        # proxy and Gemini. Named "Whisper Model" it read as the active engine, so
        # switching it looked broken. The real engine is `asr_model` (Settings →
        # Models). Same relabel as the macOS menubar.
        model_menu = pystray.Menu(
            *[pystray.MenuItem(m, self._tray_change_model, checked=lambda item, mn=m: self.config.get("whisper_model", "base") == mn, enabled=gated) for m in ["tiny", "base", "small", "medium"]]
        )

        # default=True routes the tray icon's LEFT-click to this item's
        # callback instead of opening the right-click menu. It's still shown
        # at the top of the menu so users can also invoke it via right-click.
        self._menu_open_popover = pystray.MenuItem(
            "Open Flume", self._tray_open_popover, default=True,
        )

        # Persistent "update available" row — hidden (visible=False) until
        # _offer_update() sets self._pending_update. Clicking it re-opens the
        # same update dialog on demand, which is the whole point of pairing
        # this with the tray icon's badge dot (_create_icon_image/
        # _update_tray_icon): once a user dismisses the popup with "No", the
        # badge + this menu item are the only remaining discoverability path
        # for that update, so both must persist across the session no matter
        # how many times the popup itself was declined.
        self._menu_update = pystray.MenuItem(
            lambda item: (
                f"Update available (v{self._pending_update['version']}) ↑"
                if self._pending_update else ""
            ),
            self._tray_open_update,
            visible=lambda item: self._pending_update is not None,
        )

        self._menu_items = pystray.Menu(
            self._menu_update,
            self._menu_open_popover,
            self._menu_status,
            self._menu_record,
            pystray.Menu.SEPARATOR,
            # "Open Dashboard" stays enabled while signed out — it renders the
            # sign-in wall, so it is part of the way back in. Named distinctly
            # from the "Open Flume" popover item above (self._menu_open_popover)
            # since they open two different surfaces.
            pystray.MenuItem("Open Dashboard", self._tray_open_dashboard),
            pystray.MenuItem("Open Canvas", self._tray_open_canvas, enabled=gated),
            pystray.MenuItem("Open Notes", self._tray_open_notes, enabled=gated),
            pystray.MenuItem(
                lambda item: (
                    "Return to Meeting"
                    if (self.meetings and self.meetings.active)
                    else "Start Meeting"
                ),
                self._tray_toggle_meeting, enabled=gated),
            pystray.MenuItem(
                "Auto-detect Meetings",
                self._toggle_meeting_autodetect,
                checked=lambda item: self.config.get("meeting_autodetect", True),
                enabled=gated),
            pystray.MenuItem("Settings...", self._tray_open_settings, enabled=gated),
            pystray.MenuItem("Recording Mode", mode_menu, enabled=gated),
            pystray.MenuItem("Offline Model", model_menu, enabled=gated),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: self._auth_menu_label(), self._tray_toggle_auth),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: f"Flume v{APP_VERSION}", self._tray_about),
            # Mac-parity with the menubar's "Check for Updates…". This is the
            # only caller of _check_update(announce_current=True) on Windows —
            # without it the "You're up to date" dialog and the force_dialog
            # re-offer were dead code that read as a live path (2026-08-26).
            pystray.MenuItem("Check for updates...", self._tray_check_updates),
            pystray.MenuItem("Quit", self._tray_quit),
        )

        return self._menu_items

    def start(self):
        logger.info(f"=== VERBAL v{APP_VERSION} STARTING (Windows) ===")
        # Make a paste Windows refuses visible instead of silent (paste_guard.py).
        try:
            from app import paste_guard
            paste_guard.set_prompt_hook(self._prompt_paste_blocked)
        except Exception as e:
            logger.debug("paste-blocked prompt hook not installed: %s", e)
        self._start_hotkey()
        # Update checks: a long-lived loop (first check after UPDATE_STARTUP_DELAY,
        # then every UPDATE_CHECK_INTERVAL) instead of the old one-shot thread,
        # which fired at t=0 inside updater's 30 s post-launch gate and was
        # then blocked by a once-per-session guard — i.e. it never checked at
        # all (2026-08-26: 1.0.33 never saw 1.0.34). See _update_check_loop.
        threading.Thread(target=self._update_check_loop, name="update-check", daemon=True).start()
        threading.Thread(target=self._presence_loop, daemon=True).start()

        import pystray

        # The first automatic update check is UPDATE_STARTUP_DELAY seconds away,
        # so this initial image is normally un-badged; still read the live
        # state rather than hard-coding False so a badge can never be silently
        # dropped by this construction if the timing ever changes.
        icon_image = self._create_icon_image(False, badge=self._pending_update is not None)
        self._tray_icon = pystray.Icon(
            "Flume", icon_image,
            f"Flume v{APP_VERSION}",
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
        threading.Thread(
            target=self._second_instance_watch, name="second-instance", daemon=True).start()

        # Tkinter overlay on its own thread.
        self.overlay.setup()
        # Autolearn confirm pill is also tkinter-hosted now (real
        # transparency, no WebView2 canvas). Start its mainloop up-front
        # so show() has a live tk.Tk to talk to.
        try:
            self.autolearn_widget.setup()
        except Exception as e:
            logger.debug(f"autolearn_widget.setup failed: {e}")
        try:
            if self.meeting_prompt is not None:
                self.meeting_prompt.setup()
        except Exception as e:
            logger.debug(f"meeting_prompt.setup failed: {e}")
        threading.Thread(
            target=self._meeting_detect_loop, name="meeting-detect",
            daemon=True).start()

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
            # Persistent WebView2 profile. pywebview's default private_mode
            # creates a brand-new Chromium profile under %TEMP% on EVERY
            # launch (cold cache, profile setup, and a tmpXXXX\EBWebView dir
            # left behind each run) — a visible chunk of the slow relaunch
            # reported 2026-08-28. Nothing user-visible depends on a private
            # profile: sign-in runs in the system browser (PKCE), not here.
            try:
                from app.config import CONFIG_DIR
                _wv_dir = os.path.join(str(CONFIG_DIR), "webview")
                os.makedirs(_wv_dir, exist_ok=True)
            except Exception as e:
                logger.debug("webview storage dir failed (%s); using private mode", e)
                _wv_dir = None
            logger.info("webview loop starting (%.1fs after launch)", time.time() - sys._verbal_start_time)
            if _wv_dir:
                webview.start(func=_open_dashboard_on_start, debug=False,
                              private_mode=False, storage_path=_wv_dir)
            else:
                webview.start(func=_open_dashboard_on_start, debug=False)
            # start() returns when every pywebview window is gone — Windows
            # shutdown destroys the hidden anchor too. Don't fall off into a
            # tray-only zombie that still holds the singleton mutex.
            self._hard_exit("webview loop ended")
        except Exception as e:
            logger.error(f"webview.start failed on main thread: {e}", exc_info=True)
            # Fail-closed: if the GUI loop can't run, keep the tray alive so
            # dictation still works. Block until the tray exits.
            tray_thread.join()

    _tray_base_cache = {}

    def _tray_asset(self, name):
        base = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "assets", name)

    @staticmethod
    def _taskbar_is_light():
        """Windows taskbar theme (HKCU Themes/Personalize SystemUsesLightTheme).
        Defaults to dark — the far more common setting — on any failure."""
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            try:
                v, _ = winreg.QueryValueEx(k, "SystemUsesLightTheme")
            finally:
                winreg.CloseKey(k)
            return int(v) == 1
        except Exception:
            return False

    def _create_icon_image(self, recording: bool, badge: bool = False):
        """The Flume bird mark, as on the Mac menubar (2026-08-29).

        `assets/icon.png` is the same black-on-transparent silhouette rumps
        shows as a template image; here we tint it for the taskbar theme
        (white on the default dark taskbar, near-black on a light one). While
        recording the mark sits in a terracotta disc so the state reads from
        across the room. Falls back to the old drawn glyph if the asset is
        missing, so the tray can never come up blank."""
        from PIL import Image, ImageDraw
        SIZE = 32
        img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        mask = None
        try:
            mask = self._tray_base_cache.get("icon")
            if mask is None:
                src = Image.open(self._tray_asset("icon.png")).convert("RGBA")
                mask = src.split()[3]                      # the silhouette IS the alpha
                self._tray_base_cache["icon"] = mask
        except Exception as e:
            logger.debug("tray icon asset unavailable (%s) — drawing fallback", e)
            mask = None
        if mask is not None:
            if recording:
                draw.ellipse([1, 1, SIZE - 1, SIZE - 1], fill=(200, 90, 62, 255))   # terracotta
                inner = int(SIZE * 0.68)
                tint = (255, 255, 255, 255)
            else:
                inner = SIZE
                tint = (28, 28, 30, 255) if self._taskbar_is_light() else (245, 245, 245, 255)
            m = mask.resize((inner, inner), Image.LANCZOS)
            glyph = Image.new("RGBA", (inner, inner), tint)
            glyph.putalpha(m)
            off = (SIZE - inner) // 2
            img.alpha_composite(glyph, (off, off))
        else:
            color = (232, 82, 42, 255) if recording else (242, 239, 233, 255)
            draw.ellipse([4, 4, 28, 28], fill=color)
            draw.ellipse([10, 8, 22, 20], fill=(26, 25, 23, 255))
            draw.rectangle([14, 20, 18, 26], fill=(26, 25, 23, 255))
        if badge:
            # "Update available" dot — pystray supports live-swapping `.icon`
            # on a running Icon, so _update_tray_icon() applies this any time.
            # A dark ring keeps the green legible on every base.
            draw = ImageDraw.Draw(img)
            draw.ellipse([20, 0, 32, 12], fill=(26, 25, 23, 255))
            draw.ellipse([22, 2, 30, 10], fill=(58, 166, 92, 255))
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
                badge = self._pending_update is not None
                self._tray_icon.icon = self._create_icon_image(recording, badge=badge)
                self._tray_icon.title = "Flume - Recording..." if recording else f"Flume v{APP_VERSION}"
        except Exception:
            pass

    # ── Tray menu callbacks ─────────────────────────────────────────────
    # NB: every callback below re-checks the sign-in gate. The `enabled=`
    # callables in _build_tray_menu only control how the rows LOOK; these
    # returns are what make them refuse.
    def _tray_toggle_record(self, icon=None, item=None):
        # _on_record_start gates too, but stopping needs no account and this
        # keeps the refusal (and the prompt) at the tray edge.
        if not self._is_recording and not self._require_signin():
            return
        self._toggle_recording()

    def _tray_open_popover(self, icon=None, item=None):
        """Left-click default: open the compact Flume popover.

        Marked as pystray's default menu item so a left-click on the tray icon
        invokes this instead of showing the right-click menu. Right-click still
        shows the full menu.

        Signed out, the popover is a panel of dead buttons, so left-click goes
        to the dashboard's sign-in wall instead — the one thing that IS useful.
        """
        if not self._signed_in():
            logger.info("popover suppressed: not signed in")
            self._prompt_sign_in()
            return
        try:
            self.popover.toggle()
        except Exception as e:
            logger.error(f"popover toggle failed: {e}", exc_info=True)

    def _tray_open_dashboard(self, icon=None, item=None):
        self.dashboard.show()

    def _tray_open_canvas(self, icon=None, item=None):
        if not self._require_signin():
            return
        self.dashboard.show_tab("canvas")

    def _tray_open_notes(self, icon=None, item=None):
        if not self._require_signin():
            return
        self.dashboard.show_tab("notes")

    def _tray_toggle_meeting(self, icon=None, item=None):
        if not self._require_signin():
            return
        self._toggle_meeting()

    def _tray_open_settings(self, icon=None, item=None):
        if not self._require_signin():
            return
        self.dashboard.show_tab("settings")

    def _tray_set_mode_hold(self, icon=None, item=None):
        if not self._require_signin():
            return
        self._mode = MODE_HOLD
        self.config["recording_mode"] = MODE_HOLD
        save_config(self.config)
        self._update_tray_menu()

    def _tray_set_mode_toggle(self, icon=None, item=None):
        if not self._require_signin():
            return
        self._mode = MODE_TOGGLE
        self.config["recording_mode"] = MODE_TOGGLE
        save_config(self.config)
        self._update_tray_menu()

    def _tray_change_model(self, icon=None, item=None):
        if item is None or not self._require_signin():
            return
        model_name = str(item.text if hasattr(item, 'text') else item)
        self.config["whisper_model"] = model_name
        save_config(self.config)
        self._update_tray_menu()

    def _prompt_paste_blocked(self, reason, target_app):
        """Popup for a paste Windows refused (UIPI), offering the elevated restart.

        tkinter needs its own throwaway root — the same withdraw/destroy dance
        every other dialog in this file does. Throttling lives in paste_guard.
        """
        # Off the caller's thread: paste_guard invokes this hook inline from
        # the inject path (win_injector -> _process_audio worker), so a modal
        # box here kept `_processing` True — next hotkey refused, overlay stuck
        # on "transcribing" — until the user answered (review 2026-08-28).
        threading.Thread(target=self._prompt_paste_blocked_dialog, args=(reason, target_app),
                         name="paste-blocked-prompt", daemon=True).start()
        return None

    def _prompt_paste_blocked_dialog(self, reason, target_app):
        try:
            from app import paste_guard
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
            except Exception:
                pass
            # parent=root: without it tkinter's commondialog uses
            # _default_root — the OVERLAY's Tk on another thread — and the
            # recording pill's mainloop freezes for as long as the box is open.
            yes = messagebox.askyesno(paste_guard.title(reason),
                                      paste_guard.message(reason, target_app), parent=root)
            root.destroy()
            if yes and paste_guard.open_fix(reason):
                # The elevated copy is starting and the singleton mutex has been
                # released — this process has to go now, or the new one sees the
                # name still taken and exits instead.
                logger.info("quitting for the elevated relaunch")
                self._tray_quit()
        except Exception as e:
            logger.error(f"paste-blocked prompt failed: {e}")

    def _tray_quit(self, icon=None, item=None):
        """Quit for real (tray menu "Quit", popover quit_app, elevated relaunch).

        Thin wrapper: the actual teardown lives in _hard_exit so the
        bootloader-parent watcher (_watch_bootloader_parent) and the user's
        Quit share ONE implementation — two hand-rolled exit paths would
        drift apart, and this one has already been fixed once (2026-08-26).
        """
        self._hard_exit("quit requested")

    def _hard_exit(self, reason: str):
        """Tear down the process for real, from ANY thread. Never returns.

        os._exit, NOT sys.exit: callers run on the pystray thread (tray menu),
        on an _on_main daemon thread (popover's quit_app / the elevated
        relaunch), or on the parent-watcher thread — never on the main thread,
        which is parked in webview.start(). sys.exit() from a worker thread
        raises SystemExit in THAT thread only, so the old code stopped the tray
        icon and then left the process alive: no icon, no window, but still
        holding the single-instance mutex. Every later double-click on Flume
        hit ERROR_ALREADY_EXISTS and exited silently — reported 2026-08-26 as
        "after closing the app it doesn't open again". Same lesson as
        updater.install_update. Config writes are atomic, so nothing is lost.

        Deliberately MINIMAL: hide the tray icon (else Windows keeps a ghost
        icon until the mouse sweeps the notification area), drop the webview
        windows, flush logs, exit. No network, no meeting-session stops, no
        config writes — anything that can block or raise here is a way for the
        process to lurk in Task Manager again. Every step is guarded and every
        step is optional; os._exit(0) is the only thing that must happen.

        The optional teardown is also TIME-BOUNDED (daemon thread, joined for
        at most ~1 s). pywebview's winforms `destroy()` does a synchronous
        Control.Invoke onto the GUI/main thread, so with that thread stalled
        or deadlocked an inline destroy never returns and os._exit is never
        reached — the process keeps the mutex and lurks, which is exactly the
        state a user is in when they resort to Task Manager (they kill Flume
        because it looks hung). The "child exits within ~1 s" contract must
        hold regardless of GUI-thread health.

        Re-entrant: tray Quit and the bootloader-parent watcher (or the
        elevated-relaunch quit) can fire at the same moment. The second caller
        skips the teardown — a second stop() on a stopped icon / destroy() on
        a half-closed form only raises inside pystray/pywebview — and just
        exits after giving the first a moment to flush.
        """
        # Let SharedDashboard._on_window_closed tell "user closed the window"
        # apart from "we are destroying windows on the way out" (no tray hint
        # toast while quitting). Set BEFORE the destroys below fire `closed`.
        if getattr(self, "_exiting", False):
            logger.info("exit already in progress (%s)", reason)
            time.sleep(1.5)
            os._exit(0)
        self._exiting = True
        logger.info("exiting process: %s", reason)
        # Release the singleton mutex FIRST: a relaunch during the ~1.5 s
        # teardown below used to lose the mutex race, signal the dying
        # process and exit — "I quit and reopened it, nothing came up".
        try:
            h = getattr(sys, "_verbal_singleton_mutex", None)
            if h:
                import ctypes
                ctypes.windll.kernel32.ReleaseMutex(h)
                ctypes.windll.kernel32.CloseHandle(h)
                sys._verbal_singleton_mutex = None
        except Exception as e:
            logger.debug("mutex release failed: %s", e)

        def _teardown():
            try:
                icon = self._tray_icon
                if icon:
                    # `visible = False` calls pystray's _hide() — Shell_NotifyIcon
                    # NIM_DELETE — synchronously, from any thread. stop() alone
                    # only PostMessage()s WM_STOP and relies on _mainloop's
                    # `finally` to delete the icon, but when Quit is clicked we
                    # ARE on the pystray message-loop thread and os._exit fires
                    # before control ever returns to that loop → ghost icon.
                    try:
                        icon.visible = False
                    except Exception as e:
                        logger.debug("tray hide failed: %s", e)
                    icon.stop()
            except Exception as e:
                logger.debug("tray stop failed: %s", e)
            try:
                import webview
                for w in list(getattr(webview, "windows", [])):
                    try:
                        w.destroy()
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            t = threading.Thread(target=_teardown, name="hard-exit-teardown", daemon=True)
            t.start()
            t.join(1.0)
            if t.is_alive():
                logger.info("teardown still running after 1 s (%s); exiting anyway", reason)
        except Exception as e:
            logger.debug("teardown thread failed: %s", e)
        try:
            logging.shutdown()
        except Exception:
            pass
        os._exit(0)

    def _second_instance_watch(self):
        """Wake the running app when the user launches Flume again.

        Closing the dashboard window leaves the process in the tray (by
        design), so the natural next step — double-clicking the Flume shortcut
        — spawns a second process that loses the singleton mutex. Instead of
        that copy dying silently, it pulses a named Event and this thread
        answers by showing the dashboard: to the user, "opening the app"
        opens the app. Fail-closed — if anything here breaks, the tray still
        works exactly as before.
        """
        try:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.windll.kernel32
            k32.CreateEventW.restype = wintypes.HANDLE
            k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
            k32.WaitForSingleObject.restype = wintypes.DWORD
            k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            # Auto-reset (bManualReset=False): one SetEvent → one wake.
            h = k32.CreateEventW(None, False, False, SHOW_EVENT_NAME)
            if not h:
                logger.debug("second-instance event create failed")
                return
            sys._verbal_show_event = h
            INFINITE = 0xFFFFFFFF
            while True:
                if k32.WaitForSingleObject(h, INFINITE) != 0:
                    break
                logger.info("second launch detected — showing dashboard")
                try:
                    self.dashboard.show()
                except Exception as e:
                    logger.error("dashboard show on second launch failed: %s", e)
        except Exception as e:
            logger.debug("second-instance watch died: %s", e)

    def _tray_about(self, icon=None, item=None):
        # pystray runs menu callbacks ON its message-loop thread: a modal box
        # here made the tray unresponsive until dismissed. Guarded too — an
        # unhandled TclError would propagate into pystray's win32 handler.
        def _show():
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                messagebox.showinfo(
                    f"Flume v{APP_VERSION}",
                    "Voice to text, instantly.\n\n"
                    "Hold Right Alt to record (Hold mode)\n"
                    "or press once to start/stop (Toggle mode).\n"
                    "Press ESC to cancel anytime.\n\n"
                    "Powered by Whisper + Gemini",
                    parent=root,
                )
                root.destroy()
            except Exception as e:
                logger.error("about dialog failed: %s", e)
        threading.Thread(target=_show, name="about-dialog", daemon=True).start()

    def _tray_check_updates(self, icon=None, item=None):
        """Tray "Check for updates..." — an explicit click, so announce the
        result either way (dialog for "up to date" too; silence reads as a
        broken row) and skip updater's 30 s post-launch gate (force=True: a
        human clicking cannot produce the auto-install loop the gate guards
        against). Off the pystray callback thread — the network call must not
        freeze the tray menu."""
        threading.Thread(
            target=self._check_update, kwargs={"announce_current": True, "force": True},
            name="update-check-now", daemon=True).start()

    def _tray_open_update(self, icon=None, item=None):
        """Tray menu row shown only while an update is pending (see
        _menu_update). Re-opens the SAME dialog _offer_update shows on the
        original check, ignoring the "already seen this version" gate —
        an explicit click here is the user asking to see it again, not the
        periodic check nagging them."""
        if self._pending_update:
            threading.Thread(target=self._offer_update, args=(self._pending_update,),
                             kwargs={"force_dialog": True}, name="update-dialog", daemon=True).start()

    # ── Sign-in gate (IDI-183, mirrors main.py on macOS) ──────────────────
    # Flume requires an account, so nothing account-shaped may run without one.
    # Defence in depth, because the tray is a different beast from an NSMenu:
    #   1. `enabled=` callables grey the rows out (appearance),
    #   2. every tray callback re-checks (enforcement — a greyed row that still
    #      fires, or a pystray build that ignores callables, changes nothing),
    #   3. `_on_record_start` refuses (covers the hotkeys, which bypass the tray
    #      entirely).
    _SIGNIN_PROMPT_EVERY = 4.0

    def _signed_in(self) -> bool:
        """Fails CLOSED — an auth error blocks the feature rather than allowing it."""
        try:
            return bool(auth.current_user())
        except Exception as e:
            logger.warning(f"auth check failed, treating as signed out: {e}")
            return False

    def _prompt_sign_in(self):
        """Surface the dashboard's sign-in wall, at most once every few seconds —
        a held hotkey re-fires this path continuously."""
        now = time.time()
        if now - getattr(self, "_last_signin_prompt", 0.0) < self._SIGNIN_PROMPT_EVERY:
            return
        self._last_signin_prompt = now
        try:
            self.dashboard.show()
            self.dashboard._refresh()
        except Exception as e:
            logger.warning(f"sign-in prompt failed: {e}")

    def _require_signin(self) -> bool:
        """True when the caller may proceed; otherwise prompts and returns False."""
        if self._signed_in():
            return True
        logger.info("blocked: not signed in")
        self._prompt_sign_in()
        return False

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
            # A device that just JOINED the account starts blind (the sync
            # watermark is seeded to NOW) — pull the newest cloud rows so
            # History isn't empty on a fresh machine (2026-08-15).
            self._bootstrap_history_async()
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
            # Stop ACTIVE work first (IDI-170) — mirrors main._sign_out.
            # An in-flight meeting must not keep capturing after the account
            # that started it is gone.
            try:
                meetings = getattr(self, "meetings", None)
                if meetings and meetings.active:
                    meetings.stop_async()
            except Exception as e:
                logger.debug(f"meeting stop on sign-out skipped: {e}")
            # Same rule for dictation (IDI-183): signed-out dictation is refused
            # at the start, so a recording already in flight must not survive the
            # sign-out and paste a transcript for the account we just left.
            if self._is_recording:
                logger.info("cancelling in-flight dictation on sign-out")
                try:
                    self._cancel_recording()
                except Exception as e:
                    logger.warning(f"cancel on sign-out failed: {e}")
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

    def _notify_mic_permission_blocked(self):
        """Tell the user, clearly and ONCE, that recording failed — likely
        because Microphone access is blocked in Windows Settings.

        Windows has no macOS-TCC-style programmatic "request access" call a
        desktop (non-UWP) app can make to trigger a fresh permission dialog:
        access is gated entirely by Settings > Privacy > Microphone, and if
        it's blocked, opening the mic stream just fails with no OS prompt
        ever appearing. So the fix here isn't "trigger a prompt" (not
        possible) — it's detecting the failure and surfacing it immediately,
        instead of the previous silent `recorder.start()` failure that left
        the user with no idea why the hotkey did nothing.

        Gated by config['mic_permission_notified'] (anti-nag pattern, same
        shape as config['autolearn_declined'] — see conventions #9): shown
        once, then suppressed on every subsequent failed hotkey press until
        `_on_record_start` sees the mic open successfully again, at which
        point it clears the flag so a later regression is reported again.

        Fail-closed throughout (Hard Rule #1) — this must never raise back
        into the record-start path; the caller already wraps this call too.
        """
        if self.config.get("mic_permission_notified", False):
            return
        title = "Flume couldn't start recording"
        msg = ("Microphone access looks blocked in Windows. Click to open "
               "Settings > Privacy > Microphone and allow desktop apps.")
        notified = False
        # 1. winotify (lightweight, no COM server thread) — the only backend
        # here that supports an action button, so it can deep-link straight
        # to the Settings page. Same backend/order as
        # shared_dashboard.py::_notify_native's canvas toast.
        try:
            from winotify import Notification
            toast = Notification(app_id="Flume", title=title, msg=msg)
            toast.add_actions(label="Open Microphone Settings",
                               launch="ms-settings:privacy-microphone")
            toast.show()
            notified = True
        except Exception as e:
            logger.debug(f"mic-permission winotify unavailable: {e}")
        # 2. win10toast (no action-button support, but still visible)
        if not notified:
            try:
                from win10toast import ToastNotifier
                ToastNotifier().show_toast(title, msg, duration=8, threaded=True)
                notified = True
            except Exception as e:
                logger.debug(f"mic-permission win10toast unavailable: {e}")
        # 3. Fall back to the pystray tray icon's own notify(), if available.
        if not notified:
            try:
                icon = getattr(self, "_tray_icon", None)
                if icon is not None and hasattr(icon, "notify"):
                    icon.notify(msg, title)
                    notified = True
            except Exception as e:
                logger.debug(f"mic-permission tray notify unavailable: {e}")
        if not notified:
            logger.warning(f"mic permission blocked, no toast backend available: {msg}")
        self.config["mic_permission_notified"] = True
        try:
            save_config(self.config)
        except Exception as e:
            logger.debug(f"mic-permission flag save failed: {e}")

    def _on_record_start(self):
        if self._processing:
            return
        if self._is_recording:
            return
        # The single choke point every start path reaches — tray row, toggle key
        # and hold key (see the HotkeyListener wiring: on_start/on_toggle both
        # land here). Checked before anything is saved or harvested.
        if not self._signed_in():
            logger.info("dictation blocked: not signed in")
            self._prompt_sign_in()
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
        # Latch BEFORE the mic opens (Mac parity). Overlay Cancel on the
        # Starting pill goes through `_on_esc_pressed` → `_cancel_recording`;
        # if `_is_recording` is still False that path is a no-op and the
        # dictation starts anyway after the warm-up wait.
        self._is_recording = True
        # Acknowledge the keypress BEFORE opening the mic. recorder.start() waits for
        # the first audio buffer (~275ms of device warm-up, measured), and showing the
        # pill after that made the warm-up read as app lag. The label stays "Starting"
        # until audio is actually flowing — saying "Listening" early would invite the
        # user to speak into a mic that is not live yet. Mirrors main.py.
        try:
            self.overlay.show("Starting...")
        except Exception:
            pass
        try:
            # During a meeting, dictation SHARES the meeting's mic stream via
            # a tap — a second InputStream on the same device makes WASAPI /
            # PortAudio drop one of them (Hard Rule #18, same as Mac).
            mt = self.meetings.active if self.meetings else None
            if mt is not None and mt.mic_running:
                self._meeting_mic_tap = self.recorder.feed_external
                mt.add_mic_tap(self._meeting_mic_tap)
                self.recorder.start_external(16000)
            else:
                self._meeting_mic_tap = None
                self.recorder.start()
        except Exception as e:
            logger.error(f"Failed to start recording: {e}", exc_info=True)
            self._is_recording = False
            try:
                self._detach_meeting_tap()
            except Exception:
                pass
            try:
                self.overlay.hide()      # never leave "Starting..." stranded
            except Exception:
                pass
            try:
                self._notify_mic_permission_blocked()
            except Exception as ne:
                logger.debug(f"mic-permission notify failed: {ne}")
            return
        # The mic just opened successfully — if we'd previously warned about a
        # blocked microphone, the block is gone (Settings changed, device came
        # back, etc.). Clear the one-time flag so a LATER regression is
        # reported again instead of staying silent forever.
        if self.config.get("mic_permission_notified", False):
            try:
                self.config["mic_permission_notified"] = False
                save_config(self.config)
            except Exception as e:
                logger.debug(f"mic-permission flag reset failed: {e}")
        # Hybrid pipeline: open the streaming socket and tap the mic, so a long
        # dictation is transcribed by the time you stop. Mirrors main.py; fully
        # guarded, so a failure here just means this take goes the ordinary way.
        self._stream = None
        try:
            from app import asr_stream as _as
            _prov = _as.should_stream(self.config)
            if _prov:
                _s = _as.AsrStream(_prov, self.config)
                if _s.start():
                    self._stream = _s
                    self.recorder.set_tap(_s.feed)
                    logger.info("[hybrid] streaming to %s", _prov)
                else:
                    logger.warning("[hybrid] stream unavailable (%s) — normal path", _s.error)
        except Exception as e:
            logger.warning("[hybrid] setup skipped: %s", e)
            self._stream = None
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
        self._detach_meeting_tap()
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
        self._detach_meeting_tap()
        _play_sound("stop")
        self._reset_to_ready()

    def _transcribe_with_retry(self, audio, attempts=3, chain=None, sidecar=None):
        """Transcribe, auto-retrying on 'failed' (transient network/API) with a
        short backoff. Returns (text, status). Silence returns immediately.
        Mirrors main.py:_transcribe_with_retry."""
        text, status = "", "failed"
        for i in range(attempts):
            if self._cancel_flag.is_set():
                return "", "silent"
            try:
                if sidecar is not None:
                    sidecar.clear()
                text, status = transcribe_with_status(
                    audio, self.config, self.recorder.sample_rate,
                    chain=chain, sidecar=sidecar)
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
        # Save the recording locally (playback backup + retry cache) on a
        # background thread, same as the Mac app: the archive write has nothing
        # to do with the transcript, so it runs alongside the network call rather
        # than in front of it. `_saved_path()` joins it before first use.
        # Fail-closed: a save failure leaves the path None and never blocks
        # transcription/injection.
        rec_id = recordings.new_id()
        _saved = {}

        def _save():
            try:
                _saved["path"] = recordings.save_wav(audio, self.recorder.sample_rate, rec_id)
                logger.info(f"Recording saved: {_saved['path']} (id={rec_id})")
            except Exception as e:
                logger.error(f"save_wav failed: {e}")
                _saved["path"] = None

        _saver = threading.Thread(target=_save, daemon=True)
        _saver.start()

        def _saved_path():
            _saver.join(timeout=10)
            return _saved.get("path")

        try:
            if self._cancel_flag.is_set():
                return

            from app.win_injector import get_focused_app_name

            # chained_mode: format inside the transcription round trip. Mirrors
            # main.py — see build_chain_spec(). None when the flag is off.
            _chain, _side = None, {}
            try:
                from app.ai_cleanup import build_chain_spec
                _chain = build_chain_spec(self.config, active_app=get_focused_app_name())
            except Exception as e:
                logger.debug("chained_mode setup skipped: %s", e)

            # Hybrid: a long take is already transcribed, so skip the upload+ASR leg.
            # Short takes deliberately do NOT use it — Groq's one round trip is faster
            # below the measured ~8s crossover. Mirrors main.py.
            text, status = None, None
            _st, self._stream = getattr(self, "_stream", None), None
            if _st is not None:
                try:
                    from app import asr_stream as _as
                    _secs = len(audio) / float(self.recorder.sample_rate or 16000)
                    if _secs >= _as.HYBRID_THRESHOLD_SEC:
                        _streamed = _st.finish()
                        if _streamed:
                            # Never went through transcriber.finalize(), so the
                            # dictionary must be applied here or it silently stops
                            # working on exactly the long dictations this path serves.
                            try:
                                from app import dictionary as _d
                                _streamed = _d.apply_replacements(_streamed, self.config)
                            except Exception as e:
                                logger.debug("[hybrid] dictionary pass skipped: %s", e)
                            logger.info("[hybrid] used streamed transcript (%.1fs speech)", _secs)
                            text, status = _streamed, "ok"
                        else:
                            logger.warning("[hybrid] no streamed transcript (%s) — "
                                           "transcribing normally", _st.error)
                    else:
                        logger.info("[hybrid] %.1fs < %.0fs — using Groq",
                                    _secs, _as.HYBRID_THRESHOLD_SEC)
                        _st.finish(timeout=0.1)
                except Exception as e:
                    logger.warning("[hybrid] falling back: %s", e)
                    text, status = None, None

            if text is None:
                text, status = self._transcribe_with_retry(audio, chain=_chain, sidecar=_side)
            elif _chain is not None:
                # A streamed transcript never hit the proxy, so nothing was formatted
                # server-side; clear the sidecar so process_text formats it itself.
                _side.clear()
            if self._cancel_flag.is_set():
                return

            # "silent" — empty/too-short audio. Discard the WAV, tell the user.
            if status == "silent":
                logger.warning("No speech detected — discarding recording")
                _discard = _saved_path()
                if _discard:
                    try:
                        os.remove(_discard)
                    except Exception:
                        pass
                try:
                    self.overlay.show_briefly("No speech detected. Speak louder!", duration=1.5, error=True)
                except Exception:
                    pass
                self._reset_to_ready()
                return

            # "failed" — network/API down. Keep the audio + a retryable entry.
            if status == "failed":
                logger.error("Transcription failed after retries — saved for retry")
                _path = _saved_path()
                try:
                    self.config = add_to_history(
                        self.config, "", get_focused_app_name(),
                        entry_id=rec_id, audio=_path or "", status="failed")
                except Exception as e:
                    logger.error(f"failed-entry write failed: {e}")
                self._upload_recording_async(rec_id, _path)
                try:
                    self.overlay.show_briefly("Transcription failed — retry from History", duration=2.0, error=True)
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
                                      active_app=get_focused_app_name(),
                                      chained_result=_side.get("formatted"))
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

            # Joins the background archive write; transcription + cleanup have
            # already run, so it finished long ago and this returns immediately.
            audio_path = _saved_path()
            word_count = len(result.split())
            # Resolve the dictation TARGET before injection — inject_text()
            # restores focus, so a later read can name a different app.
            target_app = get_focused_app_name()

            self.overlay.hide()
            time.sleep(0.3)

            if self._cancel_flag.is_set():
                return

            from app.win_injector import inject_text
            success = inject_text(
                result,
                allow_mentions=self.config.get("filetag_enabled", False),
                # Hand the user's clipboard back after the paste lands
                # (delayed; never on the blocked-paste fallback).
                restore_clipboard=self.config.get("restore_clipboard", True),
            )
            _play_sound("done")

            # Persist AFTER the paste (same as macOS): two atomic config.json
            # writes the user should never wait on. Must land here — before the
            # sync-push and upload blocks below, which look the entry up by
            # rec_id — and the tray rebuild has to follow the counter bump.
            try:
                self.config = add_to_history(
                    self.config, result, target_app,
                    entry_id=rec_id, audio=audio_path or "", status="done")
            except Exception as e:
                logger.error(f"history write failed: {e}")
            self._total_transcriptions += 1
            self._total_words += word_count
            try:
                self.config = update_daily_words(self.config, word_count)
            except Exception:
                pass
            self._update_tray_menu()

            # Insights ledger (peripheral, fail-closed — insights.py owns the
            # guarantees). Same post-paste slot as macOS.
            try:
                from app import insights as _ins
                _secs = len(audio) / float(self.recorder.sample_rate or 16000)
                _ins.record_dictation(self.config, save_config, word_count,
                                      seconds=_secs, app_name=target_app,
                                      fx_words=_ins.polish_delta(text, result))
            except Exception as e:
                logger.debug(f"insights record skipped: {e}")

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
                    try:
                        _push_ms = int(len(audio) / float(self.recorder.sample_rate or 16000) * 1000)
                    except Exception:
                        _push_ms = 0
                    threading.Thread(
                        target=self._sync.push,
                        args=(result, push_target, entry.get("audio_url") or "",
                              "done", rec_id, _push_ms, target_app or ""),
                        daemon=True,
                    ).start()

            # Upload the audio to the cloud + attach its URL (async, fail-closed).
            self._upload_recording_async(rec_id, audio_path)

            brief = f"Pasted | {word_count}w" if success else f"Copied | {word_count}w"
            self.overlay.show_briefly(brief, duration=2.0)
            self.dashboard.show_result(result)

        except Exception as e:
            logger.critical(f"PROCESS CRASH: {e}\n{traceback.format_exc()}")
            try:
                self.overlay.show_briefly("Error occurred", duration=2.0, error=True)
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

    def _detach_meeting_tap(self):
        try:
            tap = getattr(self, "_meeting_mic_tap", None)
            if tap and self.meetings and self.meetings.session:
                self.meetings.session.remove_mic_tap(tap)
            self._meeting_mic_tap = None
        except Exception:
            pass

    def _meeting_detect_loop(self):
        """5 s poll — Mac uses rumps.Timer; we don't have rumps. Fail-closed."""
        while not getattr(self, "_exiting", False):
            try:
                self._detect_meeting_tick()
            except Exception:
                pass
            for _ in range(50):
                if getattr(self, "_exiting", False):
                    return
                time.sleep(0.1)

    def _detect_meeting_tick(self):
        """Cheap guards, then run the window scan off-thread (EnumWindows is
        cheap but `_md_apply` must not run nested in the poll loop)."""
        try:
            if not self.meetings:
                return
            if not self.config.get("meeting_autodetect", True):
                if self.meeting_prompt and self.meeting_prompt.visible:
                    self.meeting_prompt.hide()
                return
            if self.meetings.active:
                if self.meeting_prompt and self.meeting_prompt.visible:
                    self.meeting_prompt.hide()
                return
            if getattr(self, "_md_scanning", False):
                return

            self._md_scanning = True
            launched = False
            try:
                def work():
                    info = None
                    try:
                        from app import meeting_detect
                        info = meeting_detect.detect()
                    except Exception as e:
                        logger.debug("meeting detect scan failed: %s", e)
                    try:
                        self._on_main(lambda i=info: self._md_apply(i))
                    except Exception:
                        self._md_scanning = False
                threading.Thread(target=work, daemon=True).start()
                launched = True
            finally:
                if not launched:
                    self._md_scanning = False
        except Exception as e:
            logger.debug("meeting detect tick failed: %s", e)

    def _md_apply(self, info):
        """Fold a scan result into the prompt state machine (Mac `_md_apply`)."""
        self._md_scanning = False
        try:
            if self.meetings and self.meetings.active:
                return
            if not self.config.get("meeting_autodetect", True):
                return
            if not info:
                self._md_empty += 1
                if self._md_empty >= 2:
                    self._md_active_key = None
                    self._md_handled.clear()
                    if self.meeting_prompt and self.meeting_prompt.visible:
                        self.meeting_prompt.hide()
                return
            self._md_empty = 0
            key = info.get("key") or ""
            if key in self._md_handled or key in self._md_dismissed:
                return
            self._md_active_key = key
            self._md_source = info.get("source") or ""
            self._md_handled.add(key)
            logger.info("meeting detected (auto): source=%s key=%s",
                        self._md_source, key)
            self._show_meeting_prompt(self._md_source)
        except Exception as e:
            logger.debug("meeting detect apply failed: %s", e)

    def _show_meeting_prompt(self, source):
        try:
            if self.meeting_prompt is None:
                from app.win_meeting_prompt import WinMeetingPrompt
                self.meeting_prompt = WinMeetingPrompt(self)
                self.meeting_prompt.setup()
            self.meeting_prompt.show(source)
        except Exception as e:
            logger.debug("meeting prompt show failed: %s", e)

    def _meeting_detect_result(self, take: bool):
        """Pill button result: True = start capturing this call now."""
        if not take:
            if self._md_active_key:
                self._md_dismissed.add(self._md_active_key)
                logger.info("meeting prompt dismissed for key=%s",
                            self._md_active_key)
            return
        try:
            source = self._md_source or ""
            lang = self.config.get("spoken_language", "") or ""
            res = self.meetings.start(title="", use_mic=True, use_system=True,
                                      language=lang) if self.meetings else None
            if res and res.get("ok"):
                logger.info("meeting auto-started from detection (%s)", source)
                self._update_tray_menu()
                win = self._meeting_win()
                if win:
                    self._on_main(lambda: win.show("live"))
            else:
                logger.info("auto-start not ready (%s) — opening launcher",
                            res.get("error") if res else "no manager")
                self._toggle_meeting()
        except Exception as e:
            logger.error("meeting auto-start failed: %s", e)

    def _toggle_meeting_autodetect(self, icon=None, item=None):
        try:
            on = not self.config.get("meeting_autodetect", True)
            self.config["meeting_autodetect"] = on
            save_config(self.config)
            if not on and self.meeting_prompt and self.meeting_prompt.visible:
                self.meeting_prompt.hide()
            logger.info("meeting auto-detect %s", "on" if on else "off")
        except Exception as e:
            logger.warning("toggle auto-detect failed: %s", e)

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
        # A hands-free (tapped) recording is over however we got here, so the
        # listener must not still believe one is latched — otherwise the next
        # tap is spent "stopping" it instead of starting the next dictation.
        # Mirrors main.py.
        try:
            if getattr(self, "hotkey_listener", None):
                self.hotkey_listener.clear_latch()
        except Exception:
            pass
        # Must NOT clear `_cancel_flag` — `_on_esc_pressed` sets it and then
        # calls this, which used to wipe the cancel before the transcription
        # worker's next `is_set()` check and let the text paste anyway. Cleared
        # at recording start instead (IDI-178; mirrors main.py).
        try:
            self.recorder.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up recorder: {e}")
        try:
            self._detach_meeting_tap()
        except Exception:
            pass
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
            # Fresh install / restored session with an empty local history:
            # the account may have plenty of cloud rows this device has never
            # seen (the backfill watermark starts at NOW) — seed them quietly.
            if len(self.config.get("history") or []) < 5:
                self._bootstrap_history_async()
        except Exception as e:
            logger.error(f"Sync init failed: {e}")

    def _bootstrap_history_async(self):
        """Seed local history from the cloud on a daemon thread (fail-closed).
        Mirrors main._bootstrap_history_async — quiet merge, no clipboard."""
        def _seed():
            try:
                from app.sync import bootstrap_history
                if bootstrap_history(self.config, save_config):
                    self._refresh_dashboards()
            except Exception as e:
                logger.debug(f"history bootstrap skipped: {e}")
        try:
            threading.Thread(target=_seed, daemon=True).start()
        except Exception:
            pass

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
        # FALLBACK / intentional copy: the synced text is meant to STAY on the
        # clipboard (broadcasts are never auto-pasted), so this path must never
        # restore the previous clipboard — hence restore_clipboard=False below.
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
                success = inject_text(text, restore_clipboard=False)
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
    # Windows port of main.py's update state machine (2026-08-26). Everything
    # here is peripheral: each entry point swallows its own errors so a broken
    # update path can never touch record → transcribe → inject. Threading: all
    # of it runs on daemon threads (the check loop, the dashboard bridge's
    # pywebview API thread, the pystray callback thread) — the same contexts
    # that already drove _update_tray_icon/_update_tray_menu before the port.

    def _update_check_loop(self):
        """Daemon thread started in start(). Sleeps past updater's 30-second
        post-launch gate, checks once, then re-checks every
        UPDATE_CHECK_INTERVAL (main.py's rumps.Timer cadence) for the "left
        running for days" case. Replaces the one-shot t=0 thread + once-per-
        session guard, which together meant the Windows app never performed
        a real check in a session (2026-08-26: 1.0.33 never saw 1.0.34)."""
        time.sleep(UPDATE_STARTUP_DELAY)
        while True:
            try:
                self._check_update()
            except Exception as e:
                logger.debug(f"periodic update check failed: {e}")
            time.sleep(UPDATE_CHECK_INTERVAL)

    def _check_update(self, announce_current=False, suppress_prompt=False, force=False):
        """Update poll — the startup/periodic loop above, the dashboard's
        "Check for updates" button (shared_dashboard.check_for_updates, which
        passes suppress_prompt=True, force=True) and the tray's "Check for
        updates..." row (_tray_check_updates: announce_current=True,
        force=True) all land here. Same signature as main.py so the
        cross-platform bridge is oblivious.

        `force` skips updater's 30 s post-launch gate — only ever set for an
        explicit user click, which cannot produce the auto-install loop the
        gate guards against. No once-per-session guard any more: it silently
        turned every later check into a no-op.

        Found: `_update_available` is set (badge + tray row via _offer_update,
        banner via get_update_status) and stays set until a newer version
        supersedes it or the app relaunches post-update. A DIFFERENT version
        than the one already parked invalidates the in-app flow's state for
        the old one (its downloaded installer is stale). In auto_update mode
        (config default True) the download + silent install kick off here,
        driving phase/progress so the banner shows "Downloading… / Installing"
        instead of the app just vanishing mid-session. The tk dialog only
        shows for announce_current (an explicit user action) — automatic
        finds stop at badge + banner, same nag-avoidance policy as macOS.

        Not found: check_for_update() returns None BOTH when current and when
        the request failed, so an update that is mid-download / parked ready
        is kept rather than yanked by a transient network error; otherwise the
        state clears and the badge/menu refresh if one had been showing.
        """
        from app.updater import check_for_update
        try:
            update = check_for_update(force=force)
        except Exception as e:
            logger.debug(f"update check failed: {e}")
            update = None

        try:
            in_flight = self._update_phase in ("downloading", "ready", "installing")
            if not update and self._update_available and in_flight:
                update = self._update_available

            if not update:
                from app import updater as _updater
                if getattr(_updater, "LAST_CHECK_FAILED", False):
                    # Unknown, not "current": keep whatever we knew (badge,
                    # tray row, a parked installer) and never claim up to date.
                    logger.info("update check failed (offline?) — keeping state")
                    if announce_current and not suppress_prompt:
                        self._show_check_failed_dialog()
                    return
                had_one = self._update_available is not None
                self._update_available = None
                self._update_phase = "idle"
                self._update_progress = 0.0
                self._update_ready_path = None
                if had_one:
                    self._update_tray_icon(self._is_recording)
                    self._update_tray_menu()
                if announce_current and not suppress_prompt:
                    self._show_up_to_date_dialog()
                return

            prev = self._update_available
            is_new_version = not prev or prev.get("version") != update.get("version")
            if is_new_version and self._update_phase != "idle":
                self._update_phase = "idle"
                self._update_progress = 0.0
                self._update_ready_path = None
            # Sets _update_available (via the _pending_update alias) and
            # refreshes the badge + tray row. On Windows an AUTOMATIC find also
            # shows the dialog ONCE per version (`update_dialog_seen_version`):
            # the badge-only policy meant users never learned an update existed
            # — "Windows is not picking up updates, no popup" (2026-08-28) —
            # because the tray badge is 4 px and the auto-install is silent.
            # Explicit clicks handle their own dialog below (force_dialog).
            announce_auto = (not announce_current and not suppress_prompt
                             and self._update_phase in ("idle", "failed")
                             and self.config.get("update_dialog_seen_version") != update.get("version"))
            if announce_auto:
                # Dialog "Yes" starts _download_and_install(silent=False) itself
                # and flips the phase; "No" falls through to auto_update below.
                self._offer_update(update, force_dialog=True, automatic=True)
            else:
                self._offer_update(update)

            auto_started = False
            if self.config.get("auto_update", True) and self._update_phase in ("idle", "failed"):
                # Unattended: download + /VERYSILENT install, reflected in the
                # state machine. Not when the dashboard has already parked the
                # installer (phase 'ready') — that flow promised to wait for an
                # explicit "Restart to update".
                logger.info(f"Auto-update: downloading {update.get('version')}")
                try:
                    self.overlay.show_briefly(f"Updating to v{update.get('version')}...", duration=3.0)
                except Exception as e:
                    logger.debug(f"update overlay note failed: {e}")
                threading.Thread(
                    target=self._download_and_install, args=(update, True),
                    name="auto-update", daemon=True).start()
                auto_started = True

            if announce_current and not suppress_prompt and not auto_started:
                self._offer_update(update, force_dialog=True)
        except Exception as e:
            logger.error(f"Update check handling failed: {e}")

    def _set_update_progress(self, fraction):
        """download_update on_progress callback → banner percentage."""
        try:
            self._update_progress = max(0.0, min(1.0, float(fraction)))
        except Exception:
            pass

    def _app_busy(self) -> bool:
        """True while the process must NOT be killed out from under the user:
        a dictation is being recorded or transcribed/injected, or a meeting
        session is capturing or still post-processing. Read-only peeks at
        state the record path already maintains — never touches it (Hard Rule
        1). Fail-open to False so a broken peek can never wedge an update."""
        try:
            if self._is_recording or self._processing:
                return True
            m = self.meetings
            if m is not None and (getattr(m, "active", None) or getattr(m, "processing", None)):
                return True
        except Exception as e:
            logger.debug("busy check failed: %s", e)
        return False

    def _download_and_install(self, update, silent):
        """Download `update` and hand it to updater.install_update, which
        launches the installer and os._exit()s this process (never returns
        on success). Used by the auto_update path (silent=True → /VERYSILENT)
        and the tray dialog's "Yes" (silent=False). Single-flight via
        _update_download_lock so a periodic re-check landing mid-download
        can't start a second copy of the same download; on any failure the
        phase goes to 'failed' so the banner offers Retry.

        silent=True is UNATTENDED, so it must not exit the process at an
        arbitrary moment: install_update ends in os._exit(0), and the first
        real Windows auto-update (the pre-2026-08-26 t=0 check never ran)
        would have killed a dictation mid record→transcribe→inject or a
        meeting mid-recording — transcript lost, nothing injected, tray gone.
        So after the download it parks the installer as phase 'ready' (the
        banner reads "ready to install" / "Restart to update", which the user
        may click at any time — _install_ready_update takes the same path)
        and only proceeds once _app_busy() has been False for two consecutive
        1 s polls. It abandons the install if a newer version supersedes this
        one while waiting (the parked installer is stale) or if someone else
        already installed. The tray dialog's "Yes" (silent=False) installs
        immediately: the user just asked for it, with the app idle in front
        of them."""
        if not self._update_download_lock.acquire(blocking=False):
            logger.debug("update download already in progress; skipping duplicate")
            return
        # A newer version found while this thread held the lock: the periodic
        # check's own _download_and_install for it hit the non-blocking
        # acquire above and was dropped, so this thread picks it up once the
        # lock is free (else the unattended install waits a whole
        # UPDATE_CHECK_INTERVAL). Same hand-off as _start_update_download.
        resume = None
        try:
            from app.updater import download_update, install_update
            self._update_phase = "downloading"
            self._update_progress = 0.0
            path = download_update(update, on_progress=self._set_update_progress)
            if not path:
                self._update_phase = "failed"
                logger.error(f"Update download failed for {update.get('version')}")
                return
            self._update_ready_path = path
            # BOTH paths wait for an idle app before the installer os._exit()s
            # us. The dialog's "Yes" used to install the instant the download
            # finished — but since the dialog pops unsolicited 35 s after
            # launch, "Yes" is followed by the user going back to dictating,
            # and a multi-minute download then killed the process mid
            # record→transcribe→inject (review 2026-08-28).
            wait_for_idle = True
            if wait_for_idle:
                self._update_phase = "ready"
                idle_polls = 0
                while idle_polls < 2:
                    current = self._update_available
                    if not current or current.get("version") != update.get("version"):
                        logger.info("Auto-update: %s superseded while waiting for idle; dropping it",
                                    update.get("version"))
                        try:
                            os.unlink(path)
                        except Exception:
                            pass
                        resume = current
                        return
                    if self._update_phase != "ready" or self._update_ready_path != path:
                        # The user clicked "Restart to update" (installing now)
                        # or the state was reset under us — either way this
                        # thread has nothing left to do.
                        return
                    idle_polls = idle_polls + 1 if not self._app_busy() else 0
                    time.sleep(1.0)
                logger.info(f"Auto-update: app idle, installing {update.get('version')}")
            self._update_phase = "installing"
            install_update(path, silent=silent)
        except Exception as e:
            self._update_phase = "failed"
            logger.error(f"Update failed: {e}")
        finally:
            self._update_download_lock.release()
            # In the finally (not after it): the superseded branch `return`s
            # from inside the try, so code after this block would never run.
            if resume is not None and self.config.get("auto_update", True):
                self._download_and_install(resume, True)

    def _start_update_download(self):
        """Dashboard-driven download (shared_dashboard.start_update_download),
        ported from main.py. This one must NEVER auto-install: it downloads,
        parks the installer at `_update_ready_path`, sets phase='ready', and
        stops — install only happens if/when the user clicks "Restart to
        update" (_install_ready_update). Duplicate clicks are no-ops."""
        try:
            if self._update_phase in ("downloading", "installing"):
                return
            update = self._update_available
            if not update:
                return
            if not self._update_download_lock.acquire(blocking=False):
                return
            self._update_phase = "downloading"
            self._update_progress = 0.0
        except Exception as e:
            logger.error(f"start_update_download failed: {e}")
            return

        def _run():
            # Set when a newer version superseded `update` mid-download: the
            # periodic check reset the phase to 'idle' and spawned the auto
            # path for the new version, but that thread found the lock held
            # by THIS download and was dropped ("skipping duplicate") — so
            # without a hand-off the unattended install waited a whole
            # UPDATE_CHECK_INTERVAL (4 h) and the stale installer stayed in
            # the temp dir. Chained AFTER the lock is released, below.
            resume = None
            try:
                from app.updater import download_update
                path = download_update(update, on_progress=self._set_update_progress)
                current = self._update_available
                if not current or current.get("version") != update.get("version"):
                    # A newer version superseded this one mid-download;
                    # _check_update already reset the phase — leave it.
                    if path:
                        try:
                            os.unlink(path)
                        except Exception:
                            pass
                    resume = current
                    return
                if path:
                    self._update_ready_path = path
                    self._update_phase = "ready"
                else:
                    self._update_phase = "failed"
            except Exception as e:
                self._update_phase = "failed"
                logger.error(f"Update download failed: {e}")
            finally:
                self._update_download_lock.release()
                # In the finally (not after it): the superseded branch
                # `return`s from inside the try, so code after this block
                # would never run.
                if resume is not None and self.config.get("auto_update", True):
                    self._download_and_install(resume, True)

        threading.Thread(target=_run, name="update-download", daemon=True).start()

    def _install_ready_update(self):
        """"Restart to update" (shared_dashboard.install_ready_update) — the
        ONLY thing in the dashboard flow allowed to actually run the
        installer and exit. Safe from the pywebview API thread:
        install_update() spawns the detached installer and os._exit()s
        (rule 59b — never sys.exit() off the main thread on Windows)."""
        try:
            path = self._update_ready_path
            if not path:
                return
            if not os.path.exists(path):
                # Temp dir got cleaned between download and click — let the
                # banner offer Retry instead of pretending to install.
                self._update_ready_path = None
                self._update_phase = "failed"
                return
            self._update_phase = "installing"
            from app.updater import install_update
            install_update(path)
        except Exception as e:
            self._update_phase = "failed"
            logger.error(f"Update install failed: {e}")

    def _show_check_failed_dialog(self):
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showwarning("Couldn't check for updates",
                                   "Flume couldn't reach the update server. "
                                   "Check your connection and try again.", parent=root)
            root.destroy()
        except Exception as e:
            logger.debug(f"check-failed dialog failed: {e}")

    def _show_up_to_date_dialog(self):
        """Explicit "Check for updates" with nothing newer — silence there
        reads as a broken button (same rationale as main.py's rumps.alert)."""
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("You're up to date", f"Flume v{APP_VERSION} is the latest version.",
                                parent=root)
            root.destroy()
        except Exception as e:
            logger.debug(f"up-to-date dialog failed: {e}")

    def _offer_update(self, update, force_dialog=False, automatic=False):
        """Show (or re-show) the update-available dialog and keep the
        persistent tray badge + menu item (_menu_update) in sync with it.

        Always sets self._pending_update (== _update_available) and refreshes
        the tray icon/menu — that's what makes the badge and menu row persist
        regardless of what the user does with the popup. The dialog itself
        only ever shows for `force_dialog=True` (the tray menu's explicit
        click, or an announce_current check); automatic checks stop at the
        badge + the dashboard banner.
        """
        self._pending_update = update
        try:
            self._update_tray_icon(self._is_recording)
            self._update_tray_menu()
        except Exception as e:
            logger.debug(f"update badge refresh failed: {e}")

        # Automatic finds stop at the badge/menu row + the dashboard's in-app
        # banner — the popup fires only on the tray menu's explicit click
        # (force_dialog=True). Same policy as mac's _check_update, and for the
        # same reason (2026-08-25): the OS popup doubling the in-app banner
        # for the same version reads as nagging.
        if not force_dialog:
            return

        # One dialog at a time. The automatic announce is decided on
        # `update_dialog_seen_version`, which is only persisted AFTER the
        # user answers — so a second check landing while the box is open
        # (the 35 s periodic check racing a forced one, seen live 2026-08-28)
        # would stack a second identical popup. Mark the version as seen
        # up-front, in memory, and hold a flag for the duration.
        if getattr(self, "_update_dialog_open", False):
            logger.info("update dialog already open; not stacking another")
            return
        self._update_dialog_open = True
        self._update_dialog_automatic = bool(automatic)
        try:
            self._show_update_dialog(update)
        finally:
            self._update_dialog_open = False

    def _show_update_dialog(self, update):
        try:
            import tkinter as tk
            from tkinter import messagebox
            version = update.get("version")
            self.config["update_dialog_seen_version"] = version
            phase = self._update_phase
            root = tk.Tk()
            root.withdraw()
            # A withdrawn root has no window for the messagebox to sit over,
            # so the OS may open it BEHIND the app the user is typing in and
            # it is never noticed — indistinguishable from "no popup".
            try:
                root.attributes("-topmost", True)
            except Exception:
                pass
            try:
                if phase in ("downloading", "installing"):
                    # The dashboard/auto path already has this in hand — a
                    # second "Download now?" would start nothing (single-
                    # flight lock) and just confuse.
                    messagebox.showinfo(
                        f"Flume {version} available",
                        "Flume is already downloading this update and will "
                        "restart to install it.", parent=root)
                    return
                if phase == "ready" and self._update_ready_path:
                    if messagebox.askyesno(
                            f"Flume {version} ready to install",
                            "The update has been downloaded.\n\nRestart Flume to install it now?",
                            parent=root):
                        threading.Thread(target=self._install_ready_update, daemon=True).start()
                    return
                changelog = update.get("changelog") or "Bug fixes and improvements"
                tail = "Download and install now?"
                if getattr(self, "_update_dialog_automatic", False) and self.config.get("auto_update", True):
                    tail += ("\n\n(If not, Flume will install it in the background "
                             "the next time you're not dictating.)")
                resp = messagebox.askyesno(
                    f"Flume {version} available",
                    f"{changelog}\n\n{tail}",
                    parent=root,
                )
            finally:
                root.destroy()
            self.config["update_dialog_seen_version"] = version
            try:
                save_config(self.config)
            except Exception as e:
                logger.debug(f"update-seen flag save failed: {e}")
            if resp:
                # The dashboard may have parked the installer (phase 'ready')
                # while this box sat open: install THAT, don't download again.
                if self._update_phase == "ready" and self._update_ready_path \
                        and os.path.exists(self._update_ready_path):
                    threading.Thread(target=self._install_ready_update, daemon=True).start()
                    return
                # Claim the phase synchronously so _check_update's auto_update
                # branch (which runs right after this returns on an automatic
                # find) sees it as in flight and does not start a second,
                # silent copy of the same download.
                self._update_phase = "downloading"
                self._update_progress = 0.0
                # Off the pystray callback thread so a slow download doesn't
                # freeze the tray menu; the lock makes a duplicate a no-op.
                threading.Thread(
                    target=self._download_and_install, args=(update, False),
                    name="update-install", daemon=True).start()
            # "No": nothing to remember — the badge + _menu_update row stay,
            # and the dialog only ever re-shows on another explicit click.
        except Exception as e:
            logger.error(f"update dialog failed: {e}")

SHOW_EVENT_NAME = "VerbalShowDashboardEvent_v1"


def _signal_running_instance():
    """Second process → tell the first one to show its dashboard (see
    VerbalWinApp._second_instance_watch). Best-effort; never raises."""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        EVENT_MODIFY_STATE = 0x0002
        k32.OpenEventW.restype = wintypes.HANDLE
        k32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        h = k32.OpenEventW(EVENT_MODIFY_STATE, False, SHOW_EVENT_NAME)
        if not h:
            return False
        ok = bool(k32.SetEvent(h))
        k32.CloseHandle(h)
        return ok
    except Exception:
        return False


# ── Process model of the shipped build (why the watcher below exists) ─────────
# verbal-win.spec builds a PyInstaller ONE-FILE exe (EXE(...) with no COLLECT), so
# a running Flume is TWO Flume.exe processes: the bootloader parent (~9 MB, child
# of explorer.exe — it unpacks to %TEMP%\_MEIxxxx and then just waits) and the
# real app child (~300 MB, holds the tray icon, the hotkey, the WebView2 windows
# and the "VerbalSingletonMutex_v1" mutex). Task Manager shows both. When a user
# picks the parent and hits "End task", only the bootloader dies; the child is
# orphaned and keeps running headless-ish — and keeps the mutex, so the next
# double-click on Flume loses _acquire_single_instance_mutex and exits.
# Reported 2026-08-26: "when I close the program it doesn't quit properly and I
# can see it running in task manager. If I end the program it still lurks around
# in the task manager until I kill it." _watch_bootloader_parent closes that
# hole: the child watches its bootloader parent and hard-exits with it. The
# structural fix is a onedir build (COLLECT) — one process, no bootloader — but
# that touches CI and the Inno Setup Source paths, so it is a separate change.
# The watcher detects the build layout itself (sys._MEIPASS outside the exe's
# directory == one-file) and stays off in a onedir build, where "parent is
# another Flume.exe" is a legitimate state — see _watch_bootloader_parent.


def _watch_bootloader_parent(on_parent_exit):
    """Frozen one-file build only: exit with the PyInstaller bootloader parent.

    Opens the parent process (os.getppid()) and, ONLY if its executable is the
    same file as ours (sys.executable is the bootloader path in a one-file
    child) and it was created before us (guards PID reuse), starts a daemon
    thread that blocks in WaitForSingleObject on the parent's handle. When the
    parent is gone the thread calls `on_parent_exit(reason)` — VerbalWinApp.
    _hard_exit, the same teardown as tray Quit — so an "End task" on either
    Flume.exe in Task Manager ends Flume, not just half of it.

    Never runs when not frozen: a dev run's parent is the terminal/IDE shell,
    and Flume must not die with it. Never runs in a onedir (COLLECT) build
    either, and that needs a POSITIVE one-file check, not just the path
    compare: in onedir the app IS Flume.exe, and its parent can legitimately
    be another Flume.exe with the same path and an earlier creation time —
    concretely the elevated relaunch (paste_guard._relaunch_elevated →
    ShellExecuteW "runas"), which AppInfo reparents onto the requesting
    process. Both guards would pass, the watcher would arm, and when the old
    instance then quits (_prompt_paste_blocked → _tray_quit) the healthy
    elevated copy would hard-exit with it — Flume vanishing right after the
    user asked it to fix paste. One-file is told apart by sys._MEIPASS: the
    bootloader unpacks to %TEMP%/_MEIxxxx, OUTSIDE the exe's directory,
    whereas onedir's _MEIPASS is the exe dir itself (PyInstaller < 6) or its
    `_internal` subdir (PyInstaller >= 6). Fully fail-closed: any ctypes
    failure is logged at debug and the watcher is simply not started (old
    behaviour). Returns True only if the watcher thread was started.
    """
    try:
        if not getattr(sys, "frozen", False):
            return False
        meipass = getattr(sys, "_MEIPASS", None)
        if not meipass:
            logger.debug("parent watcher: frozen but no _MEIPASS; not a one-file build")
            return False
        exe_dir = os.path.normcase(os.path.realpath(os.path.dirname(sys.executable)))
        unpack_dir = os.path.normcase(os.path.realpath(meipass))
        try:
            inside = os.path.commonpath([exe_dir, unpack_dir]) == exe_dir
        except ValueError:
            inside = False  # different drives: certainly not inside
        if inside:
            logger.debug("parent watcher: onedir layout (%s under %s); no watcher", unpack_dir, exe_dir)
            return False
        ppid = os.getppid()
        if not ppid or ppid <= 0:
            logger.debug("parent watcher: no usable ppid (%r)", ppid)
            return False

        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        SYNCHRONIZE = 0x00100000
        INFINITE = 0xFFFFFFFF
        WAIT_OBJECT_0 = 0

        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.GetCurrentProcess.argtypes = []
        k32.GetProcessTimes.restype = wintypes.BOOL
        k32.GetProcessTimes.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
        k32.WaitForSingleObject.restype = wintypes.DWORD
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.CloseHandle.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]

        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, ppid)
        if not h:
            logger.debug("parent watcher: OpenProcess(%d) failed", ppid)
            return False

        def _close():
            try:
                k32.CloseHandle(h)
            except Exception:
                pass

        # Is the parent really our bootloader? Compare executable paths (a
        # launcher script or shell wrapper fails this test and gets no
        # watcher). Not sufficient on its own for onedir — see the docstring —
        # which is why the _MEIPASS layout check above runs first.
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buf))
        if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            logger.debug("parent watcher: QueryFullProcessImageNameW failed")
            _close()
            return False
        parent_exe = buf.value[: size.value]

        def _norm(path):
            return os.path.normcase(os.path.realpath(path))

        if not parent_exe or _norm(parent_exe) != _norm(sys.executable):
            logger.debug("parent watcher: parent is not our bootloader (%s)", parent_exe)
            _close()
            return False

        # PID-reuse guard: a parent "created" after us is not our parent.
        def _created(handle):
            c, e, k, u = (wintypes.FILETIME() for _ in range(4))
            if not k32.GetProcessTimes(handle, ctypes.byref(c), ctypes.byref(e),
                                       ctypes.byref(k), ctypes.byref(u)):
                return None
            return (c.dwHighDateTime << 32) | c.dwLowDateTime

        parent_created = _created(h)
        self_created = _created(k32.GetCurrentProcess())
        if parent_created is None or self_created is None or parent_created > self_created:
            logger.debug("parent watcher: creation-time check failed (%r vs %r)",
                         parent_created, self_created)
            _close()
            return False

        def _wait():
            try:
                rc = k32.WaitForSingleObject(h, INFINITE)
            except Exception as e:
                logger.debug("parent watcher: wait raised: %s", e)
                return
            if rc != WAIT_OBJECT_0:
                # WAIT_FAILED / anything unexpected: do NOT exit on a guess.
                logger.debug("parent watcher: wait returned %r; not exiting", rc)
                return
            logger.info("bootloader parent (pid %d) exited - tearing down with it", ppid)
            try:
                on_parent_exit("bootloader parent exited")
            except Exception as e:
                logger.error("parent watcher: teardown failed: %s", e)

        threading.Thread(target=_wait, name="parent-watch", daemon=True).start()
        logger.info("watching bootloader parent pid %d", ppid)
        return True
    except Exception as e:
        logger.debug("parent watcher not started: %s", e)
        return False


def _acquire_single_instance_mutex():
    """Prevent a second Verbal from running — the second instance stacks
    every window (tray icons, overlay pills) and steals the hotkey.

    Uses a Windows named mutex; the handle stays alive for the whole
    process lifetime (stashed on the sys module) so Windows releases it
    on exit. Returns True if we acquired the singleton, False if another
    Verbal is already running. (The mutex is held by the one-file CHILD
    process, not the bootloader parent — see the process-model note above.)

    NOTE: Must call kernel32.GetLastError() directly — `ctypes.get_last_error`
    only returns non-zero when the DLL was loaded with `use_last_error=True`,
    which `ctypes.windll.kernel32` is not."""
    import ctypes
    from ctypes import wintypes
    ERROR_ALREADY_EXISTS = 183
    # use_last_error=True: ctypes captures GetLastError immediately after the
    # foreign call, before the interpreter can issue another Win32 call that
    # overwrites it (the documented way; a bare GetLastError() afterwards is
    # racy and a stale 0 would let a second instance run).
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    handle = kernel32.CreateMutexW(None, False, "VerbalSingletonMutex_v1")
    err = ctypes.get_last_error()
    if not handle:
        return True  # can't tell; let it run — mutex failure isn't fatal
    if err == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    sys._verbal_singleton_mutex = handle
    return True


def main():
    import time
    sys._verbal_start_time = time.time()
    if not _acquire_single_instance_mutex():
        # Not an error from the user's point of view: they clicked Flume, so
        # Flume should appear. Hand the running copy the request and go.
        signalled = _signal_running_instance()
        logger.info("Another Verbal instance is already running — %s",
                    "asked it to show the dashboard" if signalled else "exiting")
        return
    app = VerbalWinApp()
    # Frozen one-file build: die with the bootloader parent so an "End task"
    # in Task Manager cannot leave an orphan holding the mutex (2026-08-26).
    # No-op in dev runs and on any ctypes failure.
    _watch_bootloader_parent(app._hard_exit)
    app.start()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
