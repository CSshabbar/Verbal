"""Windows Flume popover — pywebview host for flume_popover_html().

Windows has no menubar, so the tray icon's LEFT-click opens this compact
Flume popover (parity with the Mac NSPopover in app/flume_popover.py). The
tray's right-click continues to show the classic pystray menu.

Bridge design mirrors the Mac side: `_PopoverBridge` subclasses `DashboardApi`
so every shared method the popover HTML calls (`get_state`, `save_settings`,
`copy_text`, `fetch_canvas`, `open_meeting_launcher`, …) is routed to the
same backend the dashboard uses. Popover-only actions (`toggle_recording`,
`open_window`, `open_preferences`, `open_canvas`, `open_history`, `quit_app`)
are added as overrides.

Fail-closed: tray behavior — and dictation — must not depend on the popover
building. show()/toggle() and every bridge method are wrapped so a broken
popover degrades to a no-op.
"""

import ctypes
import ctypes.wintypes as wt
import json
import logging

from app.flume_popover_html import popover_html
from app.shared_dashboard import DashboardApi

logger = logging.getLogger("verbal.popover")

WIN_W = 380
WIN_H = 600
WIN_TITLE = "Flume Popover"

SPI_GETWORKAREA = 0x0030


class _PopoverBridge(DashboardApi):
    """Popover js_api — DashboardApi + a handful of popover-only actions.

    Inheriting from DashboardApi means every shared method the popover HTML
    depends on (get_state / save_settings / copy_text / fetch_canvas /
    open_meeting_launcher / …) is available on the bridge without wrapping
    or delegation. We override / add the popover-specific ones below.
    """

    def __init__(self, popover):
        super().__init__(popover)     # popover duck-types the dashboard
        self._popover = popover

    def toggle_recording(self):
        app = self._popover.app
        app._on_main(app._toggle_recording)
        app._on_main(self._popover.hide)
        return {"ok": True}

    def open_window(self):
        app = self._popover.app
        app._on_main(lambda: app.dashboard.show())
        app._on_main(self._popover.hide)
        return {"ok": True}

    def _open_tab(self, idx):
        app = self._popover.app

        def go():
            try:
                app.dashboard.show()
                app.dashboard._on_tab_select(idx)
            except Exception as e:
                logger.debug("dashboard tab select %s failed: %s", idx, e)

        app._on_main(go)
        return {"ok": True}

    # Tab indices come from SharedDashboard._on_tab_select's TAB_MAP.
    def open_canvas(self):
        return self._open_tab(4)

    def open_history(self):
        return self._open_tab(0)

    def open_preferences(self):
        r = self._open_tab(3)  # settings
        self._popover.app._on_main(self._popover.hide)
        return r

    def quit_app(self):
        self._popover.app._on_main(self._popover.app._tray_quit)
        return {"ok": True}


class WinPopover:
    """Compact Flume popover for Windows. Lazily builds its pywebview window
    the first time show()/toggle() is called (after webview.start() has begun
    on the main thread — win_main starts the loop; win_overlay creates the
    anchor window). Subsequent shows re-use the window."""

    def __init__(self, app):
        self.app = app
        # DashboardApi reads these on the "dashboard" argument. Independent
        # of the real dashboard so we can be built before it. Once open, the
        # popover's state pushes come from DashboardApi.get_state which reads
        # sync device info through these fields.
        self._known_devices = []
        self._target_device_id = "__all__"

        self._window = None
        self._bridge = None
        self._api = None
        self._loaded = False
        self._visible = False
        self._pending_events = []

    # ── window lifecycle ────────────────────────────────────────
    def _build(self):
        import webview
        self._bridge = _PopoverBridge(self)
        self._api = self._bridge  # what DashboardApi-shaped methods live on
        self._window = webview.create_window(
            WIN_TITLE,
            html=popover_html(),
            js_api=self._bridge,
            width=WIN_W,
            height=WIN_H,
            frameless=True,
            on_top=True,
            resizable=False,
            easy_drag=False,
            background_color="#0e1012",
            hidden=True,
        )
        try:
            self._window.events.loaded += self._on_loaded
        except Exception as e:
            logger.debug("popover loaded-hook attach failed: %s", e)

    def _on_loaded(self):
        self._loaded = True
        # Keep the popover hidden after WebView2's initial paint — surface
        # only via show()/toggle().
        if not self._visible:
            try:
                self._window.hide()
            except Exception:
                pass
        # WebView2 doesn't resolve implicit viewport-height parents the way
        # WKWebView does — inject a host-side height anchor so `.recscroll`
        # inside popover_html actually scrolls. See
        # shared_dashboard._inject_scroll_fix for the full rationale.
        try:
            self._inject_scroll_fix()
        except Exception as e:
            logger.debug("popover: scroll-fix failed: %s", e)
        # Flush events emitted before the DOM was ready.
        pending = list(self._pending_events)
        self._pending_events.clear()
        for ev, payload in pending:
            self._emit(ev, payload)

    def _position(self):
        """Bottom-right of the primary work area — near the tray."""
        try:
            wa = wt.RECT()
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETWORKAREA, 0, ctypes.byref(wa), 0)
            x = wa.right - WIN_W - 12
            y = wa.bottom - WIN_H - 12
        except Exception:
            x, y = 900, 200
        try:
            if self._window:
                self._window.move(x, y)
        except Exception:
            pass

    # ── show / hide / toggle ────────────────────────────────────
    def show(self):
        try:
            if not self._window:
                self._build()
            self._position()
            self._window.show()
            self._visible = True
            self._refresh()
        except Exception as e:
            logger.error("popover show failed: %s", e)

    def hide(self):
        try:
            if self._window:
                self._window.hide()
        except Exception as e:
            logger.debug("popover hide failed: %s", e)
        self._visible = False

    def close(self):
        self.hide()

    def toggle(self):
        if self._visible:
            self.hide()
        else:
            self.show()

    @property
    def visible(self):
        return self._visible

    def _inject_scroll_fix(self):
        css = (
            "html,body{height:100vh;overflow:hidden}"
            ".view{height:100vh;display:flex;flex-direction:column}"
            ".recscroll{overflow-y:auto;-webkit-overflow-scrolling:touch;flex:1}"
        )
        js = (
            "(function(){var id='__verbal_scroll_fix';"
            "var el=document.getElementById(id);"
            "if(!el){el=document.createElement('style');el.id=id;document.head.appendChild(el);}"
            "el.textContent=" + repr(css) + ";})();"
        )
        try:
            if self._window:
                self._window.evaluate_js(js)
        except Exception as e:
            logger.debug("popover scroll-fix injection failed: %s", e)

    # ── VerbalNative event push (parity with FlumePopover._emit) ──
    def _emit(self, event, payload):
        if not self._loaded:
            self._pending_events.append((event, payload))
            return
        if not self._window:
            return
        try:
            js = "if(window.VerbalNative)window.VerbalNative(%s,%s);" % (
                json.dumps(event), json.dumps(payload, default=str))
            self._window.evaluate_js(js)
        except Exception as e:
            logger.debug("popover emit %s failed: %s", event, e)

    def _refresh(self):
        try:
            # Sync device fields from the real dashboard so DashboardApi's
            # get_state (which reads self._known_devices / _target_device_id
            # from the "dashboard" arg — us) reports the shared view.
            d = getattr(self.app, "dashboard", None)
            if d is not None:
                self._known_devices = list(getattr(d, "_known_devices", []) or [])
                self._target_device_id = getattr(d, "_target_device_id", "__all__")
        except Exception:
            pass
        if not self._api:
            return
        try:
            self._emit("state", self._api.get_state())
        except Exception as e:
            logger.debug("popover refresh failed: %s", e)

    # ── methods the record → transcribe → inject pipeline calls ──
    def update_recording_state(self, is_recording):
        self._emit("recordingState", {"recording": bool(is_recording)})

    def show_result(self, text):
        self._emit("result", {"text": text})

    # ── SharedDashboard shape DashboardApi expects on its `dashboard` arg ──
    def _load_devices(self):
        """DashboardApi.save_settings() (and the periodic refresh loop) calls
        this on the "dashboard" it was constructed with. Delegate to the real
        dashboard's implementation so device sync stays consistent."""
        try:
            d = getattr(self.app, "dashboard", None)
            if d is not None and hasattr(d, "_load_devices"):
                d._load_devices()
        except Exception as e:
            logger.debug("popover _load_devices delegate failed: %s", e)
