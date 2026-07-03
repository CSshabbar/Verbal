"""
Flume menubar popover for macOS — an NSPopover hosting a WKWebView with the
Flume popover UI, wired to the existing DashboardApi backend.

Reuses the WKWebView JS bridge (_Bridge + _SHIM) from flume_web_dashboard so the
popover HTML talks to Python via window.pywebview.api, exactly like the dashboard.
Popover-only actions (toggle_recording / open_window / open_preferences /
quit_app) are handled here; everything else falls through to DashboardApi.
"""
import json
import logging
import threading

import rumps
import objc
from AppKit import (
    NSPopover, NSViewController, NSApplication, NSMinYEdge, NSApp, NSMenu,
)
from Foundation import NSMakeRect, NSMakeSize, NSObject

try:
    from AppKit import NSEventTypeRightMouseUp, NSEventModifierFlagControl
except Exception:  # older pyobjc naming
    NSEventTypeRightMouseUp, NSEventModifierFlagControl = 4, 1 << 18
_MASK_LEFT_UP = 1 << 2   # NSEventMaskLeftMouseUp
_MASK_RIGHT_UP = 1 << 4  # NSEventMaskRightMouseUp

from app import theme as _theme  # noqa: F401 — registers Geist/JBM for WKWebView
from app.flume_popover_html import popover_html
from app.flume_web_dashboard import _Bridge, _SHIM
from app.shared_dashboard import DashboardApi

logger = logging.getLogger("verbal.flumepopover")

_POPOVER_METHODS = {"toggle_recording", "open_window", "open_canvas",
                    "open_history", "open_preferences", "quit_app"}


class _StatusClickHandler(NSObject):
    """Target for the status-bar button: left-click → popover, right/ctrl-click →
    the classic rumps menu (so API-key / model / mode items stay reachable)."""

    def initWithPopover_menu_(self, popover, classic_menu):
        self = objc.super(_StatusClickHandler, self).init()
        if self is None:
            return None
        self._popover = popover
        self._menu = classic_menu
        return self

    def togglePopover_(self, sender):
        ev = NSApp.currentEvent()
        right = False
        try:
            if ev is not None:
                right = (ev.type() == NSEventTypeRightMouseUp or
                         bool(int(ev.modifierFlags()) & int(NSEventModifierFlagControl)))
        except Exception:
            right = False
        if right and self._menu is not None:
            NSMenu.popUpContextMenu_withEvent_forView_(self._menu, ev, sender)
            return
        self._popover.toggle(sender)


class FlumePopover:
    """Duck-types the dashboard interface DashboardApi/main.py expect."""

    WIN_W, WIN_H = 360, 540

    def __init__(self, app):
        self.app = app
        self._popover = None
        self._webview = None
        self._bridge = None
        self._api = DashboardApi(self)
        # attributes DashboardApi reads:
        self._known_devices = []
        self._target_device_id = "__all__"

    # ── build ───────────────────────────────────────────────────────────────
    def _build(self):
        from WebKit import (
            WKWebView, WKWebViewConfiguration, WKUserContentController, WKUserScript,
        )
        WKUserScriptInjectionTimeAtDocumentStart = 0

        ucc = WKUserContentController.alloc().init()
        self._bridge = _Bridge.alloc().initWithDashboard_(self)
        ucc.addScriptMessageHandler_name_(self._bridge, "flume")
        ucc.addUserScript_(
            WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
                _SHIM, WKUserScriptInjectionTimeAtDocumentStart, True))

        config = WKWebViewConfiguration.alloc().init()
        config.setUserContentController_(ucc)

        rect = NSMakeRect(0, 0, self.WIN_W, self.WIN_H)
        self._webview = WKWebView.alloc().initWithFrame_configuration_(rect, config)
        try:
            self._webview.setValue_forKey_(False, "drawsBackground")
        except Exception:
            pass
        self._webview.loadHTMLString_baseURL_(popover_html(), None)

        vc = NSViewController.alloc().init()
        vc.setView_(self._webview)

        self._popover = NSPopover.alloc().init()
        self._popover.setContentViewController_(vc)
        self._popover.setContentSize_(NSMakeSize(self.WIN_W, self.WIN_H))
        # Transient: closes as soon as the user clicks anywhere outside it.
        # (Canvas/History open inside the popover now, so nothing here needs it
        # to stay open when another window appears.)
        self._popover.setBehavior_(1)  # NSPopoverBehaviorTransient
        self._popover.setAnimates_(True)

    # ── attach to the rumps status-bar button ────────────────────────────────
    def install_status_hook(self):
        """Rebind the status-item button to open this popover on left-click,
        preserving the classic rumps menu on right/ctrl-click. Safe no-op on
        failure — the classic menu keeps working."""
        try:
            si = self.app._nsapp.nsstatusitem
            btn = si.button()
            classic_menu = si.menu()  # rumps' NSMenu
            self._handler = _StatusClickHandler.alloc().initWithPopover_menu_(self, classic_menu)
            si.setMenu_(None)  # detach so left-click doesn't open the menu
            btn.setTarget_(self._handler)
            btn.setAction_("togglePopover:")
            btn.sendActionOn_(_MASK_LEFT_UP | _MASK_RIGHT_UP)
            logger.info("Flume popover attached to status item")
            return True
        except Exception as e:
            logger.warning("could not attach popover to status item (%s); classic menu kept", e)
            return False

    # ── show / toggle (called on the main thread) ────────────────────────────
    def toggle(self, button):
        try:
            if self._popover is None:
                self._build()
            if self._popover.isShown():
                self._popover.performClose_(None)
                return
            self._popover.showRelativeToRect_ofView_preferredEdge_(
                button.bounds(), button, NSMinYEdge)
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            # push fresh state on every open
            self._refresh()
        except Exception as e:
            logger.error("popover toggle failed: %s", e)

    def close(self):
        try:
            if self._popover and self._popover.isShown():
                self._popover.performClose_(None)
        except Exception:
            pass

    # ── JS bridge dispatch (same protocol as the dashboard) ───────────────────
    def _dispatch(self, mid, method, args):
        def work():
            try:
                if method in _POPOVER_METHODS:
                    fn = getattr(self, method, None)
                else:
                    fn = getattr(self._api, method, None)
                result = fn(*args) if callable(fn) else {"ok": False, "error": "no method"}
            except Exception as e:
                logger.error("popover api %s failed: %s", method, e)
                result = {"ok": False, "error": str(e)}
            if mid is not None:
                self._resolve(mid, result)
        threading.Thread(target=work, daemon=True).start()

    def _resolve(self, mid, result):
        payload = json.dumps(result, default=str)
        self._eval("window.__flumeResolve(%d, %s);" % (mid, json.dumps(payload)))

    def _emit(self, event, payload):
        self._eval("if(window.VerbalNative)window.VerbalNative(%s, %s);"
                   % (json.dumps(event), json.dumps(payload, default=str)))

    def _eval(self, js):
        if not self._webview:
            return
        def run():
            try:
                self._webview.evaluateJavaScript_completionHandler_(js, None)
            except Exception as e:
                logger.debug("popover evaluateJS failed: %s", e)
        try:
            self.app._on_main(run)
        except Exception:
            run()

    # ── popover-only actions (invoked off-thread; hop to main) ────────────────
    def toggle_recording(self):
        self.app._on_main(lambda: self.app._toggle_recording(None))
        self.app._on_main(self.close)
        return {"ok": True}

    def open_window(self):
        self.app._on_main(self.app._open_dashboard)
        self.app._on_main(self.close)
        return {"ok": True}

    def _open_tab(self, idx):
        # open the dashboard on a tab WITHOUT closing the popover
        def go():
            self.app.dashboard.show()
            try:
                self.app.dashboard._on_tab_select(idx)
            except Exception:
                pass
        self.app._on_main(go)
        return {"ok": True}

    def open_canvas(self):
        return self._open_tab(4)

    def open_history(self):
        return self._open_tab(0)

    def open_preferences(self):
        def go():
            self.app.dashboard.show()
            try:
                self.app.dashboard._on_tab_select(3)  # Settings
            except Exception:
                pass
        self.app._on_main(go)
        self.app._on_main(self.close)
        return {"ok": True}

    def quit_app(self):
        self.app._on_main(lambda: rumps.quit_application())
        return {"ok": True}

    # ── events main.py calls (mirror the dashboard interface) ─────────────────
    def update_recording_state(self, is_recording):
        self._emit("recordingState", {"recording": bool(is_recording)})

    def show_result(self, text):
        self._emit("result", {"text": text})

    def _refresh(self):
        try:
            self._emit("state", self._api.get_state())
        except Exception as e:
            logger.debug("popover refresh failed: %s", e)
