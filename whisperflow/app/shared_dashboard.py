"""Shared web dashboard for cross-platform desktop builds.

This is intentionally separate from the macOS AppKit dashboard so the current
Mac app remains untouched while Windows gets the same product surface.
"""

from __future__ import annotations

import base64
import datetime as _dt
import logging
import os
import threading
import time
from typing import Any

import pyperclip

from app.config import (
    APP_VERSION,
    NOTES_FEATURE_FLAGS,
    _entry_app,
    _entry_text,
    feature_flag,
    get_daily_words,
    load_config,
    save_config,
)

logger = logging.getLogger("verbal.shared_dashboard")


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
        self._target_device_id = "__all__"
        self._known_devices = []
        self._last_canvas_loaded = False
        self._canvas_listener_started = False

    def show(self):
        try:
            import webview
        except Exception as e:
            logger.error(f"pywebview is not available: {e}")
            from app.win_dashboard import WinDashboard

            fallback = WinDashboard(self.app)
            fallback.show()
            return

        if self._window:
            try:
                self._window.show()
                return
            except Exception:
                self._window = None

        # Render the SAME dark "Flume" UI the macOS app uses. flume_html() is
        # already dual-target: it waits for `pywebviewready` and calls the shared
        # DashboardApi via window.pywebview.api.* (native under pywebview here;
        # shimmed inside WKWebView on macOS). This is what gives Windows visual
        # parity with the Mac app instead of the retired light-theme dashboard.
        from app.flume_dashboard_html import flume_html

        api = DashboardApi(self)
        self._window = webview.create_window(
            "Flume",
            html=flume_html(),
            js_api=api,
            width=980,
            height=680,
            min_size=(760, 520),
            background_color="#0e1012",
        )
        # Windows: inject a CSS override that anchors `.screen` sections to
        # viewport height. WKWebView on macOS resolves the shared HTML's
        # `.main { height: 100% }` against an implicit viewport-height
        # ancestor; WebView2 doesn't, so `.main` collapses to content and
        # overflow-y:auto has nothing to scroll (History/Notes escape this
        # because .threepane already sets height:100vh explicitly). Keep the
        # shared HTML untouched — this fix is host-side only.
        try:
            self._window.events.loaded += self._inject_scroll_fix
        except Exception as e:
            logger.debug("scroll-fix hook attach failed: %s", e)
        threading.Thread(target=self._device_refresh_loop, daemon=True).start()
        if not self._canvas_listener_started:
            self._canvas_listener_started = True
            threading.Thread(target=self._canvas_listen_loop, daemon=True).start()
        # W3 (Windows): the recording overlay owns the pywebview event loop and
        # already called webview.start() from win_overlay.setup(). pywebview
        # only supports one start() per process, so if that flag is set the
        # newly-created window is already live on the running loop and we
        # must not start() again. On macOS this path isn't reached (Mac uses
        # flume_web_dashboard, not SharedDashboard) so the flag stays False.
        if not getattr(webview, "_verbal_started", False):
            webview._verbal_started = True
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
        # Map tray indices to Flume screen ids (see flume_dashboard_html.show()).
        # Indices match the win_main tray callbacks: canvas=3, settings=4, notes=5.
        TAB_MAP = {0: "history", 1: "history", 2: "home", 3: "canvas", 4: "settings", 5: "notes"}
        tab_name = TAB_MAP.get(idx, "home")
        self._emit("selectTab", {"tab": tab_name})

    def _refresh(self):
        self._emit("state", DashboardApi(self).get_state())

    def _emit(self, event: str, payload: dict[str, Any]):
        if not self._window:
            return
        try:
            import json

            js = f"window.VerbalNative && window.VerbalNative({json.dumps(event)}, {json.dumps(payload)});"
            self._window.evaluate_js(js)
        except Exception as e:
            logger.debug(f"Dashboard emit failed: {e}")

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
        if not user_id or not self.app._sync:
            self._known_devices = []
            return
        from app.sync import fetch_devices

        devices = fetch_devices(user_id, self.app._sync.device_id)
        self._known_devices = devices
        # Ensure our target_device_id is still valid if it was a specific device
        if self._target_device_id not in ("__all__", "__none__") and self._target_device_id is not None:
            if not any(d["device_id"] == self._target_device_id for d in devices):
                self._target_device_id = "__all__"
        self._emit("devices", {"devices": devices, "target_device_id": self._target_device_id})

    def _canvas_listen_loop(self):
        """Keep canvas synced while the dashboard is open."""
        while True:
            try:
                self._canvas_listen_once()
            except Exception as e:
                logger.debug(f"Canvas listener failed: {e}")
            time.sleep(5)

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

        user_id = self.app.config.get("sync_user_id", "")
        device_name = self.app.config.get("sync_device_name", "Windows")
        if not user_id:
            time.sleep(5)
            return

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
                            }
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
                if record.get("device_name") == device_name:
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
            header={"Authorization": f"Bearer {SUPABASE_KEY}"},
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

    def get_state(self):
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
                "sync_device_name": cfg.get("sync_device_name", "Windows"),
                "hotkey_hold": cfg.get("hotkey_hold", "alt_r"),
                "hotkey_toggle": cfg.get("hotkey_toggle", "alt_r"),
                # Notes v2 feature flags (default true) so Settings can toggle each.
                "notes_search_enabled": feature_flag(cfg, "notes_search_enabled"),
                "notes_autotitle_enabled": feature_flag(cfg, "notes_autotitle_enabled"),
                "notes_structure_detection_enabled": feature_flag(cfg, "notes_structure_detection_enabled"),
                "notes_audio_linkage_enabled": feature_flag(cfg, "notes_audio_linkage_enabled"),
            },
            sync_connected=bool(self.app._sync and self.app._sync.connected),
            devices=self.dashboard._known_devices,
            target_device_id=self.dashboard._target_device_id,
            signed_in=bool(cfg.get("auth") and cfg.get("auth", {}).get("user_id")),
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

    def _meeting_mode(self, mode):
        try:
            win = getattr(self.app, "meeting_window", None)
            if win:
                win.set_mode(mode)
        except Exception:
            pass

    def close_meeting_window(self):
        try:
            win = getattr(self.app, "meeting_window", None)
            if win:
                self.app._on_main(win.hide)
            return _ok()
        except Exception as e:
            return {"ok": False, "error": str(e)}

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

    def expand_meeting_window(self):
        """Bar → full window (fluid morph)."""
        try:
            win = getattr(self.app, "meeting_window", None)
            if win:
                win.expand()
            return _ok()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def collapse_meeting_window(self):
        """Full window → ambient bar (only while a meeting records)."""
        try:
            win = getattr(self.app, "meeting_window", None)
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

    def open_meeting(self, meeting_id):
        """Open a past meeting in the summary view (31e)."""
        try:
            m = self._meetings()
            got = m.get_meeting(meeting_id) if m else {"ok": False, "error": "unavailable"}
            if not got.get("ok"):
                return got
            row = got["meeting"]
            try:
                m.mark_meeting_opened(meeting_id)   # clears the NEW indicator
            except Exception:
                pass

            def run():
                win = self.app._meeting_win()
                if win:
                    win.show("summary")
                    # dedicated event: an explicit open must always replace the
                    # displayed meeting (the generic 'meeting' event is guarded
                    # against background sessions hijacking the view)
                    win.emit("openMeeting", row)
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
        "meetings_sync_enabled",
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
        try:
            m = self._meetings()
            if m and m.session:
                m.session.set_title(title)
                return _ok()
            return {"ok": False, "error": "No meeting."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def rename_speaker(self, speaker_id, name):
        try:
            m = self._meetings()
            if m and m.session:
                m.session.rename_speaker(speaker_id, name)
                return _ok(speakers=m.session.speakers)
            return {"ok": False, "error": "No meeting."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def ask_meetings(self, question):
        """Chat-style Q&A over the user's recorded meetings (Meetings page)."""
        try:
            from app.meetings import ask_meetings
            return ask_meetings(self.app.config, question)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def export_meeting(self, meeting_id, fmt="md"):
        """Export a meeting as .txt or .md via a native save panel (falls back
        to ~/Downloads if the panel can't be shown)."""
        try:
            import os
            import re
            import threading
            m = self._meetings()
            got = m.get_meeting(meeting_id) if m else {"ok": False, "error": "unavailable"}
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

    def get_meeting_audio(self, meeting_id):
        """Local WAV as a data-URI when present, else the public cloud URL."""
        try:
            import base64
            import os
            from app.meetings import MEETINGS_DIR
            path = os.path.join(MEETINGS_DIR, f"{meeting_id}.wav")
            if os.path.exists(path) and os.path.getsize(path) < 80 * 1024 * 1024:
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                return _ok(src=f"data:audio/wav;base64,{b64}")
            m = self._meetings()
            got = m.get_meeting(meeting_id) if m else {"ok": False}
            url = (got.get("meeting") or {}).get("audio_url") if got.get("ok") else None
            if url:
                return _ok(src=url)
            return {"ok": False, "error": "No audio for this meeting."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_meetings(self):
        m = self._meetings()
        return m.list_meetings() if m else {"ok": True, "meetings": []}

    def get_meeting(self, meeting_id):
        m = self._meetings()
        return m.get_meeting(meeting_id) if m else {"ok": False, "error": "unavailable"}

    def complete_onboarding(self):
        self.app.config["onboarded"] = True
        save_config(self.app.config)
        return _ok()

    def sign_in_google(self):
        if hasattr(self.app, "_sign_in"):
            self.app._on_main(self.app._sign_in)
            return _ok()
        return {"ok": False, "error": "not supported"}

    def sign_out_account(self):
        if hasattr(self.app, "_sign_out"):
            self.app._on_main(self.app._sign_out)
            return _ok()
        return {"ok": False, "error": "not supported"}

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

    def pin_text(self, text, should_pin):
        cfg = self.app.config = load_config()
        pinned = list(cfg.get("pinned", []))
        pinned_texts = [_entry_text(e) for e in pinned]
        if should_pin and text not in pinned_texts:
            match = next((e for e in cfg.get("history", []) if _entry_text(e) == text), None)
            pinned.insert(0, match if isinstance(match, dict) else {"text": text, "app": "", "ts": ""})
        elif not should_pin:
            pinned = [e for e in pinned if _entry_text(e) != text]
        cfg["pinned"] = pinned[:50]
        save_config(cfg)
        return self.get_state()

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
        return _ok(vocabulary=d["vocabulary"], replacements=d["replacements"])

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
        return _ok(snippets=dictionary.get_snippets(self.app.config))

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
        return _ok(snippets=dictionary.get_snippets(self.app.config))

    def delete_snippet(self, snippet_id):
        from app import dictionary
        dictionary.remove_snippet(self.app.config, snippet_id, save_config)
        return _ok(snippets=dictionary.get_snippets(self.app.config))

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
        self.app.config["history"] = []
        self.app.config["pinned"] = []
        save_config(self.app.config)
        return self.get_state()

    # ── Notes API ───────────────────────────────────────────────────────
    # ── notes: local-first, cloud-synced when enabled ─────────────────────────
    def _local_notes(self):
        notes = self.app.config.get("notes", [])
        return notes if isinstance(notes, list) else []

    def _save_local_notes(self, notes):
        self.app.config["notes"] = notes
        save_config(self.app.config)

    def _sync_on(self):
        return bool(self.app.config.get("sync_user_id", "") and self.app.config.get("sync_enabled"))

    def fetch_notes(self):
        notes = list(self._local_notes())
        # Merge any remote notes when sync is on. Uses the v2 merge contract:
        # conflict-pair preservation, audio_segments UNION, unknown-field passthrough.
        if self._sync_on():
            try:
                import httpx
                from app.sync import SUPABASE_KEY, SUPABASE_URL
                user_id = self.app.config.get("sync_user_id", "")
                resp = httpx.get(
                    f"{SUPABASE_URL}/rest/v1/notes",
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
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
        if raw_str and (run_cleanup or is_initial_dictated):
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
                from app.sync import SUPABASE_KEY, SUPABASE_URL
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
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                             "Content-Type": "application/json",
                             "Prefer": "resolution=merge-duplicates,return=minimal"},
                    json=payload,
                    timeout=10,
                )
            except Exception as e:
                logger.debug(f"Note cloud save failed: {e}")
        r = _ok(notes=notes)
        r["id"] = nid
        return r

    def delete_note(self, note_id):
        notes = [n for n in self._local_notes() if n.get("id") != note_id]
        self._save_local_notes(notes)
        if self._sync_on():
            try:
                import httpx
                from app.sync import SUPABASE_KEY, SUPABASE_URL
                httpx.delete(
                    f"{SUPABASE_URL}/rest/v1/notes?id=eq.{note_id}",
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                    timeout=10,
                )
            except Exception as e:
                logger.debug(f"Note cloud delete failed: {e}")
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
        if user_id:
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

    def toggle_note_pin(self, note_id):
        try:
            import httpx
            from app.sync import SUPABASE_KEY, SUPABASE_URL
            user_id = self.app.config.get("sync_user_id", "")
            if not user_id:
                return _err("Set User ID in Settings first")
            notes_resp = httpx.get(
                f"{SUPABASE_URL}/rest/v1/notes",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                params={"id": f"eq.{note_id}", "select": "is_pinned"},
                timeout=8,
            )
            current = notes_resp.json()[0].get("is_pinned", False) if notes_resp.status_code == 200 and notes_resp.json() else False
            resp = httpx.patch(
                f"{SUPABASE_URL}/rest/v1/notes?id=eq.{note_id}",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
                json={"is_pinned": not current},
                timeout=10,
            )
            if resp.status_code not in (200, 204):
                return _err(f"Pin toggle failed: {resp.status_code}")
            return self.fetch_notes()
        except Exception as e:
            logger.error(f"Pin toggle failed: {e}")
            return _err(str(e))

    def format_note_with_ai(self, text):
        """Explicit Reformat (Decision 2): (re)format `text` in ONE LLM call and
        return {title, formatted_content} (also `content` for the existing UI).
        Structure detection and auto-title follow their feature flags. On failure
        returns _err so the caller keeps the current content unchanged."""
        cfg = self.app.config
        if not (cfg.get("groq_api_keys") or []):
            return _err("No Groq API key configured")
        try:
            from app.ai_cleanup import format_note
            result = format_note(
                text, cfg,
                structure_detection=feature_flag(cfg, "notes_structure_detection_enabled"),
                autotitle=feature_flag(cfg, "notes_autotitle_enabled"),
            )
            if not result:
                return _err("AI format failed")
            content = result.get("formatted_content") or text
            return _ok(title=result.get("title", ""), content=content,
                       formatted_content=content)
        except Exception as e:
            logger.error(f"AI note format failed: {e}")
            return _err(str(e))

    def save_settings(self, settings):
        cfg = self.app.config
        cfg["groq_api_keys"] = [k.strip() for k in settings.get("groq_api_keys", []) if k.strip()]
        cfg["gemini_api_keys"] = [k.strip() for k in settings.get("gemini_api_keys", []) if k.strip()]
        cfg["whisper_model"] = settings.get("whisper_model", cfg.get("whisper_model", "base"))
        cfg["recording_mode"] = settings.get("recording_mode", cfg.get("recording_mode", "toggle"))
        cfg["sync_enabled"] = bool(settings.get("sync_enabled"))
        cfg["sync_user_id"] = settings.get("sync_user_id", "").strip()
        cfg["sync_device_name"] = settings.get("sync_device_name", "").strip() or "Windows"
        # Notes v2 feature flags — only overwrite when present so a partial settings
        # payload never clobbers a flag back to its default.
        for flag in NOTES_FEATURE_FLAGS:
            if flag in settings:
                cfg[flag] = bool(settings[flag])
        save_config(cfg)
        self.app.config = cfg
        self.app._mode = cfg["recording_mode"]
        if getattr(self.app, "hotkey_listener", None):
            try:
                self.app.hotkey_listener.set_mode(cfg["recording_mode"])
            except Exception:
                pass
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
            token, expires_at, ttl = pairing.create_pairing(uid, host)
            svg = pairing.qr_svg("flume://pair?t=" + token)
            return _ok(token=token, svg=svg, user_id=uid, host=host, expires_in=ttl)
        except Exception as e:
            logger.error("start_pairing failed: %s", e)
            return {"ok": False, "error": str(e)}

    def check_pairing(self, token):
        """Host: poll whether the token has been claimed by another device."""
        try:
            from app import pairing
            row = pairing.check_pairing(token)
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
        """Return a local WAV path for the entry, downloading from cloud if needed."""
        from app import recordings
        path = entry.get("audio") or ""
        if path and os.path.exists(path):
            return path
        url = entry.get("audio_url") or ""
        if url:
            dest = recordings.path_for(entry.get("id") or recordings.new_id())
            recordings.ensure_dir()
            if recordings.download(url, dest):
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
                    self.app._sync.push(result, None)
                except Exception:
                    pass
            return self.get_state()
        except Exception as e:
            logger.error("retry_transcription failed: %s", e)
            return {"ok": False, "error": str(e)}

    def fetch_canvas(self):
        try:
            import httpx

            from app.sync import SUPABASE_KEY, SUPABASE_URL

            user_id = self.app.config.get("sync_user_id", "")
            if not user_id:
                return _ok(content="", image_url=None, status="Set User ID in Settings first")
            resp = httpx.get(
                f"{SUPABASE_URL}/rest/v1/canvas",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                params={"user_id": f"eq.{user_id}", "select": "content,image_url"},
                timeout=8,
            )
            if resp.status_code != 200:
                return _err(f"Canvas load failed: {resp.status_code}")
            data = resp.json()
            row = data[0] if data else {}
            return _ok(content=row.get("content", "") or "", image_url=row.get("image_url"))
        except Exception as e:
            logger.error(f"Canvas fetch failed: {e}")
            return _err(str(e))

    def save_canvas(self, content, image_url=None):
        try:
            import httpx

            from app.sync import SUPABASE_KEY, SUPABASE_URL

            user_id = self.app.config.get("sync_user_id", "")
            if not user_id:
                return _err("Set User ID in Settings first")
            resp = httpx.post(
                f"{SUPABASE_URL}/rest/v1/canvas?on_conflict=user_id",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal,resolution=merge-duplicates",
                },
                json={
                    "user_id": user_id,
                    "content": content or "",
                    "image_url": image_url,
                    "device_name": self.app.config.get("sync_device_name", "Windows"),
                    "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                },
                timeout=10,
            )
            if resp.status_code not in (200, 201):
                return _err(f"Canvas save failed: {resp.status_code}")
            if content:
                pyperclip.copy(content)
            return _ok()
        except Exception as e:
            logger.error(f"Canvas save failed: {e}")
            return _err(str(e))

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
        if not user_id:
            return _err("Set User ID in Settings first")
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
