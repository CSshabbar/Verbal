#!/usr/bin/env python3
"""
MER-44 Phase 0 — pure-logic assertion harness for context grounding.

Unlike self_correction_fixtures.py (which deliberately calls the LIVE model to
verify PROMPT behaviour), this one is pure-logic — same convention as
snippets_fixtures.py / autolearn_fixtures.py — because everything worth checking
here is deterministic: what the context block contains, that it's fail-closed, and
that the auto-learn → grounding loop closes. No network, no LLM.

Run:
  whisperflow/.venv/bin/python context_grounding_fixtures.py

Exits 1 if any assertion fails (matches the other fixtures' convention).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from app import dictionary                                   # noqa: E402
from app.ai_cleanup import build_context_block, build_dictation_user_message  # noqa: E402

_total = 0
_passed = 0
_failed = 0


def check(name, cond):
    global _total, _passed, _failed
    _total += 1
    if cond:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name}")


def _cfg(vocab=None, reps=None, snips=None, **extra):
    d = {"vocabulary": vocab or [], "replacements": reps or [], "snippets": snips or []}
    c = {"dictionary": d}
    c.update(extra)
    return c


# ── known_terms: dedup, replacement targets, cap, fail-closed ────────────────────
c = _cfg(vocab=["RBR", "Ramiz", "Acme Corp"],
         reps=[{"from": "rameez", "to": "Ramiz", "auto": True}, {"from": "flum", "to": "Flume"}])
terms = dictionary.known_terms(c)
check("known_terms includes vocabulary", "RBR" in terms and "Acme Corp" in terms)
check("known_terms includes replacement 'to' targets (auto-learn loop closes)", "Flume" in terms)
check("known_terms dedupes case-insensitively (Ramiz once, not twice)",
      [t.lower() for t in terms].count("ramiz") == 1)
check("known_terms is bounded by limit",
      len(dictionary.known_terms(_cfg(vocab=[f"w{i}" for i in range(200)]), limit=60)) == 60)
check("known_terms never raises on malformed dictionary",
      dictionary.known_terms({"dictionary": "garbage"}) == [])
check("known_terms empty on empty dict", dictionary.known_terms(_cfg()) == [])

# ── build_context_block: content, app hint, empties, flag, fail-closed ───────────
block = build_context_block(c, active_app="Slack")
check("context block names the active app", "Active app: Slack" in block)
check("context block lists known terms", "RBR" in block and "Flume" in block)
check("context block is labeled grounding-only (must not be injected/echoed)",
      "grounding only" in block.lower() and "never output" in block.lower())
check("context block does NOT instruct the model to collapse (no over-collapse nudge)",
      "collapse" not in block.lower())

check("empty config → empty context block", build_context_block(_cfg()) == "")
check("no dict + no app → empty block", build_context_block({}) == "")
check("known terms but no active app still grounds (notes/retry path)",
      "Known terms" in build_context_block(c) and "Active app" not in build_context_block(c))
check("app but no terms still grounds on the app",
      "Active app: Cursor" in build_context_block(_cfg(), active_app="Cursor"))

# flag off → nothing, regardless of dict/app
check("context_grounding_enabled=False disables the block",
      build_context_block(_cfg(vocab=["RBR"], context_grounding_enabled=False), active_app="Slack") == "")

# fail-closed: malformed config never raises, app hint still survives
check("malformed dict is fail-closed (app hint survives, terms empty)",
      "Active app: X" in build_context_block({"dictionary": "garbage"}, active_app="X"))

# ── build_dictation_user_message: backward compat + context prepend ──────────────
plain = build_dictation_user_message("hello")
check("empty-context user message == original wrapper (backward compatible)",
      plain.startswith("TRANSCRIPTION TO FORMAT:") and "hello" in plain)
withctx = build_dictation_user_message("hello", context=block)
check("context is prepended before the transcript",
      withctx.startswith("CONTEXT") and withctx.index("CONTEXT") < withctx.index("TRANSCRIPTION"))
check("transcript is preserved verbatim under context", "```\nhello\n```" in withctx)

# ── auto-learn → grounding loop (end-to-end, local) ─────────────────────────────
# Simulate what autolearn does on a manual edit: add_replacement(..., auto=True),
# then confirm the corrected term now grounds the cleanup call.
loop_cfg = _cfg()
saved = {}
dictionary.add_replacement(loop_cfg, "shabar", "Shabbar", lambda cc: saved.update(cc), auto=True)
check("auto-learned correction flows into known_terms",
      "Shabbar" in dictionary.known_terms(loop_cfg))
check("auto-learned correction appears in the grounding block",
      "Shabbar" in build_context_block(loop_cfg))

all_green = _failed == 0
print(f"\ntotal={_total} passed={_passed} failed={_failed} ALL_GREEN={all_green}")
sys.exit(0 if all_green else 1)
