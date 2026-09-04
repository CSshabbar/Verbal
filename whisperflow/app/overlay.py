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
    NSApplication, NSEvent,
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

# Larger than the widest pill + its drop-shadow, so rounded corners and shadow
# are never clipped at the panel edge — but no larger. The panel is transparent
# yet still takes mouse events (the buttons need them, so
# setIgnoresMouseEvents_ is False), which means every pixel of it is a dead zone
# over whatever is underneath. 720×150 made that dead zone the width of a third
# of the screen; the Capsule (IDI-184) is ~124px at rest and ~215px expanded, so
# 440×96 covers the widest measured state — the Done pill with "Copy again"
# revealed, 313px — with room for the 32px shadow blur. That is 61% less
# transparent dead zone than 720×150.
PANEL_W = 440
PANEL_H = 96

_OVERLAY_ACTIONS = {"overlay_stop", "overlay_cancel", "overlay_pause",
                    "overlay_copy", "overlay_dismiss", "overlay_ready"}

# Spinner ticks per second while transcribing. The transcribing ring used to be
# a pure CSS `animation:spin`, which sat PERFECTLY STILL: this panel belongs to
# an accessory app that is never active, and a background WKWebView gets its
# animation timeline throttled (the same class of problem as :hover never firing
# — Rule #40). A JS-driven style change forces a repaint, which is exactly why
# the waveform never had this problem, so the spinner is now pushed too.
SPIN_HZ = 20
SPIN_DEG_PER_SEC = 420          # a touch faster than the old .8s/rev CSS

# Mic-level pushes per second while recording (drives the pill's waveform).
# The page interpolates between them at 30fps, so this only has to be fast
# enough to track speech envelope — not to look smooth on its own.
LEVEL_HZ = 15

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
        # True while we've temporarily dropped the app to Accessory policy so
        # the pill can show over another app's full-screen Space (see
        # _borrow_accessory_policy). Restored to Regular in hide().
        self._policy_borrowed = False
        # Emits made before the page's JS installs window.VerbalOverlay are
        # BUFFERED and flushed on the `overlay_ready` handshake — otherwise a
        # record-at-launch shows no pill at all (the eval silently no-ops).
        self._page_ready = False
        self._pending = []
        # Live-level pump (waveform). `_level_token` invalidates the running
        # thread; `_level_inflight` is backpressure so a stalled main thread
        # can never accumulate a queue of stale level evals.
        self._level_token = 0
        self._level_inflight = False
        # Hover→expand for the Capsule. CSS :hover is NOT enough here: macOS
        # delivers mouseMoved only to the ACTIVE app, and this panel belongs to a
        # background app by definition (you're typing in someone else's window),
        # so the pill would only ever expand on click. A global mouse monitor
        # sees the cursor regardless of which app is active; the page does the
        # hit-test against its own pill rect.
        self._hover_mon = None
        self._hover_t = 0.0
        self._hover_inside = False
        # Transcribing spinner pump — same shape as the level pump.
        self._spin_token = 0
        self._spin_inflight = False

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
    def _apply_panel_traits(self, win):
        """Everything that makes the panel float over every Space.

        Called at creation AND re-asserted on every order-front: after hours of
        uptime (full-screen Spaces created/destroyed, display sleep, the
        Regular↔Accessory policy flips of conventions #56), the WindowServer can
        silently shed a long-lived panel's level / collection behavior. That rot
        is invisible until the next show over a full-screen app — which is why
        it presented as "the pill stops appearing on full-screen apps until I
        restart". Re-applying is idempotent and costs nothing.
        """
        win.setLevel_(NSScreenSaverWindowLevel)
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.clearColor())
        win.setHasShadow_(False)
        win.setIgnoresMouseEvents_(False)  # buttons need clicks
        win.setFloatingPanel_(True)
        win.setBecomesKeyOnlyIfNeeded_(True)
        win.setHidesOnDeactivate_(False)
        # We close() stale panels in _heal_stale_panel; PyObjC must keep
        # ownership or that close would double-release.
        win.setReleasedWhenClosed_(False)
        # Stage Manager opt-outs: without .auxiliary + .canJoinAllApplications the
        # panel gets swept into the side strip and every click looks dead
        # (same recipe as meeting_window.py).
        win.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | (1 << 17)   # NSWindowCollectionBehaviorAuxiliary
            | (1 << 18))  # NSWindowCollectionBehaviorCanJoinAllApplications

    def _make_panel(self, rect):
        NSNonactivatingPanelMask = 1 << 7
        win = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            NSWindowStyleMaskBorderless | NSNonactivatingPanelMask,
            NSBackingStoreBuffered, False)
        self._apply_panel_traits(win)
        return win

    def _default_frame(self):
        screen = NSScreen.mainScreen()
        if not screen:
            return None
        sf = screen.frame()
        return NSMakeRect((sf.size.width - PANEL_W) / 2, 40, PANEL_W, PANEL_H)

    def setup(self):
        rect = self._default_frame()
        if rect is None:
            return
        self._window = self._make_panel(rect)

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

    # ── activation-policy borrow (full-screen Spaces) ────────────────────────
    @staticmethod
    def _cursor_screen_is_fullscreen_space():
        """Heuristic: the Space under the mouse has NO menu bar → a full-screen
        app is showing there (NSScreen.visibleFrame excludes the menu bar only
        while it's on screen). Auto-hidden menu bars trip this too; that's fine
        — the only cost of a false positive is the Dock icon blinking during the
        pill. Returns True on any error so we err toward showing the pill."""
        try:
            pt = NSEvent.mouseLocation()
            for sc in NSScreen.screens():
                f = sc.frame()
                if (f.origin.x <= pt.x <= f.origin.x + f.size.width
                        and f.origin.y <= pt.y <= f.origin.y + f.size.height):
                    vf = sc.visibleFrame()
                    top_gap = (f.origin.y + f.size.height) - (vf.origin.y + vf.size.height)
                    return top_gap < 1.0
        except Exception:
            pass
        return True

    def _borrow_accessory_policy(self):
        """A Regular-policy app's non-activating panels don't reliably appear
        over ANOTHER app's full-screen Space (conventions #56). The dashboard
        flips the app to Regular while it's open and reverts it on close /
        miniaturize / Cmd+H — but simply LEAVING the dashboard open on some
        other Space while dictating into a full-screen app fires none of those,
        so the pill silently vanished. Rather than hunt for a fourth event,
        borrow Accessory right here, at the moment the pill is ordered front,
        whenever our app isn't active and the target Space looks full-screen;
        hide() hands Regular back so Cmd+Tab/Dock keep working for the open
        dashboard. Fail-closed: any error leaves the policy untouched."""
        try:
            nsapp = NSApplication.sharedApplication()
            if nsapp.activationPolicy() != 0 or nsapp.isActive():
                return
            if not self._cursor_screen_is_fullscreen_space():
                return
            nsapp.setActivationPolicy_(1)  # Accessory
            self._policy_borrowed = True
            logger.debug("overlay: borrowed Accessory policy for full-screen Space")
        except Exception as e:
            logger.debug("overlay: policy borrow failed: %s", e)

    def _return_accessory_policy(self):
        if not self._policy_borrowed:
            return
        self._policy_borrowed = False
        try:
            nsapp = NSApplication.sharedApplication()
            dash = getattr(self.app, "dashboard", None) if self.app else None
            win = getattr(dash, "_window", None) if dash else None
            # Only give Regular back if the dashboard is still a live, on-screen
            # window — otherwise we'd re-introduce the exact leak #56 describes.
            if (win is not None and win.isVisible() and not win.isMiniaturized()
                    and not nsapp.isHidden()):
                nsapp.setActivationPolicy_(0)  # Regular
                logger.debug("overlay: returned Regular policy to open dashboard")
        except Exception as e:
            logger.debug("overlay: policy return failed: %s", e)

    def _order_front(self):
        if not self._window:
            self.setup()
        self._borrow_accessory_policy()
        try:
            self._apply_panel_traits(self._window)  # rots over hours — see docstring
        except Exception:
            pass
        self._window.orderFrontRegardless()
        if not self._on_active_space():
            self._heal_stale_panel()
        self._visible = True
        # Every state that appears on screen needs hover, not just recording:
        # Done hides "Copy again" behind it too, and show_briefly() can be the
        # first thing shown (a transcript arriving from another device).
        self._start_hover_monitor()

    def _on_active_space(self):
        """True if the pill is actually showing on the current Space.

        A canJoinAllSpaces window must report isOnActiveSpace == YES once
        ordered front; NO means its Space binding rotted (typically bound to a
        since-destroyed full-screen Space). Errors count as fine — never churn
        windows on a signal we can't read.
        """
        try:
            return bool(self._window.isOnActiveSpace())
        except Exception:
            return True

    def _heal_stale_panel(self):
        """Self-heal the fifth path of conventions #56: the panel exists, the
        activation policy is right, orderFrontRegardless ran — and the pill
        still isn't on the active (full-screen) Space, because the long-lived
        NSPanel's Space binding rotted inside the WindowServer. No event fires
        for that, and no property re-assert fixes it; the only cure users found
        was restarting the app. Do the equivalent in-place: rebuild the NSPanel
        around the SURVIVING WKWebView (its loaded page, bridge, and
        _page_ready handshake all carry over) and order the new panel front.
        Runs at most once per show, only when isOnActiveSpace says NO.
        """
        logger.info("overlay: panel missing from active Space after orderFront — rebuilding panel")
        old, self._window = self._window, None
        frame = None
        try:
            frame = old.frame() if old is not None else None
        except Exception:
            pass
        try:
            if self._webview is not None:
                self._webview.removeFromSuperview()
        except Exception:
            pass
        try:
            if old is not None:
                old.orderOut_(None)
                old.close()
        except Exception:
            pass
        try:
            if frame is None:
                frame = self._default_frame()
            if frame is None:
                return
            self._window = self._make_panel(frame)
            if self._webview is not None:
                self._window.setContentView_(self._webview)
            self._window.orderFrontRegardless()
        except Exception as e:
            # _window may be None now; the next _order_front runs setup() and
            # rebuilds the webview too — degraded, but never a dead pill.
            logger.error("overlay: panel rebuild failed: %s", e)

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

    # ── live mic level → waveform ─────────────────────────────────────────────
    def _emit_level(self, lvl):
        """Push one 0..1 level into the page (WKWebView work stays on main)."""
        js = "if(window.VerbalWave)window.VerbalWave(%.3f);" % lvl

        def _run():
            self._level_inflight = False
            if not (self._webview and self._page_ready):
                return
            try:
                self._webview.evaluateJavaScript_completionHandler_(js, None)
            except Exception as e:
                logger.debug("overlay level eval failed: %s", e)

        self._level_inflight = True
        if self.app:
            self.app._on_main(_run)
        else:
            _run()

    # ── hover → expand (Capsule) ─────────────────────────────────────────────
    def _start_hover_monitor(self):
        """Watch the cursor globally while the pill is up.

        A GLOBAL monitor (as opposed to a local one) reports events destined for
        other applications, which is the whole point — Flume is never the active
        app while you dictate. Mouse-move monitors need no Accessibility grant
        (only key events do), same as the ones in hotkey.py.
        """
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
                    pass      # a hover glitch must never touch the recording

            self._hover_mon = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSEventMaskMouseMoved | NSEventMaskLeftMouseDragged, _handler)
        except Exception as e:
            logger.debug("hover monitor unavailable (%s); pill stays collapsed", e)

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
        """Forward the cursor's panel-local position to the page, cheaply.

        Only while the cursor is actually over the (small) panel, throttled to
        ~25/s, and with a single "left" message on the way out — mouseMoved
        fires far too often to hand every event to JavaScript.
        """
        if not (self._window and self._webview and self._page_ready):
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
        js = "if(window.VerbalHover)window.VerbalHover(%.0f,%.0f);" % (x, y)
        try:
            self._webview.evaluateJavaScript_completionHandler_(js, None)
        except Exception as e:
            logger.debug("hover eval failed: %s", e)

    # ── transcribing spinner ─────────────────────────────────────────────────
    def _emit_spin(self, deg):
        js = "if(window.VerbalSpin)window.VerbalSpin(%.1f);" % (deg % 360.0)

        def _run():
            self._spin_inflight = False
            if not (self._webview and self._page_ready):
                return
            try:
                self._webview.evaluateJavaScript_completionHandler_(js, None)
            except Exception as e:
                logger.debug("overlay spin eval failed: %s", e)

        self._spin_inflight = True
        if self.app:
            self.app._on_main(_run)
        else:
            _run()

    def _start_spin_pump(self):
        """Rotate the transcribing ring from Python, because CSS won't here."""
        import threading
        self._spin_token += 1
        token = self._spin_token
        t0 = time.time()

        def _run():
            while self._spin_token == token:
                try:
                    if not self._spin_inflight:
                        self._emit_spin((time.time() - t0) * SPIN_DEG_PER_SEC)
                except Exception:
                    pass  # a stuck spinner must never touch the transcription
                time.sleep(1.0 / SPIN_HZ)

        threading.Thread(target=_run, name="overlay-spin", daemon=True).start()

    def _stop_spin_pump(self):
        was_running = self._spin_token
        self._spin_token += 1
        self._spin_inflight = False
        # Hand the ring back to the CSS keyframes explicitly. The page has no
        # timer it can trust to notice the ticks stopped, so the last word has to
        # come from here — otherwise a stopped pump leaves it frozen mid-turn.
        if was_running and self._webview and self._page_ready:
            try:
                self._webview.evaluateJavaScript_completionHandler_(
                    "if(window.VerbalSpin)window.VerbalSpin(-1);", None)
            except Exception:
                pass

    def _start_level_pump(self):
        """Sample the recorder's level on a worker thread while recording."""
        import threading
        self._level_token += 1
        token = self._level_token

        def _run():
            while self._level_token == token:
                try:
                    if not self._level_inflight:
                        rec = getattr(self.app, "recorder", None) if self.app else None
                        self._emit_level(float(getattr(rec, "level", 0.0) or 0.0))
                except Exception:
                    pass  # the waveform must never take the recording down
                time.sleep(1.0 / LEVEL_HZ)

        threading.Thread(target=_run, name="overlay-level", daemon=True).start()

    def _stop_level_pump(self):
        self._level_token += 1
        self._level_inflight = False

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
        self._stop_spin_pump()
        self._start_level_pump()

    def update_status(self, status, error=False):
        """`error=True` renders the failure pill (no ✓, no "Copy again")."""
        if not self._window:
            return
        self._cancel_autohide()
        self._stop_level_pump()   # no bars to feed once capture has ended
        if not error and status and "Transcrib" in status and "fail" not in status.lower():
            secs = int(max(0, time.time() - self._t0)) if self._t0 else 0
            self._push("transcribing", {
                "src": self._this_device(), "dst": self._target_device(), "secs": secs})
            self._start_spin_pump()
            return
        self._order_front()
        self._stop_spin_pump()      # leaving transcribing
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

    def show_briefly(self, status, duration=2.0, error=False):
        self._stop_level_pump()
        self._order_front()
        if error:
            # Same failure pill as update_status(error=True) — a flash like
            # "Mic access needed" was falling through to the plain "done" push
            # below (no error path existed here at all), rendering as if it
            # were a normal successful paste/copy confirmation. Confirmed
            # live, 2026-08-25: exactly the "shows Copied in green" confusion
            # reported for the repeated mic-denied hotkey flash.
            self._push("error", {"label": self._strip_glyphs(status) or "Something went wrong",
                                 "state": "Failed"})
        else:
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
        self._stop_level_pump()
        self._stop_spin_pump()
        self._stop_hover_monitor()
        self._push("hide")
        if self._window:
            self._window.orderOut_(None)
        self._visible = False
        self._return_accessory_policy()

    @property
    def visible(self):
        return self._visible

    def cleanup(self):
        self._stop_level_pump()
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
