"""Shared web dashboard for cross-platform desktop builds.

This is intentionally separate from the macOS AppKit dashboard so the current
Mac app remains untouched while Windows gets the same product surface.
"""

from __future__ import annotations

import base64
import datetime as _dt
import logging
import os
import sys
import threading
import time
from typing import Any

import pyperclip

from app.config import (
    APP_VERSION,
    NOTES_FEATURE_FLAGS,
    PIPELINE_FLAGS,
    _entry_app,
    _entry_text,
    feature_flag,
    get_daily_words,
    load_config,
    save_config,
)

logger = logging.getLogger("verbal.shared_dashboard")


def _session_dead(cfg) -> bool:
    """`auth.session_dead` behind a fail-closed wrapper — get_state must never
    blow up because the auth module changed shape (IDI-166)."""
    try:
        from app import auth as _auth
        return bool(_auth.session_dead(cfg))
    except Exception:
        return False


def _cloud_allowed(cfg=None) -> bool:
    """`auth.cloud_allowed` behind a fail-closed wrapper (IDI-170). False when
    signed out — every cloud path must AND this in, because `sync_user_id`
    alone used to survive sign-out and kept writing into the ex-account."""
    try:
        from app import auth as _auth
        return bool(_auth.cloud_allowed(cfg))
    except Exception:
        return False


# Shown once on the signed-out pane after a successful account deletion so the
# user doesn't read the sign-in wall as "deletion failed" (IDI-170).
ACCOUNT_DELETED_MSG = "Your account has been deleted."

# What the user-facing sync TOGGLE gates (IDI-171): history, notes, canvas and
# dictionary are "sync". Meetings + recording uploads are CAPTURE artifacts and
# stay gated on `cloud_allowed` alone — mirrored on mobile.
SYNC_OFF_MSG = "Sync is off — turn it on in Settings."


# Sentinel for "this write does not touch that column" (IDI-173). A canvas
# text-only save must NOT null the shared image, and an image-only save must NOT
# blank the shared text — the writer used to send BOTH columns on every call, so
# whichever surface the user didn't touch got wiped on the other devices.
KEEP = "__keep__"

# Menubar / tray / popover tab indices. ONE map for Mac (`flume_web_dashboard`)
# and Windows (`SharedDashboard`) — they drifted (Mac 3=settings/4=canvas,
# Windows the reverse), so the Windows tray popover's Preferences button opened
# Canvas (2026-08-26 follow-up). Integer callers must use these names, not
# literals; `show_tab("settings")` is preferred.
DASHBOARD_TAB = {
    0: "history",
    1: "history",
    2: "home",
    3: "settings",
    4: "canvas",
    5: "notes",
    6: "home",
}


def device_identity(app):
    """(device_id, device_name) for THIS device.

    `device_id` is the SAME stable id the `devices` table rows and the
    SyncClient use (`platform.node()`), which is what canvas origin filtering is
    keyed on now (IDI-173) — two devices sharing a display name used to drop
    each other's canvas updates. `device_name` defaults to the machine's real
    name, never the hardcoded "Windows" the writer used to send while the mac
    listener compared against ""."""
    import platform
    from app.config import get_device_id
    cfg = getattr(app, "config", None) or {}
    sync = getattr(app, "_sync", None)
    device_id = (getattr(sync, "device_id", "") or get_device_id(cfg) or "").strip()
    name = (cfg.get("sync_device_name") or "").strip()
    if not name:
        name = (getattr(sync, "device_name", "") or platform.node() or "").strip()
    return device_id, name


def canvas_is_own_event(record, my_device_id, my_device_name) -> bool:
    """Origin filter for a canvas realtime event (IDI-173). Pure — every
    listener (mac dashboard, Windows dashboard, native canvas window) uses it so
    the rule cannot drift.

    device_id wins whenever the event HAS one; the display-name compare is only
    a fallback for rows written by clients that predate the column."""
    if not isinstance(record, dict):
        return False
    rec_id = (record.get("device_id") or "").strip()
    if rec_id:
        return bool(my_device_id) and rec_id == my_device_id
    rec_name = (record.get("device_name") or "").strip()
    return bool(rec_name) and bool(my_device_name) and rec_name == my_device_name


def _ok(**data):
    return {"ok": True, **data}


def _err(message: str):
    return {"ok": False, "error": message}


# ── Notes v2 sync contract (see NOTES_ENHANCEMENT_SWARM.md, Agent E) ──────────
# Two devices that edited the SAME note within this many seconds are treated as a
# conflict pair: BOTH versions are kept locally (never silently discarded) and both
# are flagged so the editor can surface a one-time "resolve" prompt.
NOTES_CONFLICT_WINDOW_SECONDS = 60

# Known note fields. Anything NOT in here is an "unknown" field from a newer client
# and MUST be preserved verbatim on merge/write-back (forward-compat, Decision 7).
_NOTE_KNOWN_FIELDS = {
    "id", "title", "content", "raw_content", "audio_segments", "folder",
    "is_pinned", "device_name", "created_at", "updated_at",
    "conflict", "conflict_of", "source",
}


def _parse_iso(s):
    """Parse an ISO-8601 timestamp; return a datetime or None. Never raises."""
    if not s:
        return None
    try:
        v = str(s).replace("Z", "+00:00")
        dt = _dt.datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return dt
    except Exception:
        return None


def _union_audio_segments(a, b):
    """UNION two append-only audio-segment lists, de-duped by segment id (then url),
    ordered by created_at. Malformed entries are dropped. Never raises."""
    out, seen = [], set()
    for seg in list(a or []) + list(b or []):
        if not isinstance(seg, dict):
            continue
        sid = seg.get("id") or seg.get("url")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(seg)
    out.sort(key=lambda s: s.get("created_at", "") or "")
    return out


def _notes_conflict(a, b):
    """True iff a and b were edited within the conflict window AND diverge in a
    user-meaningful field (title/content/raw_content)."""
    ta, tb = _parse_iso(a.get("updated_at")), _parse_iso(b.get("updated_at"))
    if ta is None or tb is None:
        return False
    if abs((ta - tb).total_seconds()) > NOTES_CONFLICT_WINDOW_SECONDS:
        return False
    return (
        (a.get("content", "") or "") != (b.get("content", "") or "")
        or (a.get("title", "") or "") != (b.get("title", "") or "")
        or (a.get("raw_content") or "") != (b.get("raw_content") or "")
    )


def merge_remote_note(by_id, cand):
    """Merge one remote note dict `cand` into the {id: note} map `by_id`, in place.

    Contract (mirrored on mobile in lib/notesStorage.ts):
      • audio_segments UNION on every merge (append-only, never lost).
      • Unknown fields (newer-client columns) preserved verbatim from both sides.
      • Conflict pair: if local & remote edited the same note within
        NOTES_CONFLICT_WINDOW_SECONDS and diverge, keep BOTH — the newer keeps the
        canonical id (conflict=True, conflict_of=None); the older is stored under a
        deterministic id "<id>::conflict::<updated_at>" (conflict=True,
        conflict_of=<id>). Deterministic id => idempotent across repeated fetches.
      • Otherwise last-write-wins on known fields, unknowns unioned.
    Never raises.
    """
    rid = cand.get("id")
    if not rid:
        return
    ex = by_id.get(rid)
    if not ex:
        by_id[rid] = cand
        return

    merged_segments = _union_audio_segments(ex.get("audio_segments"), cand.get("audio_segments"))

    if _notes_conflict(ex, cand):
        newer, older = (
            (cand, ex)
            if (cand.get("updated_at", "") or "") >= (ex.get("updated_at", "") or "")
            else (ex, cand)
        )
        winner = dict(older)          # preserve older's unknown fields first
        winner.update(newer)          # newer's known+unknown fields win
        winner["audio_segments"] = merged_segments
        winner["conflict"] = True
        winner["conflict_of"] = None
        by_id[rid] = winner

        copy_id = f"{rid}::conflict::{older.get('updated_at', '') or ''}"
        copy = dict(older)
        copy["id"] = copy_id
        copy["conflict"] = True
        copy["conflict_of"] = rid
        copy["audio_segments"] = _union_audio_segments(older.get("audio_segments"), [])
        by_id[copy_id] = copy
        return

    # No conflict: last-write-wins, but preserve unknown fields from both sides.
    base = dict(ex)
    if (cand.get("updated_at", "") or "") >= (ex.get("updated_at", "") or ""):
        base.update(cand)             # remote newer: its values win, adds its unknowns
    else:
        for k, v in cand.items():     # local newer: keep local, add only missing keys
            base.setdefault(k, v)
    base["audio_segments"] = merged_segments
    by_id[rid] = base


class SharedDashboard:
    def __init__(self, app):
        self.app = app
        self._window = None
        # MER-46: see FlumeWebDashboard.__init__ — events emitted before the page
        # installs VerbalNative are queued, not dropped, so `open_meeting` can
        # show() a window and push into it immediately.
        self._page_ready = False
        self._pending = []
        self._target_device_id = "__all__"
        self._known_devices = []
        self._last_canvas_loaded = False
        self._canvas_listener_started = False
        self._canvas_stop = threading.Event()
        self._device_refresh_started = False
        self._build_lock = threading.Lock()

    def ensure_window_size(self, min_w, min_h=0):
        """Grow (never shrink) the pywebview dashboard window (Windows host).

        DPI TRAP (verified live on the winvm at 200% scaling, 2026-08-15):
        `min_w`/`min_h` arrive in CSS/logical px, but pywebview's EdgeChromium
        backend REPORTS `window.width/height` in PHYSICAL pixels and
        `resize()` SETS physical pixels (a 980-logical window reports 1934,
        and resize(1220,700) SHRANK it to 597 CSS px of innerWidth). Scale the
        requested minimums by the system DPI before comparing/resizing —
        at 96 dpi this is a no-op, so unscaled displays keep the old behavior.
        pywebview's resize marshals to the GUI thread itself. Fail-closed."""
        try:
            w = self._window
            if not w:
                return
            scale = 1.0
            try:
                import ctypes
                dpi = ctypes.windll.user32.GetDpiForSystem()
                if dpi:
                    scale = dpi / 96.0
            except Exception:
                pass   # pre-1607 Windows → assume unscaled; force3 CSS saves the flow
            cur_w = int(getattr(w, "width", 0) or 0)
            cur_h = int(getattr(w, "height", 0) or 0)
            new_w = max(cur_w, int(float(min_w) * scale))
            new_h = max(cur_h, int(float(min_h or 0) * scale))
            if new_w != cur_w or new_h != cur_h:
                w.resize(new_w, new_h)
        except Exception as e:
            logger.debug(f"ensure_window_size failed: {e}")

    def _window_alive(self):
        """False once pywebview has pruned our window from `webview.windows`
        (its on_close does that BEFORE `closed` fires). `Window.show()` on a
        dead uid is a silent no-op — the same failure that broke Start meeting
        (#67). Dashboard X is *supposed* to destroy the form (unlike meeting/
        popover, which hide); `_on_window_closed` drops the handle, but a
        reopen that races `closed` — or a missed hook — still has to rebuild
        rather than poke the corpse."""
        if self._window is None:
            return False
        try:
            import webview
            return self._window in webview.windows
        except Exception:
            return True

    def _on_window_closed(self, window=None, *_):
        # Only the CURRENT window may drop the handle: a stale/orphaned form
        # closing later must not null the live one (next show() would build a
        # third window). pywebview passes the closing Window as first arg.
        if window is not None and window is not self._window:
            return
        self._window = None
        self._page_ready = False
        self._maybe_show_tray_close_hint()

    # X on the dashboard deliberately leaves Flume running in the tray (the
    # hotkey must keep working with no window open). Users read the missing
    # window as "closed" and then find Flume.exe in Task Manager: "when I close
    # the program it doesn't quit properly and I can see it running in task
    # manager" (2026-08-26). One toast, the first time only, says where Quit is.
    TRAY_CLOSE_HINT_KEY = "tray_close_hint_shown"
    TRAY_CLOSE_HINT_TEXT = (
        "Flume is still running in the system tray so your hotkey keeps working. "
        "To quit completely, right-click the tray icon and choose Quit."
    )

    def _maybe_show_tray_close_hint(self):
        """Runs on pywebview's `closed` event. Fail-closed and cheap: only a
        dict check + flag set happen here; the config write and the toast go to
        a daemon thread (winotify shells out to PowerShell and must not stall
        the GUI thread that is tearing the window down)."""
        try:
            if os.name != "nt":
                return
            # _hard_exit sets this before destroying windows on the way out —
            # that `closed` is not the user closing a window, so no hint.
            if getattr(self.app, "_exiting", False):
                return
            cfg = getattr(self.app, "config", None)
            if not isinstance(cfg, dict) or cfg.get(self.TRAY_CLOSE_HINT_KEY):
                return
            cfg[self.TRAY_CLOSE_HINT_KEY] = True   # in-memory first: never twice
            threading.Thread(target=self._show_tray_close_hint,
                             name="tray-close-hint", daemon=True).start()
        except Exception as e:
            logger.debug("tray close hint skipped: %s", e)

    def _show_tray_close_hint(self):
        try:
            save_config(self.app.config)
        except Exception as e:
            logger.debug("tray close hint flag not persisted: %s", e)
        title = "Flume"
        # Same backend order as _notify_native (which is Canvas-titled), each
        # step guarded; no backend at all just means no hint.
        try:
            from winotify import Notification
            Notification(app_id="Flume", title=title, msg=self.TRAY_CLOSE_HINT_TEXT).show()
            return
        except Exception as e:
            logger.debug("tray close hint: winotify unavailable: %s", e)
        try:
            icon = getattr(self.app, "_tray_icon", None)
            if icon is not None and hasattr(icon, "notify"):
                icon.notify(self.TRAY_CLOSE_HINT_TEXT, title)
        except Exception as e:
            logger.debug("tray close hint: tray notify unavailable: %s", e)

    def show(self):
        try:
            import webview
        except Exception as e:
            logger.error(f"pywebview is not available: {e}")
            from app.win_dashboard import WinDashboard

            fallback = WinDashboard(self.app)
            fallback.show()
            return

        need_start = False
        with self._build_lock:
            if self._window is not None and not self._window_alive():
                logger.info("dashboard: stale handle -- rebuilding")
                self._window = None
                self._page_ready = False
            if self._window:
                try:
                    self._window.show()
                except Exception as e:
                    # Rule #67: never rebuild on a show() exception — that is
                    # the 20 s `shown` timeout (WebView2 mid-update), and a
                    # rebuild orphans a live form. Keep the handle; retry later.
                    logger.warning("dashboard show() raised (%s); keeping handle", e)
                return

            # Render the SAME dark "Flume" UI the macOS app uses. flume_html() is
            # already dual-target: it waits for `pywebviewready` and calls the shared
            # DashboardApi via window.pywebview.api.* (native under pywebview here;
            # shimmed inside WKWebView on macOS). This is what gives Windows visual
            # parity with the Mac app instead of the retired light-theme dashboard.
            from app.flume_dashboard_html import flume_html

            api = DashboardApi(self)
            # A rebuild means a fresh page: a stale `_page_ready` from the previous
            # window would let emits fire at a page that has no VerbalNative yet.
            self._page_ready = False
            # pywebview 5.3 applies these as PHYSICAL pixels — scale so the
            # CSS viewport really is 1240x740 on HiDPI (app.win_geometry).
            from app import win_geometry
            _w, _h = win_geometry.create_size(1240, 740)
            _min = (760, 520)              # logical — WinForms autoscales min_size itself
            _t_create = time.time()
            self._window = webview.create_window(
                "Flume",
                html=flume_html(),
                js_api=api,
                # 2026-08-17 (corrected): WIDE default (matches macOS) — the
                # multi-pane screens want horizontal room, and >1000px keeps the
                # Notes Studio pane visible. Height stays modest.
                width=_w,
                height=_h,
                min_size=_min,
                background_color="#0e1012",
            )
            logger.info("dashboard: window created in %.2fs (%.1fs after launch)",
                        time.time() - _t_create,
                        time.time() - getattr(sys, "_verbal_start_time", time.time()))
            # Windows: inject a CSS override that anchors `.screen` sections to
            # viewport height. WKWebView on macOS resolves the shared HTML's
            # `.main { height: 100% }` against an implicit viewport-height
            # ancestor; WebView2 doesn't, so `.main` collapses to content and
            # overflow-y:auto has nothing to scroll (History/Notes escape this
            # because .threepane already sets height:100vh explicitly). Keep the
            # shared HTML untouched — this fix is host-side only.
            try:
                # X on the title bar destroys the pywebview window; drop our
                # reference so the next show() (tray, or a second launch signalling
                # the running app) rebuilds instead of poking a dead handle.
                self._window.events.closed += self._on_window_closed
                self._window.events.loaded += self._inject_scroll_fix
                # Belt-and-braces flush, same reasoning as win_meeting_window._on_loaded:
                # on WebView2 the JS-initiated handshake can lose the bridge-init race
                # on a freshly-created window. Idempotent — the second flush finds an
                # empty queue.
                self._window.events.loaded += self.page_ready
            except Exception as e:
                logger.debug("scroll-fix hook attach failed: %s", e)
            if not self._device_refresh_started:
                self._device_refresh_started = True
                threading.Thread(target=self._device_refresh_loop, daemon=True).start()
            if not self._canvas_listener_started:
                self._canvas_listener_started = True
                threading.Thread(target=self._canvas_listen_loop, daemon=True).start()
            # W3 (Windows): win_main already called webview.start() with the
            # hidden anchor. pywebview only supports one start() per process.
            # Do NOT start() while holding `_build_lock` — start() blocks the
            # GUI loop until every window is gone.
            if not getattr(webview, "_verbal_started", False):
                webview._verbal_started = True
                need_start = True
        if need_start:
            webview.start(debug=False)

    def _inject_scroll_fix(self):
        """WebView2 needs `.screen` to have an explicit height for `.main`'s
        overflow-y:auto to work. Injected once per window load. Idempotent —
        re-running just replaces the style element with the same content."""
        css = (
            "html,body{height:100vh;overflow:hidden}"
            "section.screen{height:100vh;overflow:hidden}"
            "section.screen>.main{height:100%;overflow-y:auto;overflow-x:hidden}"
        )
        js = (
            "(function(){"
            "var id='__verbal_scroll_fix';"
            "var el=document.getElementById(id);"
            "if(!el){el=document.createElement('style');el.id=id;document.head.appendChild(el);}"
            "el.textContent=" + repr(css) + ";"
            "})();"
        )
        try:
            if self._window:
                self._window.evaluate_js(js)
        except Exception as e:
            logger.debug("scroll-fix injection failed: %s", e)

    def update_recording_state(self, is_recording: bool):
        self._emit("recordingState", {"recording": is_recording})

    def show_result(self, text: str):
        self._emit("result", {"text": text})

    def _on_tab_select(self, idx):
        tab_name = DASHBOARD_TAB.get(idx, "home")
        self._emit("selectTab", {"tab": tab_name})

    def show_tab(self, tab: str):
        """Open the dashboard on a named screen (`history`/`home`/`canvas`/
        `settings`/`notes`). Preferred over `_on_tab_select(int)` so Mac and
        Windows cannot drift on the integer map again."""
        self.show()
        self._emit("selectTab", {"tab": tab})

    def _refresh(self):
        self._emit("state", DashboardApi(self).get_state())

    def _emit(self, event: str, payload: dict[str, Any]):
        if not self._window:
            return          # never built — dropping is still correct (as before)
        if not self._page_ready:
            self._pending.append((event, payload))
            if len(self._pending) > 200:        # bound the buffer
                self._pending = self._pending[-200:]
            return
        try:
            import json

            js = f"window.VerbalNative && window.VerbalNative({json.dumps(event)}, {json.dumps(payload)});"
            self._window.evaluate_js(js)
        except Exception as e:
            logger.debug(f"Dashboard emit failed: {e}")

    def page_ready(self):
        """Called (via the bridge) when the page JS has installed VerbalNative."""
        self._page_ready = True
        pending, self._pending = self._pending, []
        for event, payload in pending:
            self._emit(event, payload)

    def _cloud_sync_on(self) -> bool:
        """The uniform desktop sync gate (IDI-171): user toggle AND signed in
        AND we have an account id. Applies to history/notes/canvas/dictionary —
        NOT to meetings/recording uploads (capture artifacts, `_cloud_allowed`
        only)."""
        cfg = self.app.config
        return bool(cfg.get("sync_user_id") and cfg.get("sync_enabled")
                    and _cloud_allowed(cfg))

    def _device_refresh_loop(self):
        while True:
            try:
                self._load_devices()
            except Exception as e:
                logger.debug(f"Device refresh failed: {e}")
            time.sleep(30)

    def _load_devices(self):
        cfg = self.app.config
        user_id = cfg.get("sync_user_id", "")
        # List devices whenever SIGNED IN — not gated on the live SyncClient, so a
        # signed-in-but-sync-off device still shows its account's other devices
        # (mirrors flume_web_dashboard._load_devices).
        # This loop no longer HEARTBEATS: presence moved to the app-level
        # `win_main._presence_loop` so closing/never-opening the dashboard can't
        # make this device look Offline to the others (IDI-177).
        if not user_id or not _cloud_allowed(cfg):
            self._known_devices = []
            return
        import platform
        from app.sync import fetch_account_devices

        my_id = self.app._sync.device_id if getattr(self.app, "_sync", None) else platform.node()
        devices = fetch_account_devices(user_id, my_id)
        self._known_devices = devices
        # Ensure our target_device_id is still valid if it was a specific device
        if self._target_device_id not in ("__all__", "__none__") and self._target_device_id is not None:
            if not any(d["device_id"] == self._target_device_id for d in devices):
                self._target_device_id = "__all__"
        self._emit("devices", {"devices": devices, "target_device_id": self._target_device_id})

    def stop_canvas_listener(self):
        """Signal the canvas listener thread to exit (IDI-173)."""
        self._canvas_stop.set()

    def _canvas_listen_loop(self):
        """Keep canvas synced while the dashboard is open.

        Stop-checked EVERY iteration (was `while True`): the thread is started
        once and latched by `_canvas_listener_started`, so without this it
        outlived sign-out and every window close for the life of the process."""
        while not self._canvas_stop.is_set():
            try:
                self._canvas_listen_once()
            except Exception as e:
                logger.debug(f"Canvas listener failed: {e}")
            self._canvas_stop.wait(5)

    def _notify_native(self, text):
        """Best-effort Windows toast (fail closed). Gives visible confirmation that
        canvas content arrived even when the dashboard isn't on the Canvas tab.

        Tries, in order: winotify → win10toast → the pystray tray icon's
        notify(). Every path is guarded; if all are unavailable we just log at
        debug. This must NEVER raise."""
        safe = (text or "").strip()
        if not safe:
            return
        title = "Flume Canvas"

        # 1. winotify (lightweight, no COM server thread)
        try:
            from winotify import Notification
            toast = Notification(app_id="Flume", title=title, msg=safe)
            toast.show()
            return
        except Exception as e:
            logger.debug(f"winotify notify unavailable: {e}")

        # 2. win10toast
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(title, safe, duration=5, threaded=True)
            return
        except Exception as e:
            logger.debug(f"win10toast notify unavailable: {e}")

        # 3. Fall back to the pystray tray icon's notify(), if the app exposes one
        try:
            icon = getattr(self.app, "_tray_icon", None)
            if icon is not None and hasattr(icon, "notify"):
                icon.notify(safe, title)
                return
        except Exception as e:
            logger.debug(f"tray notify unavailable: {e}")

        logger.debug("Native notify: no toast backend available")

    def _canvas_listen_once(self):
        import json
        import websocket

        from app.sync import SUPABASE_KEY, WS_URL
        from app.auth import get_access_token

        user_id = self.app.config.get("sync_user_id", "")
        my_device_id, my_device_name = device_identity(self.app)
        # Canvas is "sync" (IDI-171): the user toggle gates it, and being
        # signed in gates it again.
        if not user_id or not self._cloud_sync_on() or self._canvas_stop.is_set():
            time.sleep(5)
            return

        # MER-29: forward the signed-in user's JWT (falls back to the anon key)
        # so a future auth.uid()-scoped policy on `canvas` doesn't also require
        # a Realtime protocol change at cutover time.
        ws_token = get_access_token(self.app.config) or SUPABASE_KEY

        def on_open(ws):
            ws.send(
                json.dumps(
                    {
                        "topic": "realtime:*",
                        "event": "phx_join",
                        "payload": {
                            "config": {
                                "postgres_changes": [
                                    {
                                        "event": "*",
                                        "schema": "public",
                                        "table": "canvas",
                                        "filter": f"user_id=eq.{user_id}",
                                    }
                                ]
                            },
                            "access_token": ws_token,
                        },
                        "ref": "shared_canvas",
                    }
                )
            )

        def on_message(ws, raw):
            try:
                msg = json.loads(raw)
                if msg.get("event") != "postgres_changes":
                    return
                record = msg.get("payload", {}).get("data", {}).get("record", {})
                # IDI-173: skip our OWN echo by stable device_id; fall back to
                # the display-name compare only for pre-device_id rows.
                if canvas_is_own_event(record, my_device_id, my_device_name):
                    return
                content = record.get("content", "") or ""
                image_url = record.get("image_url")
                from_name = record.get("device_name", "device")
                if content:
                    pyperclip.copy(content)
                    self._notify_native(f"Received from {from_name} — copied to clipboard")
                elif image_url:
                    # Copy the image URL so it's pasteable regardless of which tab is
                    # active (the WebView still renders the preview on the Canvas tab).
                    pyperclip.copy(image_url)
                    self._notify_native(f"Received image from {from_name} — link copied")
                else:
                    # An explicit clear (content '' + image null) is a real
                    # event, not a no-op — say so and let the emit below APPLY
                    # the empty state.
                    self._notify_native(f"{from_name} cleared the canvas")
                self._emit(
                    "canvasRemote",
                    {
                        "content": content,
                        "image_url": image_url,
                        "device_name": from_name,
                    },
                )
            except Exception as e:
                logger.debug(f"Canvas message ignored: {e}")

        ws = websocket.WebSocketApp(
            WS_URL,
            header={"Authorization": f"Bearer {ws_token}"},
            on_open=on_open,
            on_message=on_message,
        )
        ws.run_forever(ping_interval=25, ping_timeout=10)


# Spoken-language options (ISO-639-1) for dictation + meetings. 'auto' lets
# Whisper detect per request; anything else is pinned (more stable for chunked
# meeting audio). Non-English pins route to full whisper-large-v3.
SPOKEN_LANGUAGES = [
    ("auto", "Auto-detect"), ("en", "English"), ("ur", "Urdu"), ("hi", "Hindi"),
    ("ar", "Arabic"), ("es", "Spanish"), ("fr", "French"), ("de", "German"),
    ("pt", "Portuguese"), ("tr", "Turkish"), ("id", "Indonesian"), ("ru", "Russian"),
    ("zh", "Chinese"), ("ja", "Japanese"),
]


class DashboardApi:
    def __init__(self, dashboard: SharedDashboard):
        self.dashboard = dashboard

    @property
    def app(self):
        return self.dashboard.app

    def get_update_status(self):
        """Polled by the dashboard's update banner + Settings > Updates. Read-only
        snapshot of state the host App owns (_update_available/_phase/_progress;
        main.py on macOS, win_main.py on Windows) — this never mutates anything,
        so it's safe to poll on a timer.

        Fail-closed via getattr: this used to read `app._update_available`
        directly, and on Windows — where VerbalWinApp only had `_pending_update`
        — every 30 s poll raised AttributeError into the log for the whole
        session (2026-08-26 report, Flume 1.0.33). A host that lacks the state
        machine now just reports "no update" instead of erroring.
        """
        from app.config import APP_VERSION
        try:
            app = self.app
            avail = getattr(app, "_update_available", None)
            return _ok(
                current_version=APP_VERSION,
                available=({"version": avail.get("version"),
                            "changelog": avail.get("changelog", "")} if avail else None),
                phase=getattr(app, "_update_phase", "idle"),
                progress=float(getattr(app, "_update_progress", 0.0) or 0.0),
            )
        except Exception as e:
            return _err(str(e))

    # How long check_for_updates waits for the Supabase round-trip before
    # answering anyway. updater.check_for_update's httpx timeout is 5 s, so
    # this only trips on a hung socket — and then the answer is simply "no
    # update known yet"; the 30 s get_update_status poll catches up later.
    CHECK_UPDATES_WAIT_S = 8.0

    def check_for_updates(self):
        """Settings > Updates' "Check for Updates" button. suppress_prompt=True
        because this is an explicit, user-visible dashboard action — the native
        rumps.alert / tk dialog popping up on top of it would be a redundant
        second prompt for the same click. force=True skips updater's 30-second
        post-launch gate: that gate guards AUTOMATIC checks against auto-install
        loops, but a human clicking the button can't loop, and on Windows the
        gated click was a silent no-op (2026-08-26). (This is a small mac delta
        too: a click within 30 s of launch used to be a silent no-op there as
        well; now it performs the check. Harmless — mac has no auto-install
        loop to guard.)

        SYNCHRONOUS, bounded by CHECK_UPDATES_WAIT_S: the check runs to
        completion before this returns, and the reply carries `available`.
        It used to fire-and-forget and the JS polled get_update_status on a
        fixed 1.5 s timer — but check_for_update's request can take up to 5 s,
        so a slow Supabase round-trip made the very click this fix is about
        toast "You're up to date" and then grow an update banner on the next
        30 s poll. Blocking here is safe: both bridges (pywebview's js_api and
        flume_web_dashboard._dispatch) run API calls on their own daemon
        thread, never the GUI thread.
        """
        check = getattr(self.app, "_check_update", None)
        if not callable(check):
            return _err("update check unavailable")

        def _run():
            try:
                check(suppress_prompt=True, force=True)
            except Exception as e:
                logger.error(f"check_for_updates failed: {e}")

        try:
            t = threading.Thread(target=_run, name="update-check-now", daemon=True)
            t.start()
            t.join(self.CHECK_UPDATES_WAIT_S)
            if t.is_alive():
                logger.debug("check_for_updates: still running after %.0fs; answering with known state",
                             self.CHECK_UPDATES_WAIT_S)
        except Exception as e:
            return _err(str(e))
        avail = getattr(self.app, "_update_available", None)
        return _ok(available=bool(avail),
                   version=(avail.get("version") if isinstance(avail, dict) else None))

    def start_update_download(self):
        fn = getattr(self.app, "_start_update_download", None)
        if not callable(fn):
            return _err("update download unavailable")
        try:
            fn()
        except Exception as e:
            return _err(str(e))
        return _ok()

    def install_ready_update(self):
        fn = getattr(self.app, "_install_ready_update", None)
        if not callable(fn):
            return _err("update install unavailable")
        try:
            fn()
        except Exception as e:
            return _err(str(e))
        return _ok()

    def get_insights(self):
        """Insights payload from the local ledger + cached cloud aggregate —
        instant, no network. See app/insights.py for the data model."""
        try:
            from app import insights
            cfg = self.app.config = load_config()
            return _ok(**insights.compute(cfg))
        except Exception as e:
            return _err(str(e))

    def refresh_insights(self):
        """Fold any new cloud `transcriptions` rows into the stats cache
        (network — the bridge already runs api methods on a worker thread),
        then return the recomputed payload."""
        try:
            from app import insights
            cfg = self.app.config = load_config()
            insights.refresh_cloud(cfg, save_config)
            return _ok(**insights.compute(cfg))
        except Exception as e:
            return _err(str(e))

    def get_state(self):
        logger.info("dashboard: get_state (%.1fs after launch)",
                    time.time() - getattr(sys, "_verbal_start_time", time.time()))
        cfg = self.app.config = load_config()
        history = cfg.get("history", [])
        pinned = cfg.get("pinned", [])
        total_words = sum(len(_entry_text(h).split()) for h in history)
        return _ok(
            version=APP_VERSION,
            recording=self.app._is_recording,
            processing=self.app._processing,
            model=cfg.get("whisper_model", "base"),
            mode=cfg.get("recording_mode", "toggle"),
            daily_words=get_daily_words(cfg),
            total_transcriptions=len(history),
            total_words=total_words,
            history=[
                {
                    "id": e.get("id", "") if isinstance(e, dict) else "",
                    "text": _entry_text(e),
                    "app": _entry_app(e),
                    "ts": e.get("ts", "") if isinstance(e, dict) else "",
                    "status": e.get("status", "done") if isinstance(e, dict) else "done",
                    "has_audio": bool((e.get("audio") or e.get("audio_url")) if isinstance(e, dict) else False),
                }
                for e in history
            ],
            pinned=[
                {
                    "text": _entry_text(e),
                    "app": _entry_app(e),
                    "ts": e.get("ts", "") if isinstance(e, dict) else "",
                }
                for e in pinned
            ],
            settings={
                "groq_api_keys": cfg.get("groq_api_keys", []),
                "gemini_api_keys": cfg.get("gemini_api_keys", []),
                "sync_enabled": cfg.get("sync_enabled", False),
                "sync_user_id": cfg.get("sync_user_id", ""),
                "sync_device_name": (cfg.get("sync_device_name")
                                     or __import__("platform").node() or ""),
                "hotkey_hold": cfg.get("hotkey_hold", "alt_r"),
                "hotkey_toggle": cfg.get("hotkey_toggle", "alt_r"),
                # Notes v2 feature flags (default true) so Settings can toggle each.
                "notes_search_enabled": feature_flag(cfg, "notes_search_enabled"),
                "notes_autotitle_enabled": feature_flag(cfg, "notes_autotitle_enabled"),
                "notes_structure_detection_enabled": feature_flag(cfg, "notes_structure_detection_enabled"),
                "notes_audio_linkage_enabled": feature_flag(cfg, "notes_audio_linkage_enabled"),
                # Pipeline + model choice, so Settings can render the CURRENT state
                # instead of guessing. These default False/"auto", and the Settings
                # pipeline radio is DERIVED from the two flags rather than stored
                # separately — one source of truth, read by the dictation path itself.
                "speed_mode": feature_flag(cfg, "speed_mode", False),
                "chained_mode": feature_flag(cfg, "chained_mode", False),
                "hybrid_mode": feature_flag(cfg, "hybrid_mode", False),
                "asr_model": cfg.get("asr_model", "auto"),
            },
            sync_connected=bool(self.app._sync and self.app._sync.connected),
            devices=self.dashboard._known_devices,
            target_device_id=self.dashboard._target_device_id,
            signed_in=bool(cfg.get("auth") and cfg.get("auth", {}).get("user_id")),
            # IDI-166: a dead refresh token drops the tokens but keeps the
            # identity, so `signed_in` stays true while every JWT-only action
            # (account deletion above all) silently fails. Surface it so the
            # sidebar/Settings can say "Session expired — sign in again".
            session_dead=_session_dead(cfg),
            # Last interactive sign-in failure. The sign-in pane renders from
            # this, so a cancel/timeout can never latch the button again.
            auth_error=getattr(self.app, "_auth_error", "") or "",
            # Non-error one-shot message for the same pane — currently only
            # "Your account has been deleted." (IDI-170). Cleared when the next
            # sign-in attempt starts, same mechanism as auth_error.
            auth_notice=getattr(self.app, "_auth_notice", "") or "",
            user=({"email": cfg["auth"].get("email", ""),
                   "name": cfg["auth"].get("name", ""),
                   "avatar_url": cfg["auth"].get("avatar_url", "")}
                  if cfg.get("auth", {}).get("user_id") else None),
            onboarded=bool(cfg.get("onboarded")),
        )

    def get_permissions(self):
        try:
            from app import permissions
            return _ok(perms=permissions.all_status())
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def request_permission(self, which):
        try:
            from app import permissions
            return _ok(perms=permissions.request(which))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Meetings (MEETINGS_DESIGN_HANDOFF.md) — all fail closed ─────────────────
    def get_meeting_permissions(self):
        """Aggregate status for the PermissionChecklistModal (31h)."""
        try:
            from app import permissions
            return permissions.meeting_permissions()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def meeting_permissions_skipped(self):
        """User chose 'Skip for now' — proceed to the pre-meeting modal; capture
        will run mic-only (system audio fails closed)."""
        try:
            self.app.config["meetings_skipped_system_audio"] = True
            save_config(self.app.config)
            self._meeting_mode("premeeting")
            return _ok()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def meeting_permissions_done(self):
        """All checklist steps complete + test passed → pre-meeting modal."""
        try:
            self.app.config.pop("meetings_skipped_system_audio", None)
            save_config(self.app.config)
            self._meeting_mode("premeeting")
            return _ok()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _meeting_win(self):
        """The meeting window via the app's LAZY accessor (`main._meeting_win`).

        These bridge methods used to read `getattr(app, "meeting_window", None)`
        directly, which is None until the window has been constructed once — so
        every call that arrived before that silently no-opped (IDI-178). The
        accessor constructs it on demand and still fails closed to None; it does
        no AppKit work (that happens in `MeetingWindow.show`), so it is safe from
        the bridge's worker thread."""
        try:
            accessor = getattr(self.app, "_meeting_win", None)
            if callable(accessor):
                return accessor()
        except Exception:
            pass
        return getattr(self.app, "meeting_window", None)

    def _meeting_mode(self, mode):
        try:
            win = self._meeting_win()
            if win:
                win.set_mode(mode)
        except Exception:
            pass

    def _notify(self, text, duration=2.5):
        """Ambient one-liner on the recording overlay pill. Fails closed."""
        try:
            ov = getattr(self.app, "overlay", None)
            if ov and hasattr(ov, "show_briefly"):
                self.app._on_main(lambda: ov.show_briefly(text, duration=duration))
        except Exception:
            pass

    def close_meeting_window(self):
        """Hide the meeting surface.

        Closing while the session is still finishing (drain → upload → summary)
        used to be completely silent: the `stopping` state at least collapses to
        the ambient bar, but `processing` just vanished and the user had no idea
        notes were still being generated (IDI-178). Mirror the cue."""
        try:
            m = self._meetings()
            working = bool(m and getattr(m, "processing", None))
            win = self._meeting_win()
            if win:
                self.app._on_main(win.hide)
            if working:
                self._notify("✦ Still finishing your meeting notes…")
            return _ok(processing=working)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def meeting_bar_resize(self, width=0, height=0):
        """Windows meeting bar: the page reports the rendered pill size
        (ResizeObserver injected by win_meeting_window._on_loaded) and the
        host shrink-wraps the borderless window around it, so the bar is a
        floating pill instead of a 560px dark strip (WebView2 cannot do
        per-pixel transparency). No-op on hosts without the hook (macOS)."""
        fn = getattr(self.dashboard, "set_bar_content_size", None)
        if fn is None:
            return {"ok": False}
        try:
            fn(int(width or 0), int(height or 0))
            return {"ok": True}
        except Exception as e:
            logger.debug("meeting_bar_resize failed: %s", e)
            return {"ok": False}

    def confirm_native(self, message="", title="Flume"):
        """Windows meeting bar: a native Yes/No box instead of the page's
        confirm(), which WebView2 draws inside the (pill-sized) window. Hosts
        without the hook (macOS) report ok=False and the page keeps its own
        confirm()."""
        fn = getattr(self.dashboard, "native_confirm", None)
        if fn is None:
            return {"ok": False}
        try:
            return {"ok": True, "yes": bool(fn(str(message), str(title)))}
        except Exception as e:
            logger.debug("confirm_native failed: %s", e)
            return {"ok": False}

    def meeting_page_ready(self):
        """Page-load handshake from the meeting window's JS — flushes any
        events emitted before the page was ready."""
        try:
            d = self.dashboard
            if hasattr(d, "page_ready"):
                d.page_ready()
            return _ok()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def dashboard_page_ready(self):
        """Page-load handshake from the DASHBOARD's JS (MER-46).

        Same contract as meeting_page_ready. Needed because `open_meeting` can now
        target a dashboard window that show() built a millisecond earlier — its
        page has no `VerbalNative` yet, so the openMeeting event has to be queued
        and flushed here instead of evaporating."""
        try:
            d = self.dashboard
            if hasattr(d, "page_ready"):
                d.page_ready()
            return _ok()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def expand_meeting_window(self):
        """Bar → full window (fluid morph)."""
        try:
            win = self._meeting_win()
            if win:
                win.expand()
            return _ok()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def collapse_meeting_window(self):
        """Full window → ambient bar (only while a meeting records)."""
        try:
            win = self._meeting_win()
            if win:
                win.collapse()
            return _ok()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def test_meeting_capture(self):
        """3-second capture self-test (31h 'Test capture')."""
        try:
            from app.system_audio import run_capture_test
            return run_capture_test(self.app)
        except ImportError:
            return {"ok": False, "error": "Capture engine not installed in this build."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _meetings(self):
        """The app's MeetingManager, or None (Windows / disabled)."""
        return getattr(self.app, "meetings", None)

    def start_meeting(self, title="", use_mic=True, use_system=True, language=""):
        m = self._meetings()
        if not m:
            return {"ok": False, "error": "Meetings unavailable on this platform."}
        return m.start(title or "", use_mic=bool(use_mic), use_system=bool(use_system),
                       language=str(language or ""))

    def get_spoken_language(self):
        """Global spoken-language setting + the picker's option list."""
        try:
            return _ok(value=str(self.app.config.get("spoken_language", "en")),
                       options=SPOKEN_LANGUAGES)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_self_speaker_label(self):
        """Name shown for the mic speaker in a meeting (signed-in user's name, else "You")."""
        try:
            from app.meetings import self_speaker_label
            return _ok(value=self_speaker_label(self.app.config))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_spoken_language(self, value):
        try:
            value = str(value or "en").strip().lower()
            if value not in {c for c, _ in SPOKEN_LANGUAGES}:
                return {"ok": False, "error": "unknown language"}
            self.app.config["spoken_language"] = value
            save_config(self.app.config)
            return _ok()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def open_meeting_launcher(self):
        """Dashboard/popover 'Start meeting' — routes through the same flow as
        the menubar item (permission checklist vs pre-meeting modal)."""
        try:
            if hasattr(self.app, "_toggle_meeting"):
                self.app._on_main(self.app._toggle_meeting)
                return _ok()
            return {"ok": False, "error": "unavailable"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _dash(self):
        """The MAIN Flume window.

        Not `self.dashboard`: one DashboardApi is created per window (dashboard,
        meeting panel, transform widget), so `self.dashboard` is whichever window
        this bridge instance belongs to. Anything that must land in the main
        window goes through the app, exactly as delete_meeting already does."""
        return getattr(self.app, "dashboard", None)

    def open_meeting(self, meeting_id):
        """Open a meeting in the DASHBOARD's detail view (31e, MER-46).

        Was `meeting_window.show('summary')`. The panel holds ONE mode at a time,
        so a past meeting fought the live screen, could not be read while another
        meeting recorded, and got yanked back to the ambient bar the moment the
        panel lost focus mid-meeting. The detail view now lives in the Flume
        window right next to the list it was opened from; the panel is
        live-meeting-only."""
        try:
            m = self._meetings()
            # self.get_meeting (not m.get_meeting) so the Windows cloud
            # fallback applies — a Mac-captured meeting opens read-only there.
            got = self.get_meeting(meeting_id)
            if not got.get("ok"):
                return got
            row = got["meeting"]
            try:
                if m:
                    m.mark_meeting_opened(meeting_id)   # clears the NEW indicator
            except Exception:
                pass
            dash = self._dash()
            if dash is None:
                return {"ok": False, "error": "no dashboard"}

            def run():
                try:
                    dash.show()
                except Exception as e:
                    logger.debug("dashboard show failed: %s", e)
                # Buffered by the dashboard until its page handshakes, so this
                # works on a window that show() only just built (the bar handoff
                # is exactly that case).
                dash._emit("openMeeting", row)
                # Opening the meeting CONSUMES a leftover handoff bar — but never
                # touch the panel while a meeting is still capturing/finishing,
                # where the bar is the live HUD.
                try:
                    win = self._meeting_win()
                    busy = bool(m and (m.active or m.processing))
                    if win and win.visible and not busy:
                        win.hide()
                except Exception:
                    pass
            self.app._on_main(run)
            return _ok()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_meeting(self, meeting_id):
        m = self._meetings()
        res = m.delete(meeting_id) if m else {"ok": False, "error": "unavailable"}
        if res.get("ok"):
            try:  # the dashboard list lives in another window — tell it
                dash = getattr(self.app, "dashboard", None)
                if dash and hasattr(dash, "_emit"):
                    dash._emit("meetingsUpdated", {"deleted": meeting_id})
            except Exception:
                pass
        return res

    _MEETING_SETTING_KEYS = (
        "meetings_enabled", "meetings_keep_audio", "meetings_keep_audio_days",
        "meetings_max_minutes", "meetings_hud_enabled", "meetings_speaker_labels",
        "meetings_sync_enabled", "meetings_notes_language",
        # Post-meeting speaker diarization (needs keep-audio + signed-in upload,
        # since AssemblyAI fetches the WAV from the bucket by signed URL).
        "meetings_diarize_enabled",
    )

    def get_meeting_settings(self):
        try:
            from app import permissions
            cfg = self.app.config
            vals = {k: cfg.get(k) for k in self._MEETING_SETTING_KEYS}
            meets = cfg.get("meetings", [])
            return _ok(settings=vals, perms=permissions.meeting_permissions(),
                       count=len(meets),
                       total_seconds=sum(int(m.get("duration_seconds") or 0) for m in meets))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_meeting_setting(self, key, value):
        try:
            if key not in self._MEETING_SETTING_KEYS:
                return {"ok": False, "error": "unknown setting"}
            self.app.config[key] = value
            save_config(self.app.config)
            return _ok()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_dictation_hotkey(self):
        """Hotkey picker: capture the next keypress (modifiers allowed — Right ⌘
        is the classic) and bind it as BOTH hold and toggle key."""
        try:
            if not hasattr(self.app, "capture_next_key"):
                # Windows: platform doesn't expose the hotkey-picker path yet.
                # Better to return a clean unsupported message than let the
                # user see a raw AttributeError from Settings.
                return {"ok": False,
                        "error": "Changing the dictation hotkey isn't supported yet on this platform."}
            got = self.app.capture_next_key(allow_modifiers=True)
            if not got:
                return {"ok": False, "cancelled": True}
            kc, label = got["keycode"], got["label"]
            if kc == self.app.config.get("transform_hotkey"):
                return {"ok": False, "error": "That key is the Transform hotkey."}
            self.app.config["hotkey_hold"] = kc
            self.app.config["hotkey_toggle"] = kc
            self.app.config["hotkey_label"] = label
            save_config(self.app.config)
            listener = getattr(self.app, "hotkey_listener", None)
            if listener is not None and hasattr(listener, "update_keys"):
                listener.update_keys(kc, kc)
            return _ok(keycode=kc, label=label)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_transform_hotkey(self):
        """Hotkey picker for Transform: ⌘⇧ + the captured (non-modifier) key."""
        try:
            # MER-41 stopgap: on Windows, `capture_next_key` and the
            # `hotkey_listener.set_transform(...)` seat don't exist yet.
            # Return a clean unsupported result instead of an AttributeError
            # bubbling up from a Settings toggle. The real port replaces both
            # branches once WinHotkeyListener lands.
            if not hasattr(self.app, "capture_next_key"):
                return {"ok": False,
                        "error": "Setting the Transform hotkey isn't supported yet on this platform."}
            got = self.app.capture_next_key(allow_modifiers=False)
            if not got:
                return {"ok": False, "cancelled": True}
            kc, label = got["keycode"], got["label"]
            if kc in (self.app.config.get("hotkey_hold"),
                      self.app.config.get("hotkey_toggle")):
                return {"ok": False, "error": "That key is the dictation hotkey."}
            self.app.config["transform_hotkey"] = kc
            self.app.config["transform_hotkey_label"] = label
            save_config(self.app.config)
            listener = getattr(self.app, "hotkey_listener", None)
            if listener is not None and hasattr(listener, "set_transform"):
                listener.set_transform(self.app._on_transform_hotkey, kc)
            return _ok(keycode=kc, label=label)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Transform settings (TRANSFORM_SWARM.md) ──────────────────────────────
    _TRANSFORM_SETTING_KEYS = (
        "transform_enabled", "transform_inline_enabled", "transform_selection_enabled",
    )

    def get_transform_settings(self):
        try:
            cfg = self.app.config
            return _ok(settings={k: bool(cfg.get(k)) for k in self._TRANSFORM_SETTING_KEYS},
                       hotkey_label=str(cfg.get("transform_hotkey_label", "T")),
                       dictation_label=str(cfg.get("hotkey_label", "Right ⌘")))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_transform_setting(self, key, value):
        try:
            if key not in self._TRANSFORM_SETTING_KEYS:
                return {"ok": False, "error": "unknown setting"}
            self.app.config[key] = bool(value)
            save_config(self.app.config)
            return _ok()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def stop_meeting(self):
        m = self._meetings()
        return m.stop_async() if m else {"ok": False, "error": "unavailable"}

    def cancel_meeting(self):
        """Discard the live meeting outright — no save, no summary, no history
        row. Distinct from stop_meeting, which finalizes the meeting and hands
        off to the dashboard; the JS side already gates this behind a
        confirm() dialog since it's irreversible."""
        try:
            m = self._meetings()
            if not (m and m.active):
                return {"ok": False, "error": "No active meeting."}
            r = m.cancel_active()
            if r.get("ok"):
                win = self._meeting_win()
                if win:
                    self.app._on_main(win.hide)
            return r
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def pause_meeting(self):
        try:
            m = self._meetings()
            if m and m.active:
                m.active.toggle_pause()
                return _ok(state=m.active.state)
            return {"ok": False, "error": "No active meeting."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def mark_moment(self, label=""):
        try:
            m = self._meetings()
            if m and m.active:
                return _ok(moment=m.active.mark_moment(label))
            return {"ok": False, "error": "No active meeting."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_meeting_scratchpad(self, text):
        try:
            m = self._meetings()
            if m and m.session:
                m.session.set_scratchpad(text)
                return _ok()
            return {"ok": False, "error": "No meeting."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_meeting_title(self, title):
        """Rename the LIVE meeting (the panel's live-screen title field)."""
        try:
            m = self._meetings()
            if m and m.session:
                m.session.set_title(title)
                return _ok()
            return {"ok": False, "error": "No meeting."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_meeting_title_by_id(self, meeting_id, title):
        """Rename any meeting — the dashboard detail view's title field (MER-46),
        which is usually pointed at a FINISHED meeting."""
        m = self._meetings()
        return (m.set_meeting_title_by_id(meeting_id, title)
                if m else {"ok": False, "error": "unavailable"})

    def rename_speaker(self, speaker_id, name):
        try:
            m = self._meetings()
            if m and m.session:
                m.session.rename_speaker(speaker_id, name)
                return _ok(speakers=m.session.speakers)
            return {"ok": False, "error": "No meeting."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def ask_meetings(self, question, meeting_id=None):
        """Q&A over the user's recorded meetings (Meetings page search field).
        `meeting_id` (Meetings v4 "Ask this meeting") scopes the context to ONE
        meeting's row — same LLM call, ranked context replaced by that row."""
        try:
            from app.meetings import ask_meetings
            rows = None
            if meeting_id:
                got = self.get_meeting(meeting_id)
                if got.get("ok") and got.get("meeting"):
                    rows = [got["meeting"]]
            return ask_meetings(self.app.config, question, rows=rows)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def export_meeting(self, meeting_id, fmt="md"):
        """Export a meeting as .txt or .md via a native save panel (falls back
        to ~/Downloads if the panel can't be shown)."""
        try:
            import os
            import re
            import threading
            # self.get_meeting so the Windows read-only cloud fallback applies.
            got = self.get_meeting(meeting_id)
            if not got.get("ok"):
                return got
            row = got["meeting"]
            from app.meetings import export_transcript_txt, export_transcript_md
            fmt = "txt" if str(fmt).lower() == "txt" else "md"
            content = export_transcript_txt(row) if fmt == "txt" else export_transcript_md(row)
            safe = re.sub(r"[^\w\s\-–—]", "", row.get("title") or "Meeting").strip()[:60] or "Meeting"
            fname = f"{safe}.{fmt}"

            box = {}
            done = threading.Event()

            def run():
                try:
                    from AppKit import NSSavePanel
                    panel = NSSavePanel.savePanel()
                    panel.setNameFieldStringValue_(fname)
                    panel.setCanCreateDirectories_(True)
                    if int(panel.runModal()) == 1:      # NSModalResponseOK
                        box["path"] = panel.URL().path()
                    else:
                        box["cancelled"] = True
                except Exception as e:
                    box["error"] = str(e)
                finally:
                    done.set()

            self.app._on_main(run)
            done.wait(180)
            path = box.get("path")
            if box.get("cancelled"):
                return {"ok": False, "cancelled": True}
            if not path:                                 # panel failed → Downloads
                path = os.path.expanduser(f"~/Downloads/{fname}")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return _ok(path=path)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def retry_meeting_summary(self, meeting_id):
        m = self._meetings()
        return m.retry_summary(meeting_id) if m else {"ok": False, "error": "unavailable"}

    def set_action_item_done(self, meeting_id, index, done):
        """Action-item checkbox on the summary (widget 33c)."""
        m = self._meetings()
        return (m.set_action_item_done(meeting_id, index, done)
                if m else {"ok": False, "error": "unavailable"})

    def set_action_item_text(self, meeting_id, index, text):
        """Inline action-item edit (widget 33c)."""
        m = self._meetings()
        return (m.set_action_item_text(meeting_id, index, text)
                if m else {"ok": False, "error": "unavailable"})

    def delete_action_item(self, meeting_id, index):
        """Remove a wrongly-extracted action item (widget 33c)."""
        m = self._meetings()
        return (m.delete_action_item(meeting_id, index)
                if m else {"ok": False, "error": "unavailable"})

    def set_transcript_text(self, meeting_id, index, text):
        """Inline transcript-segment edit (widget 33a)."""
        m = self._meetings()
        return (m.set_transcript_text(meeting_id, index, text)
                if m else {"ok": False, "error": "unavailable"})

    def delete_marked_moment(self, meeting_id, index):
        """Delete a bookmark (widget 33b)."""
        m = self._meetings()
        return (m.delete_marked_moment(meeting_id, index)
                if m else {"ok": False, "error": "unavailable"})

    def set_mark_note(self, meeting_id, index, note):
        """Attach/edit the user note on a bookmark (widget 33b)."""
        m = self._meetings()
        return (m.set_mark_note(meeting_id, index, note)
                if m else {"ok": False, "error": "unavailable"})

    def regenerate_hybrid(self, meeting_id, index):
        """Regenerate one hybrid-note AI addition (widget 33i)."""
        m = self._meetings()
        return (m.regenerate_hybrid(meeting_id, index)
                if m else {"ok": False, "error": "unavailable"})

    def get_meeting_notes(self, meeting_id, regenerate=False):
        """Full AI meeting notes page (widget: Notes page in the meeting window)."""
        m = self._meetings()
        return (m.get_meeting_notes(meeting_id, regenerate)
                if m else {"ok": False, "error": "unavailable"})

    def set_meeting_pinned(self, meeting_id, pinned):
        """Pin/unpin a meeting in the list (widget 33j)."""
        m = self._meetings()
        return (m.set_meeting_pinned(meeting_id, pinned)
                if m else {"ok": False, "error": "unavailable"})

    def set_speaker_name(self, meeting_id, sid, name):
        """Rename a speaker from the summary view (widget 33d) + fingerprint learn."""
        m = self._meetings()
        return (m.set_speaker_name(meeting_id, sid, name)
                if m else {"ok": False, "error": "unavailable"})

    def set_meeting_notes(self, meeting_id, notes_md):
        """Persist USER-EDITED AI meeting notes (Meetings v4 — desktop finally
        matches mobile's `updateNotesRemote`, which edits the same
        `meetings.notes_md` column). Cloud row is the store; the live session's
        cache is refreshed when it is this meeting. Bumps `updated_at` like the
        mobile editor so cross-device freshness comparisons keep working.
        Returns ok:false when the cloud write fails — the editor must not
        pretend an edit that didn't stick."""
        try:
            cfg = self.app.config
            if not (cfg.get("sync_user_id") and _cloud_allowed(cfg)):
                return _err("Not signed in")
            text = str(notes_md or "")
            m = self._meetings()
            try:
                s = m.session if m else None
                if s and s.id == meeting_id:
                    s.notes_md = text
            except Exception:
                pass
            import httpx
            from app.sync import SUPABASE_URL
            from app.auth import auth_header
            now = _dt.datetime.now(_dt.timezone.utc).isoformat()
            resp = httpx.patch(
                f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{meeting_id}",
                headers={**auth_header(cfg, json=True), "Prefer": "return=minimal"},
                json={"notes_md": text, "updated_at": now},
                timeout=10,
            )
            resp.raise_for_status()
            return _ok()
        except Exception as e:
            logger.debug(f"set_meeting_notes failed: {e}")
            return _err("Couldn't save the notes — check your connection")

    def get_meeting_audio(self, meeting_id):
        """Local WAV as a data-URI when present, else a short-lived signed cloud
        URL (meeting-audio is private, MER-27 — long TTL since a meeting can run
        long and the URL must stay valid for the whole playback+scrub session)."""
        try:
            import base64
            import os
            from app import recordings
            from app.meetings import MEETINGS_DIR
            path = os.path.join(MEETINGS_DIR, f"{meeting_id}.wav")
            if os.path.exists(path) and os.path.getsize(path) < 80 * 1024 * 1024:
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                return _ok(src=f"data:audio/wav;base64,{b64}")
            m = self._meetings()
            got = m.get_meeting(meeting_id) if m else {"ok": False}
            stored = (got.get("meeting") or {}).get("audio_url") if got.get("ok") else None
            if stored:
                object_path = recordings.extract_object_path(stored, "meeting-audio")
                signed = recordings.sign_url("meeting-audio", object_path, expires_in=3600)
                if signed:
                    return _ok(src=signed)
            if (got.get("meeting") or {}).get("audio_expired"):
                # MER-31 reaper already removed this — a distinct message from
                # "never had audio" so the UI can show "Audio expired — notes
                # kept" instead of a generic playback error.
                return {"ok": False, "expired": True, "error": "Audio expired — notes kept."}
            return {"ok": False, "error": "No audio for this meeting."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_meetings(self):
        m = self._meetings()
        if m:
            return m.list_meetings()
        # No capture manager (Windows): READ-ONLY cloud list, so the account's
        # Mac-captured meetings still show in the Meetings screen and the
        # Notes import picker (v3.2). Fail-closed to an empty list.
        try:
            from app.meetings import _fetch_meeting_rows
            metas = []
            for r in _fetch_meeting_rows(self.app.config, limit=50):
                if not isinstance(r, dict) or not r.get("id"):
                    continue
                metas.append({
                    "id": r.get("id"),
                    "title": r.get("title") or "",
                    "started_at": r.get("started_at") or "",
                    "duration_seconds": r.get("duration_seconds") or 0,
                    "status": r.get("status") or "ready",
                    "speakers": r.get("speakers") or {},
                    "summary": r.get("summary") or "",
                    "action_items": r.get("action_items") or [],
                    "marked_moments": r.get("marked_moments") or [],
                    "utterances": len(r.get("transcript") or []),
                    "audio_url": r.get("audio_url") or "",
                    "pinned": bool(r.get("pinned")),
                    "cloud": True,
                })
            # `opened` = everything, so read-only rows never flash NEW badges.
            return {"ok": True, "meetings": metas,
                    "opened": [x["id"] for x in metas], "active_id": None}
        except Exception as e:
            logger.debug(f"cloud meetings list fallback failed: {e}")
            return {"ok": True, "meetings": []}

    def get_meeting(self, meeting_id):
        m = self._meetings()
        if m:
            return m.get_meeting(meeting_id)
        # Windows read-only fallback (see list_meetings): the full cloud row —
        # summary/decisions/action_items/transcript — feeds the Notes import
        # and the read-only detail view.
        try:
            from app.meetings import _fetch_meeting_rows
            for r in _fetch_meeting_rows(self.app.config, limit=50):
                if isinstance(r, dict) and r.get("id") == meeting_id:
                    return {"ok": True, "meeting": r}
        except Exception as e:
            logger.debug(f"cloud get_meeting fallback failed: {e}")
        return {"ok": False, "error": "unavailable"}

    def complete_onboarding(self):
        self.app.config["onboarded"] = True
        save_config(self.app.config)
        return _ok()

    def sign_in_google(self):
        # Deliberately optimistic: the OAuth round-trip is a browser flow that
        # can take a minute. The REAL outcome (success, timeout, cancel, error)
        # arrives later as a pushed `state` event carrying `auth_error` — see
        # main._sign_in_failed / _push_auth_state (IDI-166).
        if hasattr(self.app, "_sign_in"):
            self.app._on_main(self.app._sign_in)
            return _ok()
        return {"ok": False, "error": "not supported"}

    def cancel_sign_in(self):
        """Abandon an in-flight sign-in so the pane's button is usable again
        (and REDIRECT_PORT is freed for the retry)."""
        if hasattr(self.app, "cancel_sign_in"):
            self.app._on_main(self.app.cancel_sign_in)
            return _ok()
        try:
            from app import auth as _auth
            _auth.cancel_sign_in()
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return _ok()

    def sign_out_account(self):
        if hasattr(self.app, "_sign_out"):
            self.app._on_main(self.app._sign_out)
            return _ok()
        return {"ok": False, "error": "not supported"}

    def delete_account(self):
        """MER-32: permanently delete the signed-in account — DB rows,
        storage objects, and the auth user itself (server-side, via the
        `delete-account` Edge Function), then wipe every local trace.
        Unlike sign_out_account, this returns the REAL result synchronously
        (not an optimistic _ok()) since the caller needs to know whether the
        destructive action actually succeeded before showing a confirmation."""
        from app.auth import delete_account_remote, wipe_local_account_data
        result = delete_account_remote(self.app.config)
        if not result.get("ok"):
            # `session_dead` rides along so the UI can offer "Sign in again"
            # rather than just repeating a doomed Delete (IDI-166).
            return {"ok": False,
                    "error": result.get("error", "Deletion failed — please try again"),
                    "session_dead": bool(result.get("session_dead"))}
        # Stop anything still producing data for the account we just deleted,
        # BEFORE the wipe — otherwise a draining meeting worker re-saves rows
        # into the config we are about to clear (IDI-170).
        try:
            if hasattr(self.app, "_stop_active_meeting"):
                self.app._stop_active_meeting("account deletion")
        except Exception as e:
            logger.debug(f"meeting stop before wipe skipped: {e}")
        # Wipe the LIVE config object, synchronously, right here. Passing no
        # cfg made `wipe_local_account_data` re-read from disk while
        # `self.app.config` still held auth + history in memory — any
        # concurrent `save_config(self.app.config)` (history append, device
        # refresh, note save) then RESURRECTED the deleted account's data.
        # Mutating the live dict first means a racing save writes the wiped
        # state instead. Only then do we hand off to _sign_out, which reloads
        # config from the already-wiped file.
        wipe_local_account_data(self.app.config)
        try:
            self.app._auth_notice = ACCOUNT_DELETED_MSG
            self.app._auth_error = ""
        except Exception:
            pass
        if hasattr(self.app, "_sign_out"):
            self.app._on_main(self.app._sign_out)
        return _ok()

    def start_recording(self):
        self.app._on_record_start()
        return _ok()

    def stop_recording(self):
        self.app._on_record_stop()
        return _ok()
    
    def start_hotkey_record(self, mode):
        """Start listening for a hotkey on Windows."""
        # On Windows, we'll use a separate thread or a temporary hook
        # For pywebview, we can capture the key in JS and send it back.
        # This is easier and more reliable for the HTML dashboard.
        return _ok()

    def save_hotkey(self, mode, key_name):
        cfg = self.app.config
        if mode == "hold":
            cfg["hotkey_hold"] = key_name
        else:
            cfg["hotkey_toggle"] = key_name
        save_config(cfg)
        self.app.config = cfg
        if hasattr(self.app, "_update_hotkeys"):
            self.app._update_hotkeys()
        return self.get_state()

    def set_target_device(self, device_id):
        self.dashboard._target_device_id = device_id or "__all__"
        try:
            self.app.config["sync_target_device_id"] = self.dashboard._target_device_id
            save_config(self.app.config)
        except Exception:
            pass
        return _ok(target_device_id=self.dashboard._target_device_id)

    def copy_text(self, text):
        pyperclip.copy(text or "")
        return _ok()

    def edit_text(self, old_text, new_text):
        cfg = self.app.config = load_config()
        for key in ("history", "pinned"):
            entries = []
            for e in cfg.get(key, []):
                if _entry_text(e) == old_text:
                    if isinstance(e, dict):
                        e = {**e, "text": new_text}
                    else:
                        e = {"text": new_text, "app": "", "ts": ""}
                entries.append(e)
            cfg[key] = entries
        save_config(cfg)
        # Auto-learn: a single clean word swap becomes a replacement rule.
        try:
            self._learn_from_edit(old_text, new_text, cfg)
        except Exception as e:
            logger.debug("dictionary auto-learn skipped: %s", e)
        return self.get_state()

    def _learn_from_edit(self, old_text, new_text, cfg):
        # Preferred path: delegate to the autolearn classifier so the history-view
        # edit path gets the SAME intelligence as the in-place watcher (§2 pipeline
        # — correction vs. deletion/insertion/rephrase/common-word). A confident
        # single-word correction becomes an auto-learned replacement rule.
        try:
            from app import autolearn, dictionary
            decision = autolearn.classify(old_text, new_text, cfg)
            if decision.get("action") in ("offer", "silent_learn"):
                old, new = decision.get("old"), decision.get("new")
                if old and new:
                    dictionary.add_replacement(cfg, old, new, save_config, auto=True)
            return
        except Exception as e:
            logger.debug("autolearn classify unavailable, simple heuristic: %s", e)

        # Fallback (preserves prior behavior): same-length one-word correction.
        ow, nw = (old_text or "").split(), (new_text or "").split()
        if len(ow) != len(nw):
            return  # only learn from same-length one-word corrections
        diffs = [(o, n) for o, n in zip(ow, nw) if o != n]
        if len(diffs) != 1:
            return
        o, n = diffs[0]
        o2 = "".join(c for c in o if c.isalnum())
        n2 = "".join(c for c in n if c.isalnum())
        if len(o2) >= 2 and len(n2) >= 2 and o2.lower() != n2.lower():
            from app import dictionary
            dictionary.add_replacement(cfg, o2, n2, save_config)

    # ── custom dictionary ─────────────────────────────────────────────────────
    def get_dictionary(self):
        from app import dictionary
        d = dictionary.fetch_remote(self.app.config, save_config)
        return _ok(vocabulary=d["vocabulary"], replacements=d["replacements"])

    def save_dictionary(self, vocabulary, replacements):
        from app import dictionary
        d = dictionary.save(self.app.config, vocabulary or [], replacements or [], save_config)
        # IDI-174: the cloud write is compare-and-swap now, and a lost race that
        # can't be merged in one retry is REPORTED — the local save still stands,
        # but the user needs to know it didn't reach their other devices.
        # (`d` may have been replaced by the merge, so re-read it.)
        d = dictionary.get(self.app.config)
        return _ok(vocabulary=d["vocabulary"], replacements=d["replacements"],
                   sync_error=dictionary.last_sync_error())

    # ── snippets (spoken trigger → longer text expansion) ──────────────────────
    def fetch_snippets(self):
        from app import dictionary
        try:
            dictionary.fetch_remote(self.app.config, save_config)
        except Exception as e:
            logger.debug("snippets remote fetch skipped: %s", e)
        return _ok(snippets=dictionary.get_snippets(self.app.config))

    def add_snippet(self, snippet):
        from app import dictionary
        s = snippet or {}
        dictionary.add_snippet(self.app.config, s.get("trigger", ""),
                               s.get("expansion", ""), s.get("label", ""), save_config)
        return _ok(snippets=dictionary.get_snippets(self.app.config),
                   sync_error=dictionary.last_sync_error())

    def update_snippet(self, snippet):
        from app import dictionary
        s = snippet or {}
        sid = s.get("id")
        if not sid:
            return _err("missing snippet id")
        fields = {}
        for k in ("trigger", "expansion", "label"):
            if s.get(k) is not None:
                fields[k] = s.get(k)
        dictionary.update_snippet(self.app.config, sid, save_config, **fields)
        return _ok(snippets=dictionary.get_snippets(self.app.config),
                   sync_error=dictionary.last_sync_error())

    def delete_snippet(self, snippet_id):
        from app import dictionary
        dictionary.remove_snippet(self.app.config, snippet_id, save_config)
        return _ok(snippets=dictionary.get_snippets(self.app.config),
                   sync_error=dictionary.last_sync_error())

    # ── team / organization (IDI-216) ─────────────────────────────────────────
    # Every method below is a thin wrapper over `app/organizations.py`, which owns
    # the fail-closed behavior: no team, a network blip and an unapplied migration
    # all return the same "no org" shape, and nothing here can raise into the JS
    # bridge. `get_team` is the only one the page calls on load.
    def get_team(self, refresh=False):
        from app import organizations
        from app import dictionary
        cfg = self.app.config
        org = (organizations.fetch(cfg, save_config) if refresh
               else organizations.get(cfg))
        d = dictionary.get(cfg)
        return _ok(team=org, can_admin=org.get("role") in ("owner", "admin"),
                   # Drives the "just created" screen. Local-only config key —
                   # this is a per-device onboarding nudge, not account state, so
                   # it must not become a Supabase column.
                   setup_done=bool(cfg.get("org_setup_done")),
                   personal={"vocabulary": len(d["vocabulary"]),
                             "replacements": len(d["replacements"]),
                             "snippets": len(d["snippets"]),
                             "sample": d["vocabulary"][-6:]},
                   sync_error=organizations.last_error())

    def dismiss_team_setup(self):
        cfg = self.app.config
        cfg["org_setup_done"] = True
        save_config(cfg)
        return _ok()

    def get_team_series(self, days=98):
        from app import organizations
        return _ok(**organizations.usage_series(self.app.config, days))

    def seed_team_dictionary(self):
        """Copy this user's own dictionary into the team's (onboarding step 1)."""
        from app import organizations
        res = organizations.seed_team_dictionary_from_personal(self.app.config, save_config)
        if not res.get("ok"):
            return _err(res.get("error", "Couldn't copy your dictionary"))
        cfg = self.app.config
        cfg["org_setup_done"] = True
        save_config(cfg)
        return _ok(added=res.get("added") or {}, team=organizations.get(cfg))

    def create_team(self, name, company=""):
        from app import organizations
        res = organizations.create(self.app.config, name, company, save_config)
        if not res.get("ok"):
            return _err(res.get("error", "Couldn't create the team"))
        # A brand-new team lands on the setup screen, not on an empty roster.
        cfg = self.app.config
        cfg["org_setup_done"] = False
        save_config(cfg)
        return _ok(**res)

    def invite_member(self, email, role="member"):
        from app import organizations
        res = organizations.invite(self.app.config, email, role)
        if not res.get("ok"):
            msg = res.get("error", "Couldn't send the invite")
            detail = res.get("detail") or ""
            return _err(f"{msg} — {detail}" if detail else msg)
        cfg = self.app.config
        cfg["org_setup_done"] = True   # first invite sent — setup is done
        save_config(cfg)
        return _ok(invite=res.get("invite") or {}, link=res.get("link") or "",
                   # IDI-220: a repeat invite updates the existing row rather than
                   # minting a second one, so the UI says "resent", not "sent".
                   reissued=bool(res.get("reissued")),
                   seats=res.get("seats") or {},
                   invites=organizations.list_invites(cfg))

    def list_team_invites(self):
        from app import organizations
        return _ok(invites=organizations.list_invites(self.app.config))

    def revoke_team_invite(self, invite_id):
        from app import organizations
        res = organizations.revoke_invite(self.app.config, invite_id)
        if not res.get("ok"):
            return _err(res.get("error", "Couldn't revoke that invite"))
        return _ok(invites=organizations.list_invites(self.app.config))

    def claim_team_invite(self, token, confirm_mismatch=False):
        """IDI-223: a wrong-account claim comes back as `needs_confirm` with both
        addresses rather than a flat refusal, so the page can ask before binding the
        invite to whoever happens to be signed in."""
        from app import organizations
        res = organizations.claim_invite(self.app.config, token, save_config,
                                         confirm_mismatch=bool(confirm_mismatch))
        if res.get("ok"):
            # Same reasoning as accept_pending_invite: joining via a claimed
            # link is still joining, not creating — skip the owner-only setup
            # wizard so this path doesn't hit the same redirect glitch.
            cfg = self.app.config
            cfg["org_setup_done"] = True
            save_config(cfg)
            return _ok(team=res.get("org"), already=bool(res.get("already")))
        if res.get("needs_confirm"):
            return {"ok": False, "needs_confirm": True,
                    "invited_email": res.get("invited_email", ""),
                    "current_email": res.get("current_email", ""),
                    "error": res.get("error", "")}
        return _err(res.get("error", ""))

    def preview_team_invite(self, token):
        from app import organizations
        res = organizations.invite_preview(self.app.config, token)
        return _ok(**{k: v for k, v in res.items() if k != "ok"}) if res.get("ok") \
            else _err(res.get("error", ""))

    def decline_team_invite(self, token):
        from app import organizations
        res = organizations.decline_invite(self.app.config, token)
        return _ok() if res.get("ok") else _err(res.get("error", ""))

    def get_pending_invites(self):
        """IDI-222 fallback — surfaced as a banner on the Team screen so an invite
        is recoverable even when the emailed link never reached the app."""
        from app import organizations
        return _ok(invites=organizations.pending_invites_for_me(self.app.config))

    def accept_pending_invite(self, org_id):
        from app import organizations
        res = organizations.accept_pending(self.app.config, org_id, save_config)
        if not res.get("ok"):
            return _err(res.get("error", ""))
        # A member who JOINS a team has nothing to set up — create_team's setup
        # wizard (seed the shared dictionary, invite others) is for the owner of
        # a brand-new team. Without this, org_setup_done stays at its unset
        # default and get_team() sends every freshly-invited member straight
        # back to "create a team" until they click Skip (confirmed live,
        # 2026-08-25 — the exact "redirect glitch" reported after accepting).
        cfg = self.app.config
        cfg["org_setup_done"] = True
        save_config(cfg)
        return _ok(team=res.get("org"))

    def set_team_auto_join(self, enabled):
        from app import organizations
        res = organizations.set_auto_join(self.app.config, enabled, save_config)
        return _ok(team=res.get("org")) if res.get("ok") else _err(res.get("error", ""))

    def set_member_role(self, user_id, role):
        from app import organizations
        res = organizations.set_role(self.app.config, user_id, role, save_config)
        return _ok(team=res.get("org")) if res.get("ok") else _err(res.get("error", ""))

    def remove_team_member(self, user_id):
        from app import organizations
        res = organizations.remove_member(self.app.config, user_id, save_config)
        return _ok(team=res.get("org")) if res.get("ok") else _err(res.get("error", ""))

    def leave_team(self):
        from app import organizations
        uid = self.app.config.get("sync_user_id", "")
        if not uid:
            return _err("Not signed in")
        res = organizations.remove_member(self.app.config, uid, save_config)
        return _ok(team=res.get("org")) if res.get("ok") else _err(res.get("error", ""))

    def set_team_settings(self, fields):
        from app import organizations
        res = organizations.set_org_settings(self.app.config, save_config, **(fields or {}))
        return _ok(team=res.get("org")) if res.get("ok") else _err(res.get("error", ""))

    def set_team_consent(self, usage, leaderboard):
        from app import organizations
        res = organizations.set_consent(self.app.config, usage, leaderboard, save_config)
        return _ok(team=res.get("org")) if res.get("ok") else _err(res.get("error", ""))

    def get_team_dictionary(self):
        """The SHARED set, for the team editor. Distinct from get_dictionary(),
        which is this user's own — the two are merged only at dictation time."""
        from app import organizations
        org = organizations.get(self.app.config)
        d = org.get("dictionary") or {}
        return _ok(vocabulary=d.get("vocabulary") or [],
                   replacements=d.get("replacements") or [],
                   snippets=d.get("snippets") or [],
                   can_edit=org.get("role") in ("owner", "admin"))

    def save_team_dictionary(self, vocabulary, replacements, snippets=None):
        from app import organizations
        current = organizations.get(self.app.config).get("dictionary") or {}
        payload = {
            "vocabulary": vocabulary or [],
            "replacements": replacements or [],
            # Omitting snippets must not wipe the sibling array off the shared row
            # — the same trap dictionary.save() guards against for the personal one.
            "snippets": current.get("snippets") or [] if snippets is None else snippets,
        }
        res = organizations.save_team_dictionary(self.app.config, payload, save_config)
        if not res.get("ok"):
            return _err(res.get("error", "Couldn't save the team dictionary"))
        d = res.get("dictionary") or {}
        return _ok(vocabulary=d.get("vocabulary") or [],
                   replacements=d.get("replacements") or [],
                   snippets=d.get("snippets") or [])

    def get_team_usage(self, days=30):
        from app import organizations
        return _ok(**organizations.usage_summary(self.app.config, days))

    def get_team_apps(self, days=30):
        from app import organizations
        return _ok(**organizations.app_breakdown(self.app.config, days))

    def get_team_leaderboard(self, days=7):
        from app import organizations
        return _ok(**organizations.leaderboard(self.app.config, days))

    # ── auto-learn from corrections ─────────────────────────────────────────────
    def get_autolearn_enabled(self):
        return _ok(enabled=bool(self.app.config.get("autolearn_enabled", False)))

    def set_autolearn_enabled(self, value):
        cfg = self.app.config
        cfg["autolearn_enabled"] = bool(value)
        save_config(cfg)
        self.app.config = cfg
        return _ok(enabled=cfg["autolearn_enabled"])

    # ── file tagging (Cursor/Windsurf) ─────────────────────────────────────────
    def get_filetag_settings(self):
        """Toggle state + how many open-file names we've remembered so far."""
        try:
            from app import filetags
            cfg = self.app.config
            seen = filetags.get_seen_files(cfg)
            return _ok(enabled=bool(cfg.get("filetag_enabled", False)),
                       seen_count=len(seen), files=seen[:50])
        except Exception as e:
            logger.debug("get_filetag_settings failed: %s", e)
            return _ok(enabled=bool(self.app.config.get("filetag_enabled", False)),
                       seen_count=0, files=[])

    def set_filetag_enabled(self, value):
        cfg = self.app.config
        cfg["filetag_enabled"] = bool(value)
        save_config(cfg)
        self.app.config = cfg
        return _ok(enabled=cfg["filetag_enabled"])

    def clear_history(self):
        """Step 1 of the two-step clear (IDI-172): wipe THIS device only.

        Was dead code — nothing in any UI called it. It is now the Settings →
        "Clear history" button, which then offers step 2
        (`clear_history_everywhere`) separately, because "clear my history"
        meaning "delete it off my phone too" has to be an explicit second yes."""
        self.app.config["history"] = []
        self.app.config["pinned"] = []
        save_config(self.app.config)
        try:
            self.app._total_transcriptions = 0
            self.app._total_words = 0
        except Exception:
            pass
        return self.get_state()

    def clear_history_everywhere(self):
        """Step 2: TOMBSTONE every cloud transcription of this account.

        Never a hard DELETE (IDI-172) — a hard delete is invisible to the other
        devices, so their copies survive and the next backfill re-seeds this
        one. Each device drops its copy when it sees the `deleted_at`."""
        cfg = self.app.config
        user_id = cfg.get("sync_user_id", "")
        if not user_id or not _cloud_allowed(cfg):
            return _err("Sign in to clear your other devices.")
        try:
            from app.sync import tombstone_all_transcriptions
            res = tombstone_all_transcriptions(user_id)
            if not res.get("ok"):
                return _err(res.get("error") or "Could not clear your other devices.")
            return _ok(count=res.get("count", 0))
        except Exception as e:
            logger.error("clear_history_everywhere failed: %s", e)
            return _err(str(e))

    def remove_device(self, device_id):
        """Drop another device's row from the account's device list (IDI-177).

        Scoped by user_id AND device_id so it can never touch a different
        account — and deliberately NOT offered for THIS device (signing out is
        what removes this one). It is a LIST removal, not a revocation: the
        other device keeps working and will re-register on its next heartbeat,
        which is exactly what the confirm text says."""
        device_id = (device_id or "").strip()
        cfg = self.app.config
        user_id = cfg.get("sync_user_id", "")
        if not device_id:
            return _err("No device selected")
        if not user_id or not _cloud_allowed(cfg):
            return _err("Sign in to manage your devices.")
        my_id, _name = device_identity(self.app)
        if device_id == my_id:
            return _err("This device can't remove itself — sign out instead.")
        try:
            from app.auth import auth_header
            from app.sync import delete_device_presence
            delete_device_presence(user_id, device_id, auth_header(cfg))
        except Exception as e:
            logger.debug("remove_device failed: %s", e)
            return _err(str(e))
        try:
            self.dashboard._load_devices()
        except Exception:
            pass
        return _ok(device_id=device_id)

    def remove_offline_devices(self):
        """Drop every OFFLINE row from the account's device list in one action.

        The device list has no TTL and nothing prunes it, so a reinstalled app —
        or, historically, any identity-scheme change — leaves its old row behind
        forever. One test account had 14 dead "iPhone" rows, none seen in three
        weeks, which buried the one device that was actually online.

        Deliberately MANUAL, never automatic: a phone that is merely switched off
        is offline, not gone, and it must not disappear from the list on its own.
        Same semantics as `remove_device` — a list removal, not a revocation, so
        any of these devices re-registers on its next heartbeat. Never touches
        THIS device (signing out is what removes this one)."""
        cfg = self.app.config
        user_id = cfg.get("sync_user_id", "")
        if not user_id or not _cloud_allowed(cfg):
            return _err("Sign in to manage your devices.")
        my_id, _name = device_identity(self.app)
        try:
            from app.auth import auth_header
            from app.sync import fetch_account_devices, delete_device_presence
            header = auth_header(cfg)
            rows = fetch_account_devices(user_id, my_id) or []
            stale = [d.get("device_id") for d in rows
                     if not d.get("online") and d.get("device_id")]
            removed = 0
            for did in stale:
                try:
                    delete_device_presence(user_id, did, header)
                    removed += 1
                except Exception as e:
                    # Keep going — one failed row must not abort the sweep.
                    logger.debug("remove_offline_devices: %s failed: %s", did, e)
        except Exception as e:
            logger.error("remove_offline_devices failed: %s", e)
            return _err(str(e))
        try:
            self.dashboard._load_devices()
        except Exception:
            pass
        return _ok(removed=removed)

    # ── Notes API ───────────────────────────────────────────────────────
    # ── notes: local-first, cloud-synced when enabled ─────────────────────────
    def _local_notes(self):
        notes = self.app.config.get("notes", [])
        return notes if isinstance(notes, list) else []

    def _save_local_notes(self, notes):
        self.app.config["notes"] = notes
        save_config(self.app.config)

    def _sync_on(self):
        """Notes/canvas/dictionary/history sync gate — the user toggle AND a
        real signed-in account (IDI-170/171). `sync_user_id` alone survived
        sign-out, so it can't be the only check."""
        cfg = self.app.config
        return bool(cfg.get("sync_user_id", "") and cfg.get("sync_enabled")
                    and _cloud_allowed(cfg))

    def fetch_notes(self):
        notes = list(self._local_notes())
        # Merge any remote notes when sync is on. Uses the v2 merge contract:
        # conflict-pair preservation, audio_segments UNION, unknown-field passthrough.
        if self._sync_on():
            try:
                import httpx
                from app.sync import SUPABASE_URL
                from app.auth import auth_header
                user_id = self.app.config.get("sync_user_id", "")
                resp = httpx.get(
                    f"{SUPABASE_URL}/rest/v1/notes",
                    headers=auth_header(self.app.config),
                    # select=* so raw_content, audio_segments, and any newer-client
                    # columns come back and can be preserved verbatim (forward-compat).
                    params={"user_id": f"eq.{user_id}", "order": "updated_at.desc",
                            "limit": "200", "select": "*"},
                    timeout=8,
                )
                if resp.status_code == 200:
                    by_id = {n["id"]: n for n in notes if n.get("id")}
                    for r in resp.json():
                        if not isinstance(r, dict) or not r.get("id"):
                            continue
                        # Tombstone wins unconditionally (IDI-158): a remote
                        # deleted_at removes the local copy AND its local-only
                        # ::conflict:: derivatives — never merged, never
                        # resurrected by an offline edit's newer updated_at.
                        if r.get("deleted_at"):
                            rid = r["id"]
                            for k in list(by_id.keys()):
                                if (k == rid or by_id[k].get("conflict_of") == rid
                                        or k.startswith(f"{rid}::conflict::")):
                                    by_id.pop(k, None)
                            continue
                        cand = dict(r)  # keep ALL remote fields, including unknowns
                        cand["title"] = r.get("title", "") or ""
                        cand["content"] = r.get("content", "") or ""
                        cand["created_at"] = r.get("created_at", "") or ""
                        cand["updated_at"] = r.get("updated_at", "") or ""
                        # normalize v2 fields (absent on pre-existing rows)
                        cand["raw_content"] = r.get("raw_content", None)
                        segs = r.get("audio_segments")
                        cand["audio_segments"] = segs if isinstance(segs, list) else []
                        merge_remote_note(by_id, cand)
                    notes = sorted(by_id.values(), key=lambda n: n.get("updated_at", ""), reverse=True)
                    self._save_local_notes(notes)
            except Exception as e:
                logger.debug(f"Notes remote merge failed: {e}")
        return _ok(notes=notes)

    def save_note(self, note):
        import uuid
        note = note or {}
        cfg = self.app.config
        notes = list(self._local_notes())
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        nid = note.get("id") or uuid.uuid4().hex
        title = note.get("title", "") or ""
        content = note.get("content", "") or ""
        raw_content = note.get("raw_content", None)
        # Explicit caller intent to (re)format now. Reformat and the initial dictated
        # save set this; typed edits leave it off. Control field — never stored.
        run_cleanup = bool(note.get("run_cleanup"))
        # Explicit caller intent to NOT format (Notes v3): editing the original
        # transcript of a format-failed note must never fire a surprise LLM call
        # (its raw is set, content still empty — exactly the initial-dictated
        # shape). Control field — never stored.
        no_cleanup = bool(note.get("no_cleanup"))
        incoming_segments = note.get("audio_segments")
        if not isinstance(incoming_segments, list):
            incoming_segments = None

        existing = next((n for n in notes if n.get("id") == nid), None)

        # ── Cost control (Decision 2): run AI cleanup AT MOST ONCE per dictated note.
        # Fires only on the initial dictated save — a raw transcript is present, no
        # formatted content exists yet (neither incoming nor already-stored), and the
        # note has never been formatted — OR when the caller explicitly asks
        # (run_cleanup, i.e. Reformat). Typed edits and every subsequent save skip it.
        raw_str = (raw_content or "").strip()
        existing_content = (existing.get("content", "") if existing else "") or ""
        is_initial_dictated = bool(raw_str) and not content.strip() and not existing_content.strip()
        if raw_str and not no_cleanup and (run_cleanup or is_initial_dictated):
            try:
                from app.ai_cleanup import format_note
                structure_on = feature_flag(cfg, "notes_structure_detection_enabled")
                autotitle_on = feature_flag(cfg, "notes_autotitle_enabled")
                source = raw_str if raw_str else content
                formatted = format_note(
                    source, cfg,
                    structure_detection=structure_on,
                    autotitle=autotitle_on,
                )
                if formatted:
                    content = formatted.get("formatted_content") or content
                    new_title = (formatted.get("title") or "").strip()
                    # Auto-title only when the note has no title yet — NEVER overwrite
                    # a title the user set manually (Decision / Feature 2).
                    if autotitle_on and new_title and not title.strip():
                        title = new_title
                # On failure `content` stays as-is (typically empty) so the raw
                # transcript is preserved and the UI shows "Retry formatting".
            except Exception as e:
                logger.debug(f"Note cleanup on save failed: {e}")

        found = False
        for n in notes:
            if n.get("id") == nid:
                # Merge onto the existing dict so unknown/newer-client fields are
                # preserved verbatim on write-back (forward-compat, Decision 7).
                n["title"], n["content"], n["updated_at"] = title, content, now
                if raw_content is not None:
                    n["raw_content"] = raw_content
                if incoming_segments is not None:
                    # UNION so a segment added elsewhere isn't dropped by this edit.
                    n["audio_segments"] = _union_audio_segments(n.get("audio_segments"), incoming_segments)
                elif "audio_segments" not in n:
                    n["audio_segments"] = []
                found = True
                saved = n
                break
        if not found:
            saved = {"id": nid, "title": title, "content": content,
                     "raw_content": raw_content,
                     "audio_segments": incoming_segments or [],
                     "created_at": now, "updated_at": now}
            notes.insert(0, saved)
        # newest first
        notes = sorted(notes, key=lambda n: n.get("updated_at", ""), reverse=True)
        self._save_local_notes(notes)
        # push to cloud (best-effort). Conflict copies are local-only until resolved.
        if self._sync_on() and "::conflict::" not in nid:
            try:
                import httpx
                from app.sync import SUPABASE_URL
                from app.auth import auth_header
                payload = {"id": nid, "user_id": self.app.config.get("sync_user_id", ""),
                           "title": title, "content": content,
                           "audio_segments": saved.get("audio_segments", []),
                           "device_name": self.app.config.get("sync_device_name", ""),
                           "updated_at": now}
                if raw_content is not None:
                    payload["raw_content"] = raw_content
                # Forward-compat: preserve any unknown fields we're holding for this
                # note verbatim, so an older client never strips a newer column.
                for k, v in saved.items():
                    if k not in _NOTE_KNOWN_FIELDS and k not in payload:
                        payload[k] = v
                httpx.post(
                    f"{SUPABASE_URL}/rest/v1/notes?on_conflict=id",
                    headers={**auth_header(self.app.config, json=True),
                             "Prefer": "resolution=merge-duplicates,return=minimal"},
                    json=payload,
                    timeout=10,
                )
            except Exception as e:
                logger.debug(f"Note cloud save failed: {e}")
        r = _ok(notes=notes)
        r["id"] = nid
        return r

    def ensure_window_width(self, min_width, min_height=0):
        """Grow (never shrink) the dashboard window so wide layouts fit —
        the Notes screen calls this when a note is open and the Studio column
        would otherwise be hidden by the CSS breakpoint. Fail-closed: a host
        without ensure_window_size just keeps the current size (the breakpoint
        still keeps the layout sane)."""
        try:
            fn = getattr(self.dashboard, "ensure_window_size", None)
            if callable(fn):
                fn(float(min_width), float(min_height or 0))
                return _ok()
        except Exception as e:
            logger.debug(f"ensure_window_width failed: {e}")
        return {"ok": False}

    def set_note_pinned(self, note_id, pinned):
        """Pin/unpin a note (Notes v3). Local-first; the cloud PATCH is
        best-effort. Deliberately does NOT bump updated_at — pinning is a
        preference, not an edit, so it must not reorder the recency-sorted
        list or mint a conflict pair (Apple Notes behaves the same way)."""
        on = bool(pinned)
        notes = list(self._local_notes())
        found = False
        for n in notes:
            if n.get("id") == note_id:
                n["is_pinned"] = on
                found = True
                break
        if not found:
            return _err("note not found")
        self._save_local_notes(notes)
        if self._sync_on() and "::conflict::" not in str(note_id):
            try:
                import httpx
                from app.sync import SUPABASE_URL
                from app.auth import auth_header
                httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/notes?id=eq.{note_id}",
                    headers={**auth_header(self.app.config, json=True),
                             "Prefer": "return=minimal"},
                    json={"is_pinned": on},
                    timeout=8,
                )
            except Exception as e:
                logger.debug(f"Note pin cloud sync failed: {e}")
        return _ok(notes=notes, pinned=on)

    def export_note_text(self, title, content, fmt="md"):
        """Export one note via a native save panel (fallback ~/Downloads),
        mirroring export_meeting. The DASHBOARD builds the content — it owns
        the markdown-vs-HTML distinction — so this is a plain save-text-file
        primitive and never touches the note store."""
        try:
            import os
            import re as _re
            import threading
            fmt = "txt" if str(fmt).lower() == "txt" else "md"
            safe = _re.sub(r"[^\w\s\-–—]", "", title or "Note").strip()[:60] or "Note"
            fname = f"{safe}.{fmt}"

            box = {}
            done = threading.Event()

            def run():
                try:
                    from AppKit import NSSavePanel
                    panel = NSSavePanel.savePanel()
                    panel.setNameFieldStringValue_(fname)
                    panel.setCanCreateDirectories_(True)
                    if int(panel.runModal()) == 1:      # NSModalResponseOK
                        box["path"] = panel.URL().path()
                    else:
                        box["cancelled"] = True
                except Exception as e:
                    box["error"] = str(e)
                finally:
                    done.set()

            self.app._on_main(run)
            done.wait(180)
            if box.get("cancelled"):
                return {"ok": False, "cancelled": True}
            path = box.get("path")
            if not path:                                 # panel failed → Downloads
                path = os.path.expanduser(f"~/Downloads/{fname}")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content or "")
            return _ok(path=path)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_note(self, note_id):
        # Cloud side FIRST (IDI-158), and it's a TOMBSTONE (deleted_at + content
        # cleared), not a hard DELETE — other devices' merges treat the tombstone
        # as authoritative, and nothing can back-fill the note into existence.
        # If the cloud write fails while sync is on, the note is KEPT locally and
        # an error returned — the UI must not pretend a delete that didn't stick
        # (conflict copies are local-only, so they skip the cloud step).
        if self._sync_on() and "::conflict::" not in str(note_id):
            try:
                import httpx
                import datetime as _dt
                from app.sync import SUPABASE_URL
                from app.auth import auth_header
                now = _dt.datetime.now(_dt.timezone.utc).isoformat()
                resp = httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/notes?id=eq.{note_id}",
                    headers={**auth_header(self.app.config, json=True),
                             "Prefer": "return=minimal"},
                    json={"deleted_at": now, "updated_at": now, "title": "",
                          "content": "", "raw_content": None, "audio_segments": []},
                    timeout=10,
                )
                resp.raise_for_status()
            except Exception as e:
                logger.debug(f"Note cloud delete failed: {e}")
                return {"ok": False, "error": "Couldn't delete from the cloud — check your connection",
                        "notes": list(self._local_notes())}
        nid = str(note_id)
        notes = [n for n in self._local_notes()
                 if n.get("id") != note_id
                 and n.get("conflict_of") != note_id
                 and not str(n.get("id", "")).startswith(f"{nid}::conflict::")]
        self._save_local_notes(notes)
        return _ok(notes=notes)

    # ── voice dictation into a note (repeatable) ──────────────────────────────
    def note_dictate_start(self):
        rec = getattr(self.app, "recorder", None)
        if rec is None:
            return {"ok": False, "error": "no recorder"}
        if getattr(self.app, "_is_recording", False):
            return {"ok": False, "error": "busy"}
        try:
            rec.start()
            return _ok()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def note_dictate_pause(self):
        """Pause/resume the in-note dictation (v3.2 dictation bar). Returns the
        new paused state. Fail-closed — an error never touches the recording."""
        rec = getattr(self.app, "recorder", None)
        if rec is None:
            return {"ok": False, "error": "no recorder"}
        try:
            return _ok(paused=bool(rec.toggle_pause()))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def note_dictate_cancel(self):
        """Discard the in-progress in-note dictation: stop the recorder and
        throw the audio away — nothing is transcribed, persisted or linked."""
        rec = getattr(self.app, "recorder", None)
        if rec is None:
            return {"ok": False, "error": "no recorder"}
        try:
            rec.stop()   # returned audio is deliberately dropped
            return _ok()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def note_dictate_level(self):
        """Current mic level 0..1 for the dictation bar's live waveform.
        Cheap (reads a float the audio callback already maintains); polled by
        the dashboard every ~120 ms while recording. Never raises."""
        rec = getattr(self.app, "recorder", None)
        try:
            return _ok(level=float(rec.level) if rec is not None else 0.0)
        except Exception:
            return _ok(level=0.0)

    def note_dictate_stop(self, note_id=None):
        rec = getattr(self.app, "recorder", None)
        if rec is None:
            return {"ok": False, "error": "no recorder"}
        try:
            audio = rec.stop()
            if audio is None:
                return _ok(text="")
            from app.transcriber import transcribe_with_status
            text, status = transcribe_with_status(audio, self.app.config, rec.sample_rate)
            if status != "ok" or not text:
                return _ok(text="", status=status)
            raw_text = text
            # Per-segment cleanup only (Decision 2): the newly-dictated chunk is
            # cleaned; the whole note is NOT re-formatted here.
            try:
                from app.ai_cleanup import process_text
                text = process_text(text, self.app.config)
            except Exception:
                pass
            # Audio linkage (Feature 4) — gated + fail-closed: never let recording
            # persistence break the transcribe path. Returns the appended segment so
            # the editor can attach it; when a note_id is given we also append locally.
            segment = None
            if feature_flag(self.app.config, "notes_audio_linkage_enabled"):
                try:
                    segment = self._persist_note_recording(audio, rec.sample_rate, note_id)
                    if segment and note_id:
                        self._append_audio_segment(note_id, segment)
                except Exception as e:
                    logger.debug(f"note audio linkage failed: {e}")
            result = _ok(text=text, raw_text=raw_text)
            if segment:
                result["segment"] = segment
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── note audio-segment persistence (Feature 4) ────────────────────────────
    def _persist_note_recording(self, audio, sample_rate, note_id=None):
        """Save the note's recording as a local WAV (reusing recordings.py) and
        return an audio-segment dict {id, url, created_at}. Upload to the cloud runs
        in the background; local playback works immediately via recordings.path_for.
        Returns None on failure. Never raises out (caller also guards)."""
        from app import recordings
        rec_id = recordings.new_id()
        local_path = recordings.save_wav(audio, sample_rate, rec_id)
        if not local_path:
            return None
        segment = {
            "id": rec_id,
            "url": "",
            "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        user_id = self.app.config.get("sync_user_id", "")
        # A recording is a CAPTURE artifact — signed-in gate only, no toggle
        # (IDI-171 decision), but it must stop at sign-out (IDI-170).
        if user_id and _cloud_allowed(self.app.config):
            def _upload():
                try:
                    url = recordings.upload_cloud(local_path, user_id, rec_id)
                    if url and note_id:
                        self._set_segment_url(note_id, rec_id, url)
                except Exception as e:
                    logger.debug(f"note recording upload failed: {e}")
            threading.Thread(target=_upload, daemon=True).start()
        return segment

    def _append_audio_segment(self, note_id, segment):
        """UNION-append one audio segment onto a local note's audio_segments and
        bump updated_at. Idempotent (union dedups by id)."""
        notes = list(self._local_notes())
        for n in notes:
            if n.get("id") == note_id:
                n["audio_segments"] = _union_audio_segments(n.get("audio_segments"), [segment])
                n["updated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
                self._save_local_notes(notes)
                return True
        return False

    def _set_segment_url(self, note_id, rec_id, url):
        """Fill in the cloud URL on an already-appended segment once upload finishes."""
        notes = list(self._local_notes())
        changed = False
        for n in notes:
            if n.get("id") == note_id:
                for seg in n.get("audio_segments", []) or []:
                    if isinstance(seg, dict) and seg.get("id") == rec_id and not seg.get("url"):
                        seg["url"] = url
                        changed = True
        if changed:
            self._save_local_notes(notes)
        return changed

    def search_notes(self, query):
        """Case-insensitive substring search over local notes. Title matches rank
        above content/raw matches; recency (updated_at desc) breaks ties. Linear scan
        — trivially <100ms to well past 1,000 notes, so no separate index is needed.
        When the search flag is off, returns all notes unfiltered. Never raises."""
        notes = list(self._local_notes())
        # Conflict copies are internal; don't surface them as search hits.
        notes = [n for n in notes if "::conflict::" not in (n.get("id") or "")]
        if not feature_flag(self.app.config, "notes_search_enabled"):
            return _ok(notes=notes, query=query or "")
        q = (query or "").strip().lower()
        if not q:
            return _ok(notes=notes, query="")

        def rank(n):
            if q in (n.get("title") or "").lower():
                return 0
            if q in (n.get("content") or "").lower() or q in (n.get("raw_content") or "").lower():
                return 1
            return 2

        matched = [n for n in notes if rank(n) < 2]
        # Two stable passes: recency desc first, then rank asc → title beats content,
        # newest wins ties.
        matched.sort(key=lambda n: n.get("updated_at", "") or "", reverse=True)
        matched.sort(key=rank)
        return _ok(notes=matched, query=query or "")

    def format_note_with_ai(self, text, style="structured"):
        """Explicit Reformat (Decision 2): (re)format `text` in ONE LLM call and
        return {title, formatted_content} (also `content` for the existing UI).
        Structure detection and auto-title follow their feature flags. `style`
        (Notes v3) picks the output shape — structured | prose | transcript —
        and only ever arrives from an explicit user pick. On failure returns
        _err so the caller keeps the current content unchanged."""
        # NOTE: no local-key gate here — clients hold no Groq key since IDI-178;
        # format_note goes through the groq-proxy first and local keys are only
        # a silent fallback inside it.
        cfg = self.app.config
        try:
            from app.ai_cleanup import format_note, NOTE_STYLES
            if style not in NOTE_STYLES:
                style = "structured"
            result = format_note(
                text, cfg,
                structure_detection=feature_flag(cfg, "notes_structure_detection_enabled"),
                autotitle=feature_flag(cfg, "notes_autotitle_enabled"),
                style=style,
            )
            if not result:
                return _err("AI format failed")
            content = result.get("formatted_content") or text
            return _ok(title=result.get("title", ""), content=content,
                       formatted_content=content)
        except Exception as e:
            logger.error(f"AI note format failed: {e}")
            return _err(str(e))

    def ask_notes(self, question):
        """Ask-your-notes (Notes v3, mirrors meetings.ask_meetings): rank local
        notes by token overlap, feed the top few to ONE LLM call, return
        {'ok','answer','sources'}. Explicit user action only (Enter/Ask in the
        notes search box) — never fires automatically. Fails closed."""
        try:
            import re as _re
            q = (question or "").strip()
            if not q:
                return _err("Empty question.")

            def plain(n):
                c = n.get("content") or ""
                c = _re.sub(r"<[^>]+>", " ", c)
                c = c.replace("&nbsp;", " ").replace("&amp;", "&")
                return _re.sub(r"\s+", " ", c).strip()

            notes = [n for n in self._local_notes()
                     if "::conflict::" not in (n.get("id") or "")]
            rows = [(n, plain(n)) for n in notes]
            rows = [(n, p) for (n, p) in rows
                    if p or (n.get("title") or "").strip()]
            if not rows:
                return _err("No notes yet — create one first.")

            q_tokens = {t for t in _re.findall(r"[a-z0-9]+", q.lower())
                        if len(t) > 2}

            def score(item):
                n, p = item
                title = (n.get("title") or "").lower()
                body = p.lower()
                s = 0
                for t in q_tokens:
                    if t in title:
                        s += 3
                    if t in body:
                        s += 1
                return s

            ranked = sorted(rows, key=score, reverse=True)[:6]
            ctx = "\n\n---\n\n".join(
                f"NOTE: {n.get('title') or 'Untitled'}"
                f" ({(n.get('updated_at') or '')[:10]})\n{p[:2000]}"
                for n, p in ranked)
            from app.groq_proxy import chat_via_proxy
            system = ("You answer questions from the user's personal notes. "
                      "Use ONLY the notes provided below. Be concise and direct "
                      "— a short paragraph or a few bullets. If the notes don't "
                      "contain the answer, say so plainly. Never invent facts. "
                      "Answer in the language of the question.")
            messages = [{"role": "system", "content": system},
                        {"role": "user",
                         "content": f"NOTES:\n\n{ctx}\n\nQUESTION: {q}"}]
            answer = chat_via_proxy(messages, self.app.config,
                                    max_tokens=768, timeout=30.0)
            if not answer:
                return _err("The model didn't answer — try again.")
            return _ok(answer=answer,
                       sources=[n.get("title") or "Untitled"
                                for n, _ in ranked[:3] if score((n, _)) > 0])
        except Exception as e:
            logger.error(f"ask_notes failed: {e}")
            return _err(str(e))

    def save_settings(self, settings):
        cfg = self.app.config
        cfg["groq_api_keys"] = [k.strip() for k in settings.get("groq_api_keys", []) if k.strip()]
        cfg["gemini_api_keys"] = [k.strip() for k in settings.get("gemini_api_keys", []) if k.strip()]
        cfg["whisper_model"] = settings.get("whisper_model", cfg.get("whisper_model", "base"))
        cfg["recording_mode"] = settings.get("recording_mode", cfg.get("recording_mode", "toggle"))
        cfg["sync_enabled"] = bool(settings.get("sync_enabled"))
        cfg["sync_user_id"] = settings.get("sync_user_id", "").strip()
        # Blank name → the MACHINE's name, not the literal "Windows" (IDI-173):
        # this string is the canvas/history origin label every other device
        # shows, and a Mac announcing itself as "Windows" is both wrong and the
        # exact mismatch the origin filtering had to work around.
        import platform as _plat
        cfg["sync_device_name"] = (settings.get("sync_device_name", "").strip()
                                   or _plat.node() or "This device")
        # Notes v2 feature flags — only overwrite when present so a partial settings
        # payload never clobbers a flag back to its default.
        for flag in NOTES_FEATURE_FLAGS:
            if flag in settings:
                cfg[flag] = bool(settings[flag])
        # Pipeline flags (speed_mode / chained_mode) — same "only when present" rule,
        # so switching pipeline can never silently reset an unrelated toggle.
        for flag in PIPELINE_FLAGS:
            if flag in settings:
                cfg[flag] = bool(settings[flag])
        if any(flag in settings for flag in PIPELINE_FLAGS):
            cfg["pipeline_choice_explicit"] = True   # never auto-migrated again
        # ASR model: validated against the allowed set here rather than trusted, so a
        # bad value from anywhere can't reach Groq and 400 every dictation.
        if "asr_model" in settings:
            from app.transcriber import ASR_CHOICES
            _m = str(settings.get("asr_model") or "auto").strip()
            cfg["asr_model"] = _m if _m in ASR_CHOICES else "auto"
        save_config(cfg)
        self.app.config = cfg
        self.app._mode = cfg["recording_mode"]
        if getattr(self.app, "hotkey_listener", None):
            try:
                self.app.hotkey_listener.set_mode(cfg["recording_mode"])
            except Exception:
                pass
        # IDI-167 — the menubar's Recording Mode / Whisper Model checkmarks are
        # stateful rumps items; writing the config here used to leave them
        # showing the OLD choice until restart. Hop to the main thread (AppKit
        # discipline, Hard Rule #4). hasattr-guarded so the Windows app class,
        # which has no rumps menu at all, is untouched.
        if hasattr(self.app, "sync_menu_state") and hasattr(self.app, "_on_main"):
            try:
                self.app._on_main(self.app.sync_menu_state)
            except Exception as e:
                logger.debug("menubar state sync skipped: %s", e)
        if hasattr(self.app, '_restart_sync'):
            self.app._restart_sync()
        elif hasattr(self.app, '_init_sync'):
            if self.app._sync:
                try:
                    self.app._sync.stop()
                except Exception:
                    pass
                self.app._sync = None
            self.app._init_sync()
        self.dashboard._load_devices()
        return self.get_state()

    # ── device pairing (QR) ───────────────────────────────────────────────────
    def _ensure_sync_account(self):
        """Make sure this device has a sync user_id + sync enabled, starting the
        sync client if needed. Returns the user_id. Used when the host begins
        pairing before sync was ever configured."""
        import uuid
        cfg = self.app.config
        uid = (cfg.get("sync_user_id") or "").strip()
        started = False
        if not uid:
            uid = uuid.uuid4().hex
            cfg["sync_user_id"] = uid
            started = True
        if not cfg.get("sync_enabled"):
            cfg["sync_enabled"] = True
            started = True
        if started:
            save_config(cfg)
            self.app.config = cfg
            try:
                if hasattr(self.app, "_restart_sync"):
                    self.app._restart_sync()
                elif hasattr(self.app, "_init_sync"):
                    if getattr(self.app, "_sync", None):
                        try:
                            self.app._sync.stop()
                        except Exception:
                            pass
                        self.app._sync = None
                    self.app._init_sync()
            except Exception as e:
                logger.warning("pairing: could not start sync (%s)", e)
        return uid

    def start_pairing(self):
        """Host: create a short-lived token and return a QR (SVG) for it."""
        try:
            from app import pairing
            uid = self._ensure_sync_account()
            host = (self.app.config.get("sync_device_name") or "").strip()
            if not host:
                import platform
                host = platform.node()
            token, expires_at, ttl = pairing.create_pairing(uid, host, cfg=self.app.config)
            svg = pairing.qr_svg("flume://pair?t=" + token)
            return _ok(token=token, svg=svg, user_id=uid, host=host, expires_in=ttl)
        except Exception as e:
            logger.error("start_pairing failed: %s", e)
            return {"ok": False, "error": str(e)}

    def cancel_pairing(self, token):
        """Host: revoke an unclaimed token server-side (Cancel / TTL expiry) —
        a QR photographed before Cancel must not stay claimable (IDI-157)."""
        try:
            from app import pairing
            pairing.cancel_pairing(token, cfg=self.app.config)
        except Exception as e:
            logger.debug("cancel_pairing api failed: %s", e)
        return _ok()

    def check_pairing(self, token):
        """Host: poll whether the token has been claimed by another device."""
        try:
            from app import pairing
            row = pairing.check_pairing(token, cfg=self.app.config)
            claimed = bool(row and row.get("claimed_by"))
            if claimed:
                # a new device joined — refresh the device list
                try:
                    self.dashboard._load_devices()
                except Exception:
                    pass
            return _ok(claimed=claimed, device_name=(row or {}).get("claimed_by"))
        except Exception as e:
            logger.debug("check_pairing failed: %s", e)
            return {"ok": False, "error": str(e)}

    # ── recordings: playback + retry ──────────────────────────────────────────
    def _find_entry(self, entry_id):
        for e in self.app.config.get("history", []):
            if isinstance(e, dict) and e.get("id") == entry_id:
                return e
        # Fall back to note audio segments (Feature 4) so get_audio/play_recording
        # serve note recordings the same way. Synthesizes a minimal entry pointing at
        # the local WAV (recordings.path_for) with the cloud URL for download-if-missing.
        # Fail-closed: never raises out of the lookup.
        try:
            from app import recordings
            for n in self._local_notes():
                for seg in (n.get("audio_segments") or []):
                    if isinstance(seg, dict) and seg.get("id") == entry_id:
                        return {"id": entry_id,
                                "audio": recordings.path_for(entry_id),
                                "audio_url": seg.get("url", "") or ""}
        except Exception:
            pass
        return None

    def _ensure_local_audio(self, entry):
        """Return a local WAV path for the entry, downloading from cloud if needed.
        recordings is private (MER-27) — sign a short-lived URL before fetching;
        `stored` may be a bare object path (new) or a legacy public URL (old rows)."""
        from app import recordings
        path = entry.get("audio") or ""
        if path and os.path.exists(path):
            return path
        stored = entry.get("audio_url") or ""
        if stored:
            object_path = recordings.extract_object_path(stored, "recordings")
            signed = recordings.sign_url("recordings", object_path)
            if signed:
                dest = recordings.path_for(entry.get("id") or recordings.new_id())
                recordings.ensure_dir()
                if recordings.download(signed, dest):
                    entry["audio"] = dest
                    save_config(self.app.config)
                    return dest
        return path if path else None

    def play_recording(self, entry_id):
        entry = self._find_entry(entry_id)
        if not entry:
            return {"ok": False, "error": "not found"}
        path = self._ensure_local_audio(entry)
        if not path or not os.path.exists(path):
            return {"ok": False, "error": "no audio"}
        from app import recordings
        recordings.play(path)
        return _ok()

    def get_audio(self, entry_id):
        """Return the recording as a base64 data-URI so the WebView can play it
        (works for both local files and cloud-only recordings)."""
        entry = self._find_entry(entry_id)
        if not entry:
            return {"ok": False, "error": "not found"}
        path = self._ensure_local_audio(entry)
        if not path or not os.path.exists(path):
            return {"ok": False, "error": "no audio"}
        try:
            duration = 0.0
            try:
                import soundfile as sf
                duration = float(sf.info(path).duration)
            except Exception:
                pass
            with open(path, "rb") as f:
                data = f.read()
            uri = "data:audio/wav;base64," + base64.b64encode(data).decode("ascii")
            return _ok(data_uri=uri, duration=duration)
        except Exception as e:
            logger.error("get_audio failed: %s", e)
            return {"ok": False, "error": str(e)}

    def retry_transcription(self, entry_id):
        entry = self._find_entry(entry_id)
        if not entry:
            return {"ok": False, "error": "not found"}
        path = self._ensure_local_audio(entry)
        if not path or not os.path.exists(path):
            return {"ok": False, "error": "no audio to retry"}
        try:
            from app import recordings
            from app.transcriber import transcribe_with_status
            from app.ai_cleanup import process_text
            audio, sr = recordings.load_wav(path)
            if audio is None:
                return {"ok": False, "error": "could not read audio"}
            text, status = transcribe_with_status(audio, self.app.config, sr)
            if status != "ok" or not text:
                return {"ok": False, "error": "still failing — check your connection"}
            result = process_text(text, self.app.config)
            from app.config import update_history_entry
            update_history_entry(self.app.config, entry_id, text=result, status="done")
            pyperclip.copy(result)
            # push to other devices if sync is on
            if getattr(self.app, "_sync", None):
                try:
                    # Full push shape (IDI-172): a retried entry already HAS its
                    # uploaded audio, so the receiving device gets it too.
                    self.app._sync.push(result, None,
                                        (entry.get("audio_url") or ""), "done",
                                        entry_id)
                except Exception:
                    pass
            return self.get_state()
        except Exception as e:
            logger.error("retry_transcription failed: %s", e)
            return {"ok": False, "error": str(e)}

    def fetch_canvas(self):
        try:
            import httpx

            from app.sync import SUPABASE_URL
            from app.auth import auth_header

            user_id = self.app.config.get("sync_user_id", "")
            if not user_id or not _cloud_allowed(self.app.config):
                return _ok(content="", image_url=None, status="Sign in to use Canvas")
            if not self._sync_on():
                return _ok(content="", image_url=None, status=SYNC_OFF_MSG)
            resp = httpx.get(
                f"{SUPABASE_URL}/rest/v1/canvas",
                headers=auth_header(self.app.config),
                params={"user_id": f"eq.{user_id}",
                        # D1 redesign (2026-08-17): the Live card shows origin +
                        # freshness, so the read carries them (additive).
                        "select": "content,image_url,device_name,device_id,updated_at"},
                timeout=8,
            )
            if resp.status_code != 200:
                return _err(f"Canvas load failed: {resp.status_code}")
            data = resp.json()
            row = data[0] if data else {}
            from app.config import get_device_id
            own = bool(row.get("device_id")) and row.get("device_id") == get_device_id(self.app.config)
            return _ok(content=row.get("content", "") or "", image_url=row.get("image_url"),
                       device_name=row.get("device_name") or "", updated_at=row.get("updated_at") or "",
                       own=own)
        except Exception as e:
            logger.error(f"Canvas fetch failed: {e}")
            return _err(str(e))

    def save_canvas(self, content=KEEP, image_url=KEEP):
        """Write the shared canvas (IDI-173).

        Both columns are OPTIONAL and omitted unless this call actually means to
        change them — `KEEP` (the default, and what a missing JS argument
        resolves to) leaves the column untouched. `image_url=None` is an
        explicit "remove the image"; `content=""` is an explicit "clear the
        text". Every write carries this device's `device_id` AND `device_name`
        so receivers can skip their own echo by stable id."""
        try:
            import httpx

            from app.sync import SUPABASE_URL
            from app.auth import auth_header

            user_id = self.app.config.get("sync_user_id", "")
            if not user_id or not _cloud_allowed(self.app.config):
                return _err("Sign in to use Canvas")
            if not self._sync_on():
                return _err(SYNC_OFF_MSG)
            device_id, device_name = device_identity(self.app)
            payload = {
                "user_id": user_id,
                "device_id": device_id,
                "device_name": device_name,
                "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            }
            if content is not KEEP and content != KEEP:
                payload["content"] = content or ""
            if image_url is not KEEP and image_url != KEEP:
                payload["image_url"] = image_url
            if "content" not in payload and "image_url" not in payload:
                return _err("Nothing to save")
            resp = httpx.post(
                f"{SUPABASE_URL}/rest/v1/canvas?on_conflict=user_id",
                headers={
                    **auth_header(self.app.config, json=True),
                    "Prefer": "return=minimal,resolution=merge-duplicates",
                },
                json=payload,
                timeout=10,
            )
            if resp.status_code not in (200, 201):
                return _err(f"Canvas save failed: {resp.status_code}")
            if payload.get("content"):
                pyperclip.copy(payload["content"])
            return _ok()
        except Exception as e:
            logger.error(f"Canvas save failed: {e}")
            return _err(str(e))

    def clear_canvas(self):
        """Explicit clear (IDI-173): an actual write of `{content: '',
        image_url: null}`, not a no-op. Receivers APPLY the empty content —
        which is why the write has to say both columns out loud."""
        return self.save_canvas("", None)

    def save_canvas_image_data(self, data_uri, content=""):
        """Accept an image as a base64 data-URI (from a file picker or paste in
        the WebView), upload it, and save the canvas row. Cross-platform."""
        try:
            if not data_uri:
                return _err("No image data")
            header, _, b64 = data_uri.partition(",")
            if not b64:
                b64 = header
                header = "image/png"
            ext = "png"
            if "image/" in header:
                sub = header.split("image/")[1].split(";")[0].strip().lower()
                ext = {"jpeg": "jpg"}.get(sub, sub) or "png"
                if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
                    ext = "png"
            data = base64.b64decode(b64)
            up = self._upload_image_bytes(data, ext)
            if not up.get("ok"):
                return up
            url = up.get("image_url")
            self.save_canvas(content or "", url)
            return _ok(image_url=url)
        except Exception as e:
            logger.error(f"Canvas image data upload failed: {e}")
            return _err(str(e))

    def canvas_add_image_file(self, content=""):
        """Native file picker (WKWebView can't reliably open a JS <input file>)."""
        dash = self.dashboard
        if not hasattr(dash, "pick_image_native"):
            return self.choose_canvas_image()  # pywebview fallback (Windows)
        box = dash.pick_image_native()
        if box.get("error"):
            return _err(box["error"])
        if box.get("cancelled") or not box.get("path"):
            return _ok(cancelled=True)
        up = self._upload_image_path(box["path"])
        if not up.get("ok"):
            return up
        self.save_canvas(content or "", up.get("image_url"))
        return _ok(image_url=up.get("image_url"))

    def canvas_paste_image(self, content=""):
        """Read an image from the system clipboard natively, upload + save."""
        dash = self.dashboard
        box = dash.clipboard_image_native() if hasattr(dash, "clipboard_image_native") else {}
        if box.get("error"):
            return _err(box["error"])
        if box.get("bytes"):
            up = self._upload_image_bytes(box["bytes"], box.get("ext", "png"))
            if not up.get("ok"):
                return up
            self.save_canvas(content or "", up.get("image_url"))
            return _ok(image_url=up.get("image_url"))
        # Fallback: PIL clipboard grab (Windows / no native helper)
        r = self.paste_canvas_image_from_clipboard()
        if r.get("ok") and r.get("image_url"):
            self.save_canvas(content or "", r["image_url"])
        return r if r.get("ok") else _err("No image found in the clipboard")

    def choose_canvas_image(self):
        try:
            import webview

            if not self.dashboard._window:
                return _err("Dashboard window is not ready")
            paths = self.dashboard._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Images (*.png;*.jpg;*.jpeg;*.webp;*.gif)", "All files (*.*)"),
            )
            if not paths:
                return _ok(cancelled=True)
            return self._upload_image_path(paths[0])
        except Exception as e:
            logger.error(f"Image selection failed: {e}")
            return _err(str(e))

    def paste_canvas_image_from_clipboard(self):
        try:
            from PIL import ImageGrab

            img = ImageGrab.grabclipboard()
            if img is None:
                return _err("Clipboard does not contain an image")
            import io

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return self._upload_image_bytes(buf.getvalue(), "png")
        except Exception as e:
            logger.error(f"Clipboard image upload failed: {e}")
            return _err(str(e))

    def _upload_image_path(self, path):
        with open(path, "rb") as f:
            data = f.read()
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else "png"
        if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
            ext = "png"
        return self._upload_image_bytes(data, ext)

    def _upload_image_bytes(self, data: bytes, ext: str):
        import httpx

        from app.sync import SUPABASE_KEY, SUPABASE_URL

        user_id = self.app.config.get("sync_user_id", "")
        if not user_id or not self._sync_on():
            return _err("Sign in and turn on sync to use Canvas images")
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        path = f"canvas/{user_id}_{int(time.time())}.{ext}"
        upload = httpx.post(
            f"{SUPABASE_URL}/storage/v1/object/canvas-images/{path}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": mime,
                "x-upsert": "true",
            },
            content=data,
            timeout=30,
        )
        if upload.status_code not in (200, 201):
            return _err(f"Image upload failed: {upload.status_code}")
        url = f"{SUPABASE_URL}/storage/v1/object/public/canvas-images/{path}"
        return _ok(image_url=url, preview=f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}")
