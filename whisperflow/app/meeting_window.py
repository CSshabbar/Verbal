"""
Meetings — ONE morphing surface (MEETINGS_DESIGN_HANDOFF.md 31c/31d/31e/31h).

Two layouts of the SAME panel + WKWebView, animated between with native frame
animation (NSAnimationContext):

  bar       — a compact, glassy pill top-center (like the dictation overlay):
              live dot · title · timer · waveform · quick actions. Borderless,
              NON-ACTIVATING, all-spaces, floats above fullscreen apps. Click →
              expands.
  expanded  — the full meeting window (premeeting/live/summary/permissions).
              The styleMask flips to titled+fullSizeContentView with a hidden
              titlebar, so drag/resize/traffic-lights are native. Closing while
              recording COLLAPSES to the bar instead of closing (delegate).

While recording, losing key focus auto-collapses to the bar (this superseded the
old separate meeting HUD, deleted in IDI-179). Python → JS: window.VerbalMeeting; the
extra 'layout' event ('bar'|'expanded') drives the CSS morph.

Rules honored: all AppKit on the main thread via app._on_main (Rule #4);
everything fails closed (Rule #1); the ObjC delegate class registers ONCE per
process (05-conventions Rule #18 lesson).
"""
import json
import logging
import time

from AppKit import (
    NSPanel, NSScreen, NSBackingStoreBuffered, NSApplication, NSColor,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskBorderless, NSWindowStyleMaskFullSizeContentView,
    NSScreenSaverWindowLevel, NSNormalWindowLevel, NSFloatingWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSAnimationContext,
)
from Foundation import NSMakeRect, NSMakeSize

from app import theme as _theme  # noqa: F401 — registers Geist/JBM for WKWebView
from app.meeting_html import meeting_html

logger = logging.getLogger("verbal.meetingwin")

NSNonactivatingPanelMask = 1 << 7

BAR_W, BAR_H = 560, 54   # must comfortably fit: dot·title·wave·timer·PAUSED tag·4 buttons —
# the previous 500 only accounted for 3 buttons and never the PAUSED tag, so the
# widest real state (paused, with cancel added) clipped the last button (Rule #56).
WIN_W, WIN_H = 880, 620
MIN_W, MIN_H = 700, 480

# ── window delegate (registered ONCE — Rule #18 lesson) ─────────────────────────
_DELEGATE_CLS = None


def _delegate_class():
    global _DELEGATE_CLS
    if _DELEGATE_CLS is None:
        import objc

        class _FlumeMeetingWinDelegate(objc.lookUpClass("NSObject")):
            def windowShouldClose_(self, sender):
                ctl = getattr(self, "_ctl", None)
                try:
                    if ctl and ctl._recording_active():
                        ctl.set_layout("bar")   # closing mid-meeting → collapse
                        return False
                except Exception:
                    pass
                return True

            def windowDidResignKey_(self, note):
                ctl = getattr(self, "_ctl", None)
                try:
                    if ctl:
                        ctl._on_resign_key()
                except Exception:
                    pass

        _DELEGATE_CLS = _FlumeMeetingWinDelegate
    return _DELEGATE_CLS


# WKWebView subclass that acts on the FIRST click even when its panel is not
# key. Stock WKWebView reports needsPanelToBecomeKey=YES, so the click a user
# makes coming from another app is swallowed by the key-transfer ceremony —
# buttons feel completely dead. Registered ONCE (Rule #18).
_WEBVIEW_CLS = None


def _webview_class():
    global _WEBVIEW_CLS
    if _WEBVIEW_CLS is None:
        from WebKit import WKWebView

        class _FlumeMeetingWebView(WKWebView):
            def acceptsFirstMouse_(self, event):
                return True

        _WEBVIEW_CLS = _FlumeMeetingWebView
    return _WEBVIEW_CLS


class MeetingWindow:
    """Duck-types the `dashboard` interface DashboardApi expects."""

    def __init__(self, app):
        self.app = app
        self._window = None
        self._webview = None
        self._bridge = None
        self._delegate = None
        self._ui_delegate = None
        self._api = None
        self._layout = "expanded"       # 'bar' | 'expanded'
        # Events emitted before the page's JS is ready are BUFFERED and flushed
        # on the page's ready handshake — otherwise opening a meeting into a
        # fresh window loses the mode/meeting events ("click does nothing").
        self._page_ready = False
        self._pending = []
        self._known_devices = []
        try:
            self._target_device_id = app.config.get("sync_target_device_id", "__all__") or "__all__"
        except Exception:
            self._target_device_id = "__all__"
        # Hover→reveal for the short bar (title/waveform/quick-actions), same
        # recipe as overlay.py: a global mouse monitor, because CSS :hover never
        # fires for a background, non-activating panel (05-conventions Rule #40).
        # Only runs while the layout is 'bar' — see set_layout()/_on_resign_key().
        self._hover_mon = None
        self._hover_t = 0.0
        self._hover_inside = False

    # ── helpers ───────────────────────────────────────────────────────────────
    def _recording_active(self):
        try:
            m = getattr(self.app, "meetings", None)
            # `processing` (IDI-178): the summary is still generating after Stop —
            # the red X collapses to the bar instead of closing, same as while
            # recording, so the "still finishing your notes" work stays visible.
            return bool(m and (m.active or getattr(m, "processing", False)))
        except Exception:
            return False

    def _screen_frame(self):
        screen = NSScreen.mainScreen()
        return screen.visibleFrame() if screen else NSMakeRect(0, 0, 1440, 860)

    def _bar_rect(self):
        sf = self._screen_frame()
        x = sf.origin.x + (sf.size.width - BAR_W) / 2
        y = sf.origin.y + sf.size.height - BAR_H - 12   # top-center, under menubar
        return NSMakeRect(x, y, BAR_W, BAR_H)

    def _expanded_rect(self):
        sf = self._screen_frame()
        x = sf.origin.x + (sf.size.width - WIN_W) / 2
        y = sf.origin.y + (sf.size.height - WIN_H) / 2
        return NSMakeRect(x, y, WIN_W, WIN_H)

    # ── show / build ──────────────────────────────────────────────────────────
    def show(self, mode="premeeting"):
        """Open (or focus) the surface in a CONTENT mode; content modes other
        than live always present expanded."""
        try:
            if self._window is None:
                self._build()
            self.set_layout("expanded", animate=self._window.isVisible())
            # Never activate the app and never take key eagerly: under Stage
            # Manager either one gets the panel adopted and parked off-screen.
            # orderFrontRegardless + becomesKeyOnlyIfNeeded is the exact recipe
            # the recording widget and the bar use — neither is ever swept.
            self._window.orderFrontRegardless()
            self.set_mode(mode)
        except Exception as e:
            logger.error("meeting window show failed: %s", e)

    def _build(self):
        from WebKit import (
            WKWebView, WKWebViewConfiguration, WKUserContentController,
            WKUserScript,
        )
        from app.flume_web_dashboard import _Bridge, _SHIM, _ui_delegate_class
        from app.shared_dashboard import DashboardApi

        self._api = DashboardApi(self)

        self._window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            self._expanded_rect(), self._expanded_mask(), NSBackingStoreBuffered, False)
        self._window.setReleasedWhenClosed_(False)
        self._window.setMinSize_(NSMakeSize(MIN_W, MIN_H))
        self._window.setTitle_("Meeting")
        self._apply_expanded_chrome()

        self._delegate = _delegate_class().alloc().init()
        self._delegate._ctl = self
        self._window.setDelegate_(self._delegate)

        ucc = WKUserContentController.alloc().init()
        self._bridge = _Bridge.alloc().initWithDashboard_(self)
        ucc.addScriptMessageHandler_name_(self._bridge, "flume")
        ucc.addUserScript_(
            WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
                _SHIM, 0, True))
        config = WKWebViewConfiguration.alloc().init()
        config.setUserContentController_(ucc)

        cr = self._window.contentView().bounds()
        self._webview = _webview_class().alloc().initWithFrame_configuration_(cr, config)
        self._webview.setAutoresizingMask_(0x02 | 0x10)
        # Without a WKUIDelegate, WebKit resolves confirm() with the default —
        # FALSE, silently, with nothing drawn — which would make cancelMeeting()'s
        # confirm() gate a permanent no-op (same bug as flume_web_dashboard.py's
        # _ui_delegate_class() docstring; retained on self, since UIDelegate is
        # a weak reference).
        try:
            self._ui_delegate = _ui_delegate_class().alloc().init()
            self._webview.setUIDelegate_(self._ui_delegate)
        except Exception as e:
            logger.error("could not install JS dialog delegate: %s", e)
        for _ in (1,):
            try:
                self._webview.setValue_forKey_(False, "drawsBackground")
                self._webview.setOpaque_(False)
                self._webview.setWantsLayer_(True)
                self._webview.layer().setBackgroundColor_(NSColor.clearColor().CGColor())
            except Exception:
                pass
        self._window.contentView().addSubview_(self._webview)
        self._webview.loadHTMLString_baseURL_(meeting_html(), None)

    # ── layout morph (the fluid bit) ──────────────────────────────────────────
    def _expanded_mask(self):
        return (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable |
                NSWindowStyleMaskFullSizeContentView | NSNonactivatingPanelMask)

    def _bar_mask(self):
        return NSWindowStyleMaskBorderless | NSNonactivatingPanelMask

    def _apply_expanded_chrome(self):
        w = self._window
        try:
            w.setTitlebarAppearsTransparent_(True)
            w.setTitleVisibility_(1)                    # NSWindowTitleHidden
            # NEVER movable-by-background on a webview-filled window: AppKit
            # grabs mouseDown for window-drag before WebKit ever dispatches a
            # DOM click — buttons appear completely dead. Drag via titlebar.
            w.setMovableByWindowBackground_(False)
            w.setOpaque_(True)
            w.setBackgroundColor_(
                NSColor.colorWithCalibratedRed_green_blue_alpha_(14/255, 16/255, 18/255, 1.0))
            w.setHasShadow_(True)
            # Floating level + the bar's collection-behavior trio: a nonactivating
            # panel owned by a menubar app cannot hold "active app" status, so at
            # NSNormalWindowLevel Stage Manager sweeps it into the side strip the
            # moment another app activates — the window visibly flies away and
            # users read it as "the buttons are broken".
            w.setLevel_(NSFloatingWindowLevel)
            w.setFloatingPanel_(True)
            # Key only when the user clicks into a text field — taking key
            # status eagerly is what lets Stage Manager adopt (and then park)
            # the panel. The widget/bar never take key and are never swept.
            w.setBecomesKeyOnlyIfNeeded_(True)
            # macOS 13+ Stage Manager opt-out: .auxiliary (1<<17) marks the
            # window as a companion SM must not park in the side strip, and
            # .canJoinAllApplications (1<<18) lets it stay up alongside any
            # app's stage. Transient/Stationary alone did NOT stop SM from
            # sweeping the panel once a click made it key.
            w.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorFullScreenAuxiliary
                | (1 << 17)   # NSWindowCollectionBehaviorAuxiliary
                | (1 << 18))  # NSWindowCollectionBehaviorCanJoinAllApplications
            w.setHidesOnDeactivate_(False)
        except Exception as e:
            logger.debug("expanded chrome failed: %s", e)

    def _apply_bar_chrome(self):
        w = self._window
        try:
            w.setOpaque_(False)
            w.setBackgroundColor_(NSColor.clearColor())
            w.setHasShadow_(False)                      # the CSS pill has its own
            w.setLevel_(NSScreenSaverWindowLevel)
            w.setFloatingPanel_(True)
            w.setBecomesKeyOnlyIfNeeded_(True)          # buttons work, no focus theft
            w.setMovableByWindowBackground_(True)
            w.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorStationary
                | NSWindowCollectionBehaviorFullScreenAuxiliary)
            w.setHidesOnDeactivate_(False)
        except Exception as e:
            logger.debug("bar chrome failed: %s", e)

    def set_layout(self, layout, animate=True):
        """Morph between 'bar' and 'expanded' — main-thread only."""
        def run():
            try:
                if self._window is None:
                    return
                if layout == self._layout and self._window.isVisible():
                    return
                self._layout = layout
                if layout == "bar":
                    self._start_hover_monitor()
                else:
                    self._stop_hover_monitor()
                # tell the page first so the content cross-fades during the morph
                self._eval_now("if(window.VerbalMeeting)window.VerbalMeeting('layout', %s);"
                               % json.dumps({"layout": layout}))
                w = self._window
                if layout == "bar":
                    w.setStyleMask_(self._bar_mask())
                    self._apply_bar_chrome()
                    target = self._bar_rect()
                else:
                    w.setStyleMask_(self._expanded_mask())
                    self._apply_expanded_chrome()
                    target = self._expanded_rect()
                # a styleMask flip can rebuild the frame view — re-assert the
                # webview's transparency or a stale opaque backing shows as a
                # boxy artifact around the pill
                try:
                    self._webview.setValue_forKey_(False, "drawsBackground")
                    self._webview.setOpaque_(False)
                    self._webview.layer().setBackgroundColor_(NSColor.clearColor().CGColor())
                except Exception:
                    pass
                if animate and w.isVisible():
                    NSAnimationContext.beginGrouping()
                    try:
                        NSAnimationContext.currentContext().setDuration_(0.30)
                        w.animator().setFrame_display_(target, True)
                    finally:
                        NSAnimationContext.endGrouping()
                else:
                    w.setFrame_display_(target, True)
                try:
                    w.invalidateShadow()   # drop the stale expanded-window shadow
                except Exception:
                    pass
                w.orderFrontRegardless()   # never key/activate eagerly (Stage Manager)
            except Exception as e:
                logger.error("layout morph failed: %s", e)
        try:
            self.app._on_main(run)
        except Exception:
            run()

    def expand(self):
        self.set_layout("expanded")

    def collapse(self):
        if self._recording_active():
            self.set_layout("bar")

    # ── hover → reveal (short bar) ───────────────────────────────────────────
    def _start_hover_monitor(self):
        """Watch the cursor globally while the bar is up — see the note by
        `_hover_mon`'s declaration for why this can't just be CSS `:hover`."""
        if self._hover_mon is not None:
            return
        try:
            from AppKit import NSEvent
            NSEventMaskMouseMoved = 1 << 5
            NSEventMaskLeftMouseDragged = 1 << 7

            def _handler(ev):
                try:
                    self._on_global_mouse()
                except Exception:
                    pass      # a hover glitch must never touch the meeting

            self._hover_mon = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSEventMaskMouseMoved | NSEventMaskLeftMouseDragged, _handler)
        except Exception as e:
            logger.debug("bar hover monitor unavailable (%s); bar stays collapsed", e)

    def _stop_hover_monitor(self):
        mon, self._hover_mon = self._hover_mon, None
        if mon is None:
            return
        try:
            from AppKit import NSEvent
            NSEvent.removeMonitor_(mon)
        except Exception:
            pass
        self._hover_inside = False

    def _on_global_mouse(self):
        if self._layout != "bar" or not (self._window and self._webview):
            return
        from AppKit import NSEvent
        loc = NSEvent.mouseLocation()
        f = self._window.frame()
        x = loc.x - f.origin.x
        # AppKit screen coords are bottom-up; CSS is top-down.
        y = (f.origin.y + f.size.height) - loc.y
        inside = (0 <= x <= f.size.width) and (0 <= y <= f.size.height)
        if not inside:
            if self._hover_inside:
                self._hover_inside = False
                self._hover_js(-1, -1)
            return
        now = time.time()
        if self._hover_inside and (now - self._hover_t) < 0.04:
            return
        self._hover_t = now
        self._hover_inside = True
        self._hover_js(x, y)

    def _hover_js(self, x, y):
        js = "if(window.VerbalMeetingHover)window.VerbalMeetingHover(%.0f,%.0f);" % (x, y)
        try:
            self._webview.evaluateJavaScript_completionHandler_(js, None)
        except Exception as e:
            logger.debug("bar hover eval failed: %s", e)

    def _on_resign_key(self):
        """Recording + expanded + lost focus → become the ambient bar."""
        try:
            if (self._layout == "expanded" and self._recording_active()
                    and bool(self.app.config.get("meetings_hud_enabled", True))):
                self.set_layout("bar")
        except Exception:
            pass

    # ── JS bridge (same contract as FlumeWebDashboard) ───────────────────────────
    def _dispatch(self, mid, method, args):
        import threading

        def work():
            try:
                fn = getattr(self._api, method, None)
                result = fn(*args) if callable(fn) else {"ok": False, "error": "no method"}
            except Exception as e:
                logger.error("meeting api %s failed: %s", method, e)
                result = {"ok": False, "error": str(e)}
            if mid is not None:
                self._resolve(mid, result)
        threading.Thread(target=work, daemon=True).start()

    def _resolve(self, mid, result):
        payload = json.dumps(result, default=str)
        self._eval("window.__flumeResolve(%d, %s);" % (mid, json.dumps(payload)))

    def emit(self, event, payload):
        if not self._page_ready:
            self._pending.append((event, payload))
            if len(self._pending) > 200:        # bound the buffer
                self._pending = self._pending[-200:]
            return
        self._eval("if(window.VerbalMeeting)window.VerbalMeeting(%s, %s);" % (
            json.dumps(event), json.dumps(payload or {}, default=str)))

    def page_ready(self):
        """Called (via the bridge) when the page JS has installed VerbalMeeting."""
        self._page_ready = True
        pending, self._pending = self._pending, []
        for event, payload in pending:
            self.emit(event, payload)
        # re-assert the current layout so a freshly-loaded page matches the panel
        self.emit("layout", {"layout": self._layout})

    def set_mode(self, mode):
        self.emit("mode", {"mode": mode})
        if mode in ("premeeting", "permissions"):
            self.set_layout("expanded")

    def set_handoff(self, state, row):
        """Post-meeting handoff (MER-46).

        The panel no longer renders summaries — it collapses to the ambient bar
        ("Finishing notes…" while the summary generates, then "Notes ready →")
        and clicking that bar opens the meeting in the dashboard's detail view.
        Emit BEFORE the morph so the pill paints its handoff content during the
        frame animation rather than flashing the live layout."""
        try:
            self.emit("handoff", {"state": state,
                                  "id": (row or {}).get("id"),
                                  "title": (row or {}).get("title")})
            self.set_layout("bar")
        except Exception as e:
            logger.debug("meeting handoff failed: %s", e)

    def _eval_now(self, js):
        try:
            if self._webview:
                self._webview.evaluateJavaScript_completionHandler_(js, None)
        except Exception as e:
            logger.debug("meeting evalJS failed: %s", e)

    def _eval(self, js):
        if not self._webview:
            return
        try:
            self.app._on_main(lambda: self._eval_now(js))
        except Exception:
            self._eval_now(js)

    # ── state the app reads ───────────────────────────────────────────────────
    @property
    def visible(self):
        try:
            return bool(self._window and self._window.isVisible())
        except Exception:
            return False

    def hide(self):
        self._stop_hover_monitor()
        try:
            if self._window:
                self._window.orderOut_(None)
        except Exception:
            pass
