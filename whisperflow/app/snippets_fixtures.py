#!/usr/bin/env python
"""
Standalone assertion harness for dictionary.apply_snippets().

Run: whisperflow/.venv/bin/python app/snippets_fixtures.py

Verifies the shared snippet-expansion algorithm:
  - basic expansion
  - mid-sentence expansion (rest of the sentence untouched)
  - longest-trigger-first overlap ("my email" vs "my email address")
  - case-insensitivity
  - NO recursion (an expansion that contains another trigger is not re-expanded)
  - no-match passthrough
  - guarded / empty inputs (never throws, returns input unchanged)
  - 'used' counter increments and persists via save_config_fn
"""
import os
import sys

# Allow running from anywhere: put the repo root (parent of app/) on sys.path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app import dictionary as D  # noqa: E402

_total = 0
_passed = 0
_failed = 0


def check(name, got, expected):
    global _total, _passed, _failed
    _total += 1
    ok = got == expected
    if ok:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name}\n         expected: {expected!r}\n         got:      {got!r}")


def cfg(snippets):
    """Build a config carrying the given raw snippets (normalized on read)."""
    return {"dictionary": {"vocabulary": [], "replacements": [], "snippets": snippets}}


def snip(trigger, expansion, label=""):
    return {"trigger": trigger, "expansion": expansion, "label": label}


# ── 1. basic expansion ─────────────────────────────────────────────────────────
c = cfg([snip("my linkedin", "https://linkedin.com/in/shabbar")])
check("basic expansion",
      D.apply_snippets("my linkedin", c),
      "https://linkedin.com/in/shabbar")

# ── 2. mid-sentence expansion (rest of sentence untouched) ──────────────────────
c = cfg([snip("my linkedin", "https://linkedin.com/in/shabbar")])
check("mid-sentence expansion",
      D.apply_snippets("Here is my linkedin if you want to connect.", c),
      "Here is https://linkedin.com/in/shabbar if you want to connect.")

# ── 3. longest-trigger-first overlap ────────────────────────────────────────────
c = cfg([
    snip("my email", "shabbar@work.com"),
    snip("my email address", "1600 Amphitheatre Pkwy"),
])
check("longest-first wins (address)",
      D.apply_snippets("my email address", c),
      "1600 Amphitheatre Pkwy")
check("shorter still matches on its own",
      D.apply_snippets("my email please", c),
      "shabbar@work.com please")

# ── 4. case-insensitivity ───────────────────────────────────────────────────────
c = cfg([snip("my linkedin", "https://linkedin.com/in/shabbar")])
check("case-insensitive trigger",
      D.apply_snippets("Check out MY LinkedIn now", c),
      "Check out https://linkedin.com/in/shabbar now")

# ── 5. NO recursion (expansion containing another trigger is not re-expanded) ────
c = cfg([
    snip("sig", "Best, Shabbar — my linkedin"),  # expansion CONTAINS a trigger
    snip("my linkedin", "https://linkedin.com/in/shabbar"),
])
check("no recursion into inserted expansion",
      D.apply_snippets("sig", c),
      "Best, Shabbar — my linkedin")

# recursion guard also holds mid-sentence with both triggers present in input
check("single pass expands each input occurrence once",
      D.apply_snippets("sig and my linkedin", c),
      "Best, Shabbar — my linkedin and https://linkedin.com/in/shabbar")

# ── 6. no-match passthrough ─────────────────────────────────────────────────────
c = cfg([snip("my linkedin", "https://linkedin.com/in/shabbar")])
check("no-match passthrough",
      D.apply_snippets("just some ordinary text", c),
      "just some ordinary text")

# substring that is NOT a whole-phrase word-boundary hit must not expand
c = cfg([snip("cat", "CATEGORY")])
check("word-boundary: 'cat' does not match inside 'category'",
      D.apply_snippets("the category list", c),
      "the category list")

# ── 7. guarded / empty inputs (never throws) ────────────────────────────────────
c = cfg([snip("my linkedin", "https://x")])
check("empty string passthrough", D.apply_snippets("", c), "")
check("None passthrough", D.apply_snippets(None, c), None)
check("no snippets configured passthrough",
      D.apply_snippets("hello world", cfg([])), "hello world")
check("bad config passthrough (no dictionary key)",
      D.apply_snippets("hello world", {}), "hello world")
check("junk snippet entries ignored",
      D.apply_snippets("hello", cfg([None, {}, {"trigger": "", "expansion": "x"}, 42])),
      "hello")

# multi-word aware: collapsed/extra whitespace in speech still matches
c = cfg([snip("my email address", "addr")])
check("multi-word tolerant of extra whitespace",
      D.apply_snippets("send to my  email   address ok", c),
      "send to addr ok")

# ── 8. 'used' counter increments and persists ───────────────────────────────────
_saves = {"n": 0}


def _save(cfg_obj):
    _saves["n"] += 1


c = cfg([snip("my linkedin", "https://x")])
# two occurrences → counter +2
out = D.apply_snippets("my linkedin and my linkedin", c, save_config_fn=_save)
check("both occurrences expanded", out, "https://x and https://x")
check("used counter incremented per occurrence",
      D.get_snippets(c)[0]["used"], 2)
check("persist callback fired", _saves["n"] >= 1, True)

# without save_config_fn, expansion still works, no persistence attempted
c2 = cfg([snip("my linkedin", "https://x")])
check("expands without save_config_fn",
      D.apply_snippets("my linkedin", c2), "https://x")

# ── CRUD smoke (in-memory, no network) ──────────────────────────────────────────
c = {"dictionary": {"vocabulary": [], "replacements": [], "snippets": []}}
noop = lambda _cfg: None  # noqa: E731
D.add_snippet(c, "My Sig", "Best regards", "Signature", noop)
sn = D.get_snippets(c)
check("add_snippet appends one", len(sn), 1)
check("add_snippet stores trigger", sn[0]["trigger"], "My Sig")
# dedupe by trigger (case-insensitive)
D.add_snippet(c, "my sig", "Cheers", "", noop)
check("add_snippet dedupes by trigger (case-insensitive)", len(D.get_snippets(c)), 1)
check("add_snippet dedupe replaces expansion", D.get_snippets(c)[0]["expansion"], "Cheers")
sid = D.get_snippets(c)[0]["id"]
D.update_snippet(c, sid, noop, label="Renamed", expansion="Updated")
check("update_snippet patches label", D.get_snippets(c)[0]["label"], "Renamed")
check("update_snippet patches expansion", D.get_snippets(c)[0]["expansion"], "Updated")
D.remove_snippet(c, sid, noop)
check("remove_snippet deletes", len(D.get_snippets(c)), 0)

# normalize caps + dedupe
long_trigger = "t" * 100
long_expansion = "e" * 2000
norm = D.normalize({"snippets": [
    snip(long_trigger, long_expansion),
    snip("dup", "one"),
    snip("DUP", "two"),  # dedup by trigger case-insensitive
]})
check("normalize caps trigger to 40", len(norm["snippets"][0]["trigger"]), 40)
check("normalize caps expansion to 500", len(norm["snippets"][0]["expansion"]), 500)
check("normalize dedupes triggers", len([s for s in norm["snippets"] if s["trigger"].lower() == "dup"]), 1)

# ── summary ─────────────────────────────────────────────────────────────────────
all_green = _failed == 0
print(f"\ntotal={_total} passed={_passed} failed={_failed} ALL_GREEN={all_green}")
sys.exit(0 if all_green else 1)
