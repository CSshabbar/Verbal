"""
Meetings — floating HUD (MEETINGS_DESIGN_HANDOFF.md 31d), overlay.py pattern.

A non-activating NSPanel (NSNonactivatingPanelMask | NSScreenSaverWindowLevel,
all-spaces) anchored bottom-left, shown while a meeting records and the meeting
window is NOT key. It must NEVER steal focus from the Zoom/Meet/Teams window
(05-conventions.md Rule #8).

Interface used by main/meeting_window: show(), hide(), push(event, payload),
visible. Buttons post back through the bridge: hud_star / hud_pause /
hud_return.
"""
import logging

from AppKit import (
    NSPanel, NSColor,
    NSWindowStyleMaskBorderless,
    NSScreen, NSBackingStoreBuffered, NSScreenSaverWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
)
from Foundation import NSMakeRect

from app import theme as _theme  # noqa: F401 — registers fonts for WKWebView
from app.meeting_hud_html import meeting_hud_html

logger = logging.getLogger("verbal.meetinghud")

PANEL_W = 460
PANEL_H = 90

_HUD_ACTIONS = {"hud_star", "hud_pause", "hud_return"}


class MeetingHud:
    def __init__(self, app):
        self.app = app
        self._window = None
        self._webview = None
        self._bridge = None
        self._visible = False

    # ── window (overlay.py pattern) ───────────────────────────────────────────
    def _setup(self):
        screen = NSScreen.mainScreen()
        if not screen:
            return
        NSNonactivatingPanelMask = 1 << 7
        self._window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(24, 40, PANEL_W, PANEL_H),           # bottom-left anchor
            NSWindowStyleMaskBorderless | NSNonactivatingPanelMask,
            NSBackingStoreBuffered, False)
        self._window.setLevel_(NSScreenSaverWindowLevel)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setHasShadow_(False)
        self._window.setIgnoresMouseEvents_(False)
        self._window.setFloatingPanel_(True)
        self._window.setBecomesKeyOnlyIfNeeded_(True)
        self._window.setHidesOnDeactivate_(False)
        self._window.setMovableByWindowBackground_(True)    # draggable pill
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary)
        try:
            self._build_webview()
        except Exception as e:
            logger.error("meeting hud webview failed: %s", e)

    def _build_webview(self):
        from WebKit import (
            WKWebView, WKWebViewConfiguration, WKUserContentController, WKUserScript,
        )
        from app.flume_web_dashboard import _Bridge, _SHIM

        ucc = WKUserContentController.alloc().init()
        self._bridge = _Bridge.alloc().initWithDashboard_(self)
        ucc.addScriptMessageHandler_name_(self._bridge, "flume")
        ucc.addUserScript_(
            WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(_SHIM, 0, True))
        config = WKWebViewConfiguration.alloc().init()
        config.setUserContentController_(ucc)
        self._webview = WKWebView.alloc().initWithFrame_configuration_(
            NSMakeRect(0, 0, PANEL_W, PANEL_H), config)
        self._webview.setAutoresizingMask_(0x02 | 0x10)
        for setter in ("drawsBackground",):
            try:
                self._webview.setValue_forKey_(False, setter)
            except Exception:
                pass
        try:
            self._webview.setOpaque_(False)
            self._webview.setWantsLayer_(True)
            self._webview.layer().setBackgroundColor_(NSColor.clearColor().CGColor())
        except Exception:
            pass
        self._webview.loadHTMLString_baseURL_(meeting_hud_html(), None)
        self._window.setContentView_(self._webview)

    # ── interface ─────────────────────────────────────────────────────────────
    def show(self):
        try:
            if not self._window:
                self._setup()
            if self._window:
                self._window.orderFrontRegardless()
                self._visible = True
                self._push_state()
        except Exception as e:
            logger.debug("hud show failed: %s", e)

    def hide(self):
        try:
            self.push("state", {"state": "hidden"})
            if self._window:
                self._window.orderOut_(None)
        except Exception:
            pass
        self._visible = False

    @property
    def visible(self):
        return self._visible

    def push(self, event, payload=None):
        import json
        if not self._webview:
            return
        js = "if(window.VerbalMeetingHud)window.VerbalMeetingHud(%s, %s);" % (
            json.dumps(event), json.dumps(payload or {}, default=str))

        def run():
            try:
                self._webview.evaluateJavaScript_completionHandler_(js, None)
            except Exception as e:
                logger.debug("hud eval failed: %s", e)
        try:
            self.app._on_main(run)
        except Exception:
            run()

    def _push_state(self):
        try:
            s = self.app.meetings.active if getattr(self.app, "meetings", None) else None
            if s:
                self.push("state", {"state": s.state, "title": s.title})
        except Exception:
            pass

    def cleanup(self):
        try:
            if self._window:
                self._window.orderOut_(None)
        except Exception:
            pass

    # ── bridge dispatch (button clicks) ───────────────────────────────────────
    def _dispatch(self, mid, method, args):
        if method in _HUD_ACTIONS:
            try:
                getattr(self, method)()
            except Exception as e:
                logger.error("hud action %s failed: %s", method, e)

    def _resolve(self, mid, result):
        pass  # fire-and-forget

    # ── actions ───────────────────────────────────────────────────────────────
    def hud_star(self):
        try:
            m = getattr(self.app, "meetings", None)
            if m and m.active:
                m.active.mark_moment("")
        except Exception:
            pass

    def hud_pause(self):
        try:
            m = getattr(self.app, "meetings", None)
            if m and m.active:
                m.active.toggle_pause()
                self._push_state()
        except Exception:
            pass

    def hud_return(self):
        try:
            def run():
                win = self.app._meeting_win()
                if win:
                    win.show("live")
            self.app._on_main(run)
        except Exception:
            pass
