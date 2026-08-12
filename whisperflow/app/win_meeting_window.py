"""Windows meeting window — pywebview host for meeting_html().

Parity with the macOS `MeetingWindow` (app/meeting_window.py) but hosted
in a pywebview WebView2 window. The Mac version morphs between two
layouts (compact "bar" top-center vs full "expanded" panel) with native
frame animation; WebView2 doesn't support that fluid morph — we resize
+ reposition the pywebview window on `expand()`/`collapse()` (acceptable
parity per W6-meetings-wasapi.md §"Meeting window").

Public interface the backend calls:
    show(mode="premeeting"), hide(), set_mode(mode), set_layout(layout),
    expand(), collapse(), emit(event, payload), page_ready(), .visible

The window also duck-types the `dashboard` argument DashboardApi expects
so all meeting methods on DashboardApi light up (`_known_devices`,
`_target_device_id`, `_window`, `_load_devices`).
"""

import ctypes
import ctypes.wintypes as wt
import json
import logging

from app.meeting_html import meeting_html
from app.shared_dashboard import DashboardApi

logger = logging.getLogger("verbal.meetingwin.win")

BAR_W, BAR_H = 500, 54
WIN_W, WIN_H = 880, 620
MIN_W, MIN_H = 700, 480
WIN_TITLE = "Flume Meeting"

SPI_GETWORKAREA = 0x0030


class WinMeetingWindow:
    def __init__(self, app):
        self.app = app
        self._window = None
        self._api = None
        self._layout = "expanded"      # 'bar' | 'expanded'
        self._page_ready = False
        self._pending = []             # events buffered until page ready
        self._visible = False

        # DashboardApi reads these on the "dashboard" argument.
        self._known_devices = []
        try:
            self._target_device_id = app.config.get(
                "sync_target_device_id", "__all__") or "__all__"
        except Exception:
            self._target_device_id = "__all__"
        # Guards concurrent show()s from spawning multiple windows before
        # webview.create_window returns and assigns self._window.
        import threading as _th
        self._build_lock = _th.Lock()

    # ── DashboardApi shape ──────────────────────────────────────────────
    def _load_devices(self):
        try:
            d = getattr(self.app, "dashboard", None)
            if d is not None and hasattr(d, "_load_devices"):
                d._load_devices()
        except Exception:
            pass

    # ── build / show / hide ─────────────────────────────────────────────
    def _work_area(self):
        try:
            wa = wt.RECT()
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETWORKAREA, 0, ctypes.byref(wa), 0)
            return wa.left, wa.top, wa.right, wa.bottom
        except Exception:
            return 0, 0, 1440, 860

    def _rect_for(self, layout):
        left, top, right, bottom = self._work_area()
        if layout == "bar":
            w, h = BAR_W, BAR_H
            x = (left + right - w) // 2
            y = top + 12
        else:
            w, h = WIN_W, WIN_H
            x = (left + right - w) // 2
            y = (top + bottom - h) // 2
        return x, y, w, h

    def _build(self):
        try:
            import webview
        except Exception as e:
            logger.error("pywebview unavailable; meeting window disabled: %s", e)
            return
        try:
            self._api = DashboardApi(self)
            x, y, w, h = self._rect_for(self._layout)
            self._window = webview.create_window(
                WIN_TITLE,
                html=meeting_html(),
                js_api=self._api,
                width=w,
                height=h,
                x=x,
                y=y,
                min_size=(MIN_W, MIN_H),
                frameless=False,
                on_top=False,
                background_color="#0e1012",
                hidden=True,
            )
            try:
                self._window.events.loaded += self._on_loaded
            except Exception as e:
                logger.debug("meeting loaded-hook attach failed: %s", e)
        except Exception as e:
            logger.error("meeting window create failed: %s", e, exc_info=True)
            self._window = None

    def _on_loaded(self):
        # macOS drains this window's `_pending` via the JS-initiated
        # `api('meeting_page_ready')` handshake at the bottom of
        # meeting_html.py. On pywebview / WebView2 that bridge call
        # sometimes doesn't fire promptly on freshly-created windows
        # (bridge-init race), so we call page_ready() directly here — the
        # page is DOM-loaded by now, and if the JS handshake does fire
        # later it's idempotent (our second flush finds `_pending` empty).
        try:
            self.page_ready()
        except Exception as e:
            logger.debug("meeting window: page_ready failed: %s", e)
        # WebView2 doesn't resolve `.main { height:100% }` against an implicit
        # viewport ancestor the way WKWebView does — inject the same host-side
        # height anchor SharedDashboard uses so scroll-region overflow works
        # (see shared_dashboard._inject_scroll_fix for the rationale).
        try:
            self._inject_scroll_fix()
        except Exception as e:
            logger.debug("meeting window: scroll-fix failed: %s", e)
        if not self._visible:
            try:
                self._window.hide()
            except Exception:
                pass

    def show(self, mode="premeeting"):
        try:
            with self._build_lock:
                if self._window is None:
                    self._build()
            if self._window is None:
                logger.warning("meeting window: build failed, cannot show")
                return
            if mode in ("premeeting", "permissions", "summary"):
                self._layout = "expanded"
            self._position_and_size()
            self._window.show()
            self._visible = True
            self.set_mode(mode)
            self.emit("layout", {"layout": self._layout})
        except Exception as e:
            logger.error("meeting window show failed: %s", e, exc_info=True)

    def hide(self):
        try:
            if self._window is not None:
                self._window.hide()
        except Exception:
            pass
        self._visible = False

    @property
    def visible(self):
        return self._visible

    # ── layout ──────────────────────────────────────────────────────────
    def _position_and_size(self):
        try:
            x, y, w, h = self._rect_for(self._layout)
            if self._window:
                self._window.resize(w, h)
                self._window.move(x, y)
        except Exception as e:
            logger.debug("meeting window position failed: %s", e)

    def set_layout(self, layout, animate=True):
        if layout not in ("bar", "expanded"):
            return
        self._layout = layout
        self._position_and_size()
        self.emit("layout", {"layout": layout})

    def expand(self):
        self.set_layout("expanded")

    def collapse(self):
        self.set_layout("bar")

    def set_mode(self, mode):
        self.emit("mode", {"mode": mode})
        if mode in ("premeeting", "permissions", "summary"):
            self.set_layout("expanded")

    # ── JS emit (with pending queue) ────────────────────────────────────
    def _eval(self, js):
        if self._window is None:
            return
        try:
            self._window.evaluate_js(js)
        except Exception as e:
            logger.debug("meeting evaluate_js failed: %s", e)

    def emit(self, event, payload):
        if not self._page_ready:
            self._pending.append((event, payload))
            if len(self._pending) > 200:
                self._pending = self._pending[-200:]
            return
        self._eval("if(window.VerbalMeeting)window.VerbalMeeting(%s,%s);" % (
            json.dumps(event), json.dumps(payload or {}, default=str)))

    def _inject_scroll_fix(self):
        """Anchor scroll containers to viewport height — same rationale as
        SharedDashboard._inject_scroll_fix."""
        css = (
            "html,body{height:100vh;overflow:hidden}"
            "body>*{max-height:100vh}"
            ".transcript,.mrols,.mrsc,.msum,.pdroll,.notepane,.pbody{"
            "overflow-y:auto;-webkit-overflow-scrolling:touch}"
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
            logger.debug("scroll-fix injection failed: %s", e)

    def page_ready(self):
        """Called via the bridge when the page installs window.VerbalMeeting."""
        self._page_ready = True
        pending, self._pending = self._pending, []
        for event, payload in pending:
            self.emit(event, payload)
        self.emit("layout", {"layout": self._layout})
