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

Window lifetime (DO NOT remove the closing/closed hooks):
    The window is created ONCE and re-used; like the macOS panel it is never
    destroyed by the user. pywebview's winforms backend DESTROYS the form when
    the user hits the title-bar X / Alt+F4 (Form.Close -> on_close -> the
    BrowserView is dropped from `BrowserView.instances` and `webview.windows`).
    Before 2026-08-26 there was no `events.closing`/`events.closed` handler, so
    after the first close `self._window` pointed at a dead handle: every later
    "Start meeting" logged "meeting open: ready=True skipped=False", called
    `self._window.show()` -- a silent no-op because `gui.show(uid)` finds no
    instance -- and nothing appeared, forever (user report 2026-08-26).
    Fix: `_on_closing` hides (or, mid-meeting, collapses -- macOS parity) and
    returns False so pywebview cancels the destruction; `_on_closed` drops
    every reference so that if the form IS destroyed for any reason the next
    show() rebuilds instead of poking the corpse; show() additionally checks
    `webview.windows` for a stale handle and rebuilds once.

    The veto must be USER closes only. pywebview's `closing` Event hands the
    handler no CloseReason, and WinForms routes WM_QUERYENDSESSION (shutdown /
    log-off), Task Manager "End task" and Application.Exit through the very
    same FormClosing -- to hidden forms too. Cancelling those makes Windows
    park on "Flume Meeting is preventing you from shutting down" until the
    user clicks "Shut down anyway" (review of the 2026-08-26 fix). So _build
    also subscribes a NATIVE FormClosing handler (`_on_native_closing`) on the
    BrowserForm; it runs after pywebview's (subscription order) and clears
    args.Cancel for every CloseReason other than UserClosing.
"""

import ctypes
import ctypes.wintypes as wt
import json
import logging
import threading

from app.meeting_html import meeting_html
from app.shared_dashboard import DashboardApi

logger = logging.getLogger("verbal.meetingwin.win")

BAR_W, BAR_H = 560, 54   # keep in sync with app/meeting_window.py's BAR_W — both
# host the same meeting_html(), whose `.barOpt` cap needs this width to avoid
# clipping the trailing button (05-conventions.md Rule #56).
WIN_W, WIN_H = 880, 620
MIN_W, MIN_H = 700, 480
WIN_TITLE = "Flume Meeting"
# How long show() waits for the freshly built form's `shown` Event. WinForms
# raises Shown one message-pump turn after create_window returns, so this is
# generous; it exists because every pywebview Window method (resize/move/show/
# destroy) is `_shown_call`-decorated and blocks 20s EACH when `shown` never
# fires (WebView2 runtime mid-update) -- a silent ~60s freeze per click.
SHOWN_WAIT_S = 5

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
        # True inside destroy() (and set by _on_native_closing for session
        # end / Task Manager): lets _on_closing allow the teardown. Only the
        # user's X / Alt+F4 (CloseReason.UserClosing) is intercepted.
        self._destroying = False

        # DashboardApi reads these on the "dashboard" argument.
        self._known_devices = []
        try:
            self._target_device_id = app.config.get(
                "sync_target_device_id", "__all__") or "__all__"
        except Exception:
            self._target_device_id = "__all__"
        # Guards concurrent show()s from spawning multiple windows before
        # webview.create_window returns and assigns self._window.
        self._build_lock = threading.Lock()

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
            self._destroying = False
            try:
                self._window.events.loaded += self._on_loaded
            except Exception as e:
                logger.debug("meeting loaded-hook attach failed: %s", e)
            # X / Alt+F4 must HIDE, not destroy -- see module docstring
            # (dead-handle failure, 2026-08-26). `closing` is a should_lock
            # Event: handlers run synchronously on the WinForms UI thread and a
            # False return sets FormClosingEventArgs.Cancel. `closed` is the
            # safety net if destruction happens anyway.
            try:
                self._window.events.closing += self._on_closing
                self._window.events.closed += self._on_closed
            except Exception as e:
                logger.warning("meeting close-hook attach failed (window will "
                               "die on X): %s", e)
            self._attach_native_closing()
        except Exception as e:
            logger.error("meeting window create failed: %s", e, exc_info=True)
            self._window = None

    def _attach_native_closing(self):
        """Subscribe `_on_native_closing` on the WinForms BrowserForm.

        create_window is synchronous for non-master windows (Control.Invoke on
        the UI thread), so `self._window.native` is already the BrowserForm
        here. Subscribing AFTER pywebview's own FormClosing handler means ours
        sees -- and can undo -- the args.Cancel that `_on_closing`'s False
        return produced. Fail-closed: without it the window merely keeps the
        pre-review behavior (hides on every close, including session end).
        """
        try:
            form = getattr(self._window, "native", None)
            if form is None:
                logger.debug("meeting native form not available; session-end "
                             "close will be vetoed like a user close")
                return
            form.FormClosing += self._on_native_closing
        except Exception as e:
            logger.debug("meeting native closing-hook attach failed: %s", e)

    def _on_native_closing(self, sender, args):
        """Native FormClosing, runs AFTER pywebview's `on_closing` on the
        WinForms UI thread. Windows shutdown / log-off (WM_QUERYENDSESSION ->
        CloseReason.WindowsShutDown), Task Manager "End task"
        (TaskManagerClosing) and Application.Exit (ApplicationExitCall) must
        NOT be cancelled -- a cancelled WM_QUERYENDSESSION returns 0 and Windows
        blocks the shutdown on a "Flume Meeting is preventing..." screen. Only
        the user's own X / Alt+F4 (UserClosing; also Form.Close() from our
        destroy(), which _on_closing already lets through) keeps the veto.
        """
        try:
            import System.Windows.Forms as WinForms
            if args.CloseReason == WinForms.CloseReason.UserClosing:
                return
            logger.info("meeting window: close reason %s -- allowing destroy",
                        args.CloseReason)
            self._destroying = True
            args.Cancel = False
        except Exception as e:
            logger.debug("meeting native closing-hook failed: %s", e)

    def _recording_active(self):
        """Mirror of meeting_window._recording_active: recording OR still
        generating the post-meeting summary (`processing`)."""
        try:
            m = getattr(self.app, "meetings", None)
            return bool(m and (m.active or getattr(m, "processing", False)))
        except Exception:
            return False

    def _on_closing(self, window=None, *_):
        """FormClosing interceptor -- runs ON the WinForms UI thread.

        Returning False makes pywebview set args.Cancel, so the form survives.
        Keep this trivial: `window.hide()` is safe here (Control.Invoke on the
        owning thread executes synchronously), but `evaluate_js` -- and hence
        emit()/set_layout()/set_mode() -- is NOT: it blocks on a semaphore that
        is released via the UI thread's sync context, so calling it from this
        handler deadlocks the UI thread. Anything that touches the page is
        scheduled off-thread via app._on_main.

        Parity with the macOS delegate (meeting_window.windowShouldClose_):
        closing mid-meeting (recording or processing) collapses to the bar
        instead of hiding, so the live recording never runs invisibly; idle,
        the window just hides and the next show() re-uses it.
        """
        # Programmatic teardown -- allow. `app._exiting` covers win_main
        # _hard_exit's generic `for w in webview.windows: w.destroy()` sweep,
        # which bypasses our destroy() and would otherwise be vetoed here.
        if self._destroying or getattr(self.app, "_exiting", False):
            return None
        try:
            if self._recording_active():
                logger.info("meeting window: close intercepted mid-meeting -- "
                            "collapsing to bar (window kept alive)")
                try:
                    self.app._on_main(lambda: self.set_layout("bar"))
                except Exception as e:
                    logger.debug("meeting collapse schedule failed: %s", e)
            else:
                logger.info("meeting window: close intercepted -- hiding "
                            "(window kept alive for the next Start meeting)")
                self._visible = False
                w = window if window is not None else self._window
                if w is not None:
                    w.hide()
        except Exception as e:
            # Even if hide failed, still cancel: a visible-but-alive window
            # beats a dead handle that swallows every later show().
            logger.debug("meeting close intercept failed: %s", e)
        return False

    def _reset_refs(self):
        self._window = None
        self._api = None
        self._page_ready = False
        self._visible = False
        self._pending = []
        self._destroying = False

    def _on_closed(self, window=None, *_):
        """The form really was destroyed (destroy(), or a close our
        interceptor could not cancel). Drop every reference so the next
        show() rebuilds instead of calling show() on a dead handle -- the
        silent failure behind the 2026-08-26 "nothing opens" report. Runs on a
        pywebview-spawned thread, so guard against a concurrent rebuild."""
        try:
            with self._build_lock:
                if window is None or window is self._window:
                    self._reset_refs()
            logger.info("meeting window destroyed -- next show() rebuilds")
        except Exception as e:
            logger.debug("meeting closed-hook failed: %s", e)

    def destroy(self):
        """Programmatic teardown (quit / hard reset). The only path on which
        _on_closing lets the form go."""
        w = self._window
        self._destroying = True
        try:
            if w is not None:
                w.destroy()
        except Exception as e:
            logger.debug("meeting window destroy failed: %s", e)
        with self._build_lock:
            if self._window is w:
                self._reset_refs()

    def _window_alive(self):
        """False when pywebview has already dropped our window (its on_close
        removes it from `webview.windows` before `closed` fires) -- the exact
        state that made show() a silent no-op before 2026-08-26."""
        if self._window is None:
            return False
        try:
            import webview
            return self._window in webview.windows
        except Exception:
            return True                      # can't tell -- keep old behavior

    def _wait_shown(self):
        """True once the form has raised Shown (pywebview's `shown` Event).

        Every Window method show() calls next (resize, move, show) is
        `_shown_call`-decorated: each blocks up to 20s and then raises
        WebViewException when `shown` never fires (WebView2 runtime failed to
        initialise the form, e.g. mid-update). Bounding the wait here turns a
        silent ~60s freeze into one warning and an early return; the handle is
        kept (it is still alive in `webview.windows`) so the next Start meeting
        simply retries -- Shown may well have fired by then.
        """
        try:
            ev = self._window.events.shown
            if ev.is_set() or ev.wait(SHOWN_WAIT_S):
                return True
            logger.warning("meeting window: form not shown after %ss -- "
                           "skipping this open (retry Start meeting)",
                           SHOWN_WAIT_S)
            return False
        except Exception as e:
            logger.debug("meeting shown-wait failed (%s) -- proceeding", e)
            return True                      # can't tell -- keep old behavior

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
                if self._window is not None and not self._window_alive():
                    # closed-hook missed / raced -- never show() a dead handle.
                    logger.info("meeting window: stale handle -- rebuilding")
                    self._reset_refs()
                if self._window is None:
                    self._build()
            if self._window is None:
                logger.warning("meeting window: build failed, cannot show")
                return
            # _visible BEFORE wait_shown: `loaded` fires on a pywebview thread
            # and `_on_loaded` hides when _visible is False, so a load during
            # the Shown wait used to hide the first open.
            self._visible = True
            if not self._wait_shown():
                self._visible = False
                return
            if mode in ("premeeting", "permissions"):
                self._layout = "expanded"
            self._position_and_size()
            # NOTE: Window.show() does NOT raise on a dead handle -- winforms
            # show(uid) silently returns when the uid has no BrowserView -- so
            # there is deliberately no "show() raised -> rebuild" fallback
            # here. _window_alive() above is the dead-handle protection; a
            # rebuild-on-exception could only ever fire on the `shown` timeout
            # (now handled by _wait_shown) and would orphan a second form.
            self._window.show()
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
        if mode in ("premeeting", "permissions"):
            self.set_layout("expanded")

    def set_handoff(self, state, row):
        """Post-meeting handoff (MER-46) — see MeetingWindow.set_handoff."""
        try:
            self.emit("handoff", {"state": state,
                                  "id": (row or {}).get("id"),
                                  "title": (row or {}).get("title")})
            self.set_layout("bar")
        except Exception as e:
            logger.debug("meeting handoff failed: %s", e)

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
