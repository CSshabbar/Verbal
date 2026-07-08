#!/usr/bin/env python3
"""
A9 — Adversarial QA fixtures for app/autolearn.py (mic-free, AX-free).

Covers the FULL §0 acceptance matrix and EVERY §4 failure scenario as a
negative test, plus alignment-correctness and anti-false-attribution/memory
guards. Tries HARD to break classify()/align().

Run:
  /Users/muhammadshabbar/Work/Verbal/whisperflow/.venv/bin/python \
      /Users/muhammadshabbar/Work/Verbal/whisperflow/autolearn_fixtures.py

Each fixture prints PASS/FAIL. Final line:
  total=N passed=P failed=F ALL_GREEN=bool
HOLES (behavior that PASSES the fixture but is semantically wrong per spec)
are printed after the summary.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import autolearn as al  # noqa: E402

# ── tiny test harness ────────────────────────────────────────────────────────
_results = []   # (name, passed, detail)
_holes = []     # human-readable hole notes


def record(name, passed, detail=""):
    _results.append((name, passed, detail))
    tag = "PASS" if passed else "FAIL"
    line = "[%s] %s" % (tag, name)
    if detail:
        line += "  --  " + detail
    print(line)


def hole(note):
    _holes.append(note)


def check_classify(name, t, e, expect_action, cfg=None, want_substr=None,
                   want_old=None, want_new=None, is_hole=None):
    """Assert classify(t,e,cfg).action == expect_action (+ optional fields)."""
    cfg = {} if cfg is None else cfg
    try:
        d = al.classify(t, e, cfg)
    except Exception as ex:  # never allowed to raise
        record(name, False, "RAISED %r" % ex)
        return None
    ok = d.get("action") == expect_action
    detail = "action=%s (want %s) reason=%r" % (
        d.get("action"), expect_action, d.get("reason"))
    if ok and want_substr is not None:
        ok = want_substr.lower() in (d.get("reason") or "").lower()
        if not ok:
            detail = "reason %r missing %r" % (d.get("reason"), want_substr)
    if ok and want_old is not None and d.get("old") != want_old:
        ok = False
        detail = "old=%r want %r" % (d.get("old"), want_old)
    if ok and want_new is not None and d.get("new") != want_new:
        ok = False
        detail = "new=%r want %r" % (d.get("new"), want_new)
    record(name, ok, detail)
    if ok and is_hole:
        hole(is_hole)
    return d


def check_align(name, t, e, expect_types, expect_subs=None):
    """Assert the sequence of op types (and optional #substitutions)."""
    try:
        ops, ratio = al.align(al.tokenize(t), al.tokenize(e))
    except Exception as ex:
        record(name, False, "RAISED %r" % ex)
        return
    types = [o["type"] for o in ops]
    ok = types == expect_types
    detail = "ops=%s (want %s)" % (types, expect_types)
    if ok and expect_subs is not None:
        n = sum(1 for o in ops if o["type"] == "substitute")
        ok = n == expect_subs
        if not ok:
            detail = "subs=%d want %d" % (n, expect_subs)
    record(name, ok, detail)


def check(name, cond, detail=""):
    record(name, bool(cond), detail)


# ══════════════════════════════════════════════════════════════════════════════
# §0 MATRIX — the positive/negative acceptance cases
# ══════════════════════════════════════════════════════════════════════════════

# 1. canonical single-word mis-transcription → OFFER
check_classify("s0.1 single-word mis-transcription (Shabar->Shabbar)",
               "meeting with Shabar", "meeting with Shabbar",
               "offer", want_old="Shabar", want_new="Shabbar")

# 2a. proper-noun / capitalization fix, single token → OFFER (low value)
check_classify("s0.5a caps fix single token (idiaz->iDiaz)",
               "idiaz", "iDiaz", "offer", want_new="iDiaz")
# 2b. caps fix mid-sentence camelCase → OFFER
check_classify("s0.5b caps fix in sentence (idiaz->iDiaz)",
               "i work at idiaz", "i work at iDiaz", "offer")
# 2c. ALL-CAPS acronym → OFFER
check_classify("s0.5c acronym caps (api->API)",
               "using the api gateway", "using the API gateway", "offer")
# 2d. camelCase brand → OFFER
check_classify("s0.5d camelCase brand (iphone->iPhone)",
               "i love my iphone", "i love my iPhone", "offer")

# 3. deletion of extra/hallucinated word → IGNORE
check_classify("s0.2 deletion extra word (the the report)",
               "the the report", "the report", "ignore", want_substr="deletion")
check_classify("s0.2b deletion mid-sentence (I saw the cat -> I saw cat)",
               "I saw the cat", "I saw cat", "ignore", want_substr="deletion")

# 4. insertion of a new word → IGNORE
check_classify("s0.3 insertion new word (send report -> send the report)",
               "send report", "send the report", "ignore", want_substr="insertion")

# 5. rephrase whole clause → IGNORE
check_classify("s0.4 rephrase clause",
               "can you do it", "would you handle this",
               "ignore", want_substr="multiple words")

# 6. homophone their/there → IGNORE (common word)
check_classify("s0.6a homophone their->there",
               "going to their house", "going to there house",
               "ignore", want_substr="common english word")
check_classify("s0.6b homophone there->their",
               "i went to there house", "i went to their house",
               "ignore", want_substr="common english word")
check_classify("s0.6c homophone to->too",
               "i want to go", "i want too go",
               "ignore", want_substr="common english word")

# 7. common-word typo teh->the → IGNORE
check_classify("s0.7 common-word typo (teh->the)",
               "teh report is ready", "the report is ready",
               "ignore", want_substr="common english word")

# 8. case/punct-only on a common word → IGNORE ; pure punctuation → IGNORE
check_classify("s0.8a case+punct only common word (hello world -> Hello, world.)",
               "hello world", "Hello, world.", "ignore")
check_classify("s0.8b pure punctuation only (no word change)",
               "hello world", "hello world!", "ignore",
               want_substr="no word-level change")

# ══════════════════════════════════════════════════════════════════════════════
# §4 FAILURE TABLE — every scenario as a negative test
# ══════════════════════════════════════════════════════════════════════════════

# F1 deletion mistaken for correction (core worry) — already covered s0.2; add
# an adversarial deletion that leaves a near-neighbor word.
check_classify("F1 deletion not correction (very very good -> very good)",
               "that is very very good", "that is very good",
               "ignore", want_substr="deletion")

# F5 multiple simultaneous edits → >1 substitution → IGNORE
check_classify("F5 two substitutions (rephrase-ish)",
               "the quick brown fox", "the slow brown cat",
               "ignore", want_substr="multiple words")

# F6 word occurs multiple times — pairing must not create a false substitution
# on the untouched instance. "the the report" already tests dup-delete; add a
# repeated-word substitution where only one copy changes.
check_classify("F6 repeated word, one capitalized (buffalo buffalo)",
               "buffalo buffalo", "buffalo Buffalo", "offer")

# F7 homophone (their/there) — covered in s0.6. Add non-listed-but-common trap.
check_classify("F7 homophone to/too/two",
               "me too please", "me two please",
               "ignore", want_substr="common english word")

# F10 OS autocorrect mangling — valid term -> unrelated word. Phonetic+ortho
# gate should reject on its own (kubectl -> Nutell).
check_classify("F10a autocorrect mangle rejected by gate (kubectl->Nutell)",
               "deploy with kubectl", "deploy with Nutell",
               "ignore", want_substr="not phonetically")

# F10b timing guard: a change that WOULD be offered, but arrives <300ms after
# insert with NO keystrokes → downgraded to ignore.
_d = al.classify("meeting with Shabar", "meeting with Shabbar", {})
_dg = al.apply_observation_guard(_d, keystrokes_observed=False, ms_since_insert=120)
check("F10b timing guard downgrades system change",
      _d["action"] == "offer" and _dg["action"] == "ignore",
      "base=%s guarded=%s reason=%r" % (_d["action"], _dg["action"],
                                        _dg.get("reason")))
# F10c same change WITH keystrokes observed → NOT downgraded (real edit).
_dk = al.apply_observation_guard(_d, keystrokes_observed=True, ms_since_insert=120)
check("F10c timing guard keeps user edit (keystrokes seen)",
      _dk["action"] == "offer", "guarded=%s" % _dk["action"])
# F10d late change with no keystrokes (>300ms) → NOT downgraded.
_dl = al.apply_observation_guard(_d, keystrokes_observed=False, ms_since_insert=5000)
check("F10d timing guard keeps late change (>300ms)",
      _dl["action"] == "offer", "guarded=%s" % _dl["action"])

# F9 declined-word memory — never re-offer after decline.
_cfg_declined = {}
al.record_declined(_cfg_declined, "Shabbar")
check_classify("F9a declined word suppressed (Shabbar)",
               "meeting with Shabar", "meeting with Shabbar",
               "ignore", cfg=_cfg_declined, want_substr="declined")
# record_offered is the same memory (offered==suppress).
_cfg_offered = {}
al.record_offered(_cfg_offered, "iDiaz")
check_classify("F9b offered word suppressed (case-insensitive)",
               "at idiaz", "at iDiaz",
               "ignore", cfg=_cfg_offered, want_substr="declined")
# is_declined is case-insensitive both directions.
check("F9c is_declined case-insensitive",
      al.is_declined(_cfg_declined, "shabbar") and
      al.is_declined(_cfg_declined, "SHABBAR"))
check("F9d is_declined false for unknown word",
      not al.is_declined(_cfg_declined, "Zephyr"))

# F14 config write race — record_declined with a failing save_fn must not raise
# and must still update the in-memory list.
def _boom(_):
    raise RuntimeError("disk full")
_cfg_race = {}
try:
    al.record_declined(_cfg_race, "Ozymandias", save_config_fn=_boom)
    check("F14 record_declined swallows save error",
          al.is_declined(_cfg_race, "Ozymandias"))
except Exception as ex:
    record("F14 record_declined swallows save error", False, "RAISED %r" % ex)

# ══════════════════════════════════════════════════════════════════════════════
# ALIGNMENT CORRECTNESS (§3 align) — repeated words, positions, op shapes
# ══════════════════════════════════════════════════════════════════════════════

check_align("align dup word -> single delete, no substitute",
            "the the report", "the report",
            ["delete", "match", "match"], expect_subs=0)
check_align("align clean single substitution",
            "meeting with Shabar", "meeting with Shabbar",
            ["match", "match", "substitute"], expect_subs=1)
check_align("align pure insertion",
            "send report", "send the report",
            ["match", "insert", "match"], expect_subs=0)
check_align("align repeated word only 2nd changes",
            "buffalo buffalo", "buffalo Buffalo",
            ["match", "substitute"], expect_subs=1)
check_align("align mid-sentence deletion",
            "I saw the cat", "I saw cat",
            ["match", "match", "delete", "match"], expect_subs=0)
# alignment must not manufacture a substitution from a swap of two words
_ops, _r = al.align(al.tokenize("alpha beta"), al.tokenize("beta alpha"))
check("align word-swap is 2 subs (not match)",
      sum(1 for o in _ops if o["type"] == "substitute") == 2,
      "ops=%s" % [o["type"] for o in _ops])

# ══════════════════════════════════════════════════════════════════════════════
# LONG-DOC, SMALL REGION (F11)
# ══════════════════════════════════════════════════════════════════════════════
_LONG = ("The quarterly report covers revenue growth across all regions and "
         "highlights the strong performance of our team led by Shabar during "
         "the last fiscal period ending in December")
check_classify("F11a long doc, single proper-noun fix -> OFFER",
               _LONG, _LONG.replace("Shabar", "Shabbar"),
               "offer", want_new="Shabbar")
check_classify("F11b long doc, deletion inside -> IGNORE",
               _LONG, _LONG.replace("led by Shabar ", ""),
               "ignore", want_substr="deletion")
check_classify("F11c long doc, two words changed -> IGNORE",
               _LONG,
               _LONG.replace("Shabar", "Shabbar").replace("revenue", "profit"),
               "ignore", want_substr="multiple words")
check_classify("F11d long doc, insertion inside -> IGNORE",
               _LONG, _LONG.replace("led by", "led again by"),
               "ignore", want_substr="insertion")

# ══════════════════════════════════════════════════════════════════════════════
# ROBUSTNESS / EDGE (must never raise; must fail closed)
# ══════════════════════════════════════════════════════════════════════════════
check_classify("edge None,None -> ignore no crash", None, None, "ignore")
check_classify("edge empty inserted -> ignore", "", "hello", "ignore")
check_classify("edge empty edited -> ignore", "hello", "", "ignore")
check_classify("edge punctuation-only tokens -> ignore",
               "Shabar", "!!!", "ignore")
check_classify("edge identical text -> ignore", "same text", "same text",
               "ignore", want_substr="no change")
check_classify("edge whitespace differences only -> ignore",
               "hello   world", "hello world", "ignore")
# config=None must be tolerated
try:
    _dn = al.classify("meeting with Shabar", "meeting with Shabbar", None)
    check("edge config=None tolerated", _dn["action"] == "offer")
except Exception as ex:
    record("edge config=None tolerated", False, "RAISED %r" % ex)

# non-phonetic, non-orthographic single substitution → IGNORE (word swap)
check_classify("adv word swap car->vehicle -> ignore",
               "i have a car", "i have a vehicle",
               "ignore", want_substr="not phonetically")

# mixed insert+delete (no substitution) → IGNORE (mixed)
check_classify("adv mixed insert+delete -> ignore",
               "the cat sat", "a cat ran on",
               "ignore")

# ══════════════════════════════════════════════════════════════════════════════
# ADVERSARIAL HOLE PROBES — these PASS (assert real behavior) but are WRONG
# per spec intent; flagged as holes.
# ══════════════════════════════════════════════════════════════════════════════

# HOLE 1 — F8: the "correction" is itself a typo. classify() cannot tell and
# OFFERS to learn the misspelling. Spec defers F8 to the widget/frequency layer,
# so classify offering is "expected" but semantically a poison risk.
check_classify("HOLE F8 correction-is-a-typo offered (Shabbar->Shabbr)",
               "meeting with Shabbar", "meeting with Shabbr", "offer",
               is_hole=("F8: classify() OFFERS a typo'd 'correction' "
                        "('Shabbar'->'Shabbr'); poison-prevention relies "
                        "entirely on the confirm widget / frequency gate that "
                        "classify() itself does not apply."))

# ACCEPTED LIMITATION (was HOLE 2) — typed typo of a real word. A misspelling
# ('receive'->'recieve') is itself absent from any wordlist, so classify() still
# OFFERS it. This is intentionally left to the confirm widget: the user sees the
# before->after ('receive → recieve') and won't click Add on a typo. Documented,
# not a defect of the classifier.
check_classify("typed-typo still offered — widget is the gate (receive->recieve)",
               "please receive the package", "please recieve the package",
               "offer",
               is_hole=("ACCEPTED: 'recieve' is a misspelling absent from the "
                        "system dictionary, so it passes the common-word filter "
                        "and is OFFERED — the confirm widget (before->after) is "
                        "the intended user gate against learning a typo."))

# FIXED (was HOLE 3) — wordlist now loads the macOS system dictionary (~234k
# words), so ordinary word->word edits between two real English words are
# correctly IGNORED, not offered as vocabulary.
assert len(al.COMMON_WORDS) > 50000, "wordlist too small: %d" % len(al.COMMON_WORDS)
check_classify("real-word edit not offered (cat->bat)",
               "the cat sat", "the bat sat", "ignore")
check_classify("real-word edit not offered (desert->dessert)",
               "my desert was sweet", "my dessert was sweet", "ignore")

# HOLE 4 — §2.2 two-token contiguous proper-noun run is NOT supported. A
# legitimate multi-word name fix ('new york'->'New York') is dropped as
# 'multiple words changed'.
check_classify("HOLE two-word proper noun dropped (new york->New York)",
               "i live in new york", "i live in New York",
               "ignore",
               is_hole=("§2.2 says a <=2-token contiguous run should be "
                        "allowed for names, but len(subs)>1 always rejects; "
                        "'new york'->'New York' is dropped as a rephrase."))

# FIXED (was HOLE 5) — for <=2-token inputs the changed-ratio gate is relaxed,
# but the real-word wordlist now catches single-token swaps between two real
# words: 'flume'->'plume' is IGNORED because 'plume' is a known English word.
check_classify("single-token real-word swap not offered (flume->plume)",
               "flume", "plume", "ignore")

# ── summary ───────────────────────────────────────────────────────────────────
total = len(_results)
passed = sum(1 for _, ok, _ in _results if ok)
failed = total - passed
all_green = failed == 0

print("\n" + "=" * 72)
if failed:
    print("FAILURES:")
    for name, ok, detail in _results:
        if not ok:
            print("  - %s :: %s" % (name, detail))
if _holes:
    print("HOLES (fixture passes, behavior semantically wrong per spec):")
    for h in _holes:
        print("  * " + h)
print("=" * 72)
print("total=%d passed=%d failed=%d ALL_GREEN=%s"
      % (total, passed, failed, all_green))

sys.exit(0 if all_green else 1)
