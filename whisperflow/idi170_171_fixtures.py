"""IDI-170 / IDI-171 / IDI-177 desktop fixtures — sign-out & deletion hygiene,
sync-client lifecycle, and the app-level presence heartbeat.

Runs entirely against fakes (temp HOME, monkeypatched httpx / websocket), so it
never touches Supabase or the real ~/.verbal config.

    cd whisperflow && .venv/bin/python idi170_171_fixtures.py
"""
import os
import sys
import tempfile
import threading
import time

# Isolate the config BEFORE app.config computes CONFIG_DIR from Path.home().
_HOME = tempfile.mkdtemp(prefix="idi170-home-")
os.environ["HOME"] = _HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import config as appcfg            # noqa: E402
appcfg.ensure_dirs()

from app import auth, dictionary, sync      # noqa: E402
from app import shared_dashboard as sd      # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def fresh_signed_in(uid="user-AAA", history=("hello",)):
    cfg = appcfg.load_config()
    cfg["auth"] = {"user_id": uid, "email": f"{uid}@x.io", "name": uid,
                   "access_token": "tok", "refresh_token": "ref",
                   "expires_at": time.time() + 3600}
    cfg["sync_user_id"] = uid
    cfg["sync_enabled"] = True
    cfg["history"] = [{"text": t} for t in history]
    cfg["pinned"] = [{"text": "pin"}]
    cfg["notes"] = [{"id": "n1"}]
    cfg["meetings"] = [{"id": "m1"}]
    cfg["dictionary"] = {"vocabulary": ["Flume"]}
    cfg["voice_prints"] = {"s1": [0.1]}
    cfg["groq_api_keys"] = ["device-level-key"]
    appcfg.save_config(cfg)
    auth._dead_session = False
    return cfg


class FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else []
        self.content = b"{}"
        self.text = "{}"

    def json(self):
        return self._payload


# ── 1. sign_out ───────────────────────────────────────────────────────────────
print("\n1. sign_out clears identity, kills cloud access, deletes the device row")
fresh_signed_in()
deletes = []


def fake_delete(url, headers=None, params=None, timeout=None):
    deletes.append((url, params, dict(headers or {})))
    return FakeResp(204)


sync.httpx.delete = fake_delete
auth.sign_out()
time.sleep(0.4)  # the device-row DELETE is fire-and-forget on a daemon thread

cfg = appcfg.load_config()
check("sync_user_id cleared", cfg.get("sync_user_id") == "", repr(cfg.get("sync_user_id")))
check("sync_enabled cleared", cfg.get("sync_enabled") is False)
check("auth dropped", "auth" not in cfg)
check("local history KEPT on plain sign-out", len(cfg.get("history", [])) == 1)
check("cloud_allowed() False when signed out", auth.cloud_allowed(cfg) is False)
check("devices row DELETEd exactly once", len(deletes) == 1, str(deletes))
if deletes:
    _url, params, _h = deletes[0]
    check("delete scoped by user_id AND device_id",
          params.get("user_id") == "eq.user-AAA" and params.get("device_id", "").startswith("eq."),
          str(params))
    check("delete uses the /devices endpoint", _url.endswith("/devices"), _url)

posts = []
sync.httpx.post = lambda *a, **k: (posts.append(a), FakeResp(201))[1]
sync.register_device_presence("user-AAA", "mac-1", "Mac")
check("presence heartbeat no-ops when signed out", posts == [], str(posts))

dictionary._push_remote(appcfg.load_config(), {"vocabulary": [], "replacements": [], "snippets": []})
check("dictionary push no-ops when signed out", posts == [], str(posts))

# ── 2. account switch wipes account-scoped caches ─────────────────────────────
print("\n2. _store_session wipes the previous account's caches on a uid change")
fresh_signed_in("user-AAA")
auth._store_session({"user": {"id": "user-BBB", "email": "b@x.io", "user_metadata": {}},
                     "access_token": "t2", "refresh_token": "r2", "expires_in": 3600})
cfg = appcfg.load_config()
check("new uid stored", cfg["sync_user_id"] == "user-BBB")
check("history wiped", cfg.get("history") == [])
check("pinned wiped", cfg.get("pinned") == [])
check("notes wiped", cfg.get("notes") == [])
check("meetings wiped", cfg.get("meetings") == [])
check("dictionary wiped", cfg.get("dictionary") == {})
check("voice_prints wiped", cfg.get("voice_prints") == {})
check("device-level config PRESERVED", cfg.get("groq_api_keys") == ["device-level-key"])

print("\n2b. same-uid re-sign-in must NOT wipe")
fresh_signed_in("user-CCC")
auth._store_session({"user": {"id": "user-CCC", "email": "c@x.io", "user_metadata": {}},
                     "access_token": "t3", "refresh_token": "r3", "expires_in": 3600})
cfg = appcfg.load_config()
check("history kept for the same account", len(cfg.get("history", [])) == 1)
check("session_dead cleared by a fresh session", auth.session_dead(cfg) is False)


# ── 3. delete_account uses the LIVE config (no resurrection) ──────────────────
print("\n3. delete_account wipes the LIVE config object (concurrent save can't resurrect)")


class FakeApp:
    def __init__(self, cfg):
        self.config = cfg
        self._sync = None
        self._is_recording = False
        self._processing = False
        self._auth_error = ""
        self._auth_notice = ""
        self.signed_out = False
        self.stopped_meeting = False

    def _on_main(self, fn):
        fn()

    def _stop_active_meeting(self, reason=""):
        self.stopped_meeting = True

    def _sign_out(self, _=None):
        self.signed_out = True
        auth.sign_out()
        self.config = appcfg.load_config()


class FakeDash:
    def __init__(self, app):
        self.app = app
        self._known_devices = []
        self._target_device_id = "__all__"

    def _refresh(self):
        pass


fresh_signed_in("user-DDD")
live_cfg = appcfg.load_config()
app = FakeApp(live_cfg)
api = sd.DashboardApi(FakeDash(app))
auth.delete_account_remote = lambda cfg=None: {"ok": True}
res = api.delete_account()
check("delete_account ok", res.get("ok") is True, str(res))
check("active meeting stopped before the wipe", app.stopped_meeting is True)
check("LIVE cfg object mutated in place (history)", live_cfg.get("history") == [],
      str(live_cfg.get("history")))
check("LIVE cfg object mutated in place (auth)", "auth" not in live_cfg)
check("LIVE cfg object mutated in place (sync_user_id)", live_cfg.get("sync_user_id") == "")

# a racing writer that still holds the SAME object must not resurrect anything
appcfg.save_config(live_cfg)
on_disk = appcfg.load_config()
check("concurrent save_config(live cfg) writes the WIPED state",
      on_disk.get("history") == [] and "auth" not in on_disk and not on_disk.get("sync_user_id"),
      str({k: on_disk.get(k) for k in ("history", "sync_user_id")}))
check("post-deletion notice set once", app._auth_notice == sd.ACCOUNT_DELETED_MSG, app._auth_notice)
state = api.get_state()
check("auth_notice exposed in get_state", state.get("auth_notice") == sd.ACCOUNT_DELETED_MSG)
check("signed_in False in get_state", state.get("signed_in") is False)


# ── 4. SyncClient lifecycle: close → exactly ONE reconnect ────────────────────
print("\n4. SyncClient: on_close signals only — one reconnect, no stacking")


class FakeWSApp:
    """A flapping connection: run_forever connects, immediately reports the
    socket closed, and then takes a moment to unwind (as a real one does).

    This is the shape that used to STACK: the old `on_close` slept 5 s and then
    called `_listen()` again *from inside the close handler*, so a second
    WebSocketApp went live underneath the outer `_run()` retry loop and
    `max_live` climbed past 1. Now `on_close` only signals, so exactly one
    connection exists at any time."""
    runs = []
    live = 0
    max_live = 0
    lock = threading.Lock()

    def __init__(self, url, header=None, on_open=None, on_message=None,
                 on_close=None, on_error=None):
        self.on_open, self.on_close = on_open, on_close

    def send(self, payload):
        pass

    def run_forever(self, **kw):
        with FakeWSApp.lock:
            FakeWSApp.runs.append(time.time())
            FakeWSApp.live += 1
            FakeWSApp.max_live = max(FakeWSApp.max_live, FakeWSApp.live)
        try:
            if self.on_open:
                self.on_open(self)
            if self.on_close:
                self.on_close(self, 1006, "flap")
            time.sleep(3.0)     # socket unwinding
        finally:
            with FakeWSApp.lock:
                FakeWSApp.live -= 1

    def close(self):
        pass


fake_ws_mod = type("ws", (), {"WebSocketApp": FakeWSApp})
sys.modules["websocket"] = fake_ws_mod
fresh_signed_in("user-EEE")
sync.httpx.post = lambda *a, **k: FakeResp(201)
sync.httpx.get = lambda *a, **k: FakeResp(200, [])
received = []
client = sync.SyncClient("user-EEE", "Mac", lambda t, d: received.append((t, d)))
time.sleep(9.0)   # long enough for the old code's in-on_close 5s re-listen
check("connected at least twice (the retry loop DOES reconnect)",
      len(FakeWSApp.runs) >= 2, str(len(FakeWSApp.runs)))
check("never more than ONE live connection at a time (no stacking)",
      FakeWSApp.max_live == 1, f"max_live={FakeWSApp.max_live}")
client.stop()
time.sleep(4.0)
n2 = len(FakeWSApp.runs)
time.sleep(7.0)
check("stop() ends the reconnect loop", len(FakeWSApp.runs) == n2, f"{n2} -> {len(FakeWSApp.runs)}")


# ── 5. backfill ───────────────────────────────────────────────────────────────
print("\n5. reconnect backfill replays missed rows through the same receive path")
fresh_signed_in("user-FFF")
got = []
c = sync.SyncClient.__new__(sync.SyncClient)
c.user_id = "user-FFF"
c.device_id = "this-mac"
c.device_name = "Mac"
c.on_receive = lambda t, d: got.append((t, d))
c._stop = threading.Event()
c._last_seen_at = "2026-08-06T00:00:00+00:00"
c._seen_ids, c._seen_order = set(), []

rows = [
    {"id": "1", "text": "from phone", "device_id": "iphone", "device_name": "iPhone",
     "created_at": "2026-08-06T00:00:01+00:00"},
    {"id": "2", "text": "my own echo", "device_id": "this-mac", "device_name": "Mac",
     "created_at": "2026-08-06T00:00:02+00:00"},
    {"id": "3", "text": "for someone else", "device_id": "iphone", "device_name": "iPhone",
     "target_device_id": "other-mac", "created_at": "2026-08-06T00:00:03+00:00"},
    {"id": "4", "text": "targeted at me", "device_id": "iphone", "device_name": "iPhone",
     "target_device_id": "this-mac", "created_at": "2026-08-06T00:00:04+00:00"},
]
seen_params = {}


def fake_get(url, headers=None, params=None, timeout=None):
    seen_params.update(params or {})
    return FakeResp(200, rows)


sync.httpx.get = fake_get
c._backfill()
check("own-device row skipped", "my own echo" not in [t for t, _ in got])
check("other-device-targeted row skipped", "for someone else" not in [t for t, _ in got])
check("broadcast + targeted-at-me delivered",
      [t for t, _ in got] == ["from phone", "targeted at me"], str(got))
check("bounded to 50", seen_params.get("limit") == "50", str(seen_params.get("limit")))
check("user-scoped", seen_params.get("user_id") == "eq.user-FFF")
check("only rows newer than last-seen", seen_params.get("created_at") == "gt.2026-08-06T00:00:00+00:00")
check("last_seen_at advanced", c._last_seen_at == "2026-08-06T00:00:04+00:00", c._last_seen_at)

got.clear()
c._backfill()   # same rows again → dedup by id
check("re-delivery deduped", got == [], str(got))

print("\n5b. first connect must not replay history (last_seen seeded to now)")
c2 = sync.SyncClient.__new__(sync.SyncClient)
c2._last_seen_at = sync._utc_now_iso()
check("seeded in the future of every stored row", c2._last_seen_at > "2026-08-06T00:00:04+00:00")


# ── 6. uniform gating ─────────────────────────────────────────────────────────
print("\n6. uniform gating: toggle gates sync surfaces, cloud_allowed gates capture")
from app import meetings as meetings_mod   # noqa: E402

signed_in_sync_on = fresh_signed_in("user-GGG")
check("dictionary gate on when signed in + toggle on", dictionary._cloud_gate(signed_in_sync_on) is True)
check("meetings gate on when signed in", meetings_mod._cloud_gate(signed_in_sync_on) is True)

toggle_off = dict(signed_in_sync_on, sync_enabled=False)
check("dictionary gate OFF when the toggle is off", dictionary._cloud_gate(toggle_off) is False)
check("meetings gate STAYS ON with the toggle off (capture artifact)",
      meetings_mod._cloud_gate(toggle_off) is True)

signed_out = {"sync_user_id": "user-GGG", "sync_enabled": True}   # the stale-id case
check("dictionary gate OFF when signed out", dictionary._cloud_gate(signed_out) is False)
check("meetings gate OFF when signed out", meetings_mod._cloud_gate(signed_out) is False)
check("cloud_allowed OFF for a stale sync_user_id without auth",
      auth.cloud_allowed(signed_out) is False)

dead = dict(signed_in_sync_on)
dead["auth"] = dict(dead["auth"], session_dead=True)
check("cloud_allowed STAYS TRUE on a dead session (Hard Rule #24 anon fallback)",
      auth.cloud_allowed(dead) is True)

print("\n" + ("ALL CHECKS PASSED" if not FAILS else f"{len(FAILS)} FAILURE(S): {FAILS}"))
sys.exit(1 if FAILS else 0)
