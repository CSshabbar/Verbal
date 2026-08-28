"""Windows Flume popover — pywebview host for flume_popover_html().

Windows has no menubar, so the tray icon's LEFT-click opens this compact
Flume popover (parity with the Mac NSPopover in app/flume_popover.py). The
tray's right-click continues to show the classic pystray menu.

Bridge design mirrors the Mac side: `_PopoverBridge` subclasses `DashboardApi`
so every shared method the popover HTML calls (`get_state`, `save_settings`,
`copy_text`, `fetch_canvas`, `open_meeting_launcher`, …) is routed to the
same backend the dashboard uses. Popover-only actions (`toggle_recording`,
`open_window`, `open_preferences`, `open_canvas`, `open_history`, `quit_app`)
are added as overrides.

Fail-closed: tray behavior — and dictation — must not depend on the popover
building. show()/toggle() and every bridge method are wrapped so a broken
popover degrades to a no-op.

Window lifetime (DO NOT remove the closing/closed hooks):
    The popover window is built once and re-used. It is frameless, but Alt+F4
    (and a Windows session end) still routes through Form.Close, and pywebview's
    winforms backend then DESTROYS the form -- dropping it from
    `BrowserView.instances`/`webview.windows` while our `self._window` keeps
    pointing at the corpse. show() -> `gui.show(uid)` on a dead uid is a silent
    no-op, so the tray's left-click would do nothing, forever. This is the same
    dead-handle failure that broke "Start meeting" on Windows (user report
    2026-08-26, see win_meeting_window.py). `_on_closing` hides and returns
    False (cancels the close); `_on_closed` resets every reference so the next
    show() rebuilds if the form was destroyed anyway.

    The veto is for USER closes only. The popover is built on the very first
    tray left-click, and WinForms routes Windows shutdown / log-off
    (WM_QUERYENDSESSION), Task Manager "End task" and Application.Exit through
    the same FormClosing -- hidden forms included -- while pywebview's
    `closing` Event hides the CloseReason from us. Cancelling those made nearly
    every Flume install block shutdown ("Flume is preventing you from shutting
    down", review of the 2026-08-26 fix). `_on_native_closing`, subscribed on
    the BrowserForm after pywebview's handler, clears args.Cancel for every
    CloseReason other than UserClosing.
"""

import ctypes
import ctypes.wintypes as wt
import json
import logging
import threading
import time

from app.flume_popover_html import popover_html
from app import win_geometry
from app.shared_dashboard import DashboardApi

logger = logging.getLogger("verbal.popover")

WIN_W = 300               # menu width (Mac header is 284 + item chrome)
WIN_H = 560               # initial height; the page reports its real content
MIN_H, MAX_H = 120, 900   # height via popover_resize() and we fit the window to it
WIN_TITLE = "Flume Popover"
# Bound on waiting for the fresh form's `shown` Event before calling the
# `_shown_call`-decorated move()/show() (each blocks 20s if Shown never
# fires) -- see win_meeting_window.SHOWN_WAIT_S.
SHOWN_WAIT_S = 5

SPI_GETWORKAREA = 0x0030


class _PopoverBridge(DashboardApi):
    """Popover js_api — DashboardApi + a handful of popover-only actions.

    Inheriting from DashboardApi means every shared method the popover HTML
    depends on (get_state / save_settings / copy_text / fetch_canvas /
    open_meeting_launcher / …) is available on the bridge without wrapping
    or delegation. We override / add the popover-specific ones below.
    """

    def __init__(self, popover):
        super().__init__(popover)     # popover duck-types the dashboard
        self._popover = popover

    def toggle_recording(self):
        app = self._popover.app
        app._on_main(app._toggle_recording)
        app._on_main(self._popover.hide)
        return {"ok": True}

    def open_window(self):
        app = self._popover.app
        app._on_main(lambda: app.dashboard.show())
        app._on_main(self._popover.hide)
        return {"ok": True}

    def _open_tab(self, tab):
        app = self._popover.app

        def go():
            try:
                app.dashboard.show_tab(tab)
            except Exception as e:
                logger.debug("dashboard tab select %s failed: %s", tab, e)

        app._on_main(go)
        return {"ok": True}

    def open_canvas(self):
        return self._open_tab("canvas")

    def open_history(self):
        return self._open_tab("history")

    def open_preferences(self):
        r = self._open_tab("settings")
        self._popover.app._on_main(self._popover.hide)
        return r

    def quit_app(self):
        self._popover.app._on_main(self._popover.app._tray_quit)
        return {"ok": True}

    # ── menu-style popover (2026-08-29, port of menubar_menu.py) ──────────
    def hide_popover(self):
        self._popover.app._on_main(self._popover.hide)
        return {"ok": True}

    def popover_resize(self, height):
        try:
            self._popover.set_content_height(int(height))
        except Exception as e:
            logger.debug("popover resize failed: %s", e)
        return {"ok": True}

    def popover_state(self):
        """Everything the menu renders, read fresh — the Mac menu rebuilds on
        open (`menuNeedsUpdate:`) instead of being pushed into; same idea."""
        app = self._popover.app
        try:
            from app.config import load_config, get_daily_words, _entry_text, _entry_app
            from app import auth
            cfg = app.config = load_config()
            signed_in = False
            try:
                signed_in = bool(auth.current_user())
            except Exception:
                signed_in = False
            session_dead = False
            try:
                session_dead = bool(signed_in and auth.session_dead(cfg))
            except Exception:
                pass
            meeting_active, meeting_label = False, ""
            try:
                m = getattr(app, "meetings", None)
                meeting_active = bool(m and m.active)
                if meeting_active:
                    src = str(getattr(m, "source_label", "") or "")
                    meeting_label = " · ".join(x for x in ("Meeting", src) if x)
            except Exception:
                meeting_active = False
            history = cfg.get("history", []) or []
            pinned = cfg.get("pinned", []) or []
            recent = []
            for e in history[:10]:
                ts = (e.get("ts", "") if isinstance(e, dict) else "") or ""
                recent.append({"text": _entry_text(e), "app": _entry_app(e) or "",
                               "ts": ts[-5:] if len(ts) >= 5 else ts})
            upd = getattr(app, "_update_available", None) or {}
            allowed = False
            try:
                allowed = bool(auth.cloud_allowed(cfg) and (cfg.get("sync_user_id") or "").strip())
            except Exception:
                pass
            sync_on = bool(cfg.get("sync_enabled") and allowed)
            live = bool(getattr(app, "_sync", None) and getattr(app._sync, "connected", False))
            return {
                "ok": True,
                "signed_in": signed_in,
                "session_dead": session_dead,
                "recording": bool(getattr(app, "_is_recording", False)),
                "processing": bool(getattr(app, "_processing", False)),
                "rec_elapsed": self._popover.rec_elapsed(),
                "meeting_active": meeting_active,
                "meeting_label": meeting_label,
                "status_line": str(getattr(app, "_status_line", "") or ""),
                "hotkey_label": str(cfg.get("hotkey_label", "") or "").strip(),
                "mode": str(cfg.get("recording_mode", "toggle") or "toggle"),
                "model": str(cfg.get("whisper_model", "base") or "base"),
                "daily_words": int(get_daily_words(cfg) or 0) if signed_in else 0,
                "recent": recent if signed_in else [],
                "pinned": [{"text": _entry_text(e)} for e in pinned[:10]] if signed_in else [],
                "sync_enabled": sync_on,
                "sync_allowed": allowed,
                "sync_connecting": bool(cfg.get("sync_enabled") and allowed and not live),
                "update_version": str(upd.get("version", "") or "") if upd else "",
                "auth_label": app._auth_menu_label() if hasattr(app, "_auth_menu_label") else "",
                "version": getattr(app, "APP_VERSION", ""),
            }
        except Exception as e:
            logger.warning("popover_state failed: %s", e)
            return {"ok": False, "error": str(e)}

    def popover_tick(self):
        app = self._popover.app
        try:
            lvl = 0.0
            try:
                lvl = float(getattr(app.recorder, "level", 0.0) or 0.0)
            except Exception:
                pass
            return {"ok": True, "recording": bool(getattr(app, "_is_recording", False)),
                    "processing": bool(getattr(app, "_processing", False)),
                    "level": max(0.0, min(1.0, lvl)), "elapsed": self._popover.rec_elapsed()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def start_meeting(self):
        app = self._popover.app
        app._on_main(self._popover.hide)
        try:
            return self.open_meeting_launcher()
        except Exception as e:
            logger.debug("start_meeting via popover failed: %s", e)
            return {"ok": False, "error": str(e)}

    def open_notes(self):
        return self._open_tab("notes")

    def set_mode(self, mode):
        app = self._popover.app
        fn = app._tray_set_mode_hold if str(mode) == "hold" else app._tray_set_mode_toggle
        app._on_main(fn)
        return {"ok": True}

    def set_model(self, name):
        app = self._popover.app
        name = str(name or "base")
        if name not in ("tiny", "base", "small", "medium"):
            return {"ok": False, "error": "unknown model"}
        app._on_main(lambda: app._tray_change_model(None, name))
        return {"ok": True}

    def set_sync(self, on):
        """Checkmark semantics like the Mac `sync_item`: routed through the shared
        save_settings so the device row / realtime channel follow the flag."""
        try:
            st = self.get_state()
            s = (st or {}).get("settings") or {}
            return self.save_settings({
                "groq_api_keys": s.get("groq_api_keys", []),
                "gemini_api_keys": s.get("gemini_api_keys", []),
                "whisper_model": (st or {}).get("model", "base"),
                "sync_enabled": bool(on),
                "sync_user_id": s.get("sync_user_id", ""),
                "sync_device_name": s.get("sync_device_name", "This PC"),
            })
        except Exception as e:
            logger.warning("popover set_sync failed: %s", e)
            return {"ok": False, "error": str(e)}

    def toggle_auth(self):
        app = self._popover.app
        app._on_main(self._popover.hide)
        threading.Thread(target=app._tray_toggle_auth, name="popover-auth", daemon=True).start()
        return {"ok": True}

    def open_update(self):
        app = self._popover.app
        app._on_main(self._popover.hide)
        try:
            app._tray_open_update()
        except Exception as e:
            logger.debug("open_update failed: %s", e)
        return {"ok": True}

    def check_updates(self):
        app = self._popover.app
        app._on_main(self._popover.hide)
        try:
            app._tray_check_updates()
        except Exception as e:
            logger.debug("check_updates failed: %s", e)
        return {"ok": True}

    def about(self):
        app = self._popover.app
        app._on_main(self._popover.hide)
        try:
            app._tray_about()
        except Exception as e:
            logger.debug("about failed: %s", e)
        return {"ok": True}


class WinPopover:
    """Compact Flume popover for Windows. Lazily builds its pywebview window
    the first time show()/toggle() is called (after webview.start() has begun
    on the main thread — win_main starts the loop; win_overlay creates the
    anchor window). Subsequent shows re-use the window."""

    def __init__(self, app):
        self.app = app
        # DashboardApi reads these on the "dashboard" argument. Independent
        # of the real dashboard so we can be built before it. Once open, the
        # popover's state pushes come from DashboardApi.get_state which reads
        # sync device info through these fields.
        self._known_devices = []
        self._target_device_id = "__all__"

        self._window = None
        self._bridge = None
        self._api = None
        self._loaded = False
        self._visible = False
        self._pending_events = []
        # True inside destroy() (and set by _on_native_closing for session end
        # / Task Manager): the paths on which _on_closing lets pywebview tear
        # the form down. Only the user's Alt+F4 / X are intercepted.
        self._destroying = False
        self._build_lock = threading.Lock()
        self._content_h = WIN_H          # set by popover_resize (page-measured)
        self._rec_started_at = 0.0       # header timer; win_main has no _rec_started_at

    # ── window lifecycle ────────────────────────────────────────
    def _build(self):
        import webview
        self._bridge = _PopoverBridge(self)
        self._api = self._bridge  # what DashboardApi-shaped methods live on
        self._window = webview.create_window(
            WIN_TITLE,
            html=popover_html(),
            js_api=self._bridge,
            # pywebview 5.3 applies these as PHYSICAL px (05-conventions #71)
            width=win_geometry.create_size(WIN_W, WIN_H)[0],
            height=win_geometry.create_size(WIN_W, WIN_H)[1],
            frameless=True,
            on_top=True,
            resizable=False,
            easy_drag=False,
            background_color="#1c1c1e",
            hidden=True,
        )
        self._destroying = False
        try:
            self._window.events.loaded += self._on_loaded
        except Exception as e:
            logger.debug("popover loaded-hook attach failed: %s", e)
        # Alt+F4 must HIDE, not destroy -- see module docstring (dead-handle
        # failure, 2026-08-26). `closing` handlers run synchronously on the
        # WinForms UI thread; returning False sets FormClosingEventArgs.Cancel.
        try:
            self._window.events.closing += self._on_closing
            self._window.events.closed += self._on_closed
        except Exception as e:
            logger.warning("popover close-hook attach failed (window will die "
                           "on Alt+F4): %s", e)
        self._attach_native_closing()

    def _attach_native_closing(self):
        """Subscribe `_on_native_closing` on the WinForms BrowserForm.

        create_window is synchronous for non-master windows (Control.Invoke),
        so `self._window.native` is the BrowserForm by now; subscribing after
        pywebview's own FormClosing handler lets ours undo the args.Cancel
        that `_on_closing`'s False return set. Fail-closed: without it the
        popover just keeps the pre-review behavior (hides on every close).
        """
        try:
            form = getattr(self._window, "native", None)
            if form is None:
                logger.debug("popover native form not available; session-end "
                             "close will be vetoed like a user close")
                return
            form.FormClosing += self._on_native_closing
        except Exception as e:
            logger.debug("popover native closing-hook attach failed: %s", e)

    def _on_native_closing(self, sender, args):
        """Native FormClosing, runs AFTER pywebview's `on_closing` on the
        WinForms UI thread. Windows shutdown / log-off (WindowsShutDown), Task
        Manager "End task" (TaskManagerClosing) and Application.Exit
        (ApplicationExitCall) must not be cancelled -- a cancelled
        WM_QUERYENDSESSION returns 0 and Windows blocks the shutdown on the
        "Flume is preventing..." screen. Only UserClosing (X / Alt+F4, and
        Form.Close() from destroy(), which _on_closing already lets through)
        keeps the veto.
        """
        try:
            import System.Windows.Forms as WinForms
            if args.CloseReason == WinForms.CloseReason.UserClosing:
                return
            logger.info("popover: close reason %s -- allowing destroy",
                        args.CloseReason)
            self._destroying = True
            args.Cancel = False
        except Exception as e:
            logger.debug("popover native closing-hook failed: %s", e)

    def _on_closing(self, window=None, *_):
        """FormClosing interceptor -- runs ON the WinForms UI thread.

        Keep it trivial: `hide()` is safe (Control.Invoke on the owning thread
        runs synchronously) but `evaluate_js` -- so `_emit`/`_refresh` -- would
        deadlock here (it blocks on a semaphore released via the UI thread's
        sync context). Returning False cancels the destruction.
        """
        # Programmatic teardown -- allow. `app._exiting` covers win_main
        # _hard_exit's generic `for w in webview.windows: w.destroy()` sweep,
        # which bypasses our destroy() and would otherwise be vetoed here.
        if self._destroying or getattr(self.app, "_exiting", False):
            return None
        try:
            logger.info("popover: close intercepted -- hiding (window kept alive)")
            self._visible = False
            w = window if window is not None else self._window
            if w is not None:
                w.hide()
        except Exception as e:
            logger.debug("popover close intercept failed: %s", e)
        return False

    def _reset_refs(self):
        self._window = None
        self._bridge = None
        self._api = None
        self._loaded = False
        self._visible = False
        self._pending_events = []
        self._destroying = False

    def _on_closed(self, window=None, *_):
        """The form really was destroyed. Drop every reference so the next
        show()/toggle() rebuilds instead of calling show() on a dead handle
        (silent no-op -- the 2026-08-26 failure mode)."""
        try:
            with self._build_lock:
                if window is None or window is self._window:
                    self._reset_refs()
            logger.info("popover window destroyed -- next show() rebuilds")
        except Exception as e:
            logger.debug("popover closed-hook failed: %s", e)

    def destroy(self):
        """Programmatic teardown (quit). The only path _on_closing lets through."""
        w = self._window
        self._destroying = True
        try:
            if w is not None:
                w.destroy()
        except Exception as e:
            logger.debug("popover destroy failed: %s", e)
        with self._build_lock:
            if self._window is w:
                self._reset_refs()

    def _window_alive(self):
        """False once pywebview has pruned our window from `webview.windows`
        (its on_close does that before `closed` fires)."""
        if self._window is None:
            return False
        try:
            import webview
            return self._window in webview.windows
        except Exception:
            return True                      # can't tell -- keep old behavior

    def _wait_shown(self):
        """True once the form raised Shown. move()/show() are `_shown_call`
        methods that each block 20s and raise when `shown` never fires
        (WebView2 failed to initialise the form); bound that here so a tray
        click degrades to one warning instead of a silent 40s stall. The
        handle is kept -- still alive in `webview.windows` -- so the next
        click retries."""
        try:
            ev = self._window.events.shown
            if ev.is_set() or ev.wait(SHOWN_WAIT_S):
                return True
            logger.warning("popover: form not shown after %ss -- skipping "
                           "this open", SHOWN_WAIT_S)
            return False
        except Exception as e:
            logger.debug("popover shown-wait failed (%s) -- proceeding", e)
            return True                      # can't tell -- keep old behavior

    def _on_loaded(self):
        self._loaded = True
        # Keep the popover hidden after WebView2's initial paint — surface
        # only via show()/toggle().
        if not self._visible:
            try:
                self._window.hide()
            except Exception:
                pass
        # WebView2 doesn't resolve implicit viewport-height parents the way
        # WKWebView does — inject a host-side height anchor so `.recscroll`
        # inside popover_html actually scrolls. See
        # shared_dashboard._inject_scroll_fix for the full rationale.
        try:
            self._inject_scroll_fix()
        except Exception as e:
            logger.debug("popover: scroll-fix failed: %s", e)
        # Flush events emitted before the DOM was ready.
        pending = list(self._pending_events)
        self._pending_events.clear()
        for ev, payload in pending:
            self._emit(ev, payload)

    def _position(self):
        """Bottom-right of the primary work area — near the tray."""
        # Work area is PHYSICAL; pywebview 5.3's move() multiplies by the DPI
        # scale (logical) while create/resize are physical — at 150-200 % the
        # popover was half-size and pushed off-screen ("tray click does
        # nothing"). One DPI-aware SetWindowPos instead (rule #71).
        try:
            wa = wt.RECT()
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETWORKAREA, 0, ctypes.byref(wa), 0)
            form = getattr(self._window, "native", None) if self._window else None
            hwnd = form.Handle.ToInt64() if form is not None else None
            h = self._height()
            if hwnd:
                scale = win_geometry.system_scale()
                x = wa.right - int((WIN_W + 12) * scale)
                y = wa.bottom - int((h + 12) * scale)
                win_geometry.set_window_rect(hwnd, x, y, WIN_W, h, scale)
            elif self._window:
                self._window.move(wa.right - WIN_W - 12, wa.bottom - h - 12)
        except Exception as e:
            logger.debug("popover position failed: %s", e)

    def _height(self):
        """Window height in CSS px: the page-reported content height, clamped
        to the work area so a long Recent list can never push the menu off
        the top of the screen."""
        try:
            wa = wt.RECT()
            ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(wa), 0)
            scale = win_geometry.system_scale() or 1.0
            cap = int((wa.bottom - wa.top) / scale) - 24
        except Exception:
            cap = MAX_H
        return max(MIN_H, min(int(self._content_h or WIN_H), min(MAX_H, cap)))

    def set_content_height(self, h):
        """Called from the page (popover_resize) whenever its content height
        changes — a submenu opening, a row appearing. Re-fit while visible."""
        h = int(h)
        if h <= 0 or h == self._content_h:
            return
        self._content_h = h
        if self._visible:
            self.app._on_main(self._position)

    def rec_elapsed(self):
        return (time.time() - self._rec_started_at) if self._rec_started_at else 0.0

    # ── show / hide / toggle ────────────────────────────────────
    def show(self):
        try:
            with self._build_lock:
                if self._window is not None and not self._window_alive():
                    # closed-hook missed / raced -- never show() a dead handle.
                    logger.info("popover: stale handle -- rebuilding")
                    self._reset_refs()
                if not self._window:
                    self._build()
            if self._window is None:
                return
            # _visible BEFORE wait_shown: `_on_loaded` fires on a pywebview
            # thread and hides when _visible is False, so a load during the
            # Shown wait used to hide the first open.
            self._visible = True
            if not self._wait_shown():
                self._visible = False
                return
            self._position()
            # Window.show() does NOT raise on a dead handle (winforms show(uid)
            # silently returns when the uid has no BrowserView), so there is
            # deliberately no rebuild-on-exception here: _window_alive() above
            # is the dead-handle guard, and a rebuild triggered by the `shown`
            # timeout would only orphan a second form.
            self._window.show()
            self._refresh()
            self._emit("opened", {})
        except Exception as e:
            logger.error("popover show failed: %s", e)

    def hide(self):
        try:
            if self._window:
                self._window.hide()
        except Exception as e:
            logger.debug("popover hide failed: %s", e)
        self._visible = False

    def close(self):
        self.hide()

    def toggle(self):
        if self._visible:
            self.hide()
        else:
            self.show()

    @property
    def visible(self):
        return self._visible

    def _inject_scroll_fix(self):
        # Menu-style page (2026-08-29): the window is fitted to the content, so
        # the only job left here is to make sure nothing ever scrolls.
        css = "html,body{overflow:hidden}"
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
            logger.debug("popover scroll-fix injection failed: %s", e)

    # ── VerbalNative event push (parity with FlumePopover._emit) ──
    def _emit(self, event, payload):
        if not self._loaded:
            self._pending_events.append((event, payload))
            return
        if not self._window:
            return
        try:
            js = "if(window.VerbalNative)window.VerbalNative(%s,%s);" % (
                json.dumps(event), json.dumps(payload, default=str))
            self._window.evaluate_js(js)
        except Exception as e:
            logger.debug("popover emit %s failed: %s", event, e)

    def _refresh(self):
        try:
            # Sync device fields from the real dashboard so DashboardApi's
            # get_state (which reads self._known_devices / _target_device_id
            # from the "dashboard" arg — us) reports the shared view.
            d = getattr(self.app, "dashboard", None)
            if d is not None:
                self._known_devices = list(getattr(d, "_known_devices", []) or [])
                self._target_device_id = getattr(d, "_target_device_id", "__all__")
        except Exception:
            pass
        if not self._api:
            return
        try:
            self._emit("state", self._api.get_state())
        except Exception as e:
            logger.debug("popover refresh failed: %s", e)

    # ── methods the record → transcribe → inject pipeline calls ──
    def update_recording_state(self, is_recording):
        self._rec_started_at = time.time() if is_recording else 0.0
        self._emit("recordingState", {"recording": bool(is_recording)})

    def show_result(self, text):
        self._emit("result", {"text": text})

    # ── SharedDashboard shape DashboardApi expects on its `dashboard` arg ──
    def _load_devices(self):
        """DashboardApi.save_settings() (and the periodic refresh loop) calls
        this on the "dashboard" it was constructed with. Delegate to the real
        dashboard's implementation so device sync stays consistent."""
        try:
            d = getattr(self.app, "dashboard", None)
            if d is not None and hasattr(d, "_load_devices"):
                d._load_devices()
        except Exception as e:
            logger.debug("popover _load_devices delegate failed: %s", e)
