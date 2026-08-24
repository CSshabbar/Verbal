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
    load_config, save_config,
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
from app import menubar_menu
# NB: there is no native canvas window — app/canvas_window.py was deleted in
# IDI-179. The canvas lives in the dashboard's tab 4.
# NB: there is no menubar popover either — flume_popover.py was deleted in
# IDI-183 and the menubar surface is a real NSMenu (menubar_menu.py).
# flume_popover_html.py stays: it is the WINDOWS tray popover's HTML, and
# flume_dashboard_html imports its _mark_data_uri().

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

# Shortest recording worth transcribing. Below this it is an accidental key
# brush (or a tap in HOLD mode) and Whisper answers noise with a hallucination,
# so the clip is discarded. Applied against the recorder's real sample rate.
MIN_RECORDING_SECONDS = 1.0

# How often the background update check re-runs after the startup poll
# (`_start_app`'s one-shot check + `updater.check_for_update`'s own 30s
# startup suppression already cover "just launched"). 4h is frequent enough
# that a release is discovered same-day without hammering the
# `app_versions_latest` endpoint from every idle desktop.
UPDATE_CHECK_INTERVAL = 4 * 60 * 60

_UPDATE_BADGE_CACHE = {}   # (base_path, dark) -> temp PNG path, rendered once per process


def _menu_bar_is_dark():
    """Best-effort read of the CURRENT menu bar appearance. Used only to
    manually reproduce rumps' `template=True` light/dark tinting for the
    update-badge icon variant (see `_badged_icon_path` for why that variant
    can't just use template mode itself). Fails closed to light/black —
    matches the glyph's normal default and is the safer guess since a black
    glyph is still legible on translucency in either menu bar, whereas
    guessing 'dark' wrong on a light bar can wash the glyph out entirely."""
    try:
        from AppKit import NSApp
        appearance = NSApp.effectiveAppearance()
        name = appearance.bestMatchFromAppearancesWithNames_(
            ["NSAppearanceNameAqua", "NSAppearanceNameDarkAqua"])
        return name == "NSAppearanceNameDarkAqua"
    except Exception:
        return False


def _badged_icon_path(base_path, dark=None):
    """Composite a small terracotta "update available" dot onto the
    top-right corner of `base_path` (ICON_PATH or ICON_ACTIVE_PATH) and
    return a path to the rendered PNG, cached per (base_path, appearance)
    for the life of the process — the source icons never change at runtime.

    Deliberately NOT rendered as a rumps `template` image. NSStatusItem
    template images are pure alpha masks: the WHOLE image is tinted one
    solid color for the current appearance, so a colored dot composited
    into a template image would just get flattened to the same monochrome
    as the rest of the icon — never actually appear terracotta/red. So this
    variant opts OUT of template mode (`VerbalApp._set_menubar_icon` flips
    `self.template` accordingly) and manually recolors the glyph to match
    the current menu bar appearance, reproducing what template mode would
    have done automatically. Caveat: if the user flips System Settings'
    appearance while a badge is showing, the glyph only picks up the new
    tint on the next icon swap (next record start/stop or update check),
    not live — an accepted, purely cosmetic edge case.
    """
    if dark is None:
        dark = _menu_bar_is_dark()
    cache_key = (base_path, dark)
    cached = _UPDATE_BADGE_CACHE.get(cache_key)
    if cached and os.path.exists(cached):
        return cached
    from PIL import Image, ImageDraw
    import tempfile
    img = Image.open(base_path).convert("RGBA")
    # Recolor the glyph's shape (its alpha mask) to a flat tint matching
    # what `template=True` would have picked for this appearance, since
    # we're rendering as a normal (non-template) color image below.
    tint = (255, 255, 255, 255) if dark else (0, 0, 0, 255)
    alpha = img.split()[3]
    solid = Image.new("RGBA", img.size, tint)
    solid.putalpha(alpha)
    img = solid
    w, h = img.size
    draw = ImageDraw.Draw(img)
    r = max(3, int(round(min(w, h) * 0.32)))
    cx, cy = w - r - 1, r + 1
    # A thin ring in the tint color first, so the terracotta dot reads as a
    # distinct badge instead of blending into the glyph on either menu bar.
    draw.ellipse([cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2], fill=tint)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(200, 90, 62, 255))
    fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="flume_update_badge_")
    os.close(fd)
    img.save(tmp_path, "PNG")
    _UPDATE_BADGE_CACHE[cache_key] = tmp_path
    return tmp_path


class VerbalApp(rumps.App):
    def __init__(self):
        super().__init__("Flume", icon=ICON_PATH, template=True)

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

        # Transient status shown in the menubar menu's header row while
        # something long-running is happening ("Downloading update…"). Empty
        # means idle, and the header falls back to "Ready" + the hotkey hint.
        self._status_line = ""
        # Wall-clock start of the current dictation, so the header's timer is
        # right even when the menu is opened mid-recording.
        self._rec_started_at = 0.0
        # Last interactive sign-in failure, surfaced in the dashboard's sign-in
        # pane via get_state (IDI-166). "" = nothing to report.
        self._auth_error = ""
        # One-shot informational message for the SAME pane (IDI-170) — e.g.
        # "Your account has been deleted." Cleared when a new sign-in starts.
        self._auth_notice = ""

        # Mic permission gate (the "no permission pop-up like Zoom" fix).
        # True once `_ensure_mic_permission` has observed a real 'granted'
        # read — TCC doesn't flip granted->not_determined mid-run, so one
        # confirmed read is good for the rest of the process's life and this
        # keeps the check off the hot path (`_on_record_start` fires on every
        # hotkey press). `_mic_denied_alerted` throttles the heavyweight
        # rumps.alert to once per launch once the user has already been told.
        self._mic_permission_cached = False
        self._mic_denied_alerted = False

        # Persistent "update available" state (menu-bar badge + menu row).
        # Set once a check finds a newer version and held until either a
        # still-newer version supersedes it or the app relaunches post-update
        # — see `_check_update`/`_refresh_update_badge`. `_update_dismissed_version`
        # is the version the user last clicked "Later" on, so the periodic
        # background check can keep badging without popping the alert again
        # for that same version.
        self._update_available = None
        self._update_dismissed_version = None

        # Running totals. WRITE-ONLY on macOS since IDI-183 — the menu header
        # takes its number from get_daily_words() instead — but they must stay:
        # win_main.py has its own `_status_text()` that reads them for its tray
        # row, and the cross-platform shared_dashboard.py resets them when the
        # user clears history.
        history = self.config.get("history", [])
        self._total_transcriptions = len(history)
        self._total_words = sum(len(_entry_text(h).split()) for h in history)

        # Sync client — starts if sync is enabled in config
        self._sync = None
        self._init_sync()

        # Meetings (MEETINGS_DESIGN_HANDOFF.md) — manager + lazy window. Fails
        # closed: if construction fails, meetings are simply unavailable and
        # dictation is untouched (Rule #1).
        # NB: there is no separate floating meeting HUD — meeting_hud.py was
        # deleted in IDI-179 (superseded by meeting_window.py's morphing
        # bar ⇄ expanded panel, and unreferenced since).
        self.meetings = None
        self.meeting_window = None
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
        # Dev-only. It wipes auth + onboarding + sync state, so it must never be
        # one mis-click away in a shipped build: the item only exists when
        # VERBAL_DEV is set (IDI-178). The handler itself stays for that use.
        self._dev_mode = bool(os.environ.get("VERBAL_DEV"))

        # The menubar surface: a real NSMenu with one custom-drawn header row
        # (IDI-183). menubar_menu.build() assigns the item references the
        # callbacks below mutate — record_btn, meeting_btn, mode_hold/toggle,
        # model_items, autodetect_item, sync_item, signin_item, reset_onb_item.
        self.menu = menubar_menu.build(self)
        # The NSMenu only exists once `self.menu` has been assigned, so the
        # delegate (rebuild-on-open + header animation) is attached after it.
        # Fails closed: without it the menu is static but fully usable.
        self._menu_ctl.attach()
        # Apply the gate NOW rather than waiting for the first menu open. The
        # delegate keeps it fresh, but a launch-time apply means a signed-out
        # start is already locked even if the delegate never fires.
        self._menu_ctl.refresh()
        self.sync_menu_state()
        # rumps appends its own quit row at launch; name it the way a Mac app
        # does. Passing the key here survives rumps' later set_callback(), which
        # only overwrites the key equivalent when it is given one.
        self.quit_button = rumps.MenuItem("Quit Flume", key="q")

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
        self._md_handled = set()          # call keys already prompted this sighting
        # Keys the user explicitly said "not now" to. Kept SEPARATE from
        # _md_handled because that set is cleared whenever the call disappears for
        # two polls (so the next call prompts fresh) — which also erased the
        # dismissal, so a detection that merely flickered off-screen for 10s came
        # back and asked again. The log showed 7 prompts for one key. A dismissal
        # is durable for the session, like `autolearn_declined` (conventions #9).
        self._md_dismissed = set()
        self._md_empty = 0                # consecutive polls with no call detected
        self._md_source = ""              # last detected source label
        self._md_scanning = False         # a background window scan is in flight
        self._meeting_detect_timer = rumps.Timer(self._detect_meeting_tick, 5.0)

        # 0.04s, not 0.1s. Everything main-thread goes through this queue, so its
        # tick is the floor on any UI hop the dictation path WAITS for — and it waits
        # for exactly one: hiding the pill before focus is restored (main.py, the
        # `_hidden` event). At 0.1s that hop cost 0-100ms, ~50ms on average, on every
        # dictation. At 0.04s it costs ~20ms. The price is 25 wakeups/sec doing one
        # `get_nowait` on an empty queue, which is negligible next to the audio and
        # webview timers this app already runs.
        self._ui_timer = rumps.Timer(self._drain_ui_queue, 0.04)

        # Periodic background re-check for the persistent update badge/menu
        # row (Task: "a small update icon... if a new update is launched
        # automatically that shows a popup and a small bubble icon"). The
        # one-shot `_check_update()` call in `_start_app` covers "just
        # launched"; this covers "left running for days".
        self._update_check_timer = rumps.Timer(self._periodic_update_check, UPDATE_CHECK_INTERVAL)

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

    def _status_note(self, text=""):
        """Set (or clear) the transient line the menu header shows when idle.

        Replaces the old `status_item` menu row: the counts it used to carry now
        live in the header's right-hand column, and recording/transcribing are
        derived from app state, so the only thing left to say here is the
        occasional long-running note like "Downloading update…".
        """
        self._status_line = text or ""

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
        logger.info("Starting Flume")
        self.overlay.setup()
        self.hotkey_listener.start()
        self._ui_timer.start()
        # Poll for calls in progress (Granola-style prompt). Meetings-only, macOS-only;
        # fails closed — a detection error never touches dictation/capture.
        if self.meetings:
            self._meeting_detect_timer.start()
        threading.Thread(target=self._preload_model, daemon=True).start()
        threading.Thread(target=self._check_update, daemon=True).start()
        self._update_check_timer.start()
        threading.Thread(target=self._load_dictionary_once, daemon=True).start()
        threading.Thread(target=self._presence_loop, daemon=True).start()

        # Make a paste the OS refuses visible instead of silent (paste_guard.py).
        # Registered here rather than at import time so the hook is only live
        # once there is a main-thread UI queue to hop onto.
        try:
            from app import paste_guard
            paste_guard.set_prompt_hook(self._prompt_paste_blocked)
        except Exception as e:
            logger.debug("paste-blocked prompt hook not installed: %s", e)

        # No bare accessibility prompt at launch (IDI-166): the onboarding
        # wizard's permission step asks for Accessibility WITH context
        # ("Lets Flume paste text into other apps") via
        # permissions.request('accessibility'), which is the same TCC prompt.
        # Firing it here too meant a contextless system dialog on first run.

        # dashboard.show() sets Regular activation policy itself (and reverts to
        # Accessory when the window closes) — see flume_web_dashboard.py's
        # _delegate_class() docstring for why this can't be a one-time,
        # permanent switch at launch (it silently breaks the recording
        # overlay's visibility over full-screen apps for the rest of the
        # session otherwise).
        self.dashboard.show()
        self._install_edit_menu()

        # Reflect sign-in state in the menubar. Sign-in is REQUIRED (IDI-166),
        # so there is no first-run "Later" alert any more — the dashboard we
        # just showed renders the sign-in wall itself. As of IDI-183 that is
        # enforced rather than merely un-advertised: the menu greys out every
        # account feature and `_on_record_start` refuses, so there is no longer
        # a signed-out hotkey path into dictation.
        self._update_auth_menu()

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

    PRESENCE_INTERVAL = 30

    def _presence_loop(self):
        """APP-level device heartbeat (IDI-177).

        This used to ride `FlumeWebDashboard._device_refresh_loop`, whose
        condition is `while self._window is not None` — so closing the
        dashboard silently stopped the heartbeat and the Mac showed Offline to
        every other device within ~5 min. Presence is an app fact, not a
        window fact, so it lives here: a daemon thread, every 30 s, gated on
        being SIGNED IN (not on `sync_user_id`, which used to survive
        sign-out). Fail-closed — it can never raise into the app."""
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
        """Start sync client if enabled in config."""
        if not self.config.get("sync_enabled"):
            return
        # IDI-170/171: the user toggle alone isn't enough — a signed-out app
        # must never open a realtime channel on the ex-account's user_id.
        if not auth.cloud_allowed(self.config):
            logger.info("Sync: not signed in, skipping")
            return
        user_id = self.config.get("sync_user_id", "").strip()
        if not user_id:
            logger.info("Sync: no user_id configured, skipping")
            return
        try:
            from app.sync import SyncClient
            device_name = self.config.get("sync_device_name", "") or "Mac"
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
        See sync.bootstrap_history — quiet merge, no clipboard/paste."""
        def _seed():
            try:
                from app.sync import bootstrap_history
                if bootstrap_history(self.config, save_config):
                    self._on_main(self._refresh_dashboards)
            except Exception as e:
                logger.debug(f"history bootstrap skipped: {e}")
        try:
            threading.Thread(target=_seed, daemon=True).start()
        except Exception:
            pass

    def _this_device_id(self) -> str:
        from app.config import get_device_id
        return self._sync.device_id if self._sync else get_device_id(self.config)

    def _on_sync_receive(self, text: str, device_name: str, record: dict | None = None):
        """Called when another device pushes a transcription (IDI-172).

        Used to be paste-and-forget: the text went to the clipboard, was typed
        into whatever app happened to be focused, and then vanished — a phone
        dictation never appeared in the Mac's History at all, and a BROADCAST
        (no target) hijacked the keyboard of every signed-in device at once.

        Now: it always lands in local history (so it's readable/copyable later)
        and only AUTO-PASTES when this device was explicitly targeted. A
        broadcast (`target_device_id` null / "__all__") is history + clipboard
        only."""
        record = record or {}
        import pyperclip
        pyperclip.copy(text)
        logger.info(f"Sync received from {device_name}: '{text[:40]}'")

        entry_id = ""
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
                # the cloud row id — how a later tombstone finds this entry
                fields["sync_id"] = record["id"]
            self.config = update_history_entry(self.config, entry_id, **fields)
            self._total_transcriptions += 1
            self._total_words += len(text.split())
            self._on_main(self._refresh_dashboards)
        except Exception as e:
            logger.error(f"Sync receive: could not save to history: {e}")

        target = record.get("target_device_id")
        targeted = bool(target) and target == self._this_device_id()
        brief = f"📱 {device_name} · {len(text.split())}w"
        if targeted:
            self._on_main(lambda: self._paste_synced(text, brief))
        else:
            # Broadcast: never steal the keyboard. Say where it went.
            self._on_main(lambda: self.overlay.show_briefly(
                brief + " · in History", duration=2.5))

    def _on_sync_tombstone(self, record: dict):
        """A history row was deleted on another device — drop our copy."""
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
                self._on_main(self._refresh_dashboards)
        except Exception as e:
            logger.debug(f"tombstone prune failed: {e}")

    def _on_sync_pushed(self, entry_id: str, row_id: str):
        """Remember which cloud row a local dictation became, so a remote
        tombstone can prune it and the audio upload can patch it."""
        try:
            self.config = update_history_entry(self.config, entry_id, sync_id=row_id)
        except Exception as e:
            logger.debug(f"sync_id record failed: {e}")

    def _paste_synced(self, text: str, brief: str):
        """Paste synced text into the currently focused app."""
        try:
            from app.injector import inject_text
            # Respect the result: a blocked paste (no Accessibility grant) must
            # not report "Pasted" — paste_guard has just told the user why, and a
            # contradicting pill would undo that.
            if inject_text(text):
                self.overlay.show_briefly(brief, duration=2.5)
            else:
                self.overlay.show_briefly("In clipboard · paste with ⌘V", duration=2.5)
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

    def _open_settings(self, _=None):
        """Settings… — the dashboard's Settings tab (index 3)."""
        if not self._require_signin():
            return
        try:
            self.dashboard.show()
            self.dashboard._on_tab_select(3)
        except Exception as e:
            logger.warning(f"open settings failed: {e}")

    def _toggle_sync(self, sender=None):
        """Menu checkmark for cross-device sync. Gated: enabling sync without an
        account is exactly what cloud_allowed() exists to prevent.

        `_init_sync` is the gate that matters (signed in + a user_id), so this
        only has to flip the flag and restart the client; the menu delegate
        disables the row entirely while signed out.
        """
        if not self._require_signin():
            return
        try:
            on = not bool(self.config.get("sync_enabled", False))
            self.config["sync_enabled"] = on
            save_config(self.config)
            if self._sync:
                try:
                    self._sync.stop()
                except Exception:
                    pass
                self._sync = None
            if on:
                self._init_sync()
            if sender is not None:
                sender.state = 1 if on else 0
            logger.info("sync %s", "on" if on else "off")
        except Exception as e:
            logger.warning("toggle sync failed: %s", e)

    # ── Google auth ───────────────────────────────────────────────────────────
    def _update_auth_menu(self):
        u = auth.current_user()
        if u:
            self.signin_item.title = f"Sign out ({u.get('email', 'account')})"
            self.signin_item.set_callback(self._sign_out)
        else:
            self.signin_item.title = "Sign in with Google"
            self.signin_item.set_callback(self._sign_in)

    def _push_auth_state(self):
        """Re-render the dashboard from the current auth state.
        The sign-in pane is data-driven off `get_state`, so this is how a
        FAILED sign-in gets back to the user — without it the pane kept the
        button disabled forever and only a restart recovered (IDI-166)."""
        try:
            self.dashboard._refresh()
        except Exception as e:
            logger.debug("auth state push failed: %s", e)

    def _sign_in(self, _=None):
        # Clear any previous failure the moment a new attempt starts, and push
        # it so the pane shows "Opening browser…" instead of the stale error.
        self._auth_error = ""
        self._auth_notice = ""   # the "account deleted" notice is one-shot
        self._push_auth_state()

        def work():
            try:
                a = auth.sign_in_with_google()
                self._on_main(lambda: self._after_sign_in(a))
            except auth.SignInCancelled:
                logger.info("Sign-in cancelled by the user")
                self._on_main(lambda: self._sign_in_failed(""))
            except Exception as e:
                logger.error(f"Sign-in failed: {e}")
                msg = str(e) or "Sign-in failed — please try again."
                self._on_main(lambda: self._sign_in_failed(msg))
        threading.Thread(target=work, daemon=True).start()

    def _sign_in_failed(self, message):
        """Surface a failed/timed-out/cancelled sign-in IN THE DASHBOARD (an
        alert alone left the static sign-in pane latched, IDI-166). The empty
        message case is a user cancel — reset the pane, say nothing."""
        self._auth_error = message or ""
        self._push_auth_state()

    def cancel_sign_in(self):
        """Called from the dashboard's Cancel affordance."""
        try:
            auth.cancel_sign_in()
        except Exception as e:
            logger.debug("cancel_sign_in failed: %s", e)
        self._auth_error = ""
        self._push_auth_state()

    def _after_sign_in(self, auth_info):
        self._auth_error = ""
        self._auth_notice = ""
        self.config = load_config()  # picks up sync_user_id set during sign-in
        # An account SWITCH wiped the previous account's caches inside
        # auth._store_session — drop the stale in-memory counters too.
        history = self.config.get("history", [])
        self._total_transcriptions = len(history)
        self._total_words = sum(len(_entry_text(h).split()) for h in history)
        self._update_auth_menu()
        threading.Thread(target=self._detect_and_prompt, args=(auth_info,), daemon=True).start()

    def _detect_and_prompt(self, auth_info):
        others = []
        try:
            from app.sync import fetch_devices
            from app.config import get_device_id
            others = fetch_devices(auth_info.get("user_id", ""), get_device_id(self.config)) or []
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
            # A device that just JOINED the account starts blind (the sync
            # watermark is seeded to NOW) — pull the newest cloud rows so
            # History isn't empty on a fresh machine (2026-08-15).
            self._bootstrap_history_async()
        try:
            self.dashboard.show()  # bring Flume to the front after sign-in
            self.dashboard._refresh()
        except Exception:
            pass

    def _stop_active_meeting(self, reason=""):
        """Best-effort stop of an in-flight meeting capture. Same path the
        meeting UI's Stop uses (`MeetingManager.stop_async` → the session's
        stop on a worker thread), so the transcript/summary still finalize."""
        try:
            if self.meetings and self.meetings.active:
                logger.info("Stopping active meeting (%s)", reason or "sign-out")
                self.meetings.stop_async()
        except Exception as e:
            logger.debug(f"meeting stop on {reason or 'sign-out'} skipped: {e}")

    def _sign_out(self, _=None):
        # Sign-out must stop ACTIVE work, not just the sync socket (IDI-170):
        # a meeting left recording keeps capturing audio and then tries to
        # upload/patch rows for an account this device no longer owns.
        self._stop_active_meeting("sign-out")
        # Same rule for dictation (IDI-183): now that signed-out dictation is
        # refused at the start, a recording already in flight must not survive
        # the sign-out and paste a transcript for an account we just left.
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
        auth.sign_out()   # also clears sync_user_id + deletes our devices row
        self.config = load_config()
        self._update_auth_menu()
        try:
            self.dashboard._refresh()
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

    # The menu greys these rows out while signed out; the guards are what make
    # them refuse. See _require_signin. ("Open Flume" is deliberately NOT gated —
    # it renders the sign-in wall, so it is the way back in.)
    def _open_canvas(self, _=None):
        if not self._require_signin():
            return
        self.dashboard.show()
        self.dashboard._on_tab_select(4)

    def _open_notes(self, _=None):
        if not self._require_signin():
            return
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

    def _toggle_meeting(self, _=None):
        if not self._require_signin():
            return
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
            if key in self._md_handled or key in self._md_dismissed:
                return  # already asked this sighting, or dismissed for the session
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
            # Remember the refusal so this call can't re-prompt when the window
            # flickers off-screen and back (see _md_dismissed).
            if self._md_active_key:
                self._md_dismissed.add(self._md_active_key)
                logger.info("meeting prompt dismissed for key=%s", self._md_active_key)
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

    def sync_menu_state(self):
        """Re-derive the menubar checkmarks from config (IDI-167).

        The Recording Mode / Whisper Model submenus are stateful rumps items
        that were only ever updated by their OWN callbacks — changing either
        from the dashboard's Settings screen wrote the config but left the
        menubar showing the old checkmark. Anything that mutates
        `recording_mode` / `whisper_model` outside those callbacks must call
        this (on the main thread — rumps menu items are AppKit).
        """
        cfg = self.config or {}
        mode = cfg.get("recording_mode", MODE_TOGGLE)
        if getattr(self, "mode_hold", None) is not None:
            self.mode_hold.state = 1 if mode == MODE_HOLD else 0
        if getattr(self, "mode_toggle", None) is not None:
            self.mode_toggle.state = 1 if mode == MODE_TOGGLE else 0
        model = cfg.get("whisper_model", "base")
        for name, item in (getattr(self, "model_items", None) or {}).items():
            item.state = 1 if name == model else 0

    def _set_mode_hold(self, _):
        if not self._require_signin():
            return
        self._mode = MODE_HOLD
        self.mode_hold.state = 1
        self.mode_toggle.state = 0
        self.config["recording_mode"] = MODE_HOLD
        save_config(self.config)
        if self.hotkey_listener:
            self.hotkey_listener.set_mode(MODE_HOLD)

    def _set_mode_toggle(self, _):
        if not self._require_signin():
            return
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

    # ── sign-in gate ──────────────────────────────────────────────────────────
    # Flume requires an account, so dictation requires one too. This reverses the
    # IDI-166 note that hotkey dictation kept working while signed out: the
    # menubar menu greys every row out, and leaving the hotkey live meant anyone
    # who knew it could still record with no account behind it.
    _SIGNIN_PROMPT_EVERY = 4.0   # seconds; holding the key must not spam windows

    def _signed_in(self) -> bool:
        """Fails CLOSED — an auth error blocks dictation rather than allowing it."""
        try:
            return bool(auth.current_user())
        except Exception as e:
            logger.warning(f"auth check failed, treating as signed out: {e}")
            return False

    def _require_signin(self) -> bool:
        """True when the caller may proceed; otherwise prompts and returns False.

        Every account-shaped menu callback goes through this. A disabled menu item
        SHOULD never fire, but the enabled state is applied by us (auto-enabling
        is off) and refreshed by a delegate — so treating "the row was greyed out"
        as the enforcement would make the gate depend on two AppKit behaviours
        instead of one plain check. Mirrors win_main.py.
        """
        if self._signed_in():
            return True
        logger.info("blocked: not signed in")
        self._prompt_sign_in()
        return False

    def _prompt_sign_in(self):
        """Show the sign-in wall the dashboard already renders, at most once every
        few seconds — a held hotkey fires this repeatedly."""
        now = time.time()
        if now - getattr(self, "_last_signin_prompt", 0.0) < self._SIGNIN_PROMPT_EVERY:
            return
        self._last_signin_prompt = now
        try:
            self.dashboard.show()
            self.dashboard._refresh()
        except Exception as e:
            logger.warning(f"sign-in prompt failed: {e}")

    def _ensure_mic_permission(self):
        """Gate every record-start on the real macOS microphone permission.

        This is the fix for "I don't get the permission pop-up like Zoom
        does": before this, the hotkey path went straight to
        `self.recorder.start()`, which just silently produced no audio if
        TCC hadn't decided yet — `permissions.request_microphone()` (the
        function that actually fires `AVCaptureDevice.
        requestAccessForMediaType_completionHandler_`, i.e. the real system
        prompt) was ONLY ever called from the dashboard's buried Settings
        screen, which a first-time user has no reason to open.

        Cached once granted so this is a fast no-op on the hot path
        (`_on_record_start` fires on every hotkey press) — TCC doesn't flip
        granted back to not-determined mid-run, so one confirmed 'granted'
        read is good for the rest of the process's life.

        Returns True to let the record-start proceed, False to abort it
        (Hard Rule #1: fail VISIBLY, never silently proceed into a mic
        stream that can't capture anything, and never crash/hang the hotkey
        path over a permissions check).
        """
        if self._mic_permission_cached:
            return True
        try:
            from app import permissions
            status = permissions.check_microphone()
        except Exception as e:
            # The PROBE itself failing must never block a working setup —
            # proceed and let recorder.start() be the real judge.
            logger.debug(f"mic permission probe failed, proceeding: {e}")
            return True

        if status == "granted":
            self._mic_permission_cached = True
            return True

        if status == "denied":
            # macOS never re-prompts once denied — calling requestAccess
            # again would be a silent no-op. Say so clearly instead of
            # opening a mic stream that will capture nothing.
            self._prompt_mic_denied()
            return False

        # 'not_determined' (first-ever recording) or 'unknown' (the pyobjc
        # probe couldn't tell). Fire the REAL TCC prompt right now, on the
        # actual record attempt — Zoom-style — instead of only from the
        # buried Settings screen. requestAccess's completion handler is
        # async and can take as long as the user takes to click Allow/Don't
        # Allow, so this does NOT block the hotkey press waiting on it (that
        # would freeze the whole rumps run loop for however long the system
        # dialog sits there): it fires the prompt and lets this recording
        # attempt proceed optimistically. A still-undetermined mic stream
        # either raises (caught by `_on_record_start`'s own except, which
        # already cleans up the pill) or opens silent; either way the VERY
        # NEXT press re-checks and will either go fast ('granted', cached)
        # or show the clear denied prompt above if they declined.
        try:
            permissions.request_microphone()
        except Exception as e:
            logger.debug(f"mic permission request failed: {e}")
        return True

    def _prompt_mic_denied(self):
        """Native, visible alert for an already-denied mic — same
        `rumps.alert` pattern as `_show_update_prompt`/`_prompt_paste_blocked`.
        Throttled to once per launch: after the first alert, later presses
        while still denied just flash the overlay instead of re-popping the
        modal, so a user who keeps hitting the hotkey isn't nagged with a
        dialog on every single press — but they still get SOME visible
        feedback every time (never a silent no-op)."""
        if self._mic_denied_alerted:
            try:
                self.overlay.show_briefly("Mic access needed — check Settings", duration=1.6)
            except Exception:
                pass
            return
        self._mic_denied_alerted = True
        try:
            from app import permissions
            resp = rumps.alert(
                title="Microphone access needed",
                message=(
                    "Flume needs Microphone access to record your dictation.\n\n"
                    "Open System Settings → Privacy & Security → Microphone "
                    "and turn Flume on, then try again."
                ),
                ok="Open Settings",
                cancel="Not now",
            )
            if resp == 1:
                permissions._open_settings("Privacy_Microphone")
        except Exception as e:
            logger.error(f"mic-denied prompt failed: {e}")

    def _toggle_recording(self, _):
        if self._is_recording:
            self._on_record_stop()
        else:
            self._on_record_start()

    def _on_record_start(self):
        if self._processing:
            return
        # The single choke point for every start path — the menu row, the toggle
        # key and the hold key all arrive here, so the sign-in gate lives here
        # and nowhere else. Checked BEFORE anything is saved, harvested or opened.
        if not self._signed_in():
            logger.info("dictation blocked: not signed in")
            self._prompt_sign_in()
            return
        if not self._ensure_mic_permission():
            logger.info("dictation blocked: microphone permission not granted")
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
            # Acknowledge the keypress IMMEDIATELY, before the microphone is opened.
            #
            # recorder.start() waits for CoreAudio's first buffer — measured 275ms
            # median on this machine (209-449ms), essentially all of it device warm-up
            # that no amount of our code can remove. Showing the pill after that wait
            # made the whole warm-up read as app lag. Showing it before makes the app
            # feel instant, and the two-state label is the honest part: it does NOT
            # say "Listening" until audio is actually flowing, because speaking into
            # a mic that is not live yet loses those words for real.
            self.overlay.show("Starting…")
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
            # Hybrid pipeline: open the streaming socket NOW and tap the mic, so that
            # by the time the user stops, transcription is already essentially done.
            # Fully guarded — if anything here fails the tap is never installed and
            # this take transcribes the ordinary way, one dictation slower at worst.
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
            play_start()

            self._set_menubar_icon(ICON_ACTIVE_PATH)
            # The menu header derives "Recording" + its timer from this.
            self._rec_started_at = time.time()
            self._status_note("")
            self.record_btn.title = "Stop Recording"
            # Audio is live now (recorder.start() only returns once the first buffer
            # has landed), so it is finally true to say so.
            self.overlay.show("Listening…")
            self.dashboard.update_recording_state(True)
        except Exception as e:
            self._is_recording = False
            # The pill was shown before the mic was opened, so a failure here has to
            # take it down — otherwise "Starting…" hangs on screen forever.
            try:
                self.overlay.hide()
            except Exception:
                pass
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

            self._set_menubar_icon(ICON_PATH)
            self.record_btn.title = "Start Recording"
            self.dashboard.update_recording_state(False)

            # Minimum audio to avoid accidental clicks / hallucinations. Derive the
            # sample count from the recorder's ACTUAL rate — it captures at the mic's
            # native rate (recorder._get_native_rate), so a hard-coded 48000 meant
            # "1 second" only on a 48kHz device: on a 16kHz Bluetooth/HFP mic it
            # silently demanded 3 seconds and discarded everything shorter, logging
            # the contradictory "1.49s (< 1.0s minimum)". Mirrors win_main.py.
            min_samples = int(self.recorder.sample_rate * MIN_RECORDING_SECONDS)
            if audio is None or len(audio) < min_samples:
                duration = len(audio) / self.recorder.sample_rate if audio is not None else 0
                logger.warning(f"Audio too short: {duration:.2f}s "
                               f"(< {MIN_RECORDING_SECONDS:.2f}s minimum, "
                               f"{self.recorder.sample_rate}Hz)")
                self._status_note("")
                self.overlay.hide()
                return

            self._processing = True
            self._status_note("")
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

    def _transcribe_with_retry(self, audio, attempts=3, chain=None, sidecar=None):
        """Transcribe, auto-retrying on 'failed' (transient network/API) with a
        short backoff. Returns (text, status). Silence returns immediately.

        `chain`/`sidecar` carry chained_mode through to the proxy — see
        transcriber.transcribe_with_status(). The sidecar is reset before each
        attempt so a partial result from a failed try can never be mistaken for
        this attempt's formatting."""
        text, status = "", "failed"
        for i in range(attempts):
            if self._cancel_flag.is_set():
                return "", "silent"
            if sidecar is not None:
                sidecar.clear()
            text, status = transcribe_with_status(audio, self.config, self.recorder.sample_rate,
                                                  chain=chain, sidecar=sidecar)
            if status in ("ok", "silent"):
                return text, status
            if i < attempts - 1:
                logger.warning(f"Transcription failed (attempt {i+1}) — retrying…")
                time.sleep(1.5 * (i + 1))
        return text, status

    def _history_entry(self, entry_id):
        for e in self.config.get("history", []):
            if isinstance(e, dict) and e.get("id") == entry_id:
                return e
        return None

    def _upload_recording_async(self, rec_id, local_path):
        """Upload the WAV to the cloud and attach its URL to the history entry."""
        def work():
            try:
                user_id = self.config.get("sync_user_id", "")
                # Recording uploads are a CAPTURE artifact, so they follow
                # `cloud_allowed` (signed in) and NOT the `sync_enabled`
                # toggle — but they must stop dead at sign-out (IDI-170/171).
                if not user_id or not local_path or not auth.cloud_allowed(self.config):
                    return
                url = recordings.upload_cloud(local_path, user_id, rec_id)
                if url:
                    self.config = update_history_entry(self.config, rec_id, audio_url=url)
                    # IDI-172: the row was pushed before the upload finished, so
                    # backfill its audio_url now — otherwise the receiving device
                    # can see the text but never play the audio.
                    try:
                        entry = self._history_entry(rec_id) or {}
                        if self._sync and entry.get("sync_id"):
                            self._sync.update_pushed_audio_url(entry["sync_id"], url)
                    except Exception as e:
                        logger.debug(f"audio_url sync patch skipped: {e}")
                    self._on_main(self._refresh_dashboards)
            except Exception as e:
                logger.debug(f"recording upload failed: {e}")
        threading.Thread(target=work, daemon=True).start()

    def _refresh_dashboards(self):
        try:
            self.dashboard._refresh()
        except Exception:
            pass
        # The menubar menu needs no push — its delegate rebuilds it on open.

    def _process_audio(self, audio):
        rec_id = recordings.new_id()
        # The archive write (resample + encode + prune of the recordings dir) used
        # to run to completion before the first byte of audio left the machine, yet
        # nothing about the transcript depends on it. Run it alongside the network
        # call instead; `_saved_path()` joins it back before the path is first used,
        # by which point transcription has long since paid for it.
        _saved = {}

        def _save():
            try:
                _saved["path"] = recordings.save_wav(audio, self.recorder.sample_rate, rec_id)
                logger.info(f"Recording saved: {_saved['path']} (id={rec_id})")
            except Exception as e:
                _saved["path"] = None
                logger.error(f"save_wav failed: {e}")

        _saver = threading.Thread(target=_save, daemon=True)
        _saver.start()

        def _saved_path():
            _saver.join(timeout=10)
            return _saved.get("path")

        try:
            if self._cancel_flag.is_set():
                return

            # chained_mode: ask the Edge Function to format inside the same round
            # trip. The spec is built HERE because it needs the dictation target
            # app, and it must be read before injection moves focus. None when the
            # flag is off, which leaves the two-round-trip path untouched.
            _chain, _side = None, {}
            try:
                from app.ai_cleanup import build_chain_spec
                _chain = build_chain_spec(self.config, active_app=get_focused_app_name())
            except Exception as e:
                logger.debug("chained_mode setup skipped: %s", e)

            # Hybrid: if this take was long enough, the streamed transcript is already
            # waiting and skips the whole upload+ASR leg. Short takes deliberately do
            # NOT use it — Groq's one round trip is faster below the measured ~8s
            # crossover, because streaming still owes its own formatting trip.
            text, status = None, None
            _st, self._stream = getattr(self, "_stream", None), None
            if _st is not None:
                try:
                    from app import asr_stream as _as
                    _secs = len(audio) / float(self.recorder.sample_rate or 16000)
                    if _secs >= _as.HYBRID_THRESHOLD_SEC:
                        _streamed = _st.finish()
                        if _streamed:
                            # A streamed transcript never passes through
                            # transcriber.finalize(), so the dictionary would silently
                            # stop applying on exactly the long dictations this path
                            # handles. Apply the replacement rules here. (No
                            # prompt-echo scrub: AssemblyAI is sent no glossary, so
                            # there is no echo to strip.)
                            try:
                                from app import dictionary as _d
                                _streamed = _d.apply_replacements(_streamed, self.config)
                            except Exception as e:
                                logger.debug("[hybrid] dictionary pass skipped: %s", e)
                            logger.info("[hybrid] used streamed transcript (%.1fs speech, "
                                        "%.2fs tail)", _secs, _st.wait_after_stop() or -1)
                            text, status = _streamed, "ok"
                        else:
                            logger.warning("[hybrid] no streamed transcript (%s) — "
                                           "transcribing normally", _st.error)
                    else:
                        logger.info("[hybrid] %.1fs < %.0fs — using Groq",
                                    _secs, _as.HYBRID_THRESHOLD_SEC)
                        _st.finish(timeout=0.1)     # close the socket, ignore its text
                except Exception as e:
                    logger.warning("[hybrid] falling back: %s", e)
                    text, status = None, None

            if text is None:
                text, status = self._transcribe_with_retry(audio, chain=_chain, sidecar=_side)
            elif _chain is not None:
                # A streamed transcript never went through the proxy, so nothing was
                # formatted server-side. Clear the sidecar so process_text does the
                # formatting itself instead of reusing a stale chain result.
                _side.clear()

            if self._cancel_flag.is_set():
                return

            if status == "silent":
                logger.warning("No speech detected — discarding recording")
                _discard = _saved_path()
                if _discard:
                    try:
                        os.remove(_discard)
                    except Exception:
                        pass
                self._on_main(lambda: self.overlay.update_status(
                    "⚠️ No speech detected. Speak louder!", error=True))
                time.sleep(1.5)
                self._on_main(self._reset_to_ready)
                return

            if status == "failed":
                # Network/API down — keep the audio and save a retryable entry.
                logger.error("Transcription failed after retries — saved for retry")
                _path = _saved_path()
                self.config = add_to_history(
                    self.config, "", get_focused_app_name(),
                    entry_id=rec_id, audio=_path or "", status="failed")
                self._upload_recording_async(rec_id, _path)
                self._on_main(lambda: self.overlay.update_status(
                    "⚠️ Transcription failed — retry from History", error=True))
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
                # chained_result is the formatting the proxy already did in the
                # transcription round trip (chained_mode); process_text still owns
                # every decision around it and ignores it when its own rules say to.
                result = process_text(text, self.config, active_app=get_focused_app_name(),
                                      chained_result=_side.get("formatted"))
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
            # Joins the background archive write. By now transcription + cleanup
            # have run, so it finished long ago and this returns immediately.
            audio_path = _saved_path()
            word_count = len(result.split())
            # Resolve the dictation TARGET here, before injection: inject_text()
            # calls restore_focused_app(), so asking afterwards can answer with a
            # different app. Only the two save_config() writes move past the paste
            # — this read must not.
            target_app = get_focused_app_name()

            # The pill must be gone before inject_text() restores focus to the
            # target app. This used to be a flat `time.sleep(0.3)` — a guess at how
            # long the hop to the main thread takes, paid in full on every single
            # dictation. Wait for the hide to actually happen instead: `_on_main`
            # enqueues onto `_ui_queue`, drained by a 0.1s rumps.Timer, so this
            # normally returns in well under 100ms. The timeout keeps the old
            # behaviour as a ceiling if the main thread is wedged.
            _hidden = threading.Event()

            def _hide_overlay():
                try:
                    self.overlay.hide()
                finally:
                    _hidden.set()

            self._on_main(_hide_overlay)
            if not _hidden.wait(timeout=0.5):
                logger.warning("overlay hide did not confirm in 0.5s — injecting anyway")

            if self._cancel_flag.is_set():
                return

            success = inject_text(result, allow_mentions=self.config.get("filetag_enabled", False))
            play_done()

            # Persist AFTER the paste. These are two atomic config.json writes
            # (~3.5ms on a 34KB config, ~7ms at 250KB) and nothing about the
            # injected text depends on them, so the user should never wait on them.
            # They must still land HERE — before the sync-push and upload blocks
            # below, which both look the entry up by rec_id — and the app name is
            # the pre-injection `target_app`, not a fresh (post-focus-restore) read.
            self.config = add_to_history(
                self.config, result, target_app,
                entry_id=rec_id, audio=audio_path or "", status="done")
            self._total_transcriptions += 1
            self._total_words += word_count
            self.config = update_daily_words(self.config, word_count)

            # Insights ledger (peripheral, fail-closed — insights.py owns the
            # guarantees). Runs after the paste like the other persistence.
            try:
                from app import insights as _ins
                _secs = len(audio) / float(self.recorder.sample_rate or 16000)
                _ins.record_dictation(self.config, save_config, word_count,
                                      seconds=_secs, app_name=target_app,
                                      fx_words=_ins.polish_delta(text, result))
            except Exception as e:
                logger.debug("insights record skipped: %s", e)

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
                    # IDI-172: push the full shape. audio_url is normally still
                    # empty here (the WAV upload starts below and takes seconds)
                    # — `_upload_recording_async` patches the row once it lands.
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

            # Upload the audio to the cloud + attach its URL (async)
            self._upload_recording_async(rec_id, audio_path)

            if success:
                brief = f"Pasted · {word_count}w"
            else:
                brief = "In clipboard · paste with ⌘V"

            self._on_main(lambda: self._show_result(brief))

        except Exception as e:
            logger.critical(f"PROCESS CRASH: {e}\n{traceback.format_exc()}")
            self._on_main(self._reset_to_ready)
        finally:
            self._processing = False

    def _prompt_paste_blocked(self, reason, target_app):
        """Popup for a paste macOS refused, with a button that opens the setting.

        Called from the dictation worker thread, so the alert has to hop to the
        main thread: rumps.alert spins a modal NSAlert and must never run off it
        (conventions #4). Throttling lives in paste_guard — by the time this is
        called, it has already decided the user should be asked.
        """
        from app import paste_guard
        ok, cancel = paste_guard.buttons(reason)
        title = paste_guard.title(reason)
        body = paste_guard.message(reason, target_app)

        def _show():
            try:
                # This alert deliberately activates Verbal — unlike the overlay
                # and auto-learn panels (conventions #8), stealing focus is
                # harmless here because the paste has already failed.
                if rumps.alert(title=title, message=body, ok=ok, cancel=cancel) == 1:
                    paste_guard.open_fix(reason)
            except Exception as e:
                logger.error(f"paste-blocked prompt failed: {e}")

        self._on_main(_show)

    def _show_result(self, brief):
        try:
            # The `status` argument this used to take was the menubar counts
            # string, which the header now derives itself — so it only ever
            # shadowed the real transcriber status. Dropped with the row.
            self._status_note("")
            self.overlay.show_briefly(brief, duration=2.0)
            self.dashboard._refresh()
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
            # A hands-free (tapped) recording is over however we got here, so the
            # listener must not still believe one is latched — otherwise the next
            # tap is spent "stopping" it instead of starting the next dictation.
            try:
                if self.hotkey_listener:
                    self.hotkey_listener.clear_latch()
            except Exception:
                pass
            # NOTE (IDI-165 carry-over, fixed in IDI-178): this must NOT clear
            # `_cancel_flag`. `_on_esc_pressed` sets the flag and then QUEUES
            # this reset — if the UI queue drained before the transcription
            # worker reached its next `_cancel_flag.is_set()` check, the cancel
            # was silently lost and the text still pasted. The flag is cleared
            # at RECORDING START (`_on_record_start`) instead, so for the whole
            # life of one dictation it means exactly "this one was cancelled".
            self._status_note("")
            self.overlay.hide()
            self._set_menubar_icon(ICON_PATH)
            self.record_btn.title = "Start Recording"
            self.dashboard.update_recording_state(False)
        except Exception as e:
            logger.error(f"Reset error: {e}")

    def _change_model(self, sender):
        if not self._require_signin():
            return
        model_name = sender.title
        for name, item in self.model_items.items():
            item.state = 1 if name == model_name else 0
        self.config["whisper_model"] = model_name
        save_config(self.config)

    def _set_menubar_icon(self, base_path):
        """The one place that assigns `self.icon` — so the persistent
        update-available badge (a small terracotta dot in the corner)
        applies uniformly no matter which base icon (idle vs. recording) is
        showing. Fails closed to the plain icon: a badge render failure must
        never leave the menu bar with no icon at all.
        """
        if self._update_available:
            try:
                badged = _badged_icon_path(base_path)
            except Exception as e:
                logger.debug(f"update badge render failed, using plain icon: {e}")
                badged = None
            if badged and os.path.exists(badged):
                # The badge variant can't be a rumps `template` image (see
                # `_badged_icon_path`'s docstring for why) — flip out of
                # template mode only while a badge is actually showing.
                if self.template is not False:
                    self.template = False
                self.icon = badged
                return
        if self.template is not True:
            self.template = True
        if os.path.exists(base_path):
            self.icon = base_path

    def _refresh_update_badge(self):
        """Re-apply whichever base icon is currently showing, so a change to
        `_update_available` (found/cleared) is reflected immediately instead
        of waiting for the next record start/stop to happen to swap icons."""
        try:
            base = ICON_ACTIVE_PATH if self._is_recording else ICON_PATH
            self._set_menubar_icon(base)
        except Exception as e:
            logger.debug(f"update badge refresh failed: {e}")

    def _check_update(self, announce_current=False):
        """Background update poll — both the one-shot startup check
        (`_start_app`) and the periodic re-check (`_update_check_timer`,
        every `UPDATE_CHECK_INTERVAL`) land here. `check_for_update()`
        returns None both when we're current AND when the check fails, so a
        MANUAL check has to say something either way — silence reads as a
        broken menu item.

        Persistence (the discoverable badge/menu-row this feeds): finding an
        update sets `_update_available` and stays set — surfaced via the
        badge + "Update available" menu row — until either a newer version
        supersedes it or the user actually updates. The popup itself,
        though, is throttled to once per version: if the user already hit
        "Later" for this exact version, later periodic checks keep the badge
        current but don't pop the alert again (`_update_dismissed_version`)
        — only a genuinely newer version, or the user manually re-opening
        the prompt from the menu row, shows it again.
        """
        from app.updater import check_for_update
        update = check_for_update()
        if update:
            is_new_version = update["version"] != self._update_dismissed_version
            self._update_available = update
            self._on_main(self._refresh_update_badge)
            if is_new_version:
                self._on_main(lambda: self._show_update_prompt(update))
        else:
            had_one = self._update_available is not None
            self._update_available = None
            self._update_dismissed_version = None
            if had_one:
                self._on_main(self._refresh_update_badge)
            if announce_current:
                from app.config import APP_VERSION
                self._on_main(lambda: rumps.alert(
                    "You're up to date",
                    f"Flume v{APP_VERSION} is the latest version."))

    def _check_update_now(self, _=None):
        """Menubar 'Check for Updates…' — same path as the startup poll."""
        threading.Thread(target=self._check_update, args=(True,), daemon=True).start()

    def _periodic_update_check(self, _timer=None):
        """`_update_check_timer` callback (runs on the main thread, like every
        rumps.Timer) — hops the actual network call to a daemon thread so a
        slow/hung request never stalls the UI queue."""
        threading.Thread(target=self._check_update, daemon=True).start()

    def _open_update_prompt(self, _=None):
        """'Update available (vX.Y.Z) ↑' menu row — re-shows the same dialog
        for whatever update is currently pending, without re-hitting the
        network (the badge already told us it's there)."""
        update = self._update_available
        if update:
            self._show_update_prompt(update)

    def _show_update_prompt(self, update):
        changelog = update.get('changelog', 'Bug fixes and improvements')
        resp = rumps.alert(
            f"Flume {update['version']} available",
            f"{changelog}\n\nDownload and install now?",
            ok="Update",
            cancel="Later",
        )
        if resp == 1:
            self._status_note("Downloading update…")
            threading.Thread(target=self._do_update, args=(update,), daemon=True).start()
        else:
            # "Later": keep the badge/menu row alive (this version is still
            # not installed), just stop nagging with a fresh popup for it —
            # the periodic check will alert again only once something newer
            # ships.
            self._update_dismissed_version = update.get("version")

    def _do_update(self, update):
        from app.updater import download_update, install_update
        path = download_update(update)
        if path:
            install_update(path)
        else:
            self._on_main(lambda: rumps.alert("Update failed", "Could not download the update. Try again later."))
            self._on_main(lambda: self._status_note(""))

    def _about(self, _):
        from app.config import APP_VERSION
        rumps.alert(
            f"Flume v{APP_VERSION}",
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
