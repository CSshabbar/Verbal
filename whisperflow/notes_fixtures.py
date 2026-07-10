#!/usr/bin/env python3
"""
Agent F — Adversarial QA fixtures for the Notes v2 enhancement (desktop, pure
logic only; no LLM, no network, no recorder, no disk writes).

Asserts the TESTABLE logic behind NOTES_ENHANCEMENT_SWARM.md:

  • Search ranking            — title beats content, recency breaks ties, flag OFF,
                                conflict copies excluded, raw_content matches.
  • Auto-title                — never overwrites a manually-set title; fills an
                                empty title on the initial dictated save.
  • Structure detection       — the classify/format DECISION (prompt-assembly) and
                                the response PARSER over a corpus of
                                rambling-implied-list / plain-prose / mixed inputs.
                                The live LLM is stubbed; we test what our own code
                                decides and parses (per the task's "stub/inspect the
                                prompt+parser" instruction).
  • audio_segments round-trip — append, read back, absent-field tolerance, dedup
                                UNION, unknown-field preservation on write-back.
  • Cost control (Decision 2) — N edits => exactly ONE cleanup call unless Reformat.
  • Feature flags             — each of the four OFF disables cleanly, editor intact.
  • Sync conflict (Decision 3)— two edits within the window => BOTH kept, never
                                silently discarded; audio UNION on conflict.

The live LLM is never called: app.ai_cleanup.format_note is monkeypatched with a
counting/inspecting stub, save_config is neutralized, and _sync_on() is False so no
HTTP is attempted.

Run:
  /Users/muhammadshabbar/Work/Verbal/whisperflow/.venv/bin/python \
      /Users/muhammadshabbar/Work/Verbal/whisperflow/notes_fixtures.py

Each fixture prints PASS/FAIL. Final line:
  total=N passed=P failed=F ALL_GREEN=bool
HOLES (fixture passes but behavior is semantically limited per spec) print after.
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import ai_cleanup as ac            # noqa: E402
from app import shared_dashboard as sd       # noqa: E402
from app.config import feature_flag          # noqa: E402

# ── tiny test harness (mirrors autolearn_fixtures.py) ─────────────────────────
_results = []   # (name, passed, detail)
_holes = []


def record(name, passed, detail=""):
    _results.append((name, passed, bool(passed) and "" or detail))
    tag = "PASS" if passed else "FAIL"
    line = "[%s] %s" % (tag, name)
    if detail and not passed:
        line += "  --  " + detail
    print(line)


def check(name, cond, detail=""):
    record(name, bool(cond), detail)


def hole(note):
    _holes.append(note)


# ── environment isolation: no disk, no network ────────────────────────────────
# _save_local_notes -> save_config would touch the real user config file. Neuter it.
sd.save_config = lambda *_a, **_k: None


def make_api(config=None):
    """A DashboardApi wired to an in-memory fake app. _sync_on() is False (no
    sync_user_id/sync_enabled) so save_note/fetch_notes never touch the network."""
    cfg = {} if config is None else dict(config)
    cfg.setdefault("notes", list(cfg.get("notes", [])))
    cfg.setdefault("groq_api_keys", ["fake-key"])
    app = types.SimpleNamespace(
        config=cfg, _is_recording=False, _processing=False, recorder=None
    )
    dash = types.SimpleNamespace(app=app)
    return sd.DashboardApi(dash)


class FormatStub:
    """Stand-in for ai_cleanup.format_note. Counts calls, records the flags it was
    invoked with, and returns a deterministic {title, formatted_content}."""

    def __init__(self, title="Auto Title", formatted="FORMATTED", result=True):
        self.calls = 0
        self.last_kwargs = None
        self.last_text = None
        self._title = title
        self._formatted = formatted
        self._result = result

    def __call__(self, text, config, *, structure_detection=True, autotitle=True,
                 timeout=8.0):
        self.calls += 1
        self.last_text = text
        self.last_kwargs = dict(structure_detection=structure_detection,
                                autotitle=autotitle, timeout=timeout)
        if not self._result:
            return None
        return {"title": self._title if autotitle else "",
                "formatted_content": self._formatted}


def install_format_stub(stub):
    """save_note/format_note_with_ai do `from app.ai_cleanup import format_note`
    at call time, so patching the module attribute is sufficient."""
    ac.format_note = stub


# real reference kept so tests that need the true parser still can call it
_REAL_FORMAT_NOTE = ac.format_note


def now_iso(offset_s=0):
    import datetime as _dt
    return (_dt.datetime.now(_dt.timezone.utc)
            + _dt.timedelta(seconds=offset_s)).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# 1. SEARCH RANKING  (Feature 1 / Decision 9)
# ══════════════════════════════════════════════════════════════════════════════

def _mk_note(nid, title="", content="", raw=None, updated=None, extra=None):
    n = {"id": nid, "title": title, "content": content,
         "raw_content": raw, "audio_segments": [],
         "created_at": updated or now_iso(), "updated_at": updated or now_iso()}
    if extra:
        n.update(extra)
    return n


# title match must rank above a content-only match
_api = make_api()
_api.app.config["notes"] = [
    _mk_note("c", content="the alpha widget is here", updated=now_iso(10)),  # content hit, newer
    _mk_note("t", title="alpha release", content="unrelated", updated=now_iso(0)),  # title hit, older
]
_r = _api.search_notes("alpha")
_ids = [n["id"] for n in _r["notes"]]
check("search title beats content (despite content being newer)",
      _r["ok"] and _ids == ["t", "c"], "order=%s" % _ids)

# recency tiebreak within the SAME rank tier (two title matches)
_api = make_api()
_api.app.config["notes"] = [
    _mk_note("old", title="alpha old", updated=now_iso(0)),
    _mk_note("new", title="alpha new", updated=now_iso(30)),
]
_r = _api.search_notes("alpha")
_ids = [n["id"] for n in _r["notes"]]
check("search recency tiebreak within same tier (newer first)",
      _ids == ["new", "old"], "order=%s" % _ids)

# raw_content is searchable (raw transcript behind a formatted note)
_api = make_api()
_api.app.config["notes"] = [
    _mk_note("r", title="Meeting", content="formatted body",
             raw="we discussed the zephyr project at length"),
]
_r = _api.search_notes("zephyr")
check("search matches raw_content", [n["id"] for n in _r["notes"]] == ["r"],
      "ids=%s" % [n["id"] for n in _r["notes"]])

# non-matching query returns nothing (no results)
_r = _api.search_notes("nonexistentxyz")
check("search no-results returns empty list", _r["notes"] == [],
      "got=%s" % _r["notes"])

# empty query returns ALL notes (list view, not filtered)
_api = make_api()
_api.app.config["notes"] = [_mk_note("a", title="a"), _mk_note("b", title="b")]
_r = _api.search_notes("")
check("search empty query returns all notes", len(_r["notes"]) == 2)
_r = _api.search_notes("   ")
check("search whitespace-only query returns all notes", len(_r["notes"]) == 2)

# case-insensitive
_api = make_api()
_api.app.config["notes"] = [_mk_note("x", title="Quarterly REVENUE report")]
check("search case-insensitive",
      [n["id"] for n in _api.search_notes("revenue")["notes"]] == ["x"])

# conflict copies are internal — never surfaced as search hits
_api = make_api()
_api.app.config["notes"] = [
    _mk_note("n", title="alpha canonical"),
    _mk_note("n::conflict::2020", title="alpha conflict copy"),
]
_r = _api.search_notes("alpha")
check("search excludes ::conflict:: copies",
      [n["id"] for n in _r["notes"]] == ["n"],
      "ids=%s" % [n["id"] for n in _r["notes"]])

# empty query ALSO excludes conflict copies from the list surface
_r = _api.search_notes("")
check("search empty-query list excludes ::conflict:: copies",
      [n["id"] for n in _r["notes"]] == ["n"])

# feature flag OFF -> search disabled cleanly: returns ALL (minus conflict copies),
# ignoring the query, never raising.
_api = make_api({"notes_search_enabled": False})
_api.app.config["notes"] = [
    _mk_note("a", title="apple"), _mk_note("b", title="banana"),
    _mk_note("z::conflict::1", title="apple copy"),
]
_r = _api.search_notes("apple")
check("search flag OFF returns all real notes unfiltered",
      _r["ok"] and sorted(n["id"] for n in _r["notes"]) == ["a", "b"],
      "ids=%s" % [n["id"] for n in _r["notes"]])


# ══════════════════════════════════════════════════════════════════════════════
# 2. AUTO-TITLE  (Feature 2 — never overwrite a manual title)
# ══════════════════════════════════════════════════════════════════════════════

# initial dictated save with EMPTY title -> auto-title fills it
stub = FormatStub(title="Grocery Run", formatted="- [ ] milk")
install_format_stub(stub)
_api = make_api()
_res = _api.save_note({"raw_content": "buy milk and eggs", "title": "", "content": ""})
_saved = _res["notes"][0]
check("autotitle fills empty title on initial dictated save",
      stub.calls == 1 and _saved["title"] == "Grocery Run",
      "calls=%d title=%r" % (stub.calls, _saved["title"]))
check("initial dictated save stores formatted content",
      _saved["content"] == "- [ ] milk", "content=%r" % _saved["content"])
check("initial dictated save preserves raw_content",
      _saved["raw_content"] == "buy milk and eggs")

# initial dictated save with a MANUAL title -> title preserved, never overwritten
stub = FormatStub(title="AI Chosen Title", formatted="body")
install_format_stub(stub)
_api = make_api()
_res = _api.save_note({"raw_content": "some dictation",
                       "title": "My Manual Title", "content": ""})
check("autotitle NEVER overwrites a manually-set title",
      _res["notes"][0]["title"] == "My Manual Title",
      "title=%r" % _res["notes"][0]["title"])

# autotitle flag OFF -> no title applied even though cleanup runs; format_note
# invoked with autotitle=False.
stub = FormatStub(title="Should Not Apply", formatted="body")
install_format_stub(stub)
_api = make_api({"notes_autotitle_enabled": False})
_res = _api.save_note({"raw_content": "dictation text", "title": "", "content": ""})
check("autotitle flag OFF -> title stays empty",
      _res["notes"][0]["title"] == "" and
      stub.last_kwargs["autotitle"] is False,
      "title=%r kwargs=%s" % (_res["notes"][0]["title"], stub.last_kwargs))

install_format_stub(_REAL_FORMAT_NOTE)  # restore between sections


# ══════════════════════════════════════════════════════════════════════════════
# 3. STRUCTURE DETECTION — the DECISION (prompt-assembly) + PARSER over a corpus
#    (live LLM stubbed; we test our own classify/format decision and parser)
# ══════════════════════════════════════════════════════════════════════════════

# 3a. prompt-assembly decision: the structure-detection rule is present iff the flag
#     is on; the title instruction is present iff autotitle is on. This is the code
#     that "decides" whether the LLM is even instructed to build a checklist.
_p_on = ac.build_notes_system_prompt(structure_detection=True, autotitle=True)
_p_off = ac.build_notes_system_prompt(structure_detection=False, autotitle=False)
check("prompt includes checklist rule when structure flag ON",
      "- [ ] item" in _p_on)
check("prompt OMITS checklist rule when structure flag OFF",
      "- [ ] item" not in _p_off)
check("prompt includes TITLE instruction when autotitle ON",
      "TITLE:" in _p_on)
check("prompt OMITS TITLE instruction when autotitle OFF",
      "TITLE:" not in _p_off)
# the structure rule always carries base formatter rules (never dropped)
check("base formatter rules retained in both prompt variants",
      "NOTE FORMATTER" in _p_on and "NOTE FORMATTER" in _p_off)

# 3b. RESPONSE PARSER over the three corpus shapes. We simulate what the LLM returns
#     for each category and assert the parser routes {title, body} correctly and
#     preserves the markdown shape verbatim.
def _parse(raw, autotitle=True):
    return ac._parse_note_response(raw, autotitle)

# rambling-implied-list -> LLM emits a checklist; parser peels title, keeps items
_d = _parse("TITLE: Errand List\n\n- [ ] buy milk\n- [ ] call dentist\n"
            "- [ ] finish report")
check("parser: implied-list -> title extracted + checklist body preserved",
      _d["title"] == "Errand List"
      and _d["formatted_content"].count("- [ ] ") == 3
      and _d["formatted_content"].startswith("- [ ] buy milk"),
      "d=%r" % _d)

# plain prose -> LLM emits prose (NO checkbox); parser leaves it as prose
_d = _parse("TITLE: Morning Reflection\n\nToday felt calm and productive; "
            "I spent the morning reading by the window.")
check("parser: plain prose stays prose (no checklist injected)",
      _d["title"] == "Morning Reflection"
      and "- [ ]" not in _d["formatted_content"]
      and _d["formatted_content"].startswith("Today felt calm"),
      "d=%r" % _d)

# mixed -> intro prose + checklist; both survive, in order
_d = _parse("TITLE: Launch Plan\n\nHere is what is left before we ship:\n\n"
            "- [ ] finalize copy\n- [x] fix the crash\n- [ ] ping design")
check("parser: mixed intro-prose + checklist both preserved in order",
      _d["title"] == "Launch Plan"
      and _d["formatted_content"].startswith("Here is what is left")
      and "- [ ] finalize copy" in _d["formatted_content"]
      and "- [x] fix the crash" in _d["formatted_content"],
      "d=%r" % _d)

# parser robustness
check("parser: no TITLE line -> title empty, whole text is body",
      _parse("just a body line, no title")["title"] == "" and
      _parse("just a body line, no title")["formatted_content"] ==
      "just a body line, no title")
check("parser: autotitle OFF -> TITLE line is NOT peeled (kept in body)",
      _parse("TITLE: X\n\nbody", autotitle=False)["title"] == "" and
      "TITLE: X" in _parse("TITLE: X\n\nbody", autotitle=False)["formatted_content"])
check("parser: strips surrounding quotes from title",
      _parse('TITLE: "Quoted Title"\n\nbody')["title"] == "Quoted Title")
check("parser: case-insensitive TITLE marker",
      _parse("title: lower marker\n\nbody")["title"] == "lower marker")
check("parser: empty/None input -> empty title+body, no raise",
      _parse("")["title"] == "" and _parse(None)["formatted_content"] == "")

hole("Structure detection's ACTUAL classification (is this transcript a list?) is "
     "the live LLM's job and is NOT exercised here — these fixtures verify only "
     "(a) our prompt carries/omits the rule per flag and (b) our parser handles "
     "all three response shapes. A regressed/mis-tuned LLM that returns prose for "
     "an implied list would pass every fixture above. Covered by the spec's "
     "two-week dogfood + corpus-retune step, not by unit tests.")


# ══════════════════════════════════════════════════════════════════════════════
# 4. audio_segments ROUND-TRIP  (Feature 4 / Decisions 3 & 7)
# ══════════════════════════════════════════════════════════════════════════════

# append via save_note (incoming_segments) then read back
install_format_stub(FormatStub())
_api = make_api()
seg1 = {"id": "rec1", "url": "u1", "created_at": now_iso(0)}
_api.save_note({"id": "note1", "title": "t", "content": "c",
                "audio_segments": [seg1]})
_saved = next(n for n in _api._local_notes() if n["id"] == "note1")
check("audio append: segment stored & readable round-trip",
      [s["id"] for s in _saved["audio_segments"]] == ["rec1"],
      "segs=%s" % _saved["audio_segments"])

# append a SECOND segment on a later edit -> UNION, both kept, ordered by created_at
seg2 = {"id": "rec2", "url": "u2", "created_at": now_iso(5)}
_api.save_note({"id": "note1", "title": "t", "content": "c2",
                "audio_segments": [seg2]})
_saved = next(n for n in _api._local_notes() if n["id"] == "note1")
check("audio append: UNION keeps both segments across edits",
      [s["id"] for s in _saved["audio_segments"]] == ["rec1", "rec2"],
      "segs=%s" % [s["id"] for s in _saved["audio_segments"]])

# re-adding the same segment id is idempotent (dedup)
_api.save_note({"id": "note1", "title": "t", "content": "c3",
                "audio_segments": [seg1]})
_saved = next(n for n in _api._local_notes() if n["id"] == "note1")
check("audio append: duplicate id de-duped (idempotent union)",
      [s["id"] for s in _saved["audio_segments"]] == ["rec1", "rec2"])

# absent-field tolerance: a typed edit with no audio_segments must NOT wipe them
_api.save_note({"id": "note1", "title": "typed edit", "content": "c4"})
_saved = next(n for n in _api._local_notes() if n["id"] == "note1")
check("audio absent-field tolerance: edit without segments preserves existing",
      [s["id"] for s in _saved["audio_segments"]] == ["rec1", "rec2"],
      "segs=%s" % [s["id"] for s in _saved["audio_segments"]])

# a typed note (never dictated) shows NO audio -> empty list, not error
_api = make_api()
_api.save_note({"id": "typed", "title": "Plain", "content": "typed body"})
_saved = next(n for n in _api._local_notes() if n["id"] == "typed")
check("typed note has empty audio_segments (no playback control implied)",
      _saved["audio_segments"] == [])

# _union_audio_segments direct: None-tolerant, drops malformed, orders by created_at
_u = sd._union_audio_segments(None, None)
check("union(None,None) -> []", _u == [])
_u = sd._union_audio_segments(
    [{"id": "b", "created_at": "2026-01-02"}],
    [{"id": "a", "created_at": "2026-01-01"}, "GARBAGE", {"no_id": 1}])
check("union drops malformed + orders by created_at",
      [s["id"] for s in _u] == ["a", "b"], "u=%s" % _u)

# _append_audio_segment helper round-trips and is idempotent
_api = make_api()
_api.app.config["notes"] = [_mk_note("n", title="t")]
ok1 = _api._append_audio_segment("n", {"id": "s1", "url": "", "created_at": now_iso()})
ok2 = _api._append_audio_segment("n", {"id": "s1", "url": "", "created_at": now_iso()})
_saved = next(n for n in _api._local_notes() if n["id"] == "n")
check("_append_audio_segment appends once, idempotent on repeat",
      ok1 and ok2 and [s["id"] for s in _saved["audio_segments"]] == ["s1"])
check("_append_audio_segment on missing note -> False (no raise)",
      _api._append_audio_segment("does-not-exist", {"id": "x"}) is False)


# ── unknown-field preservation on write-back (forward-compat, Decision 7) ──────
# merge_remote_note must preserve columns a newer client added, from BOTH sides.
by_id = {"n": {"id": "n", "title": "local", "content": "L",
               "updated_at": now_iso(0), "local_unknown": "keepL"}}
cand = {"id": "n", "title": "remote", "content": "R",
        "updated_at": now_iso(1000), "remote_unknown": "keepR"}
sd.merge_remote_note(by_id, cand)  # >window apart -> LWW, remote newer
merged = by_id["n"]
check("merge preserves BOTH sides' unknown fields (LWW, remote newer)",
      merged.get("local_unknown") == "keepL"
      and merged.get("remote_unknown") == "keepR"
      and merged["content"] == "R",
      "merged=%s" % merged)

# local newer -> local values win but remote unknowns still added
by_id = {"n": {"id": "n", "title": "local", "content": "L",
               "updated_at": now_iso(1000), "local_unknown": "L"}}
cand = {"id": "n", "title": "remote", "content": "R",
        "updated_at": now_iso(0), "remote_unknown": "R"}
sd.merge_remote_note(by_id, cand)
merged = by_id["n"]
check("merge (local newer) keeps local content + adds remote unknown",
      merged["content"] == "L" and merged.get("remote_unknown") == "R",
      "merged=%s" % merged)

# save_note write-back payload path preserves unknown fields verbatim: the known
# set _NOTE_KNOWN_FIELDS drives what is treated as unknown. Verify the guard set.
check("_NOTE_KNOWN_FIELDS covers the v2 columns",
      {"raw_content", "audio_segments", "conflict", "conflict_of"}
      <= sd._NOTE_KNOWN_FIELDS)

# absent audio_segments on a remote row is tolerated by merge (no crash, -> [])
by_id = {"n": _mk_note("n", title="local", updated=now_iso(0))}
sd.merge_remote_note(by_id, {"id": "n", "title": "remote",
                             "updated_at": now_iso(1000)})  # no audio_segments key
check("merge tolerates remote row missing audio_segments",
      by_id["n"]["audio_segments"] == [])


# ══════════════════════════════════════════════════════════════════════════════
# 5. COST CONTROL  (Decision 2) — N edits => exactly ONE cleanup unless Reformat
# ══════════════════════════════════════════════════════════════════════════════

stub = FormatStub(title="T", formatted="FMT")
install_format_stub(stub)
_api = make_api()

# initial dictated save -> ONE cleanup
r = _api.save_note({"id": "cc", "raw_content": "raw transcript here",
                    "title": "", "content": ""})
c_after_initial = stub.calls
check("cost: initial dictated save runs cleanup exactly once",
      c_after_initial == 1, "calls=%d" % c_after_initial)

# five subsequent typed edits (carrying raw_content, but no run_cleanup) -> ZERO more
for i in range(5):
    _api.save_note({"id": "cc", "raw_content": "raw transcript here",
                    "title": "T", "content": "edited body %d" % i})
check("cost: 5 typed edits trigger NO further cleanup",
      stub.calls == c_after_initial, "calls=%d (want %d)" %
      (stub.calls, c_after_initial))

# explicit Reformat (run_cleanup=True) -> exactly ONE more
_api.save_note({"id": "cc", "raw_content": "raw transcript here",
                "title": "T", "content": "body", "run_cleanup": True})
check("cost: explicit Reformat triggers exactly one more cleanup",
      stub.calls == c_after_initial + 1, "calls=%d" % stub.calls)

# a purely typed NEW note (no raw_content) never triggers cleanup
before = stub.calls
_api.save_note({"id": "typed2", "title": "Typed", "content": "hand typed"})
check("cost: typed note (no raw) never triggers cleanup",
      stub.calls == before, "calls delta=%d" % (stub.calls - before))

# run_cleanup control field is NOT persisted onto the note
saved = next(n for n in _api._local_notes() if n["id"] == "cc")
check("cost: run_cleanup control flag not stored on the note",
      "run_cleanup" not in saved)


# ══════════════════════════════════════════════════════════════════════════════
# 6. FEATURE FLAGS — each OFF disables cleanly without breaking the editor
# ══════════════════════════════════════════════════════════════════════════════

# defaults: absent flag -> True; explicit False -> False; malformed -> default True
check("flag default True when absent", feature_flag({}, "notes_search_enabled"))
check("flag explicit False respected",
      feature_flag({"notes_search_enabled": False}, "notes_search_enabled") is False)
check("flag malformed value falls back to default True",
      feature_flag({"notes_search_enabled": "yes"}, "notes_search_enabled") is True)

# search OFF already covered above (returns all). autotitle OFF covered above.
# structure OFF -> format_note called with structure_detection=False, editor still saves.
stub = FormatStub(title="T", formatted="FMT")
install_format_stub(stub)
_api = make_api({"notes_structure_detection_enabled": False})
r = _api.save_note({"id": "s", "raw_content": "raw here", "title": "", "content": ""})
check("flag structure OFF -> cleanup runs with structure_detection=False, save ok",
      stub.last_kwargs["structure_detection"] is False and r["ok"]
      and r["notes"][0]["content"] == "FMT",
      "kwargs=%s" % stub.last_kwargs)

# audio-linkage OFF -> note_dictate_stop transcribes but attaches NO segment.
# Stub the transcriber + process_text; audio-linkage branch must be skipped.
import app.transcriber as _tr        # noqa: E402
_tr.transcribe_with_status = lambda audio, cfg, sr: ("hello world", "ok")
ac.process_text = lambda text, cfg: text

class _FakeRec:
    sample_rate = 16000
    def start(self):  # noqa: E301
        return True
    def stop(self):   # noqa: E301
        return object()   # non-None "audio"

_api = make_api({"notes_audio_linkage_enabled": False})
_api.app.recorder = _FakeRec()
res = _api.note_dictate_stop(note_id="whatever")
check("flag audio-linkage OFF -> dictation transcribes but attaches no segment",
      res["ok"] and res.get("text") == "hello world" and "segment" not in res,
      "res=%s" % res)

# audio-linkage ON -> a segment IS produced (persistence stubbed on the instance)
_api = make_api({"notes_audio_linkage_enabled": True})
_api.app.recorder = _FakeRec()
_seg = {"id": "recX", "url": "", "created_at": now_iso()}
_api._persist_note_recording = lambda audio, sr, nid=None: _seg
res = _api.note_dictate_stop(note_id=None)
check("flag audio-linkage ON -> dictation returns an attached segment",
      res["ok"] and res.get("segment") == _seg, "res=%s" % res)

install_format_stub(_REAL_FORMAT_NOTE)


# ══════════════════════════════════════════════════════════════════════════════
# 7. SYNC CONFLICT  (Decision 3) — two edits within window => BOTH kept
# ══════════════════════════════════════════════════════════════════════════════

base_t = now_iso(0)
# local & remote diverge, edited 20s apart (< 60s window) -> conflict pair
by_id = {"n": {"id": "n", "title": "Local title", "content": "LOCAL body",
               "updated_at": base_t, "audio_segments": [{"id": "segL"}]}}
cand = {"id": "n", "title": "Remote title", "content": "REMOTE body",
        "updated_at": now_iso(20), "audio_segments": [{"id": "segR"}]}
sd.merge_remote_note(by_id, cand)
canonical = by_id.get("n")
copies = [k for k in by_id if "::conflict::" in k]
check("conflict: BOTH versions kept (canonical + one ::conflict:: copy)",
      canonical is not None and len(copies) == 1, "keys=%s" % list(by_id))
check("conflict: canonical flagged conflict=True, conflict_of=None",
      canonical.get("conflict") is True and canonical.get("conflict_of") is None)
if copies:
    copy = by_id[copies[0]]
    check("conflict: copy flagged conflict=True, conflict_of=<canonical id>",
          copy.get("conflict") is True and copy.get("conflict_of") == "n")
    check("conflict: newer edit wins the canonical slot",
          canonical.get("content") == "REMOTE body",
          "content=%r" % canonical.get("content"))
    check("conflict: canonical audio_segments UNION both devices' segments",
          sorted(s["id"] for s in canonical.get("audio_segments", []))
          == ["segL", "segR"],
          "segs=%s" % canonical.get("audio_segments"))
else:
    check("conflict: copy flagged conflict=True, conflict_of=<canonical id>",
          False, "no conflict copy created")
    check("conflict: newer edit wins the canonical slot", False, "n/a")
    check("conflict: canonical audio_segments UNION both devices' segments",
          False, "n/a")

# conflict pair is IDEMPOTENT across repeated fetches (deterministic copy id)
sd.merge_remote_note(by_id, cand)
copies2 = [k for k in by_id if "::conflict::" in k]
check("conflict: re-merging same remote is idempotent (no duplicate copies)",
      len(copies2) == 1, "copies=%s" % copies2)

# edits > window apart -> NO conflict, last-write-wins (no silent-loss worry: older
# simply loses, which is acceptable outside the window per spec)
by_id = {"n": {"id": "n", "title": "A", "content": "old",
               "updated_at": now_iso(0)}}
sd.merge_remote_note(by_id, {"id": "n", "title": "B", "content": "new",
                             "updated_at": now_iso(1000)})
check("no conflict when edits are > window apart (LWW)",
      by_id["n"]["content"] == "new"
      and not any("::conflict::" in k for k in by_id),
      "keys=%s" % list(by_id))

# within window but IDENTICAL user-meaningful fields -> NOT a conflict
by_id = {"n": {"id": "n", "title": "same", "content": "same",
               "raw_content": "same", "updated_at": now_iso(0)}}
sd.merge_remote_note(by_id, {"id": "n", "title": "same", "content": "same",
                             "raw_content": "same", "updated_at": now_iso(10)})
check("within window but no divergence -> NOT flagged as conflict",
      not any("::conflict::" in k for k in by_id)
      and by_id["n"].get("conflict") is not True,
      "keys=%s conflict=%s" % (list(by_id), by_id["n"].get("conflict")))

# _notes_conflict direct: missing timestamps -> not a conflict (fail closed)
check("_notes_conflict: missing timestamps -> False",
      sd._notes_conflict({"content": "a"}, {"content": "b"}) is False)

# merge on an all-new remote id just inserts it
by_id = {}
sd.merge_remote_note(by_id, {"id": "fresh", "title": "New"})
check("merge inserts a brand-new remote note", by_id.get("fresh") is not None)

# merge tolerates a remote row with no id (no raise, no insert)
by_id = {}
sd.merge_remote_note(by_id, {"title": "no id"})
check("merge tolerates remote row missing id (no raise, no insert)", by_id == {})


# ══════════════════════════════════════════════════════════════════════════════
# 8. FIRST-RUN / EDGE (Decision 5 & 6) — never break the editor, fail closed
# ══════════════════════════════════════════════════════════════════════════════

# a pre-existing note (raw_content None, audio_segments absent) edits normally and
# is NOT retroactively cleaned (no raw -> no cleanup).
stub = FormatStub()
install_format_stub(stub)
_api = make_api()
_api.app.config["notes"] = [{"id": "pre", "title": "Legacy", "content": "old body",
                             "created_at": now_iso(-9999), "updated_at": now_iso(-9999)}]
r = _api.save_note({"id": "pre", "title": "Legacy", "content": "edited old body"})
check("first-run: pre-existing note edits without triggering cleanup",
      stub.calls == 0 and r["notes"][0]["content"] == "edited old body")

# cleanup FAILURE (format_note returns None) -> raw saved, content stays empty so
# the UI can show "Retry formatting"; never raises.
install_format_stub(FormatStub(result=None))
_api = make_api()
r = _api.save_note({"id": "f", "raw_content": "raw only", "title": "", "content": ""})
saved = r["notes"][0]
check("cleanup failure: raw preserved, formatted content empty (Retry path)",
      saved["raw_content"] == "raw only" and (saved["content"] or "") == "",
      "content=%r raw=%r" % (saved["content"], saved["raw_content"]))

# save_note tolerates None / empty input without raising
_api = make_api()
r = _api.save_note(None)
check("save_note(None) does not raise and returns ok", r.get("ok") is True)

install_format_stub(_REAL_FORMAT_NOTE)


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
    print("HOLES (fixture passes, behavior semantically limited per spec):")
    for h in _holes:
        print("  * " + h)
print("=" * 72)
print("total=%d passed=%d failed=%d ALL_GREEN=%s"
      % (total, passed, failed, all_green))

sys.exit(0 if all_green else 1)
