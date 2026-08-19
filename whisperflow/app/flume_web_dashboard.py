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
from app.shared_dashboard import DashboardApi, _cloud_allowed

logger = logging.getLogger("verbal.flumeweb")

_DELEGATE_CLS = None


def _delegate_class():
    """windowWillClose_ hands activation policy back to Accessory (menu-bar-only,
    no Dock icon) — see the comment on `setActivationPolicy_` in `show()` for why
    this matters: a Regular-policy app's floating panels (the recording overlay,
    autolearn pill, Transform preview) do NOT reliably stay visible over ANOTHER
    app's full-screen Space, even with the right NSWindowCollectionBehavior set.
    Without reverting this on close, the very first time a user opens the
    dashboard (main.py calls dashboard.show() at every launch) silently
    degrades the overlay for the rest of the session — reported as "the
    recording pill doesn't show up over full-screen apps"."""
    global _DELEGATE_CLS
    if _DELEGATE_CLS is None:
        class _FlumeDashboardDelegate(objc.lookUpClass("NSObject")):
            def windowWillClose_(self, note):
                try:
                    NSApplication.sharedApplication().setActivationPolicy_(1)  # Accessory
                except Exception as e:
                    logger.debug("revert activation policy failed: %s", e)

        _DELEGATE_CLS = _FlumeDashboardDelegate
    return _DELEGATE_CLS

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
// The page bootstraps off pywebview's `pywebviewready` event. Under WKWebView
// nothing ever fired it, so the first paint relied entirely on a blind 400ms
// setTimeout — slow machines flashed an empty shell, fast ones loaded twice
// (IDI-167). This shim IS the bridge, and it exists the instant this script
// runs, so announce it for real. Injected at document-start, hence the
// DOMContentLoaded hop: the page's own listener isn't registered yet.
(function(){
  var fire = function(){
    try { window.dispatchEvent(new Event('pywebviewready')); }
    catch(e) {
      var ev = document.createEvent('Event');
      ev.initEvent('pywebviewready', false, false);
      window.dispatchEvent(ev);
    }
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', fire);
  } else {
    setTimeout(fire, 0);
  }
})();
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

    # 2026-08-17 (user feedback, corrected): WIDE by default — the old 980
    # width felt cramped and hid the Notes Studio pane (collapses under
    # 1000px); the two-pane Canvas and three-pane History/Notes want the
    # horizontal room. Height stays modest; both clamped to the visible
    # screen in _build so small displays still fit.
    WIN_W, WIN_H = 1280, 760

    def __init__(self, app):
        self.app = app
        self._window = None
        self._webview = None
        self._bridge = None
        self._delegate = None
        self._api = DashboardApi(self)
        self._ready = False
        # MER-46: events emitted before the page installed VerbalNative used to
        # evaporate. `open_meeting` can now show() a window and push into it in
        # the same breath (the meeting bar's handoff), so queue until the page's
        # `dashboard_page_ready` handshake — same contract as MeetingWindow.
        self._page_ready = False
        self._pending = []
        self._canvas_stop = threading.Event()
        # attributes DashboardApi reads:
        self._known_devices = []
        try:
            self._target_device_id = app.config.get("sync_target_device_id", "__all__") or "__all__"
        except Exception:
            self._target_device_id = "__all__"

    # ── window ────────────────────────────────────────────────────────────────
    def show(self):
        # Regular (0) activation policy makes this normal titled window
        # Cmd+Tab/Dock reachable like a real app while it's open — but it must
        # be reverted to Accessory (1) when the window closes (the delegate's
        # windowWillClose_ does that), or every floating panel's
        # full-screen-Space visibility silently degrades for the rest of the
        # session. See _delegate_class()'s docstring.
        NSApplication.sharedApplication().setActivationPolicy_(0)
        if self._window and self._window.isVisible():
            self._window.makeKeyAndOrderFront_(None)
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            return
        if self._window is None:
            self._build()
        self._window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def ensure_window_size(self, min_w, min_h=0):
        """Grow (never shrink) the window's CONTENT area to at least
        min_w × min_h points, animated, clamped to the screen's visible frame,
        keeping the top-left corner anchored. Called by DashboardApi when the
        Notes screen needs its Studio column (CSS hides it under 1000px, and
        the default window is 980 wide). Main-thread via _on_main; fail-closed."""
        def run():
            try:
                win = self._window
                if win is None:
                    return
                content = win.contentView().frame().size
                new_w = max(float(content.width), float(min_w or 0))
                new_h = max(float(content.height), float(min_h or 0))
                if new_w == content.width and new_h == content.height:
                    return
                fr = win.frame()
                dw = new_w - content.width
                dh = new_h - content.height
                x = fr.origin.x
                y = fr.origin.y - dh          # grow downward, keep the top edge
                w = fr.size.width + dw
                h = fr.size.height + dh
                scr = win.screen() or NSScreen.mainScreen()
                if scr is not None:
                    vf = scr.visibleFrame()
                    w = min(w, vf.size.width)
                    h = min(h, vf.size.height)
                    if x + w > vf.origin.x + vf.size.width:
                        x = vf.origin.x + vf.size.width - w
                    if x < vf.origin.x:
                        x = vf.origin.x
                    if y < vf.origin.y:
                        y = vf.origin.y
                win.setFrame_display_animate_(NSMakeRect(x, y, w, h), True, True)
            except Exception as e:
                logger.debug("ensure_window_size failed: %s", e)
        self.app._on_main(run)

    def _build(self):
        from WebKit import (
            WKWebView, WKWebViewConfiguration, WKUserContentController,
            WKUserScript,
        )
        WKUserScriptInjectionTimeAtDocumentStart = 0

        screen = NSScreen.mainScreen()
        sf = screen.frame() if screen else NSMakeRect(0, 0, 1440, 900)
        # Clamp the taller default to the actual screen (menu bar + margin),
        # so a 900-high display still gets a fully visible window.
        try:
            vf = screen.visibleFrame() if screen else sf
            win_w = min(self.WIN_W, int(vf.size.width) - 40)
            win_h = min(self.WIN_H, int(vf.size.height) - 24)
        except Exception:
            win_w, win_h = self.WIN_W, self.WIN_H
        x = (sf.size.width - win_w) / 2
        y = (sf.size.height - win_h) / 2
        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                 NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, win_w, win_h), style, NSBackingStoreBuffered, False)
        self._window.setTitle_("Flume")
        self._window.setMinSize_(NSMakeSize(760, 520))
        self._window.setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(14/255, 16/255, 18/255, 1.0))
        self._delegate = _delegate_class().alloc().init()
        self._window.setDelegate_(self._delegate)

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
        self._page_ready = False    # fresh page — wait for its handshake

        # keep the sidebar device list fresh
        threading.Thread(target=self._device_refresh_loop, daemon=True).start()
        # realtime canvas updates from other devices
        threading.Thread(target=self._canvas_listen_loop, daemon=True).start()

    # ── realtime canvas (WS) ─────────────────────────────────────────────────────
    def _canvas_listen_loop(self):
        import time
        # Stop-checked every iteration: `_canvas_stop` (explicit shutdown) OR
        # the window going away.
        while self._window is not None and not self._canvas_stop.is_set():
            try:
                self._canvas_listen_once()
            except Exception as e:
                logger.debug("canvas listener failed: %s", e)
            self._canvas_stop.wait(5)

    def stop_canvas_listener(self):
        self._canvas_stop.set()

    def _canvas_listen_once(self):
        import time
        from app.shared_dashboard import canvas_is_own_event, device_identity
        cfg = self.app.config
        user_id = cfg.get("sync_user_id", "")
        my_device_id, my_device_name = device_identity(self.app)
        # Canvas is "sync" (IDI-171): the user toggle gates it, and being
        # SIGNED IN gates it again — `sync_user_id` alone used to survive
        # sign-out and kept a realtime channel open on the ex-account.
        if (not user_id or not cfg.get("sync_enabled") or not _cloud_allowed(cfg)
                or self._canvas_stop.is_set()):
            time.sleep(5)
            return
        import websocket
        from app.sync import SUPABASE_KEY, WS_URL
        from app.auth import get_access_token

        def on_open(ws):
            ws.send(json.dumps({
                "topic": "realtime:*", "event": "phx_join",
                "payload": {"config": {"postgres_changes": [
                    {"event": "*", "schema": "public", "table": "canvas",
                     "filter": f"user_id=eq.{user_id}"}]},
                    "access_token": get_access_token(self.app.config) or SUPABASE_KEY},
                "ref": "flume_canvas"}))

        def on_message(ws, raw):
            try:
                msg = json.loads(raw)
                if msg.get("event") != "postgres_changes":
                    return
                rec = msg.get("payload", {}).get("data", {}).get("record", {})
                # IDI-173: own-write filtering is by stable device_id (two Macs
                # both called "MacBook Pro" used to swallow each other's
                # updates); the name compare survives only as the fallback for
                # rows written before the column existed.
                if canvas_is_own_event(rec, my_device_id, my_device_name):
                    return
                # NOTE: empty content is APPLIED, not dropped — an explicit
                # clear from another device has to actually clear this one.
                self._emit("canvasRemote", {
                    "content": rec.get("content", "") or "",
                    "image_url": rec.get("image_url"),
                    "device_name": rec.get("device_name", "device"),
                })
            except Exception as e:
                logger.debug("canvas msg ignored: %s", e)

        ws_token = get_access_token(self.app.config) or SUPABASE_KEY
        ws = websocket.WebSocketApp(
            WS_URL, header={"Authorization": f"Bearer {ws_token}"},
            on_open=on_open, on_message=on_message)
        ws.run_forever(ping_interval=25, ping_timeout=10)

    # ── native image helpers (WKWebView can't do JS file-pick / image-paste) ─────
    def pick_image_native(self):
        """Open a native NSOpenPanel (on the main thread) and return
        {"path": ...} | {"cancelled": True} | {"error": ...}."""
        box = {}
        done = threading.Event()

        def run():
            try:
                from AppKit import NSOpenPanel
                panel = NSOpenPanel.openPanel()
                panel.setCanChooseFiles_(True)
                panel.setCanChooseDirectories_(False)
                panel.setAllowsMultipleSelection_(False)
                panel.setAllowedFileTypes_(["png", "jpg", "jpeg", "webp", "gif"])
                if int(panel.runModal()) == 1:  # NSModalResponseOK
                    urls = panel.URLs()
                    if urls and len(urls):
                        box["path"] = urls[0].path()
                    else:
                        box["cancelled"] = True
                else:
                    box["cancelled"] = True
            except Exception as e:
                box["error"] = str(e)
            finally:
                done.set()

        self.app._on_main(run)
        done.wait(180)
        return box

    def clipboard_image_native(self):
        """Read an image from the macOS clipboard (NSPasteboard). Returns
        {"bytes": ..., "ext": "png"} | {} | {"error": ...}."""
        box = {}
        done = threading.Event()

        def run():
            try:
                from AppKit import (
                    NSPasteboard, NSPasteboardTypePNG, NSPasteboardTypeTIFF,
                    NSBitmapImageRep, NSBitmapImageFileTypePNG,
                )
                pb = NSPasteboard.generalPasteboard()
                data = pb.dataForType_(NSPasteboardTypePNG)
                if data is None:
                    tiff = pb.dataForType_(NSPasteboardTypeTIFF)
                    if tiff is not None:
                        rep = NSBitmapImageRep.imageRepWithData_(tiff)
                        if rep is not None:
                            data = rep.representationUsingType_properties_(
                                NSBitmapImageFileTypePNG, {})
                if data is not None:
                    box["bytes"] = bytes(data)
                    box["ext"] = "png"
            except Exception as e:
                box["error"] = str(e)
            finally:
                done.set()

        self.app._on_main(run)
        done.wait(30)
        return box

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
        if not self._webview:
            return          # never built — dropping is still correct (as before)
        if not self._page_ready:
            self._pending.append((event, payload))
            if len(self._pending) > 200:        # bound the buffer
                self._pending = self._pending[-200:]
            return
        self._eval("window.VerbalNative && window.VerbalNative(%s, %s);" % (
            json.dumps(event), json.dumps(payload, default=str)))

    def page_ready(self):
        """Called (via the bridge) when the page JS has installed VerbalNative."""
        self._page_ready = True
        pending, self._pending = self._pending, []
        for event, payload in pending:
            self._emit(event, payload)

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
        # List devices whenever SIGNED IN — do NOT gate on the live SyncClient.
        # A signed-in Mac with sync toggled off still has an account and must show
        # its other devices (and itself must show online to them), or the two apps
        # never see each other. (Was: `not user_id or not self.app._sync` → empty.)
        if not user_id or not _cloud_allowed(cfg):
            self._known_devices = []
            self._refresh()
            return
        try:
            from app.sync import fetch_account_devices
            from app.config import get_device_id
            my_id = (self.app._sync.device_id if getattr(self.app, "_sync", None)
                     else get_device_id(self.app.config))
            # NOTE: the presence heartbeat used to live HERE, inside a loop
            # conditioned on `while self._window is not None` — so closing the
            # dashboard made this Mac go Offline to every other device within
            # ~5 min. It now runs app-level in `main._presence_loop` (IDI-177);
            # this loop only REFRESHES the list.
            # ALL account devices (online + offline), not just the last-5-min set.
            self._known_devices = fetch_account_devices(user_id, my_id) or []
            self._refresh()
        except Exception as e:
            logger.debug("load_devices failed: %s", e)
