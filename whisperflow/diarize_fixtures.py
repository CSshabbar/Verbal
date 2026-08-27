"""Pure-logic fixtures for meetings.map_diarized_speakers — the overlap mapping that
turns AssemblyAI's who-spoke-when into the transcript's speaker ids.

No network, no audio: the mapping is a pure function precisely so these can pin its
rules. Follows the repo convention: top-level check(), exit 1 unless ALL_GREEN.
"""
import sys

from app.meetings import (map_diarized_speakers, split_utterances_by_turns,
                          apply_speaker_names, _parse_summary_json as parse_summary_json)

RESULTS = []


def check(name, cond):
    RESULTS.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name)


def U(spk, t0, t1, text="x"):
    return {"speaker": spk, "t0": t0, "t1": t1, "text": text}


def D(spk, s, e):
    return {"speaker": spk, "start": float(s), "end": float(e)}


# ── the reported failure: two people in conversation, no 90s gaps ─────────────
# The gap heuristic labelled everything s1; diarization sees A and B alternating.
tr = [U("s1", 0, 5), U("s1", 6, 10), U("s1", 11, 15), U("s1", 16, 20)]
dz = [D("A", 0, 5), D("B", 6, 10), D("A", 11, 15), D("B", 16, 20)]
ids, hint = map_diarized_speakers(tr, dz)
check("alternating pair splits into s1/s2", ids == ["s1", "s2", "s1", "s2"])
check("majority hint points old s1 at a new id", hint.get("s1") in ("s1", "s2"))

# ── first-appearance ordering: ids stay familiar ──────────────────────────────
tr = [U("s1", 0, 5), U("s1", 6, 10)]
dz = [D("Z", 0, 5), D("Q", 6, 10)]
ids, _ = map_diarized_speakers(tr, dz)
check("new ids are s1,s2 by first appearance (not vendor letters)", ids == ["s1", "s2"])

# ── self is ground truth ──────────────────────────────────────────────────────
tr = [U("self", 0, 5), U("s1", 6, 10)]
dz = [D("A", 0, 5), D("B", 6, 10)]
ids, _ = map_diarized_speakers(tr, dz)
check("self never relabelled", ids[0] == "self")
check("system utterance still mapped", ids[1] == "s1")

# ── the user's own cluster is excluded, not surfaced as a phantom speaker ─────
# Cluster A overlaps mostly self (it IS the user, heard in the mixdown);
# a system utterance overlapping A more than B must NOT become a new speaker of A.
tr = [U("self", 0, 10), U("self", 20, 30), U("s1", 40, 50)]
dz = [D("A", 0, 10), D("A", 20, 30), D("A", 40, 44), D("B", 44, 50)]
ids, _ = map_diarized_speakers(tr, dz)
check("self-cluster excluded from system mapping", ids[2] == "s1")
# B overlaps 6s of the 10s utterance (>=30%) -> should win and become s1:
check("...and the non-self cluster still maps it", ids[2] == "s1")

# ── weak overlap keeps the old label (never merge on a murky signal) ──────────
tr = [U("s1", 0, 10)]
dz = [D("A", 9, 10)]           # 10% overlap only
ids, _ = map_diarized_speakers(tr, dz)
check("overlap under 30% keeps the old id", ids == ["s1"])

# ── threshold boundary: exactly 30% counts ────────────────────────────────────
tr = [U("s1", 0, 10)]
dz = [D("A", 7, 10)]           # 3s of 10s = 30%
ids, _ = map_diarized_speakers(tr, dz)
check("overlap at exactly 30% maps", ids == ["s1"] and True)  # mapped to alias s1

# ── one real speaker stays one speaker ────────────────────────────────────────
tr = [U("s1", 0, 5), U("s2", 200, 205)]   # gap heuristic over-split a long pause
dz = [D("A", 0, 5), D("A", 200, 205)]
ids, _ = map_diarized_speakers(tr, dz)
check("gap-split of one person is merged back", ids == ["s1", "s1"])

# ── fail-closed shapes ────────────────────────────────────────────────────────
ids, hint = map_diarized_speakers([], [D("A", 0, 1)])
check("empty transcript -> empty", ids == [] and hint == {})
tr = [U("s1", 0, 5)]
ids, hint = map_diarized_speakers(tr, [])
check("no diarization -> ids unchanged", ids == ["s1"] and hint == {})
ids, _ = map_diarized_speakers([{"speaker": "s1"}], [D("A", 0, 1)])   # missing t0/t1
check("malformed utterance never raises", isinstance(ids, list))

# ── three-way meeting ─────────────────────────────────────────────────────────
tr = [U("self", 0, 4), U("s1", 5, 9), U("s1", 10, 14), U("s1", 15, 19)]
dz = [D("ME", 0, 4), D("A", 5, 9), D("B", 10, 14), D("C", 15, 19)]
ids, _ = map_diarized_speakers(tr, dz)
check("three remote speakers found where the gap heuristic saw one",
      ids == ["self", "s1", "s2", "s3"])

# ── self-cluster needs a CLEAR majority (2026-08-27) ─────────────────────────
# Cluster A: 10s on self, 8s on a system utterance (55% self). Under the old
# plurality rule A was "the user" and the remote person talking over them vanished.
tr = [U("self", 0, 10), U("s1", 20, 28), U("s1", 30, 40)]
dz = [D("A", 0, 10), D("A", 20, 28), D("B", 30, 40)]
ids, _ = map_diarized_speakers(tr, dz)
check("55%-self cluster is NOT excluded (remote talker survives)", ids[1] != ids[2] and ids[1] != "self")
tr = [U("self", 0, 30), U("s1", 40, 44), U("s1", 50, 60)]
dz = [D("A", 0, 30), D("A", 40, 44), D("B", 50, 60)]
ids, _ = map_diarized_speakers(tr, dz)
check("88%-self cluster IS excluded (no phantom user)", ids[1] == "s1" and ids[2] == "s1")

# ── turn splitting from per-word timestamps ───────────────────────────────────
def W(t0, *pairs):
    """pairs: (word, dur) sequential from t0 → [[w, s, e], ...]"""
    out, t = [], float(t0)
    for w, d in pairs:
        out.append([w, round(t, 2), round(t + d, 2)]); t += d
    return out

# One 20s Groq chunk holding two people: A 0-9s, B 9-20s.
u = dict(U("s1", 0, 20, "sounds good to me. great so next week we ship"),
         words=W(0, ("sounds",2),("good",2),("to",2),("me.",3),("great",2),("so",2),("next",2),("week",2),("we",1.5),("ship",1.5)))
dz = [D("A", 0, 9), D("B", 9, 20)]
parts = split_utterances_by_turns([u], dz)
check("chunk splits into two turns", len(parts) == 2)
check("split text is partitioned at the turn boundary",
      parts[0]["text"] == "sounds good to me." and parts[1]["text"] == "great so next week we ship")
check("first part keeps chunk t0, last keeps chunk t1", parts[0]["t0"] == 0 and parts[1]["t1"] == 20)
check("words key is consumed", all("words" not in p for p in parts))
ids, _ = map_diarized_speakers(parts, dz)
check("...and then maps to two different speakers", ids == ["s1", "s2"])

# Third participant who only interjects inside someone else's chunk
u = dict(U("s1", 0, 12, "so the plan is yes exactly and then we go"),
         words=W(0, ("so",1),("the",1),("plan",1),("is",1),("yes",1),("exactly",1),("and",1),("then",1),("we",2),("go",2)))
dz = [D("A", 0, 4), D("C", 4, 6), D("A", 6, 12)]
parts = split_utterances_by_turns([u], dz)
ids, _ = map_diarized_speakers(parts, dz)
check("interjecting third voice survives as its own turn", len(parts) == 3 and ids == ["s1", "s2", "s1"])

# No words → passthrough; self → passthrough; no dz → passthrough (minus words)
parts = split_utterances_by_turns([U("s1", 0, 10)], dz)
check("utterance without words passes through", parts == [U("s1", 0, 10)])
u = dict(U("self", 0, 10), words=W(0, ("a",5),("b",5)))
check("self never split", split_utterances_by_turns([u], [D("A",0,5),D("B",5,10)])[0]["speaker"] == "self")
u = dict(U("s1", 0, 10), words=W(0, ("a",5),("b",5)))
check("no diarization → unchanged text, words stripped",
      split_utterances_by_turns([u], [])[0] == U("s1", 0, 10))
check("garbage never raises", isinstance(split_utterances_by_turns([{"speaker":"s1","words":"x"}], dz), list))

# Single-speaker chunk with words: no split, original text kept verbatim
u = dict(U("s1", 0, 10, "Hello, there."), words=W(0, ("Hello,",5),("there.",5)))
check("single-turn chunk keeps original text", split_utterances_by_turns([u], [D("A",0,10)])[0]["text"] == "Hello, there.")

# ── transcript-derived names ──────────────────────────────────────────────────
raw = ('{"summary":"Speaker 2 will draft the plan.","decisions":["Speaker 2 owns rollout"],'
       '"action_items":[{"owner":"s2","task":"Speaker 2 drafts plan","due":null}],"hybrid_notes":[],'
       '"speaker_names":{"s2":"Sara","s1":"Speaker 4","self":"Bob","s3":"O\'Neil 3","s9":"sara"}}')
parsed = parse_summary_json(raw)
check("only valid names parsed (no self, no placeholders, no digits, unique)", parsed["speaker_names"] == {"s2": "Sara"})
spk = {"self": "You", "s1": "Marco", "s2": "Speaker 2"}
renamed = apply_speaker_names(spk, {"s2": "Sara", "s1": "Luis"}, parsed)
check("placeholder renamed, user-set name untouched", spk == {"self": "You", "s1": "Marco", "s2": "Sara"} and renamed == ["s2"])
check("prose mentions rewritten", parsed["summary"] == "Sara will draft the plan." and parsed["decisions"] == ["Sara owns rollout"]
      and parsed["action_items"][0]["task"] == "Sara drafts plan")
spk = {"self": "You", "s1": "Sara", "s2": "Speaker 2"}
check("name already taken is not duplicated", apply_speaker_names(spk, {"s2": "sara"}) == [] and spk["s2"] == "Speaker 2")
check("apply never raises on garbage", apply_speaker_names(None, {"s2": "X"}) == [])

ok = all(c for _, c in RESULTS)
print(f"\ntotal={len(RESULTS)} passed={sum(1 for _, c in RESULTS if c)} ALL_GREEN={ok}")
sys.exit(0 if ok else 1)
