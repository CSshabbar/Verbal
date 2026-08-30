#!/usr/bin/env python3
"""
Assertion harness for the team layer (IDI-216).

Pins the two things that are pure, load-bearing and easy to break silently:

  §1  the personal ∪ team merge rule (`dictionary.merge_with_team`) — union,
      personal wins a key collision, and the ORDERING that keeps the user's own
      vocabulary in the bias prompt's tail.
  §2  the fail-closed contract of `organizations` — every entry point returns the
      "no org" shape rather than raising, on junk config, no session, and a
      module that can't reach the network.

Run:  .venv/bin/python organizations_fixtures.py
"""
import sys

sys.path.insert(0, ".")

from app import dictionary, organizations  # noqa: E402

_passed = 0
_failed = []


def shape(d):
    """Compare dictionaries on their STABLE content only.

    `normalize()` mints a fresh `id` and `created_at`/`updated_at` for any snippet
    that arrives without them, so two normalize() calls on the same input are never
    `==`. Every equality assertion below is about the merge RULE, not about those
    generated fields."""
    d = dictionary.normalize(d)
    return {
        "vocabulary": d["vocabulary"],
        "replacements": [(r["from"], r["to"]) for r in d["replacements"]],
        "snippets": [(s["trigger"], s["expansion"]) for s in d["snippets"]],
    }


def check(label, cond):
    global _passed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed.append(label)
        print(f"  FAIL {label}")


PERSONAL = {
    "vocabulary": ["Idiaz", "shab"],
    "replacements": [{"from": "ideas", "to": "Idiaz"}],
    "snippets": [{"trigger": "my email", "expansion": "me@idiaz.io"}],
}
TEAM = {
    "vocabulary": ["Flume", "IDIAZ", "Verbal"],
    "replacements": [{"from": "ideas", "to": "IDIAZ Ltd"}, {"from": "flum", "to": "Flume"}],
    "snippets": [
        {"trigger": "my email", "expansion": "team@idiaz.io"},
        {"trigger": "legal", "expansion": "Confidential."},
    ],
}

print("§1 merge rule — union, personal-wins, tail ordering")
m = dictionary.merge_with_team(PERSONAL, TEAM)

check("union keeps team-only vocabulary", "Flume" in m["vocabulary"] and "Verbal" in m["vocabulary"])
check("union keeps personal vocabulary", "Idiaz" in m["vocabulary"] and "shab" in m["vocabulary"])
# 'IDIAZ' is a case-insensitive collision with personal 'Idiaz' — personal spelling wins,
# so the team's casing must NOT appear and the word must appear exactly once.
check("collision resolves to the PERSONAL spelling", "IDIAZ" not in m["vocabulary"])
check("no duplicate on a case-insensitive collision",
      sum(1 for w in m["vocabulary"] if w.lower() == "idiaz") == 1)
# The tail is what Whisper conditions on and what build_prompt protects when trimming.
check("personal vocabulary occupies the TAIL", m["vocabulary"][-2:] == ["Idiaz", "shab"])

reps = {r["from"]: r["to"] for r in m["replacements"]}
check("team-only replacement survives", reps.get("flum") == "Flume")
check("collided replacement resolves to PERSONAL", reps.get("ideas") == "Idiaz")
check("no duplicate replacement key", len(m["replacements"]) == 2)

snips = {s["trigger"]: s["expansion"] for s in m["snippets"]}
check("team-only snippet survives", snips.get("legal") == "Confidential.")
check("collided snippet trigger resolves to PERSONAL", snips.get("my email") == "me@idiaz.io")
check("no duplicate snippet trigger", len(m["snippets"]) == 2)

check("empty team is a no-op", shape(dictionary.merge_with_team(PERSONAL, {})) == shape(PERSONAL))
check("empty personal yields the team set",
      dictionary.merge_with_team({}, TEAM)["vocabulary"] == dictionary.normalize(TEAM)["vocabulary"])
check("junk input doesn't raise", isinstance(dictionary.merge_with_team(None, "nonsense"), dict))

print()
print("§2 effective() — reads local state only, fails closed to personal")
# No org cached at all.
cfg_no_org = {"dictionary": PERSONAL}
check("no org  -> personal only", shape(dictionary.effective(cfg_no_org)) == shape(PERSONAL))

# Org cached, but the user's sync toggle is OFF: the shared dictionary is synced
# user content, so it must not apply — membership is unaffected, only the words.
cfg_sync_off = {
    "dictionary": PERSONAL,
    "sync_enabled": False,
    "org": {"org_id": "o1", "role": "member", "dictionary": TEAM},
}
check("sync OFF -> personal only", shape(dictionary.effective(cfg_sync_off)) == shape(PERSONAL))

cfg_on = dict(cfg_sync_off, sync_enabled=True)
eff = dictionary.effective(cfg_on)
check("sync ON  -> merged set", "Flume" in eff["vocabulary"] and eff["vocabulary"][-2:] == ["Idiaz", "shab"])
check("effective_snippets matches effective()",
      [(s["trigger"], s["expansion"]) for s in dictionary.effective_snippets(cfg_on)]
      == [(s["trigger"], s["expansion"]) for s in eff["snippets"]])
check("apply_replacements uses the TEAM rule too",
      dictionary.apply_replacements("the flum app", cfg_on) == "the Flume app")
check("apply_replacements still prefers the PERSONAL rule on a collision",
      dictionary.apply_replacements("ideas ltd", cfg_on) == "Idiaz ltd")
check("apply_snippets expands a TEAM snippet",
      dictionary.apply_snippets("send the legal now", cfg_on) == "send the Confidential. now")
check("apply_snippets prefers the PERSONAL expansion on a collision",
      dictionary.apply_snippets("my email please", cfg_on) == "me@idiaz.io please")
check("build_prompt includes team + personal terms",
      "Flume" in (dictionary.build_prompt(cfg_on) or "") and "shab" in (dictionary.build_prompt(cfg_on) or ""))
check("known_terms includes the team's corrected side",
      "Flume" in dictionary.known_terms(cfg_on))

print()
print("§3 organizations — fail-closed shape")
check("get(None) -> NO_ORG", organizations.get(None)["org_id"] == "")
check("get(junk) -> NO_ORG", organizations.get({"org": "not-a-dict"})["org_id"] == "")
check("get() with no org_id -> NO_ORG", organizations.get({"org": {"name": "x"}})["org_id"] == "")
check("is_admin false without an org", organizations.is_admin({}) is False)
check("team_dictionary empty when sync off",
      organizations.team_dictionary({"sync_enabled": False, "org": {"org_id": "o", "dictionary": TEAM}})
      == {"vocabulary": [], "replacements": [], "snippets": []})
# _gate is what keeps every network entry point from firing while signed out.
check("_gate closed with no sync_user_id", organizations._gate({}) is False)
check("_gate closed on junk", organizations._gate(None) is False)
# The network entry points must return a shaped failure, never raise, when signed out.
check("fetch() signed out returns NO_ORG", organizations.fetch({}, lambda c: None)["org_id"] == "")
check("create() signed out returns ok:False", organizations.create({}, "T", "", lambda c: None)["ok"] is False)
check("invite() with no org returns ok:False", organizations.invite({}, "a@b.co")["ok"] is False)
check("list_invites() with no org returns []", organizations.list_invites({}) == [])
check("usage_summary() with no org returns no rows", organizations.usage_summary({})["rows"] == [])
# usage_summary must NOT gate on role — the RPC returns the caller's own row to a
# plain member, and gating the request is what made a member's Team screen zeroes.
_ORIG_RPC2, _ORIG_GET2 = organizations._rpc, organizations.get
try:
    _asked = []
    organizations.get = lambda cfg: {**organizations.NO_ORG, "org_id": "org-1", "role": "member",
                                     "members": [{"user_id": "u1", "usage_consent": True}]}
    def _spy(cfg, fn, args):
        _asked.append(fn)
        return [{"user_id": "u1", "display_name": "Me", "role": "member",
                 "dictations": 60, "words": 4000, "speech_ms": 300000, "last_active": None}]
    organizations._rpc = _spy
    r = organizations.usage_summary({"sync_user_id": "u1"}, 30)
    check("usage_summary asks the RPC even for a plain member", _asked == ["org_usage_summary"])
    check("usage_summary returns a member their own row", len(r["rows"]) == 1 and r["ok"] is True)
    check("usage_summary member row carries real numbers", r["rows"][0]["words"] == 4000)
finally:
    organizations._rpc, organizations.get = _ORIG_RPC2, _ORIG_GET2
check("leaderboard() with no org is disabled", organizations.leaderboard({})["enabled"] is False)
check("save_team_dictionary() with no org returns ok:False",
      organizations.save_team_dictionary({}, PERSONAL, lambda c: None)["ok"] is False)
check("app_breakdown() with no org returns an empty map",
      organizations.app_breakdown({}) == {"ok": True, "apps": {}})

# ── app_breakdown shaping (IDI-216, per-person app mix) ─────────────────────
# The RPC returns one flat row per (member, app); the client's whole job is to
# group it by member, biggest-first, and refuse to invent anything. Stub _rpc so
# the transform is tested without a network.
_ORIG_RPC = organizations._rpc
_ORIG_GET = organizations.get
try:
    organizations.get = lambda cfg: {**organizations.NO_ORG, "org_id": "org-1"}
    organizations._rpc = lambda cfg, fn, args: [
        {"user_id": "u1", "app": "Slack",  "dictations": 80, "words": 6000},
        {"user_id": "u1", "app": "Cursor", "dictations": 30, "words": 2400},
        {"user_id": "u2", "app": "Chrome", "dictations": 60, "words": 4000},
        {"user_id": "u1", "app": "   ",    "dictations": 5,  "words": 100},   # blank app
        {"user_id": "",   "app": "Ghost",  "dictations": 9,  "words": 90},    # no member
        "not a dict",                                                        # junk row
    ]
    r = organizations.app_breakdown({"sync_user_id": "u1"}, 30)
    check("app_breakdown groups by member", sorted(r["apps"].keys()) == ["u1", "u2"])
    check("app_breakdown keeps the RPC's order", [a["app"] for a in r["apps"]["u1"]] == ["Slack", "Cursor"])
    check("app_breakdown drops a blank app name", len(r["apps"]["u1"]) == 2)
    check("app_breakdown drops a row with no member", "Ghost" not in str(r["apps"]))
    check("app_breakdown survives a junk row", r["ok"] is True)
    check("app_breakdown coerces counts to int", r["apps"]["u2"][0]["dictations"] == 60)

    # A failing RPC must return the same shape, not raise — this panel is
    # peripheral and must never take the Team screen down with it.
    def _boom(cfg, fn, args):
        raise RuntimeError("network down")
    organizations._rpc = _boom
    r2 = organizations.app_breakdown({"sync_user_id": "u1"}, 30)
    check("app_breakdown fails closed", r2 == {"ok": False, "apps": {}})
finally:
    organizations._rpc = _ORIG_RPC
    organizations.get = _ORIG_GET

print()
total = _passed + len(_failed)
print(f"total={total} passed={_passed} failed={len(_failed)} ALL_GREEN={not _failed}")
if _failed:
    for f in _failed:
        print("  -", f)
    sys.exit(1)
