"""Pure-logic fixtures for meetings.map_diarized_speakers — the overlap mapping that
turns AssemblyAI's who-spoke-when into the transcript's speaker ids.

No network, no audio: the mapping is a pure function precisely so these can pin its
rules. Follows the repo convention: top-level check(), exit 1 unless ALL_GREEN.
"""
import sys

from app.meetings import map_diarized_speakers

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

ok = all(c for _, c in RESULTS)
print(f"\ntotal={len(RESULTS)} passed={sum(1 for _, c in RESULTS if c)} ALL_GREEN={ok}")
sys.exit(0 if ok else 1)
