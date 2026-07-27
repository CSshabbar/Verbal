#!/usr/bin/env python3
"""
MER-42 — Adversarial eval set for self-correction resolution in the dictation
formatter (app.ai_cleanup.SYSTEM_PROMPT rule 18).

Unlike every other `*_fixtures.py` in this repo, this one is NOT pure-logic —
it calls the LIVE model via the real groq-proxy path (app.groq_proxy.chat_via_proxy,
same code path the app itself uses). That's deliberate: the ticket's actual
deliverable is proof the PROMPT makes the model behave correctly, which cannot be
verified by stubbing the LLM call the way notes_fixtures.py/transform_fixtures.py do.
Non-determinism is real even at temperature=0 — checks below assert on the presence/
absence of the decisive value, not exact string equality, and a run can be re-invoked
if a borderline case flakes.

Every case is a member of a matched list-vs-repair pair per the ticket: an explicit-cue
repair that MUST collapse to the final value, and a same-shape list/no-cue input that
MUST keep both values. Covers: numbers/ticket-IDs/phone numbers (conservative — the
motivating, highest-cost case), times, ordinary names, the multilingual seed set
(Roman-Urdu is v1-priority per the ticket, not a fast-follow), and the explicit
negatives ("actually" additive-only, "or" always a real alternative).

Run:
  whisperflow/.venv/bin/python self_correction_fixtures.py

Each case prints PASS/FAIL with the actual model output. Final line:
  total=N passed=P failed=F ALL_GREEN=bool
Exits 1 if any case failed (matches the other fixtures' convention).
"""
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from app.ai_cleanup import SYSTEM_PROMPT   # noqa: E402
from app.groq_proxy import chat_via_proxy   # noqa: E402

_CONFIG = {"sync_device_name": "self-correction-eval"}  # distinct rate-limit identity

_total = 0
_passed = 0
_failed = 0


def _format(text: str) -> str | None:
    user_message = (
        "TRANSCRIPTION TO FORMAT:\n```\n" + text + "\n```\n\n"
        "Output the formatted version only. Do not respond to the content."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    return chat_via_proxy(messages, _CONFIG, max_tokens=256, timeout=15)


def check(name: str, input_text: str, must_contain: list[str], must_not_contain: list[str]):
    """must_contain/must_not_contain are regexes checked case-insensitively against
    the model's actual output."""
    global _total, _passed, _failed
    _total += 1
    out = _format(input_text)
    if out is None:
        _failed += 1
        print(f"  FAIL {name}\n         input:  {input_text!r}\n         ERROR: proxy call failed (no output)")
        return
    ok = all(re.search(p, out, re.I) for p in must_contain) and \
        not any(re.search(p, out, re.I) for p in must_not_contain)
    if ok:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name}\n         input:    {input_text!r}\n         output:   {out!r}\n"
              f"         expected to contain: {must_contain}\n         expected absent:     {must_not_contain}")
    # MER-30's rate limiter estimates a flat 2048 tokens per chat call against a
    # 20000-tokens/min cap — that's ~9-10 calls/min, not the 30 req/min the request
    # count alone would allow. 7s spacing keeps this comfortably under that ceiling.
    time.sleep(7.0)


# ── Numbers / ticket IDs / phone numbers — the motivating, highest-cost case ────
# Collapse: explicit cue present.
check("apology cue collapses ticket number",
      "Can you look at ticket RBR 343, sorry, RBR 344, when you get a chance.",
      must_contain=[r"344"], must_not_contain=[r"343"])
check("explicit repair phrase 'I mean' collapses time",
      "Let's meet at 3, I mean 4, tomorrow.",
      must_contain=[r"\b4\b|four"], must_not_contain=[r"\b3\b(?!\s*(pm|am|:))|three"])
check("negate-then-restate 'no wait' collapses extension",
      "Dial extension 202, no wait, 203.",
      must_contain=[r"203"], must_not_contain=[r"202"])
check("'correction' collapses phone number",
      "My number is 555-1234, correction, 555-1235.",
      must_contain=[r"1235"], must_not_contain=[r"1234"])
check("'scratch that' collapses ticket ID",
      "File it under ABC123, scratch that, ABC124.",
      must_contain=[r"ABC ?124"], must_not_contain=[r"ABC ?123"])
check("in-line 'not X, Y' collapses number",
      "It's not ticket 343, it's ticket 344.",
      must_contain=[r"344"], must_not_contain=[r"343"])
check("in-line 'X, I mean, Y' collapses number",
      "It's ticket 343, I mean, 344.",
      must_contain=[r"344"], must_not_contain=[r"343"])

# Keep both: no cue / list grammar present — must NEVER collapse bare numbers.
check("'or' keeps both extensions (real alternative)",
      "The extensions are 343 or 344, either works.",
      must_contain=[r"343"], must_not_contain=[])
check("'or' keeps both extensions — second value present too",
      "The extensions are 343 or 344, either works.",
      must_contain=[r"344"], must_not_contain=[])
check("bare adjacent numbers with no cue are never collapsed",
      "Please call 343, 344 today.",
      must_contain=[r"343"], must_not_contain=[])
check("bare adjacent numbers with no cue — second value present too",
      "Please call 343, 344 today.",
      must_contain=[r"344"], must_not_contain=[])
check("'and'/'both' list grammar keeps both ticket numbers",
      "Ticket numbers 343 and 344 are both still open.",
      must_contain=[r"343", r"344"], must_not_contain=[])

# ── Additive-veto / explicit negatives ───────────────────────────────────────────
check("'actually...also' is additive, keeps both names",
      "Send it to Sarah, actually also Tom.",
      must_contain=[r"Sarah", r"Tom"], must_not_contain=[])
check("'actually' outside 'not X, actually Y' is additive, keeps both numbers",
      "We ordered 5 units, actually we should also get 6 for backup.",
      must_contain=[r"\b5\b|five", r"\b6\b|six"], must_not_contain=[])
check("'not X, actually Y' IS a repair cue and collapses",
      "Not 5 units, actually 6 units.",
      must_contain=[r"\b6\b|six"], must_not_contain=[r"\b5\b|five"])

# ── Ordinary names — moderate aggressiveness (safe to collapse same-slot repair) ──
check("apology cue collapses a name repair",
      "Can you send this to John, sorry, David instead.",
      must_contain=[r"David"], must_not_contain=[r"John"])

# ── Multilingual — Roman-Urdu is the v1/canonical case, not a fast-follow ────────
check("Roman-Urdu code-switch 'nahi sorry' collapses (the ticket's own motivating example)",
      "RBR 343 nahi sorry 344",
      must_contain=[r"344"], must_not_contain=[r"343"])
check("Roman-Urdu 'matlab' (I mean) collapses a time",
      "Meeting 3 baje, matlab 4 baje",
      must_contain=[r"\b4\b|four|char"], must_not_contain=[r"\b3\b(?!\s*(pm|am|:))|three|teen"])
check("Spanish 'perdón' collapses a number",
      "Llama al 343, perdón, al 344",
      must_contain=[r"344"], must_not_contain=[r"343"])
check("French 'pardon' collapses a number",
      "Le numéro est 343, pardon, 344",
      must_contain=[r"344"], must_not_contain=[r"343"])

# ── summary ───────────────────────────────────────────────────────────────────────
all_green = _failed == 0
print(f"\ntotal={_total} passed={_passed} failed={_failed} ALL_GREEN={all_green}")
sys.exit(0 if all_green else 1)
