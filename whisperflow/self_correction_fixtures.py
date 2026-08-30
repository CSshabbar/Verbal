#!/usr/bin/env python3
"""
MER-42/MER-43 — Adversarial eval set for self-correction resolution in the dictation
formatter (app.ai_cleanup.SYSTEM_PROMPT rule 18, mirrored in verbal-mobile/lib/groq.ts).

Unlike every other `*_fixtures.py` in this repo, this one is NOT pure-logic — it calls
the LIVE model via the real groq-proxy path (app.groq_proxy.chat_via_proxy, same code
path the app itself uses). That's deliberate: the deliverable is proof the PROMPT makes
the model behave correctly, which cannot be verified by stubbing the LLM call the way
notes_fixtures.py/transform_fixtures.py do. Non-determinism is real even at
temperature=0 — checks below assert on the presence/absence of the decisive value, not
exact string equality, and a run can be re-invoked if a borderline case flakes.

Two passes:
  - DESKTOP pass: imports the real app.ai_cleanup.SYSTEM_PROMPT and the real
    build_dictation_user_message() wrapper (not a hand-copy — MER-43 Part 6 fidelity
    fix) — covers the full Part 4 scenario matrix, punctuation-shape variants, hard/
    edge cases, and the multilingual seed set.
  - MOBILE pass: exercises MOBILE_SYSTEM_PROMPT, a literal copy of groq.ts's
    formatText() SYSTEM template (kept in sync manually, like the two prompts
    themselves — see that file's own note). This is a representative subset targeting
    the specific desktop/mobile divergences MER-43 fixed (cue families that were
    missing on mobile, the name-without-cue asymmetry, the "and"+cue carve-out,
    directionality, tight adjacency) — not the full matrix, to keep total run time
    reasonable under the shared rate limit.

REGRESSION-tagged cases are the ones lifted directly from real user reports (see the
companion Linear doc §5's write-ups) — unpunctuated cue, "and sorry" bridge, and
Whisper's false-sentence-break fragmentation. The in-line "not X, Y" case is tagged
GAP1 instead: it was found on the FIRST LIVE EVAL RUN (a cleanly-punctuated sentence),
not from a live user report, so it isn't a "regression" in the same sense.

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

from app.ai_cleanup import SYSTEM_PROMPT, build_dictation_user_message   # noqa: E402
from app.groq_proxy import chat_via_proxy   # noqa: E402

_CONFIG = {"sync_device_name": "self-correction-eval"}  # distinct rate-limit identity

# Literal copy of verbal-mobile/lib/groq.ts's formatText() SYSTEM template as of the
# MER-43 parity pass. Manually kept in sync with that file — if you edit groq.ts's
# SYSTEM, update this too, or the mobile pass below silently stops being representative.
MOBILE_SYSTEM_PROMPT = """You are a TEXT FORMATTER, not an AI assistant.
You receive raw voice transcription and output a formatted version.
NEVER add, invent, or respond to the content.
NEVER add headings unless the speaker said them word-for-word.
Only reformat: fix punctuation, capitalization, remove fillers (um, uh — never a
repair cue, see below), format lists when speaker says "number one/two", add
paragraph breaks on topic changes.

SELF-CORRECTIONS (repairs) — collapse to ONLY the corrected final value when ALL of
these hold: (a) an explicit repair cue is present — apology repairs (sorry, my bad,
oops, whoops, my mistake, pardon), explicit repair phrases (I mean, I meant, rather,
that should be, make that, let me rephrase, correction), negate-then-restate (no wait,
scratch that, strike that, forget that, or "not X, Y"), false-start markers (uh no,
hang on) — in ANY language, recognize the PATTERN, not just these exact words (e.g.
Roman-Urdu "nahi"/"matlab", Hindi "nahi"/"matlab"/"arre", Spanish "perdón"/"digo"/"o
sea", French "pardon"/"enfin"/"plutôt", Arabic "afwan"/"aqsid"/"yaani"); (b) the new
value replaces the old one of the SAME KIND (number-for-number, time-for-time,
name-for-name — even across a magnitude change) — a different kind of value, or a
genuinely separate point, is never collapsed; (c) same breath/clause, not separated
by unrelated content; (d) no list nearby ("and"/"plus"/"also"/"too"/"or"/"both"/a
comma series) — EXCEPT "and" directly before a cue is not a list veto ("343 and sorry
344" still collapses to 344).

The raw transcript often has NO comma around the cue (Whisper rarely punctuates short
interjections) — judge this by the WORDS alone: "343 sorry 353" and "343, sorry, 353"
are the SAME pattern, both collapse to 353. Whisper can also do the OPPOSITE and
insert a false "?" or "." plus a capitalized next word right before the cue, making
one continuous correction look like two sentences — still the same repair, judge by
meaning not punctuation: "Can you work on the ticket 343? Sorry, 353." → "Can you
work on the ticket 353."

Numbers, ticket/ID numbers, and phone numbers are conservative: NEVER collapse bare
adjacent ones without an explicit cue. Ordinary words and names are moderate: collapse
on a clear same-slot repair even WITHOUT an explicit cue (a wrong guess there costs
little) — "send this to John, David instead" → "David" is fine to collapse even
without "sorry"/"I mean". Multiple corrections in one breath resolve to the LAST
value: "343, sorry 344, no wait 345" → "345". A repair inside a real list only
replaces its own slot: "apples, oranges, sorry tangerines, and bananas" → "apples,
tangerines, and bananas". A cue word with no candidate same-kind value around it is
just content, not a repair: "I want to say sorry to the team" keeps "sorry" as spoken.

"actually" only counts as a repair cue inside "not X, actually Y" (otherwise it's
additive, keep both); "or" always means a real alternative, keep both. The later
value always wins. The STRONGEST signal is the in-line pattern "it's not X, it's Y" /
"not X, Y" / "not X, actually Y" (either order) — treat as a confident repair and
collapse to Y: "it's not ticket 343, it's ticket 344" → "ticket 344"; "not 5 units,
actually 6 units" → "6 units". Example: "call ticket RBR 343, sorry, RBR 344" → "call
ticket RBR 344". Do NOT collapse "the extensions are 343 or 344" or "send it to
Sarah, actually also Tom".

Return ONLY the formatted text."""


def _mobile_user_message(text: str) -> str:
    """Mirrors groq.ts formatText()'s exact user-message wrapper (no "Do not respond
    to the content" line — that's a desktop-only addition)."""
    return f"TRANSCRIPTION TO FORMAT:\n```\n{text}\n```\n\nOutput the formatted version only."


_total = 0
_passed = 0
_failed = 0


def _call(system_prompt: str, user_message: str) -> str | None:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    return chat_via_proxy(messages, _CONFIG, max_tokens=256, timeout=15)


def check(name: str, input_text: str, must_contain: list[str], must_not_contain: list[str]):
    """Desktop pass — real SYSTEM_PROMPT + real build_dictation_user_message()."""
    _run(name, _call(SYSTEM_PROMPT, build_dictation_user_message(input_text)),
         input_text, must_contain, must_not_contain)


def check_mobile(name: str, input_text: str, must_contain: list[str], must_not_contain: list[str]):
    """Mobile pass — MOBILE_SYSTEM_PROMPT (kept in sync with groq.ts, see above)."""
    _run(f"[mobile] {name}", _call(MOBILE_SYSTEM_PROMPT, _mobile_user_message(input_text)),
         input_text, must_contain, must_not_contain)


def _run(name: str, out: str | None, input_text: str, must_contain: list[str], must_not_contain: list[str]):
    """must_contain/must_not_contain are regexes checked case-insensitively against
    the model's actual output."""
    global _total, _passed, _failed
    _total += 1
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


# ══════════════════════════════════════════════════════════════════════════════════
# DESKTOP PASS
# ══════════════════════════════════════════════════════════════════════════════════

# ── Numbers / ticket IDs / phone numbers — the motivating, highest-cost case ────
check("apology cue collapses ticket number",
      "Can you look at ticket RBR 343, sorry, RBR 344, when you get a chance.",
      must_contain=[r"344"], must_not_contain=[r"343"])
check("REGRESSION (real user report, unpunctuated 'sorry' — no commas at all)",
      "Can you work on the ticket 343 sorry 353.",
      must_contain=[r"353"], must_not_contain=[r"343"])
check("REGRESSION (real user report, 'and sorry' — 'and' must not trigger the list veto)",
      "Today I would be working on ticket 343 and sorry 344.",
      must_contain=[r"344"], must_not_contain=[r"343"])
check("REGRESSION (real user report, Whisper fragments the repair into a false '?' sentence break)",
      "Can you work on the ticket 343? Sorry, 353.",
      must_contain=[r"353"], must_not_contain=[r"343"])
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
check("GAP1 (found on first live eval run, not a live-user regression) in-line 'not X, Y' collapses number",
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
check("Roman-Urdu code-switch 'nahi sorry' collapses (unpunctuated — punctuation shape 1/3)",
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

# ── MER-43 Part 3/6: fill the Roman-Urdu punctuation-shape 2x2 (§7 of the doc
# flagged this was never tested — only English cues got all 3 shapes) ───────────
check("Roman-Urdu code-switch 'nahi' collapses (comma-punctuated — shape 2/3)",
      "Ticket RBR 343, nahi, RBR 344.",
      must_contain=[r"344"], must_not_contain=[r"343"])
check("Roman-Urdu code-switch 'nahi' collapses (Whisper-fragmented '?' break — shape 3/3)",
      "Ticket RBR 343? Nahi, RBR 344.",
      must_contain=[r"344"], must_not_contain=[r"343"])

# ── MER-43 Part 3: Hindi + Arabic — named in the prompt, previously zero coverage ─
check("Hindi 'arre' collapses a ticket number",
      "Ticket 343, arre, 344.",
      must_contain=[r"344"], must_not_contain=[r"343"])
check("Hindi 'matlab' collapses a time",
      "Meeting at 3 baje, matlab 4 baje.",
      must_contain=[r"\b4\b|four|char"], must_not_contain=[r"\b3\b(?!\s*(pm|am|:))|three|teen"])
check("Arabic 'afwan' collapses a ticket number",
      "Ticket 343, afwan, 344.",
      must_contain=[r"344"], must_not_contain=[r"343"])
check("Arabic 'yaani' collapses an extension",
      "Extension 202, yaani 203.",
      must_contain=[r"203"], must_not_contain=[r"202"])

# ── MER-43 Part 4: scenario matrix — content types not covered by MER-42's eval ──
check("number <10 collapses",
      "We need 5 units, I mean 6 units.",
      must_contain=[r"\b6\b|six"], must_not_contain=[r"\b5\b|five"])
check("number <10 list keeps both",
      "We need 5 and 6 units.",
      must_contain=[r"\b5\b|five", r"\b6\b|six"], must_not_contain=[])
check("date collapses",
      "Let's meet March 14th, sorry, March 15th.",
      must_contain=[r"15"], must_not_contain=[r"\b14\b"])
check("date list keeps both",
      "Let's meet on the 14th and 15th of March.",
      must_contain=[r"14"], must_not_contain=[])
check("date list keeps both — second value present too",
      "Let's meet on the 14th and 15th of March.",
      must_contain=[r"15"], must_not_contain=[])
check("currency collapses",
      "That's $20, I mean $25.",
      must_contain=[r"\$25"], must_not_contain=[r"\$20"])
check("currency alternative keeps both",
      "That's either $20 or $25.",
      must_contain=[r"\$20", r"\$25"], must_not_contain=[])
check("percentage collapses",
      "The discount is 20%, sorry, 25%.",
      must_contain=[r"25%"], must_not_contain=[r"20%"])
check("percentage range keeps both",
      "The discount is between 20% and 25%.",
      must_contain=[r"20%", r"25%"], must_not_contain=[])
check("place/company collapses",
      "Ship it to Acme, I mean Globex.",
      must_contain=[r"Globex"], must_not_contain=[r"Acme"])
check("place/company list keeps both",
      "Ship it to Acme and Globex.",
      must_contain=[r"Acme", r"Globex"], must_not_contain=[])
check("email collapses (after rule 11 address assembly)",
      "Email john at gmail dot com, sorry, jane at gmail dot com.",
      must_contain=[r"jane"], must_not_contain=[r"john"])
check("email list keeps both",
      "Email john at gmail dot com and jane at gmail dot com.",
      must_contain=[r"john", r"jane"], must_not_contain=[])
check("URL/domain collapses",
      "The site is at example dot com, I mean example dot org.",
      must_contain=[r"\.org"], must_not_contain=[r"\.com"])
check("URL/domain alternative keeps both",
      "The site is at example dot com or example dot org.",
      must_contain=[r"\.com", r"\.org"], must_not_contain=[])
check("code identifier collapses (must not mangle backticks, rule 14)",
      "Edit build dot js, I mean build dot ts.",
      must_contain=[r"build\.?ts"], must_not_contain=[r"build\.?js"])
check("code identifier list keeps both",
      "Edit build dot js and build dot ts.",
      must_contain=[r"build\.?js", r"build\.?ts"], must_not_contain=[])

# ── MER-43 Part 4: hard/edge scenarios ───────────────────────────────────────────
check("multiple corrections in one breath resolve to the LAST value",
      "Ticket 343, sorry 344, no wait 345.",
      must_contain=[r"345"], must_not_contain=[r"\b343\b", r"\b344\b"])
check("correction INSIDE a real list preserves the other items",
      "I bought apples, oranges, sorry tangerines, and bananas.",
      must_contain=[r"apples", r"tangerines", r"bananas"], must_not_contain=[r"oranges"])
check("identical old/new value is a harmless no-op",
      "Ticket 344, sorry, 344.",
      must_contain=[r"344"], must_not_contain=[])
check("different-kind value after a cue is NOT a same-slot swap, keeps both",
      "Send it to 344, sorry, tell Dave.",
      must_contain=[r"344", r"Dave"], must_not_contain=[])
check("non-adjacent same-kind values (no tight adjacency) are never collapsed",
      "Ticket 343 has been open for a while now and needs review soon, also check 344.",
      must_contain=[r"343", r"344"], must_not_contain=[])
check("directionality — correct value FIRST, then 'not X' naming the wrong one, still collapses",
      "It's 344, not 343.",
      must_contain=[r"344"], must_not_contain=[r"343"])
check("magnitude change is still a same-kind swap and collapses",
      "Ticket 343, sorry, 3430.",
      must_contain=[r"3430"], must_not_contain=[r"\b343\b"])

# ── MER-43 Part 3: cue-as-content negatives — the cue word IS the message, no swap ─
check("cue-as-content: 'sorry' with no candidate value is not a repair",
      "I want to say sorry to the whole team for the mistake.",
      must_contain=[r"sorry", r"team"], must_not_contain=[])
check("cue-as-content: 'no' as a direct answer is not a repair",
      "The answer is no, we're not doing that.",
      must_contain=[r"\bno\b"], must_not_contain=[])
check("cue-as-content: 'make that' as an instruction (no prior same-kind value) is not a repair",
      "Please make that report longer before you send it.",
      must_contain=[r"make that", r"longer"], must_not_contain=[])
check("cue-as-content: 'correction' used as a noun is not a repair",
      "That grammatical correction is really hard to get right.",
      must_contain=[r"correction"], must_not_contain=[])


# ══════════════════════════════════════════════════════════════════════════════════
# MOBILE PASS — targeted subset covering the specific desktop/mobile divergences
# MER-43 fixed (Part 1.2): cue families that were missing on mobile, the
# name-without-cue asymmetry, the "and"+cue carve-out, directionality, and tight
# adjacency. Not the full matrix (see module docstring) — the full matrix already
# runs against the desktop wording above, and the two prompts are meant to encode
# identical logic (Part 5 parity contract), so a full duplicate run would mostly
# re-prove the same thing at 2x the rate-limit cost.
# ══════════════════════════════════════════════════════════════════════════════════

check_mobile("name collapses WITHOUT an explicit cue (moderate asymmetry — was mobile-missing)",
             "Send this to John, David instead.",
             must_contain=[r"David"], must_not_contain=[r"John"])
check_mobile("'my bad' collapses (was missing from mobile's cue list)",
             "Call 343, my bad, 344.",
             must_contain=[r"344"], must_not_contain=[r"343"])
check_mobile("'oops' collapses (was missing from mobile's cue list)",
             "Meet at 3, oops, 4.",
             must_contain=[r"\b4\b|four"], must_not_contain=[r"\b3\b(?!\s*(pm|am|:))|three"])
check_mobile("'I meant' collapses (was missing from mobile's cue list)",
             "Ticket 343, I meant 344.",
             must_contain=[r"344"], must_not_contain=[r"343"])
check_mobile("'rather' collapses (was missing from mobile's cue list)",
             "Extension 202, rather 203.",
             must_contain=[r"203"], must_not_contain=[r"202"])
check_mobile("'make that' collapses given a prior same-kind value (was missing from mobile)",
             "Let's meet Monday, make that Tuesday.",
             must_contain=[r"Tuesday"], must_not_contain=[r"Monday"])
check_mobile("'strike that' collapses (was missing from mobile's cue list)",
             "File it under ABC123, strike that, ABC124.",
             must_contain=[r"ABC ?124"], must_not_contain=[r"ABC ?123"])
check_mobile("'uh no' false-start collapses (was missing from mobile's cue list)",
             "Call 343, uh no, 344.",
             must_contain=[r"344"], must_not_contain=[r"343"])
check_mobile("'hang on' collapses (was missing from mobile's cue list)",
             "Meet at 3, hang on, 4.",
             must_contain=[r"\b4\b|four"], must_not_contain=[r"\b3\b(?!\s*(pm|am|:))|three"])
check_mobile("Hindi 'arre' collapses (was missing from mobile's cue list)",
             "Ticket 343, arre, 344.",
             must_contain=[r"344"], must_not_contain=[r"343"])
check_mobile("'and'+immediate-cue carve-out (was relied on but unencoded on mobile)",
             "Today ticket 343 and sorry 344.",
             must_contain=[r"344"], must_not_contain=[r"343"])
check_mobile("bare adjacent numbers still never collapse (identifiers stay conservative)",
             "Please call 343, 344 today.",
             must_contain=[r"343", r"344"], must_not_contain=[])
check_mobile("directionality reversed phrasing still collapses",
             "It's 344, not 343.",
             must_contain=[r"344"], must_not_contain=[r"343"])
check_mobile("tight adjacency still required (non-adjacent values never collapse)",
             "Ticket 343 has been open for a while now and needs review soon, also check 344.",
             must_contain=[r"343", r"344"], must_not_contain=[])


# ── summary ───────────────────────────────────────────────────────────────────────
all_green = _failed == 0
print(f"\ntotal={_total} passed={_passed} failed={_failed} ALL_GREEN={all_green}")
sys.exit(0 if all_green else 1)
