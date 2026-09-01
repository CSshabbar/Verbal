#!/usr/bin/env python3
"""Pure-logic fixtures for meetings.is_meeting_hallucination.

Run:  whisperflow/.venv/bin/python meeting_hallucination_fixtures.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.meetings import is_meeting_hallucination  # noqa: E402

_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  ok  {name}")
    else:
        _fail += 1
        print(f" FAIL {name}")


print("meeting hallucination gate")

# Silence / YouTube classics
check("thank you.", is_meeting_hallucination("Thank you."))
check("thanks for watching", is_meeting_hallucination("Thanks for watching."))
check("bare you", is_meeting_hallucination("you"))
check("ellipsis", is_meeting_hallucination("..."))
check("empty", is_meeting_hallucination(""))
check("whitespace", is_meeting_hallucination("   "))

# Real speech must survive
check("real sentence kept", not is_meeting_hallucination(
    "We should ship the Android build to the Play Store next week."))
check("thank you inside sentence", not is_meeting_hallucination(
    "Thank you for joining, let's start with the roadmap."))
check("one filename ok", not is_meeting_hallucination(
    "Can you open meetings.py and check the chunker?"))
check("urdu-ish kept", not is_meeting_hallucination(
    "یہ تھوڑا لمبا ٹکٹ ہے اس کو کرنا پڑے گا"))

# Repetition loops (Whisper quiet-audio failure)
check("word loop", is_meeting_hallucination(
    "Zagio Maki! Zagio Maki! Zagio Maki! Zagio Maki! Zagio Maki! Zagio Maki!"))
check("supabase.sql loop", is_meeting_hallucination(
    "sql, supabase.sql, supabase.sql, supabase.sql, supabase.sql, supabase.sql,"))
check("recent. loop", is_meeting_hallucination(
    "recent. recent. recent. recent. recent"))

# Filename soup (former filetag bias echo)
check("three extensions", is_meeting_hallucination(
    "context.md, CLAUDE.md, whisperflow_build_prompt.md,"))
check("sql spam", is_meeting_hallucination(
    "sql, supabase.sql, supabase.sql, supabase.sql, supabase,"))

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
