"""
Flume recording overlay — a floating, non-activating panel hosting the Flume
overlay HTML (Recording → Transcribing → Done) in a WKWebView.

Keeps the OverlayBar interface main.py already uses (setup / show /
update_status / show_briefly / hide / visible) and derives the rich UI data
(device name, elapsed seconds, word count) from those calls, so main.py needs
no changes beyond passing the app reference.

Interactive: the pill's buttons (stop / cancel / pause / copy again) post back
through the pywebview bridge to methods here, which hop to the app on the main
thread. The panel is non-activating so clicking it never steals key focus from
the app you're dictating into.

Sound effects are unchanged — they live in main.py (play_start/stop/done).
"""
import logging
import re
import time

from AppKit import (
    NSPanel, NSColor,
    NSWindowStyleMaskBorderless,
    NSScreen, NSBackingStoreBuffered, NSScreenSaverWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
)
from Foundation import NSMakeRect

from app import theme as _theme  # noqa: F401 — registers Geist/JBM for WKWebView
from app.overlay_html import overlay_html

logger = logging.getLogger("verbal.overlay")

# Generously larger than the widest pill + its drop-shadow. The panel is
# transparent, so the extra area is invisible — it just stops the pill's rounded
# corners / shadow from being clipped at the panel edges.
PANEL_W = 720
PANEL_H = 150

_OVERLAY_ACTIONS = {"overlay_stop", "overlay_cancel", "overlay_pause",
                    "overlay_copy", "overlay_dismiss", "overlay_ready"}

# Statuses that must NOT render as a success pill. Used only as a backstop —
# main.py passes `error=True` explicitly (see update_status).
_ERROR_HINTS = ("no speech", "failed", "error", "couldn't", "could not", "unable")


class OverlayBar:
    def __init__(self, app=None):
        self.app = app
        self._window = None
        self._webview = None
        self._bridge = None
        self._visible = False
        self._ready = False
        self._t0 = 0.0  # record start (for elapsed seconds)
        # Emits made before the page's JS installs window.VerbalOverlay are
        # BUFFERED and flushed on the `overlay_ready` handshake — otherwise a
        # record-at-launch shows no pill at all (the eval silently no-ops).
        self._page_ready = False
        self._pending = []

    # ── device-name helpers ───────────────────────────────────────────────────
    def _this_device(self):
        try:
            return (self.app.config.get("sync_device_name") or "").strip() or "MAC"
        except Exception:
            return "MAC"

    def _target_device(self):
        """Name of the currently selected send-target, or this device if local."""
        try:
            dash = getattr(self.app, "dashboard", None)
            tid = getattr(dash, "_target_device_id", "__all__") if dash else "__all__"
            if tid in (None, "", "__all__", "__none__"):
                return self._this_device()
            for d in getattr(dash, "_known_devices", []) or []:
                if d.get("device_id") == tid:
                    return d.get("device_name") or self._this_device()
        except Exception:
            pass
        return self._this_device()

    # ── window / webview ──────────────────────────────────────────────────────
    def setup(self):
        screen = NSScreen.mainScreen()
        if not screen:
            return
        sf = screen.frame()
        x = (sf.size.width - PANEL_W) / 2
        y = 40

        NSNonactivatingPanelMask = 1 << 7
        self._window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, PANEL_W, PANEL_H),
            NSWindowStyleMaskBorderless | NSNonactivatingPanelMask,
            NSBackingStoreBuffered, False)
        self._window.setLevel_(NSScreenSaverWindowLevel)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setHasShadow_(False)
        self._window.setIgnoresMouseEvents_(False)  # buttons need clicks
        self._window.setFloatingPanel_(True)
        self._window.setBecomesKeyOnlyIfNeeded_(True)
        self._window.setHidesOnDeactivate_(False)
        # Stage Manager opt-outs: without .auxiliary + .canJoinAllApplications the
        # panel gets swept into the side strip and every click looks dead
        # (same recipe as meeting_window.py).
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | (1 << 17)   # NSWindowCollectionBehaviorAuxiliary
            | (1 << 18))  # NSWindowCollectionBehaviorCanJoinAllApplications

        try:
            self._build_webview()
        except Exception as e:
            logger.error("overlay webview build failed: %s", e)

    def _build_webview(self):
        from WebKit import (
            WKWebViewConfiguration, WKUserContentController, WKUserScript,
        )
        from app.flume_web_dashboard import _Bridge, _SHIM
        from app.meeting_window import _webview_class   # acceptsFirstMouse (Rule #18)

        ucc = WKUserContentController.alloc().init()
        self._bridge = _Bridge.alloc().initWithDashboard_(self)
        ucc.addScriptMessageHandler_name_(self._bridge, "flume")
        ucc.addUserScript_(
            WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(_SHIM, 0, True))

        config = WKWebViewConfiguration.alloc().init()
        config.setUserContentController_(ucc)

        rect = NSMakeRect(0, 0, PANEL_W, PANEL_H)
        self._webview = _webview_class().alloc().initWithFrame_configuration_(rect, config)
        self._webview.setAutoresizingMask_(0x02 | 0x10)
        # Make the web view fully transparent so only the CSS pill shows (no dark
        # square backing behind the rounded corners).
        try:
            self._webview.setValue_forKey_(False, "drawsBackground")
        except Exception:
            pass
        try:
            self._webview.setOpaque_(False)
        except Exception:
            pass
        try:
            from AppKit import NSColor as _NSColor
            self._webview.setWantsLayer_(True)
            self._webview.layer().setBackgroundColor_(_NSColor.clearColor().CGColor())
            self._webview.layer().setOpaque_(False)
        except Exception:
            pass
        self._page_ready = False
        self._webview.loadHTMLString_baseURL_(overlay_html(), None)
        self._window.setContentView_(self._webview)
        self._ready = True
        # Fail-open backstop: if the page never reports ready (load failure), stop
        # buffering after a few seconds so the overlay degrades to its old
        # best-effort behaviour instead of going permanently silent.
        import threading

        def _unblock():
            if self._page_ready:
                return
            if self.app:
                self.app._on_main(self.overlay_ready)
            else:
                self.overlay_ready()
        threading.Timer(3.0, _unblock).start()

    def _order_front(self):
        if not self._window:
            self.setup()
        self._window.orderFrontRegardless()
        self._visible = True

    def _push(self, mode, data=None):
        import json
        if not self._page_ready:
            self._pending.append((mode, data))
            if len(self._pending) > 20:          # bound the buffer
                self._pending = self._pending[-20:]
            return
        js = "if(window.VerbalOverlay)window.VerbalOverlay(%s, %s);" % (
            json.dumps(mode), json.dumps(data or {}))
        if self._webview:
            try:
                self._webview.evaluateJavaScript_completionHandler_(js, None)
            except Exception as e:
                logger.debug("overlay eval failed: %s", e)

    def overlay_ready(self):
        """Page-load handshake — flush emits made while the page was loading."""
        if self._page_ready:
            return
        self._page_ready = True
        pending, self._pending = self._pending, []
        for mode, data in pending:
            self._push(mode, data)

    # ── interface used by main.py ─────────────────────────────────────────────
    def _cancel_autohide(self):
        self._done_token = getattr(self, "_done_token", 0) + 1

    def show(self, status="Listening…"):
        self._cancel_autohide()
        self._order_front()
        self._t0 = time.time()
        self._push("recording", {"device": self._this_device()})

    def update_status(self, status, error=False):
        """`error=True` renders the failure pill (no ✓, no "Copy again")."""
        if not self._window:
            return
        self._cancel_autohide()
        if not error and status and "Transcrib" in status and "fail" not in status.lower():
            secs = int(max(0, time.time() - self._t0)) if self._t0 else 0
            self._push("transcribing", {
                "src": self._this_device(), "dst": self._target_device(), "secs": secs})
            return
        self._order_front()
        text = (status or "").strip()
        if error or self._looks_like_error(text):
            # Never show the success checkmark or a "Copy again" CTA here — the
            # CTA would copy the PREVIOUS dictation's text.
            self._push("error", {"label": self._strip_glyphs(text) or "Something went wrong",
                                 "state": "Failed"})
        else:
            self._push("done", {"label": text, "meta": ""})

    @staticmethod
    def _looks_like_error(status):
        low = (status or "").lower()
        return any(h in low for h in _ERROR_HINTS)

    @staticmethod
    def _strip_glyphs(status):
        # The pill has its own "!" disc — drop any leading warning emoji.
        return re.sub(r"^[\s⚠️❗❌✖]+", "", status or "").strip()

    def show_briefly(self, status, duration=2.0):
        self._order_front()
        secs = int(max(0, time.time() - self._t0)) if self._t0 else 0
        m = re.search(r"(\d+)\s*w", status or "", re.I)
        words = m.group(1) if m else ""
        if status and status.lower().startswith("pasted"):
            label = f"Pasted to {self._this_device()}"
        elif status and "clipboard" in status.lower():
            label = "Copied to clipboard"
        else:
            label = status or "Done"
        meta = (f"{words}W · {secs}S" if words else f"{secs}S")
        self._push("done", {"label": label, "meta": meta})
        # auto-dismiss the Done pill after `duration` (unless replaced sooner)
        self._done_token = getattr(self, "_done_token", 0) + 1
        token = self._done_token
        import threading
        def _auto_hide():
            if getattr(self, "_done_token", None) != token:
                return
            if self.app:
                self.app._on_main(self.hide)
            else:
                self.hide()
        threading.Timer(max(0.5, float(duration or 2.0)), _auto_hide).start()

    def hide(self):
        self._push("hide")
        if self._window:
            self._window.orderOut_(None)
        self._visible = False

    @property
    def visible(self):
        return self._visible

    def cleanup(self):
        if self._window:
            try:
                self._window.orderOut_(None)
            except Exception:
                pass

    # ── bridge dispatch (button clicks from the pill) ─────────────────────────
    def _dispatch(self, mid, method, args):
        if method in _OVERLAY_ACTIONS:
            try:
                getattr(self, method)()
            except Exception as e:
                logger.error("overlay action %s failed: %s", method, e)

    def _resolve(self, mid, result):
        pass  # overlay actions are fire-and-forget

    # ── button actions ────────────────────────────────────────────────────────
    def overlay_stop(self):
        if self.app:
            self.app._on_main(lambda: self.app._toggle_recording(None))

    def overlay_cancel(self):
        """Cancel — must behave EXACTLY like the ESC key.

        Routing straight to `_cancel_recording` was a no-op while TRANSCRIBING:
        it never set `_cancel_flag`, and `_reset_to_ready` cleared it, so the
        in-flight transcription completed and still pasted into the focused app.
        `_on_esc_pressed` is the one path that sets the flag BEFORE any reset, so
        we delegate to it (it is also called off the main thread by the hotkey
        listener and hops to main itself).
        """
        app = self.app
        if not app:
            self.hide()
            return
        esc = getattr(app, "_on_esc_pressed", None)
        if callable(esc):
            try:
                esc()
            except Exception as e:
                logger.error("overlay cancel failed: %s", e)
            # ESC is a no-op when neither recording nor processing (e.g. the Done
            # pill lingering) — don't leave a dead pill on screen.
            if not getattr(app, "_processing", False) and not getattr(app, "_is_recording", False):
                app._on_main(self.hide)
            return
        if hasattr(app, "_cancel_recording"):
            app._on_main(app._cancel_recording)
        else:
            app._on_main(self.hide)

    def overlay_pause(self):
        rec = getattr(self.app, "recorder", None)
        if not (rec and hasattr(rec, "toggle_pause")):
            return
        try:
            paused = bool(rec.toggle_pause())
        except Exception as e:
            logger.error("overlay pause failed: %s", e)
            return
        # Reflect it on the pill: flip the icon and FREEZE the elapsed timer
        # (audio stops accruing, so a ticking clock drifts from reality).
        self._push("paused", {"paused": paused})

    def overlay_copy(self):
        text = getattr(self.app, "_last_result_text", "") if self.app else ""
        if text:
            try:
                import pyperclip
                pyperclip.copy(text)
            except Exception as e:
                logger.debug("overlay copy failed: %s", e)

    def overlay_dismiss(self):
        if self.app:
            self.app._on_main(self.hide)
        else:
            self.hide()
