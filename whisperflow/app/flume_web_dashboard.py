"""
Flume desktop dashboard for macOS — a WKWebView hosting the Flume HTML,
wired to the existing DashboardApi backend.

Why WKWebView (not pywebview): the Mac app is a rumps menubar app that already
owns the Cocoa run loop, so pywebview.start() (used by the Windows build) can't
run here. A WKWebView inside an NSWindow lives in the same run loop.

JS ↔ Python bridge:
  - JS calls window.pywebview.api.<method>(...args) → a shim posts to the
    'flume' message handler → we dispatch to DashboardApi off the main thread →
    resolve the JS promise via window.__flumeResolve(id, json).
  - Python → JS events use window.VerbalNative(event, payload), the same event
    names the shared DashboardApi already emits.
"""
import json
import logging
import threading

from AppKit import (
    NSWindow, NSScreen, NSBackingStoreBuffered, NSApplication,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSWindowStyleMaskMiniaturizable,
    NSColor,
)
from Foundation import NSMakeRect, NSMakeSize, NSObject
import objc

from app import theme as _theme  # noqa: F401  — registers Geist/JBM for WKWebView
from app.flume_dashboard_html import flume_html
from app.shared_dashboard import DashboardApi

logger = logging.getLogger("verbal.flumeweb")

# Injected before the page's own scripts: makes WKWebView look like pywebview.
_SHIM = """
window.__flumeCbs = {}; window.__flumeId = 0;
window.pywebview = { api: new Proxy({}, { get: function(_, name){
  return function(){ var args = Array.prototype.slice.call(arguments);
    return new Promise(function(resolve){
      var id = ++window.__flumeId; window.__flumeCbs[id] = resolve;
      window.webkit.messageHandlers.flume.postMessage(JSON.stringify({id:id, method:name, args:args}));
    });
  };
}})};
window.__flumeResolve = function(id, jsonStr){
  var cb = window.__flumeCbs[id]; if(!cb) return; delete window.__flumeCbs[id];
  try { cb(JSON.parse(jsonStr)); } catch(e){ cb(jsonStr); }
};
"""


class _Bridge(NSObject):
    def initWithDashboard_(self, dash):
        self = objc.super(_Bridge, self).init()
        if self is None:
            return None
        self._dash = dash
        return self

    def userContentController_didReceiveScriptMessage_(self, ucc, message):
        try:
            body = message.body()
            msg = json.loads(body) if isinstance(body, str) else dict(body)
        except Exception as e:
            logger.error("bridge: bad message: %s", e)
            return
        mid = msg.get("id")
        method = msg.get("method", "")
        args = msg.get("args", []) or []
        self._dash._dispatch(mid, method, args)


class FlumeWebDashboard:
    """Duck-types the old DashboardWindow: show(), update_recording_state(), etc.
    Also serves as the `dashboard` object DashboardApi expects."""

    WIN_W, WIN_H = 980, 680

    def __init__(self, app):
        self.app = app
        self._window = None
        self._webview = None
        self._bridge = None
        self._api = DashboardApi(self)
        self._ready = False
        # attributes DashboardApi reads:
        self._known_devices = []
        try:
            self._target_device_id = app.config.get("sync_target_device_id", "__all__") or "__all__"
        except Exception:
            self._target_device_id = "__all__"

    # ── window ────────────────────────────────────────────────────────────────
    def show(self):
        if self._window and self._window.isVisible():
            self._window.makeKeyAndOrderFront_(None)
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            return
        if self._window is None:
            self._build()
        self._window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def _build(self):
        from WebKit import (
            WKWebView, WKWebViewConfiguration, WKUserContentController,
            WKUserScript,
        )
        WKUserScriptInjectionTimeAtDocumentStart = 0

        screen = NSScreen.mainScreen()
        sf = screen.frame() if screen else NSMakeRect(0, 0, 1440, 900)
        x = (sf.size.width - self.WIN_W) / 2
        y = (sf.size.height - self.WIN_H) / 2
        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                 NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, self.WIN_W, self.WIN_H), style, NSBackingStoreBuffered, False)
        self._window.setTitle_("Flume")
        self._window.setMinSize_(NSMakeSize(760, 520))
        self._window.setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(14/255, 16/255, 18/255, 1.0))

        ucc = WKUserContentController.alloc().init()
        self._bridge = _Bridge.alloc().initWithDashboard_(self)
        ucc.addScriptMessageHandler_name_(self._bridge, "flume")
        ucc.addUserScript_(
            WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
                _SHIM, WKUserScriptInjectionTimeAtDocumentStart, True))

        config = WKWebViewConfiguration.alloc().init()
        config.setUserContentController_(ucc)

        cr = self._window.contentView().bounds()
        self._webview = WKWebView.alloc().initWithFrame_configuration_(cr, config)
        self._webview.setAutoresizingMask_(0x02 | 0x10)  # width+height flexible
        try:
            self._webview.setValue_forKey_(False, "drawsBackground")  # transparent → our bg
        except Exception:
            pass
        self._window.contentView().addSubview_(self._webview)
        self._webview.loadHTMLString_baseURL_(flume_html(), None)
        self._ready = True

        # keep the sidebar device list fresh
        threading.Thread(target=self._device_refresh_loop, daemon=True).start()

    # ── JS bridge dispatch ──────────────────────────────────────────────────────
    def _dispatch(self, mid, method, args):
        def work():
            try:
                fn = getattr(self._api, method, None)
                result = fn(*args) if callable(fn) else {"ok": False, "error": "no method"}
            except Exception as e:
                logger.error("api %s failed: %s", method, e)
                result = {"ok": False, "error": str(e)}
            if mid is not None:
                self._resolve(mid, result)
        threading.Thread(target=work, daemon=True).start()

    def _resolve(self, mid, result):
        payload = json.dumps(result, default=str)
        js = "window.__flumeResolve(%d, %s);" % (mid, json.dumps(payload))
        self._eval(js)

    def _emit(self, event, payload):
        self._eval("window.VerbalNative(%s, %s);" % (json.dumps(event), json.dumps(payload, default=str)))

    def _eval(self, js):
        if not self._webview:
            return
        def run():
            try:
                self._webview.evaluateJavaScript_completionHandler_(js, None)
            except Exception as e:
                logger.debug("evaluateJS failed: %s", e)
        # WKWebView must be touched on the main thread.
        try:
            self.app._on_main(run)
        except Exception:
            run()

    # ── events the app calls (same interface as the old dashboard) ──────────────
    def update_recording_state(self, is_recording):
        self._emit("recordingState", {"recording": bool(is_recording)})

    def show_result(self, text):
        self._emit("result", {"text": text})

    def _on_tab_select(self, idx):
        TAB = {0: "history", 1: "history", 2: "home", 3: "settings", 4: "canvas", 5: "notes", 6: "home"}
        self._emit("selectTab", {"tab": TAB.get(idx, "home")})

    def _refresh(self):
        try:
            self._emit("state", self._api.get_state())
        except Exception as e:
            logger.debug("refresh failed: %s", e)

    # ── device presence (mirrors shared_dashboard) ──────────────────────────────
    def _device_refresh_loop(self):
        import time
        while self._window is not None:
            try:
                self._load_devices()
            except Exception as e:
                logger.debug("device refresh failed: %s", e)
            time.sleep(30)

    def _load_devices(self):
        cfg = self.app.config
        user_id = cfg.get("sync_user_id", "")
        if not user_id or not getattr(self.app, "_sync", None):
            return
        try:
            from app.sync import fetch_devices
            device_id = self.app._sync.device_id if self.app._sync else ""
            self._known_devices = fetch_devices(user_id, device_id) or []
            self._refresh()
        except Exception as e:
            logger.debug("fetch_devices failed: %s", e)
