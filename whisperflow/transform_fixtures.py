"""Offline fixtures for transform.py's pure gate (TRANSFORM_SWARM.md P1.1).

Run: .venv/bin/python transform_fixtures.py   → exits non-zero on any failure.
No network, no LLM — the gate must be free and deterministic.
"""
import sys

sys.path.insert(0, ".")
from app.transform import detect_trailing_instruction, _strip_wrapping  # noqa: E402

CASES = [
    # (raw transcript, expected body-prefix or None)
    ("Hey team, the deploy is done and metrics look clean. So Flume, make this more formal.",
     ("Hey team, the deploy is done", "make this more formal")),
    ("The quarterly numbers are in and we beat target by 12 percent, flume turn this into bullet points",
     ("The quarterly numbers", "turn this into bullet points")),
    # homophones
    ("Thanks for the intro yesterday, plume, make the tone warmer please",
     ("Thanks for the intro", "make the tone warmer please")),
    ("I think we should postpone the launch until Q3. Bloom, translate this to German.",
     ("I think we should postpone", "translate this to German")),
    # trigger without body must NOT fire
    ("Flume make a note", None),
    ("so flume, make this formal", None),
    # no trigger — the overwhelming majority
    ("Just a normal dictation about the new onboarding flow and next steps.", None),
    # trigger word mid-sentence as CONTENT must not fire (no tail match)
    ("The flume in the water park was the best ride of the day honestly.", None),
    ("I rode the flume today and it was fun", None),
    ("We watched the plume rise over the ridge for an hour", None),
    # instruction too short
    ("Here is the body of my message, so Flume, formal.", None),
    # 'send this to Flume and…' — gate fires, split at trigger; LLM refines later
    ("Draft the update for the board with revenue and churn, flume and make it professional",
     ("Draft the update", "and make it professional")),
]

fails = 0
for raw, want in CASES:
    got = detect_trailing_instruction(raw)
    if want is None:
        ok = got is None
    else:
        ok = (got is not None and got[0].startswith(want[0])
              and got[1].lower().startswith(want[1].lower()[:12]))
    status = "ok  " if ok else "FAIL"
    if not ok:
        fails += 1
    print(f"{status} {raw[:58]!r:60} -> {got!r}")

# custom trigger words honored
got = detect_trailing_instruction(
    "The report body goes here with details, verbal, make it shorter",
    trigger_words=["verbal"])
ok = got is not None and got[1].startswith("make it shorter")
print(("ok  " if ok else "FAIL"), "custom trigger ->", got)
fails += 0 if ok else 1

# output unwrapping
for wrapped, original, want in [
    ('"Hello there."', "hey", "Hello there."),
    ("```text\nHello there.\n```", "hey", "Hello there."),
    ("Hello there.", "hey", "Hello there."),
]:
    out = _strip_wrapping(wrapped, original)
    ok = out == want
    print(("ok  " if ok else "FAIL"), f"unwrap {wrapped!r} -> {out!r}")
    fails += 0 if ok else 1

print("\n%d failure(s)" % fails)
sys.exit(1 if fails else 0)
