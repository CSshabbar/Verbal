#!/usr/bin/env python3
"""
Meeting auto-detection — pure-logic assertion harness for meeting_detect._match.

Why this exists: `detect()` searches EVERY on-screen window title, so a loose
pattern doesn't just misfire occasionally — it fires on whatever happens to be
open. The Google-Meet call-code regex `[a-z]{3}-[a-z]{4}-[a-z]{3}` had no
boundaries and no corroboration, so an ordinary Chrome tab containing
"…axo-data-and…" was reported as a live call and produced 7 "Take notes" prompts
in one evening with no meeting anywhere (2026-08-19, `gmeet:axo-data-and` in
app.log). This harness pins both halves of the contract:

  - the app-open / article-title / slug cases NEVER detect a call, and
  - every real in-call window shape still does.

Pure logic — no window scan, no permissions, no network. Same convention as
prompt_echo_fixtures.py.

Run:
  whisperflow/.venv/bin/python meeting_detect_fixtures.py

Exits 1 if any assertion fails.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from app import meeting_detect as md  # noqa: E402

_total = _passed = _failed = 0


def check(label, ok):
    global _total, _passed, _failed
    _total += 1
    if ok:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}")


def detects(owner, title):
    return bool(md._match(owner, title))


print("== NOT a call: the regression that caused this harness ==")
check("the real false positive: 'axo-data-and' inside a hyphenated slug",
      not detects("Google Chrome", "Supabase axo-data-and-more | Table editor"))
check("a well-delimited 3-4-3 run with no 'Meet' anywhere",
      not detects("Google Chrome", "something axo-data-and something"))
check("an ordinary YouTube title",
      not detects("Google Chrome",
                  "12 INCREDIBLE Mac Apps You Can't Live Without! - YouTube"))
check("an article slug that happens to be 3-4-3",
      not detects("Google Chrome", "the-best-way to ship - Some Blog"))

print("\n== NOT a call: talking ABOUT a meeting tool is not being in one ==")
check("a video about Google Meet (site name is YouTube's, not Meet's)",
      not detects("Google Chrome", "How to use Google Meet in 2026 - YouTube"))
check("a doc mentioning Google Meet mid-title",
      not detects("Google Chrome", "Google Meet cheat sheet | Notion"))
check("a non-browser owner is never matched as a browser",
      not detects("Code", "meet-the-team.md — Verbal"))

print("\n== NOT a call: app merely open (the module's core premise) ==")
check("Zoom idle main window", not detects("zoom.us", "Zoom"))
check("Webex idle window — the bare 'webex' clause is gone",
      not detects("Cisco Webex Meetings", "Webex"))
check("Teams chat window", not detects("Microsoft Teams", "Chat | Microsoft Teams"))

print("\n== IS a call: Google Meet ==")
check("'Meet - <code>' prefix form", detects("Google Chrome", "Meet - abc-defg-hij"))
check("en-dash prefix form", detects("Google Chrome", "Meet – abc-defg-hij"))
check("code + trailing site name", detects("Google Chrome", "abc-defg-hij - Google Meet"))
check("NAMED call, no code (the case the old code missed entirely)",
      detects("Google Chrome", "Weekly standup - Google Meet"))
check("bare 'Google Meet' title", detects("Google Chrome", "Google Meet"))
check("the host itself is proof", detects("Google Chrome", "meet.google.com/abc-defg-hij"))

print("\n== IS a call: Zoom / Webex / Teams ==")
check("Zoom in the browser", detects("Google Chrome", "Zoom Meeting"))
check("Zoom native in-call window", detects("zoom.us", "Zoom Meeting"))
check("Webex in-call window", detects("Cisco Webex Meetings", "Webex Meeting"))
check("Teams in-call window", detects("Microsoft Teams", "Meeting with Sam | Microsoft Teams"))

print("\n== Windows exe owners canonicalize onto the same matchers ==")
check("chrome.exe Meet prefix", detects("chrome.exe", "Meet - abc-defg-hij"))
check("msedge.exe named Meet", detects("msedge.exe", "Weekly standup - Google Meet"))
check("Zoom.exe in-call", detects("Zoom.exe", "Zoom Meeting"))
check("CptHost.exe Zoom meeting host", detects("CptHost.exe", "Zoom Meeting"))
check("ms-teams.exe in-call", detects("ms-teams.exe", "Meeting with Sam | Microsoft Teams"))
check("Zoom.exe idle is still not a call", not detects("Zoom.exe", "Zoom"))
check("canonical owner string is Mac-shaped",
      md._canonical_owner("chrome.exe") == "Google Chrome")

print("\n== key shape (drives the ask-once-per-call dedupe in main._md_apply) ==")
check("a code becomes the key so a different room re-prompts",
      md._match("Google Chrome", "Meet - abc-defg-hij")["key"] == "gmeet:abc-defg-hij")
check("no code falls back to a stable 'gmeet:meet' key",
      md._match("Google Chrome", "Weekly standup - Google Meet")["key"] == "gmeet:meet")

print("\n== fail-closed ==")
check("empty owner -> no match", not detects("", "Meet - abc-defg-hij"))
check("empty title -> no match", not detects("Google Chrome", ""))

all_green = _failed == 0
print(f"\ntotal={_total} passed={_passed} failed={_failed} ALL_GREEN={all_green}")
sys.exit(0 if all_green else 1)
