"""IDI-172 / IDI-173 / IDI-174 desktop fixtures — history sync (tombstones,
receive-into-history, push shape), canvas origin/clear semantics, and the
dictionary compare-and-swap write.

Runs entirely against fakes (temp HOME, monkeypatched httpx), so it never
touches Supabase or the real ~/.verbal config.

    cd whisperflow && .venv/bin/python idi172_174_fixtures.py
"""
import os
import sys
import tempfile
import threading
import time

# Timestamps are RELATIVE to now: SyncClient._deliver drops rows older than 3
# days as replay artifacts (2026-08-15), which silently broke these fixtures'
# fixed 2026-08-06 dates (found 2026-08-30). Ordering is preserved.
from datetime import datetime as _dt, timedelta as _td, timezone as _tz
_BASE = _dt.now(_tz.utc) - _td(minutes=30)      # frozen once: equal offsets → equal strings
def _ts(sec):
    return (_BASE + _td(seconds=sec)).isoformat()
_TS = {i: _ts(i) for i in range(5)}

# Isolate the config BEFORE app.config computes CONFIG_DIR from Path.home().
_HOME = tempfile.mkdtemp(prefix="idi172-home-")
os.environ["HOME"] = _HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import config as appcfg            # noqa: E402
appcfg.ensure_dirs()

from app import auth, dictionary, sync      # noqa: E402
from app import shared_dashboard as sd      # noqa: E402

FAILS = []
PASSES = [0]


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if cond:
        PASSES[0] += 1
    else:
        FAILS.append(name)


class FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else []
        self.content = b"{}"
        self.text = "{}"

    def json(self):
        return self._payload


def signed_in(uid="user-172"):
    cfg = appcfg.load_config()
    cfg["auth"] = {"user_id": uid, "email": f"{uid}@x.io", "name": uid,
                   "access_token": "tok", "refresh_token": "ref",
                   "expires_at": time.time() + 3600}
    cfg["sync_user_id"] = uid
    cfg["sync_enabled"] = True
    cfg["sync_device_name"] = "Test Mac"
    appcfg.save_config(cfg)
    auth._dead_session = False
    return cfg


# ══════════════════════════════════════════════════════════════════════════════
# IDI-172 — history sync
# ══════════════════════════════════════════════════════════════════════════════
print("\n1. tombstone contract: pure helpers")
check("is_tombstone true only with deleted_at",
      sync.is_tombstone({"id": "a", "deleted_at": _TS[0]}) is True
      and sync.is_tombstone({"id": "b"}) is False)
live, dead = sync.drop_tombstones([
    {"id": "1", "text": "alive"},
    {"id": "2", "text": "", "deleted_at": _TS[0]},
    "not-a-dict",
])
check("drop_tombstones splits live rows from dead ids",
      [r["id"] for r in live] == ["1"] and dead == ["2"], f"{live} {dead}")
hist = [{"id": "L1", "sync_id": "2"}, {"id": "L2", "sync_id": "9"}, {"id": "2"}]
pruned = sync.prune_local_history(hist, ["2"])
check("prune_local_history drops by sync_id AND by raw id",
      [e.get("id") for e in pruned] == ["L2"], str(pruned))
check("prune_local_history is a no-op with no ids",
      sync.prune_local_history(hist, []) == hist)


print("\n2. SyncClient._deliver: tombstones prune, never deliver as content")
signed_in()
delivered, tombstoned = [], []
c = sync.SyncClient.__new__(sync.SyncClient)
c.user_id = "user-172"
c.device_id = "this-mac"
c.device_name = "Test Mac"
c.on_receive = lambda t, d, r=None: delivered.append((t, d, r))
c.on_tombstone = lambda r: tombstoned.append(r.get("id"))
c.on_pushed = None
c._stop = threading.Event()
c._last_seen_at = _TS[0]
c._last_tombstone_at = _TS[0]
c._seen_ids, c._seen_order = set(), []

live_row = {"id": "r1", "text": "hello from phone", "device_id": "iphone",
            "device_name": "iPhone", "created_at": _TS[1]}
c._deliver(live_row)
check("live row delivered once", len(delivered) == 1 and delivered[0][0] == "hello from phone")
check("record passed through to the handler", delivered[0][2] is live_row)

# the SAME row, now tombstoned — must prune even though its id was already seen
c._deliver({"id": "r1", "text": "", "device_id": "iphone", "device_name": "iPhone",
            "deleted_at": _ts(60)})
check("tombstone of an ALREADY-SEEN id still prunes (dedup bypassed)",
      tombstoned == ["r1"], str(tombstoned))
check("tombstone never delivered as content", len(delivered) == 1, str(delivered))
check("tombstone watermark advanced",
      c._last_tombstone_at == _ts(60), c._last_tombstone_at)

# a tombstone of OUR OWN row must still prune here (the row carries the
# ORIGINATING device_id, so the own-device skip would be exactly backwards)
tombstoned.clear()
c._deliver({"id": "r9", "device_id": "this-mac", "device_name": "Test Mac",
            "deleted_at": _ts(120)})
check("tombstone on OUR OWN row still prunes", tombstoned == ["r9"], str(tombstoned))


print("\n3. backfill drops tombstoned rows and prunes them")
rows = [
    {"id": "b1", "text": "kept", "device_id": "iphone", "device_name": "iPhone",
     "created_at": _ts(3601)},
    {"id": "b2", "text": "", "device_id": "iphone", "device_name": "iPhone",
     "created_at": _ts(3602),
     "deleted_at": _ts(3900)},
]
seen_params = []


def fake_get(url, headers=None, params=None, timeout=None):
    seen_params.append(dict(params or {}))
    if (params or {}).get("deleted_at", "").startswith("gt."):
        return FakeResp(200, [])          # the tombstone sweep
    return FakeResp(200, rows)


sync.httpx.get = fake_get
delivered.clear()
tombstoned.clear()
c._last_seen_at = _ts(3600)
c._backfill()
check("backfill delivers only the live row",
      [t for t, _d, _r in delivered] == ["kept"], str(delivered))
check("backfill prunes the tombstoned row", tombstoned == ["b2"], str(tombstoned))
check("backfill select carries deleted_at/audio_url/status",
      "deleted_at" in seen_params[0]["select"] and "audio_url" in seen_params[0]["select"]
      and "status" in seen_params[0]["select"], seen_params[0]["select"])
check("a SEPARATE deleted_at-keyed sweep runs (a tombstone never moves created_at)",
      any(p.get("deleted_at", "").startswith("gt.") for p in seen_params), str(seen_params))
check("tombstone sweep is bounded + user-scoped",
      all(p.get("user_id") == "eq.user-172" for p in seen_params)
      and [p for p in seen_params if "deleted_at" in p][0]["limit"] == "200")


print("\n4. push shape: audio_url + status included when present")
pushed = []


def fake_post(url, headers=None, json=None, timeout=None, params=None):
    pushed.append({"url": url, "json": json, "headers": dict(headers or {})})
    return FakeResp(201, [{"id": "row-abc"}])


sync.httpx.post = fake_post
pushed_ids = []
c.on_pushed = lambda entry_id, row_id: pushed_ids.append((entry_id, row_id))
c._push_rest("some text", None, "user-172/rec1.wav", "done", "rec1")
p = pushed[-1]["json"]
check("audio_url in the push payload", p.get("audio_url") == "user-172/rec1.wav", str(p))
check("status in the push payload", p.get("status") == "done", str(p))
check("device_id + device_name always sent",
      p.get("device_id") == "this-mac" and p.get("device_name") == "Test Mac")
check("no target_device_id on a broadcast", "target_device_id" not in p, str(p))
check("row id handed back so the local entry can be linked",
      pushed_ids == [("rec1", "row-abc")], str(pushed_ids))
check("the row we just wrote is pre-marked seen (never echoed back to us)",
      "row-abc" in c._seen_ids)

pushed.clear()
c._push_rest("bare", "other-device")
p = pushed[-1]["json"]
check("empty audio_url/status are OMITTED, never written as blanks",
      "audio_url" not in p and "status" not in p, str(p))
check("targeted push carries target_device_id", p.get("target_device_id") == "other-device")

patched = []


def fake_patch(url, headers=None, json=None, params=None, timeout=None):
    patched.append({"url": url, "json": json, "params": dict(params or {})})
    return FakeResp(200, [{"id": "row-abc"}])


sync.httpx.patch = fake_patch
c.update_pushed_audio_url("row-abc", "user-172/rec1.wav")
check("late audio_url patch is row- AND user-scoped",
      patched and patched[-1]["params"] == {"id": "eq.row-abc", "user_id": "eq.user-172"},
      str(patched))


print("\n5. clearing the cloud copy TOMBSTONES (never DELETEs)")
deleted_urls = []
sync.httpx.delete = lambda url, headers=None, params=None, timeout=None: (
    deleted_urls.append(url), FakeResp(204))[1]
patched.clear()
sync.httpx.get = lambda url, headers=None, params=None, timeout=None: FakeResp(
    200, [{"id": "x1", "audio_url": "user-172/x1.wav"}])
res = sync.tombstone_all_transcriptions("user-172")
check("tombstone_all reports ok", res.get("ok") is True, str(res))
body = patched[-1]["json"]
check("PATCH sets deleted_at + blanks text/edited_text/audio_url",
      body.get("deleted_at") and body.get("text") == ""
      and body.get("edited_text") is None and body.get("audio_url") is None, str(body))
check("PATCH is user-scoped and only touches live rows",
      patched[-1]["params"].get("user_id") == "eq.user-172"
      and patched[-1]["params"].get("deleted_at") == "is.null", str(patched[-1]["params"]))
check("the audio object is removed best-effort",
      any("x1.wav" in u for u in deleted_urls), str(deleted_urls))
check("no hard DELETE of the transcriptions table",
      not any("/transcriptions" in u for u in deleted_urls), str(deleted_urls))


print("\n6. receive: ALWAYS history, paste ONLY when this device is the target")
from app.main import VerbalApp                       # noqa: E402


class FakeOverlay:
    def __init__(self):
        self.briefs = []

    def show_briefly(self, text, duration=0):
        self.briefs.append(text)


class FakeSync:
    device_id = "this-mac"
    device_name = "Test Mac"


class FakeMacApp:
    def __init__(self):
        self.config = signed_in()
        self._sync = FakeSync()
        self.overlay = FakeOverlay()
        self._total_transcriptions = 0
        self._total_words = 0
        self.pasted = []
        self.refreshed = 0

    def _on_main(self, fn):
        fn()

    def _paste_synced(self, text, brief):
        self.pasted.append(text)

    def _refresh_dashboards(self):
        self.refreshed += 1

    _this_device_id = VerbalApp._this_device_id


import app.main as mainmod                          # noqa: E402
mainmod.pyperclip = type("pc", (), {"copy": staticmethod(lambda t: None)})
sys.modules.setdefault("pyperclip", mainmod.pyperclip)

app = FakeMacApp()
app.config["history"] = []
VerbalApp._on_sync_receive(app, "broadcast text", "iPhone", {
    "id": "cloud-1", "created_at": _ts(7200),
    "audio_url": "user-172/a.wav", "status": "done"})
hist = app.config.get("history", [])
check("broadcast appended to local history", len(hist) == 1 and hist[0]["text"] == "broadcast text",
      str(hist))
check("history entry keeps the source device name", hist[0].get("device_name") == "iPhone")
check("history entry keeps created_at", hist[0].get("created_at") == _ts(7200))
check("history entry keeps audio_url", hist[0].get("audio_url") == "user-172/a.wav")
check("history entry records the cloud row id", hist[0].get("sync_id") == "cloud-1")
check("broadcast does NOT auto-paste", app.pasted == [], str(app.pasted))
check("dashboard refreshed after receive", app.refreshed >= 1)
check("the user is told where it went",
      any("History" in b for b in app.overlay.briefs), str(app.overlay.briefs))

VerbalApp._on_sync_receive(app, "just for you", "iPhone", {
    "id": "cloud-2", "target_device_id": "this-mac"})
check("targeted-at-me DOES auto-paste", app.pasted == ["just for you"], str(app.pasted))
check("targeted row also lands in history", len(app.config["history"]) == 2)

VerbalApp._on_sync_receive(app, "for the other mac", "iPhone", {
    "id": "cloud-3", "target_device_id": "some-other-mac"})
check("a row targeted at ANOTHER device never pastes here",
      app.pasted == ["just for you"], str(app.pasted))

VerbalApp._on_sync_tombstone(app, {"id": "cloud-1"})
ids = [e.get("sync_id") for e in app.config["history"]]
check("remote tombstone prunes the matching local entry",
      "cloud-1" not in ids and len(app.config["history"]) == 2, str(ids))

from app.win_main import VerbalWinApp                 # noqa: E402
check("win_main mirrors the receive handler (3-arg record form)",
      VerbalWinApp._on_sync_receive.__code__.co_argcount == 4)
check("win_main has the tombstone handler", hasattr(VerbalWinApp, "_on_sync_tombstone"))


# ══════════════════════════════════════════════════════════════════════════════
# IDI-173 — canvas
# ══════════════════════════════════════════════════════════════════════════════
print("\n7. canvas origin filtering (device_id, with name fallback)")
own = {"device_id": "mac-A", "device_name": "MacBook Pro"}
other_same_name = {"device_id": "mac-B", "device_name": "MacBook Pro"}
legacy_own = {"device_name": "MacBook Pro"}
legacy_other = {"device_name": "iPhone"}
check("own event skipped by device_id",
      sd.canvas_is_own_event(own, "mac-A", "MacBook Pro") is True)
check("SAME display name, different device_id → NOT own (the bug)",
      sd.canvas_is_own_event(other_same_name, "mac-A", "MacBook Pro") is False)
check("old row without device_id falls back to the name compare",
      sd.canvas_is_own_event(legacy_own, "mac-A", "MacBook Pro") is True)
check("old row from another name is not own",
      sd.canvas_is_own_event(legacy_other, "mac-A", "MacBook Pro") is False)
check("empty record is never own", sd.canvas_is_own_event({}, "mac-A", "MacBook Pro") is False)


print("\n8. canvas writes: omit untouched columns, clear says both out loud")


class FakeCanvasDash:
    def __init__(self, app):
        self.app = app
        self._known_devices = []
        self._target_device_id = "__all__"

    def _refresh(self):
        pass

    def _load_devices(self):
        pass


class FakeCanvasApp:
    def __init__(self):
        self.config = signed_in()
        self._sync = FakeSync()
        self._is_recording = False
        self._processing = False


capp = FakeCanvasApp()
api = sd.DashboardApi(FakeCanvasDash(capp))
writes = []


def canvas_post(url, headers=None, json=None, timeout=None, params=None):
    writes.append(json)
    return FakeResp(200)


import httpx as _httpx                                # noqa: E402
_real_post = _httpx.post
_httpx.post = canvas_post
sd.pyperclip = type("pc", (), {"copy": staticmethod(lambda t: None)})

api.save_canvas("just text")
w = writes[-1]
check("text-only save OMITS image_url (never nulls a shared image)",
      "image_url" not in w and w.get("content") == "just text", str(w))
check("every canvas write carries device_id AND device_name",
      w.get("device_id") == "this-mac" and w.get("device_name") == "Test Mac", str(w))
check("device_name defaults to the real device name, not 'Windows'",
      w.get("device_name") != "Windows")

api.save_canvas(sd.KEEP, "https://x/img.png")
w = writes[-1]
check("image-only save OMITS content (never blanks shared text)",
      "content" not in w and w.get("image_url") == "https://x/img.png", str(w))

api.clear_canvas()
w = writes[-1]
check("clear writes content:'' AND image_url:null explicitly",
      w.get("content") == "" and "image_url" in w and w["image_url"] is None, str(w))

bad = api.save_canvas()
check("a write that touches nothing is refused, not sent blank",
      bad.get("ok") is False, str(bad))
_httpx.post = _real_post

# name default when the user never set one
capp.config["sync_device_name"] = ""
did, dname = sd.device_identity(capp)
check("device_identity falls back to the machine name, never 'Windows'",
      dname and dname != "Windows", dname)
check("device_identity uses the SyncClient's stable device_id", did == "this-mac")
capp.config["sync_device_name"] = "Test Mac"


print("\n9. canvas listeners apply an empty-content clear")
# NB (IDI-179): this section used to also assert that the NATIVE canvas window
# (app/canvas_window.py::CanvasWindow.applyRemoteText_) stopped falsy-dropping an
# incoming clear. That module was unreferenced by the app since IDI-178 and has
# been DELETED — this fixture file was its only importer. The rule it guarded
# (a clear is an explicit empty write and receivers must APPLY it, never
# falsy-drop it) is still enforced below on the two live listeners.
import inspect                                        # noqa: E402
import os                                             # noqa: E402
check("the deleted native canvas window is really gone (no live importer left)",
      not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "app", "canvas_window.py")))
from app import flume_web_dashboard as fwd            # noqa: E402
lsrc = inspect.getsource(fwd.FlumeWebDashboard._canvas_listen_once)
check("mac dashboard listener filters by device_id (canvas_is_own_event)",
      "canvas_is_own_event" in lsrc)
check("mac dashboard listener still emits empty content",
      'rec.get("content", "") or ""' in lsrc)
loop = inspect.getsource(fwd.FlumeWebDashboard._canvas_listen_loop)
check("mac canvas listener has a per-iteration stop-check", "_canvas_stop" in loop)
sloop = inspect.getsource(sd.SharedDashboard._canvas_listen_loop)
check("shared canvas listener has a per-iteration stop-check (was `while True`)",
      "_canvas_stop" in sloop and "while True:" not in sloop)


# ══════════════════════════════════════════════════════════════════════════════
# IDI-174 — dictionary compare-and-swap
# ══════════════════════════════════════════════════════════════════════════════
print("\n10. dictionary merge helpers (pure)")
check("vocabulary is a case-insensitive union",
      dictionary.merge_vocabulary(["Flume", "kubectl"], ["flume", "Supabase"])
      == ["flume", "Supabase", "kubectl"],
      str(dictionary.merge_vocabulary(["Flume", "kubectl"], ["flume", "Supabase"])))
reps = dictionary.merge_replacements(
    [{"from": "shabar", "to": "Shabbar"}],
    [{"from": "Shabar", "to": "OLD"}, {"from": "verbel", "to": "Verbal"}])
check("replacements key on `from`, the newer (local) write wins",
      reps == [{"from": "shabar", "to": "Shabbar"}, {"from": "verbel", "to": "Verbal"}],
      str(reps))
snips = dictionary.merge_snippets(
    [{"trigger": "sig", "expansion": "NEW", "updated_at": "2026-08-06T03:00:00"}],
    [{"trigger": "SIG", "expansion": "OLD", "updated_at": "2026-08-06T01:00:00"},
     {"trigger": "addr", "expansion": "somewhere", "updated_at": "2026-08-06T02:00:00"}])
check("snippets union by trigger, newer expansion wins",
      [s["expansion"] for s in snips] == ["NEW", "somewhere"], str(snips))
older = dictionary.merge_snippets(
    [{"trigger": "sig", "expansion": "STALE", "updated_at": "2026-08-05T00:00:00"}],
    [{"trigger": "sig", "expansion": "FRESH", "updated_at": "2026-08-06T00:00:00"}])
check("an older local snippet loses to a newer remote one",
      [s["expansion"] for s in older] == ["FRESH"], str(older))


print("\n11. dictionary CAS: conflict → merge → ONE retry")
cfg = signed_in("user-174")
cfg["dictionary"] = {"vocabulary": ["local-word"], "replacements": [], "snippets": []}
appcfg.save_config(cfg)

calls = {"get": 0, "patch": 0, "post": 0}
patch_bodies, patch_params = [], []
remote_rows = [
    {"updated_at": "T1", "vocabulary": ["remote-old"], "replacements": [], "snippets": []},
    {"updated_at": "T2", "vocabulary": ["remote-new"], "replacements": [], "snippets": []},
]


def dget(url, headers=None, params=None, timeout=None):
    row = remote_rows[min(calls["get"], len(remote_rows) - 1)]
    calls["get"] += 1
    return FakeResp(200, [row])


def dpatch(url, headers=None, json=None, params=None, timeout=None):
    calls["patch"] += 1
    patch_bodies.append(json)
    patch_params.append(dict(params or {}))
    # first attempt loses the race (0 rows), second wins
    return FakeResp(200, [] if calls["patch"] == 1 else [{"user_id": "user-174"}])


def dpost(url, headers=None, json=None, timeout=None, params=None):
    calls["post"] += 1
    return FakeResp(201)


_httpx.get, _httpx.patch, _httpx.post = dget, dpatch, dpost
saved = []
res = dictionary._push_remote(appcfg.load_config(),
                              dictionary.normalize(cfg["dictionary"]),
                              lambda c: saved.append(c))
check("CAS filter is user_id + the updated_at we read",
      patch_params[0] == {"user_id": "eq.user-174", "updated_at": "eq.T1"}, str(patch_params[0]))
check("exactly ONE retry after the conflict", calls["patch"] == 2, str(calls))
check("the retry uses the REFETCHED updated_at",
      patch_params[1].get("updated_at") == "eq.T2", str(patch_params[1]))
check("the retry writes the MERGED vocabulary, not an overwrite",
      sorted(patch_bodies[1]["vocabulary"]) == ["local-word", "remote-new"],
      str(patch_bodies[1]["vocabulary"]))
check("all columns are written on every attempt",
      all(set(("vocabulary", "replacements", "snippets", "updated_at")) <= set(b)
          for b in patch_bodies))
check("a successful merge is persisted locally too", len(saved) == 1, str(len(saved)))
check("success is reported", res.get("ok") is True and dictionary.last_sync_error() == "",
      str(res))

print("\n11b. 0 rows TWICE surfaces a failure instead of swallowing it")
calls["patch"] = 0
calls["get"] = 0


def dpatch_always_lose(url, headers=None, json=None, params=None, timeout=None):
    calls["patch"] += 1
    return FakeResp(200, [])


_httpx.patch = dpatch_always_lose
res = dictionary._push_remote(appcfg.load_config(),
                              dictionary.normalize(cfg["dictionary"]))
check("both attempts lost → NOT ok", res.get("ok") is False, str(res))
check("stopped after exactly two attempts (no retry storm)", calls["patch"] == 2, str(calls))
check("the failure is surfaced to the caller", bool(dictionary.last_sync_error()),
      dictionary.last_sync_error())

print("\n11c. first-ever write (no row) inserts")
calls["post"] = 0
_httpx.get = lambda url, headers=None, params=None, timeout=None: FakeResp(200, [])
res = dictionary._push_remote(appcfg.load_config(),
                              dictionary.normalize(cfg["dictionary"]))
check("no row → insert/upsert path", calls["post"] == 1 and res.get("ok") is True, str(calls))
check("last_sync_error cleared on success", dictionary.last_sync_error() == "")

print("\n11d. sync off is not an error")
off = dict(appcfg.load_config(), sync_enabled=False)
res = dictionary._push_remote(off, dictionary.normalize(cfg["dictionary"]))
check("sync-off push reports ok (nothing to sync)", res.get("ok") is True, str(res))


# ══════════════════════════════════════════════════════════════════════════════
# IDI-177 — device list
# ══════════════════════════════════════════════════════════════════════════════
print("\n12. remove_device is scoped and refuses to remove THIS device")
dapp = FakeCanvasApp()
dapi = sd.DashboardApi(FakeCanvasDash(dapp))
dels = []
_httpx.delete = lambda url, headers=None, params=None, timeout=None: (
    dels.append((url, dict(params or {}))), FakeResp(204))[1]
sync.httpx.delete = _httpx.delete
r = dapi.remove_device("other-device")
check("remove_device ok", r.get("ok") is True, str(r))
check("DELETE scoped by user_id AND device_id",
      dels and dels[-1][1] == {"user_id": "eq.user-172", "device_id": "eq.other-device"},
      str(dels))
check("DELETE targets the devices table", dels[-1][0].endswith("/devices"))
r = dapi.remove_device("this-mac")
check("this device cannot remove itself", r.get("ok") is False, str(r))
r = dapi.remove_device("")
check("no device id is refused", r.get("ok") is False, str(r))


print(f"\n{PASSES[0]} checks passed")
print("ALL CHECKS PASSED" if not FAILS else f"{len(FAILS)} FAILURE(S): {FAILS}")
sys.exit(1 if FAILS else 0)
