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
import time

from app.meeting_html import meeting_html
from app import win_geometry
from app.shared_dashboard import DashboardApi

logger = logging.getLogger("verbal.meetingwin.win")

BAR_PILL_H = 36          # the Windows pill (Mac's is 44 inside a 54 panel; slimmer here since there is
                         # no shadow/blur halo around it — the window IS the pill, see set_bar_content_size)
BAR_ANIM_S = 0.18        # hover expand/collapse: eased window-width animation length
BAR_LEAVE_GRACE_S = 0.22 # cursor must be outside this long before the pill collapses (no flicker)
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
            # pywebview 5.3 applies width/height/min_size as PHYSICAL pixels
            # (see win_geometry) — hand it scaled values so the CSS viewport
            # is really WIN_W x WIN_H. show() re-applies geometry anyway.
            cw, ch = win_geometry.create_size(w, h)
            cmin = (MIN_W, MIN_H)          # logical — WinForms autoscales it (win_geometry)
            self._window = webview.create_window(
                WIN_TITLE,
                html=meeting_html(),
                js_api=self._api,
                width=cw,
                height=ch,
                x=x,
                y=y,
                min_size=cmin,
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
        # Windows-only bar CSS: the window IS the pill (win_geometry pill
        # region), so the page paints the pill colour edge to edge, drops
        # #barRoot's padding/centering (the pill may overflow the viewport
        # while it grows — the ResizeObserver below then widens the window)
        # and pins the pill height. Host-side injection keeps meeting_html()
        # untouched for macOS.
        try:
            css = ("body.lay-bar{background:#0d0f11 !important;overflow:hidden}"
                   "html:has(body.lay-bar){overflow:hidden}"
                   "body.lay-bar #barRoot{background:transparent;left:0;right:auto;width:max-content;"
                   "justify-content:flex-start;padding:0;height:%dpx}"
                   # The window is clipped to the pill, so the pill's own shadow can never show;
                   # slimmer proportions than the Mac panel (no halo) and no reveal transition:
                   # each animation frame would otherwise be a separate SetWindowPos (jitter) —
                   # the expansion is one jump, like a native menu.
                   "body.lay-bar .barPill{box-shadow:none;height:%dpx;padding:0 5px 0 11px;gap:8px;"
                   "border-color:rgba(240,240,240,.08)}"
                   "body.lay-bar #barPill .barOpt{transition:none;gap:8px}"
                   "body.lay-bar .barDot{width:7px;height:7px}"
                   "body.lay-bar .barTimer{font-size:12px}"
                   "body.lay-bar .barTitle{font-size:11.5px;max-width:140px}"
                   "body.lay-bar .barWave{min-width:32px;height:14px}"
                   "body.lay-bar .barBtn{width:22px;height:22px}"
                   "body.lay-bar .barBtn svg{width:11px;height:11px}" % (BAR_PILL_H, BAR_PILL_H))
            self._eval("(function(){var s=document.createElement('style');"
                       "s.textContent=%s;document.head.appendChild(s);})();" % json.dumps(css))
        except Exception as e:
            logger.debug("meeting window: chroma css failed: %s", e)
        # WebView2 renders confirm()/alert() as an in-page dialog, which the
        # pill-sized bar window clips to a sliver ("This page says…", nothing
        # clickable). cancelMeeting() is the only confirm in meeting_html; on
        # Windows route it to a native TopMost MessageBox owned by the form
        # (DashboardApi.confirm_native -> WinMeetingWindow.native_confirm).
        try:
            self._eval(
                "window.cancelMeeting=function(){"
                "api('confirm_native','Discard this meeting? The recording and transcript will not be saved.',"
                "'Discard meeting').then(function(r){if(r&&r.ok&&r.yes)api('cancel_meeting');});};"
                "window.confirm=function(m){console.warn('confirm() suppressed on Windows bar:',m);return false;};")
        except Exception as e:
            logger.debug("meeting window: confirm override failed: %s", e)
        # Shrink-wrap: report the visible pill's size so the host can size the
        # borderless bar window to it (hover/peek widens the pill → the window
        # follows; at rest it is just dot + timer). WebView2 has no per-pixel
        # alpha and TransparencyKey does not key its surface (tested
        # 2026-08-28), so a 560px window shows as a dark strip around the pill.
        try:
            self._eval(
                "(function(){if(window.__barRO)return;"
                "function pill(){return document.body.classList.contains('handoff')?"
                "document.getElementById('barHandoff'):document.getElementById('barPill');}"
                "var last='';function report(){if(!document.body.classList.contains('lay-bar'))return;"
                "var p=pill();if(!p)return;var r=p.getBoundingClientRect();"
                "var k=Math.round(r.width)+'x'+Math.round(r.height);if(k===last)return;"
                "if(!(window.pywebview&&window.pywebview.api&&window.pywebview.api.meeting_bar_resize))return;"
                "last=k;window.pywebview.api.meeting_bar_resize(Math.round(r.width),Math.round(r.height));}"
                "var ro=new ResizeObserver(report);"
                "['barPill','barHandoff'].forEach(function(id){var e=document.getElementById(id);if(e)ro.observe(e);});"
                "new MutationObserver(function(){last='';report();}).observe(document.body,{attributes:true,attributeFilter:['class']});"
                "window.__barRO=ro;report();})();")
        except Exception as e:
            logger.warning("meeting window: bar resize observer failed: %s", e)
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
            if self._layout == "bar":
                # Mac's bar is a non-activating panel; pywebview's show() ends
                # in Activate() and would steal focus from the call app.
                self._show_noactivate() or self._window.show()
            else:
                self._window.show()
            self.set_mode(mode)
            self.emit("layout", {"layout": self._layout})
            if self._layout == "bar":
                self._start_hover_watch()      # hide() ends the watch; re-show must restart it
        except Exception as e:
            logger.error("meeting window show failed: %s", e, exc_info=True)

    def _show_noactivate(self):
        try:
            form = getattr(self._window, "native", None)
            hwnd = form.Handle.ToInt64() if form is not None else None
            if not hwnd:
                return False
            SW_SHOWNOACTIVATE = 4
            ctypes.windll.user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            return True
        except Exception as e:
            logger.debug("show-noactivate failed: %s", e)
            return False

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
    def _apply_chrome(self, layout):
        """Give the collapsed bar the same chrome as the Mac bar (a floating
        borderless strip) and the expanded view a normal window.

        pywebview fixes `frameless` / `min_size` / `on_top` at create time, so
        collapsing used to leave the 560x54 bar with a title bar, a taskbar
        button, and a 700x480 MinimumSize that silently REFUSED the resize —
        "the collapsed meetings bar shows up as a big window, like a tab"
        (2026-08-28). Flip the WinForms properties on the form directly, on
        the UI thread (Invoke; every property here must be set there).
        Fail-closed: any error leaves the old (ugly but working) chrome.
        """
        form = getattr(self._window, "native", None) if self._window else None
        if form is None:
            logger.warning("meeting window: no native form; chrome for layout=%s not applied", layout)
            return
        try:
            import System.Windows.Forms as WinForms
            from System.Drawing import Color, Size

            def _do():
                try:
                    # Remember what pywebview set at create time (its unit
                    # handling differs by version — win_geometry) and restore
                    # exactly that on expand rather than recomputing.
                    if getattr(self, "_native_back_color", None) is None:
                        self._native_back_color = form.BackColor
                    # MinimumSize is physical at runtime: compute it from the
                    # window's own DPI (never trust the create-time value —
                    # WinForms' AutoScaleMode.Dpi may already have scaled it).
                    scale = win_geometry.window_scale(form.Handle.ToInt64())
                    if layout == "bar":
                        form.MinimumSize = Size(0, 0)
                        form.FormBorderStyle = getattr(WinForms.FormBorderStyle, "None")
                        form.ShowInTaskbar = False
                        form.TopMost = True
                        # No TransparencyKey: it adds WS_EX_LAYERED, which
                        # does not key WebView2's surface AND stopped :hover
                        # from ever firing in the page (hover test 2026-08-28).
                        # The pill shape comes from SetWindowRgn instead
                        # (win_geometry.set_window_pill_region); the form is
                        # painted the pill's own colour for the 1px seam.
                        form.TransparencyKey = Color.Empty
                        form.BackColor = Color.FromArgb(0x0d, 0x0f, 0x11)
                    else:
                        form.TransparencyKey = Color.Empty
                        form.BackColor = self._native_back_color
                        form.FormBorderStyle = WinForms.FormBorderStyle.Sizable
                        form.MinimumSize = Size(int(MIN_W * scale), int(MIN_H * scale))
                        form.ShowInTaskbar = True
                        form.TopMost = False
                except Exception as e:
                    logger.warning("meeting chrome apply failed: %s", e, exc_info=True)

            if form.InvokeRequired:
                form.Invoke(WinForms.MethodInvoker(_do))
            else:
                _do()
        except Exception as e:
            logger.warning("meeting chrome failed: %s", e, exc_info=True)

    # The bar window is EXACTLY the pill (no padding: the injected CSS zeroes
    # #barRoot's padding and drops the shadow) and is clipped to a pill shape
    # with SetWindowRgn — the only way to get a floating pill without
    # per-pixel alpha on WebView2.
    BAR_PAD_W = 0

    def set_bar_content_size(self, width, height):
        """Called via DashboardApi.meeting_bar_resize from the page (see
        _on_loaded). Keeps the pill centred at the top of the work area while
        the window width follows the pill: ~110px at rest, up to BAR_W when
        hovered/peeked. Ignored outside bar layout."""
        if self._layout != "bar" or not width or getattr(self, "_modal", False):
            return
        w = max(60, min(BAR_W, int(width) + self.BAR_PAD_W))
        h = BAR_PILL_H                     # fixed by the injected CSS; never trust a mid-layout measurement
        if (w, h) == getattr(self, "_bar_content_wh", None) and not getattr(self, "_bar_needs_measure", False):
            return
        first = getattr(self, "_bar_needs_measure", True) or getattr(self, "_bar_content_wh", None) is None
        self._bar_needs_measure = False
        self._bar_content_wh = (w, h)
        if first:
            self._bar_cur_w = w
            self._position_and_size()      # first frame of this bar session: snap
            return
        self._animate_bar_width(getattr(self, "_bar_cur_w", w), w)

    def _animate_bar_width(self, w_from, w_to):
        """Ease the pill window from one logical width to another, keeping it
        centred (both edges move, like the Mac bar). One animator at a time —
        a newer target supersedes a running one via the generation counter."""
        self._bar_anim_gen = getattr(self, "_bar_anim_gen", 0) + 1
        gen = self._bar_anim_gen

        def _run():
            try:
                form = getattr(self._window, "native", None)
                hwnd = form.Handle.ToInt64() if form is not None else None
                if not hwnd:
                    return
                # Target monitor is the primary (SPI_GETWORKAREA) — use ITS
                # scale, not the monitor the form happens to be on now.
                scale = win_geometry.system_scale()
                left, top, right, bottom = self._work_area()
                y = top + int(12 * scale)
                t0 = time.time()
                while True:
                    if gen != self._bar_anim_gen or self._layout != "bar":
                        return
                    t = min(1.0, (time.time() - t0) / BAR_ANIM_S)
                    e = 1 - (1 - t) ** 3            # ease-out cubic
                    w = w_from + (w_to - w_from) * e
                    self._bar_cur_w = w              # a superseding animation starts from HERE
                    x = (left + right - int(w * scale)) // 2
                    pw, ph = win_geometry.set_window_rect(hwnd, x, y, int(round(w)), BAR_PILL_H, scale)
                    win_geometry.set_window_pill_region(hwnd, pw, ph)
                    if t >= 1.0:
                        return
                    time.sleep(1 / 60)
            except Exception as e:
                logger.debug("bar width animation failed: %s", e)

        threading.Thread(target=_run, name="meeting-bar-anim", daemon=True).start()

    def _position_and_size(self):
        try:
            if not self._window:
                return
            # Chrome first: the bar's resize is clamped by MinimumSize and a
            # border-style change alters the client/frame size, so the
            # geometry must be applied after it.
            self._apply_chrome(self._layout)
            form = getattr(self._window, "native", None)
            hwnd = None
            try:
                hwnd = form.Handle.ToInt64() if form is not None else None
            except Exception:
                hwnd = None
            if not hwnd:
                logger.warning("meeting window: no native handle (form=%r) -- using pywebview resize/move fallback", form)
            if hwnd:
                # One DPI-aware SetWindowPos in PHYSICAL pixels for both the
                # position (work-area space) and the size (logical constants
                # x monitor scale). pywebview 5.3's resize() takes physical
                # and move() logical, which halved every window at 200 %.
                scale = win_geometry.system_scale()   # target = primary work area
                left, top, right, bottom = self._work_area()
                if self._layout == "bar":
                    w, h = getattr(self, "_bar_content_wh", None) or (BAR_W, BAR_PILL_H)
                    x = (left + right - int(w * scale)) // 2
                    y = top + int(12 * scale)
                else:
                    w, h = WIN_W, WIN_H
                    x = (left + right - int(w * scale)) // 2
                    y = (top + bottom - int(h * scale)) // 2
                pw, ph = win_geometry.set_window_rect(hwnd, x, y, w, h, scale)
                if self._layout == "bar":
                    win_geometry.set_window_pill_region(hwnd, pw, ph)
                else:
                    win_geometry.clear_window_region(hwnd)
            else:
                x, y, w, h = self._rect_for(self._layout)
                self._window.resize(w, h)
                self._window.move(x, y)
        except Exception as e:
            logger.warning("meeting window position failed: %s", e, exc_info=True)

    def set_layout(self, layout, animate=True):
        if layout not in ("bar", "expanded"):
            return
        entering_bar = layout == "bar" and layout != self._layout
        if entering_bar:
            # Re-measure on every entry (the pill may have a title/PAUSED tag
            # now) but keep the LAST measured width as the interim size — the
            # (BAR_W) fallback painted a 560 px dark strip on every collapse.
            self._bar_needs_measure = True
        self._layout = layout
        if entering_bar:
            # Flip the page to lay-bar BEFORE the window becomes bar-shaped, so
            # the expanded content is never shown clipped inside the pill.
            self.emit("layout", {"layout": layout})
            self._position_and_size()
        else:
            self._position_and_size()
            self.emit("layout", {"layout": layout})
        if layout == "bar":
            self._start_hover_watch()

    def native_confirm(self, message, title="Flume"):
        """Yes/No MessageBox on the WinForms UI thread, owned by (and TopMost
        with) the meeting form. Blocking on the caller's (pywebview API)
        thread only. Fail-closed: any error means 'No'."""
        form = getattr(self._window, "native", None) if self._window else None
        logger.info("native confirm requested: %r (form=%s)", title, form is not None)
        try:
            import System.Windows.Forms as WinForms
            result = [False]

            def _ask():
                try:
                    r = WinForms.MessageBox.Show(
                        form, str(message), str(title),
                        WinForms.MessageBoxButtons.YesNo,
                        WinForms.MessageBoxIcon.Warning,
                        WinForms.MessageBoxDefaultButton.Button2)
                    result[0] = (r == WinForms.DialogResult.Yes)
                except Exception as e:
                    logger.warning("native confirm failed: %s", e)

            if form is None:
                return False                  # no owner → no modal on a bridge thread
            self._modal = True                # hover/resize must not shrink the owner under the box
            try:
                if form.InvokeRequired:
                    form.Invoke(WinForms.MethodInvoker(_ask))
                else:
                    _ask()
            finally:
                self._modal = False
            return bool(result[0])
        except Exception as e:
            logger.warning("native confirm unavailable: %s", e)
            return False

    # ── hover (peek) ────────────────────────────────────────────────────
    def _start_hover_watch(self):
        """Host-side hover for the bar, like meeting_window.py on macOS:
        the page's `:hover` never fires in this window (borderless/TopMost
        WebView2 — verified with a scripted cursor move, 2026-08-28), so poll
        GetCursorPos and hand the page window-relative CSS coords via its
        `VerbalMeetingHover(x, y)` hook (x < 0 = pointer left). The pill
        toggles `.peek`, the ResizeObserver reports the new width and
        set_bar_content_size grows/shrinks the window to match."""
        # Generation counter, not is_alive(): an old loop can take up to
        # ~350 ms (poll + leave-grace) to notice `_layout`/`_visible` flipped;
        # a bar→expanded→bar within that window used to find it alive, skip
        # spawning, and then lose hover for the whole session.
        self._hover_gen = getattr(self, "_hover_gen", 0) + 1
        threading.Thread(target=self._hover_loop, args=(self._hover_gen,),
                         name="meeting-bar-hover", daemon=True).start()

    def _hover_loop(self, gen=None):
        import ctypes
        from ctypes import wintypes
        pt = wintypes.POINT()
        rc = wt.RECT()
        inside_prev = None
        user32 = ctypes.windll.user32
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wt.RECT)]
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        logger.info("bar hover watch started")
        while (self._layout == "bar" and self._window is not None and self._visible
               and (gen is None or gen == getattr(self, "_hover_gen", gen))):
            try:
                if getattr(self, "_modal", False):
                    time.sleep(0.1)
                    continue
                form = getattr(self._window, "native", None)
                hwnd = form.Handle.ToInt64() if form is not None else None
                if not hwnd:
                    break
                user32.GetCursorPos(ctypes.byref(pt))
                user32.GetWindowRect(hwnd, ctypes.byref(rc))
                inside = rc.left <= pt.x < rc.right and rc.top <= pt.y < rc.bottom
                if inside_prev and not inside:
                    # Grace period: skimming off the edge and back must not
                    # collapse + re-expand (that read as "wild" flicker).
                    deadline = time.time() + BAR_LEAVE_GRACE_S
                    while time.time() < deadline:
                        time.sleep(0.03)
                        user32.GetCursorPos(ctypes.byref(pt))
                        user32.GetWindowRect(hwnd, ctypes.byref(rc))
                        if rc.left <= pt.x < rc.right and rc.top <= pt.y < rc.bottom:
                            inside = True
                            break
                if inside or inside_prev:
                    scale = win_geometry.window_scale(hwnd)
                    if inside:
                        x, y = (pt.x - rc.left) / scale, (pt.y - rc.top) / scale
                    else:
                        x, y = -1, -1
                    self._eval("if(window.VerbalMeetingHover)window.VerbalMeetingHover(%d,%d);" % (x, y))
                if inside != inside_prev:
                    logger.info("bar hover: inside=%s cursor=%d,%d rect=%d,%d-%d,%d", inside, pt.x, pt.y, rc.left, rc.top, rc.right, rc.bottom)
                inside_prev = inside
            except Exception as e:
                logger.debug("bar hover loop: %s", e)
                time.sleep(0.2)               # transient (e.g. mid-rebuild): keep watching
                continue
            time.sleep(0.05 if not inside_prev else 0.12)
        logger.info("bar hover watch ended (layout=%s visible=%s)", self._layout, self._visible)
        try:
            self._eval("if(window.VerbalMeetingHover)window.VerbalMeetingHover(-1,-1);")
        except Exception:
            pass

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
