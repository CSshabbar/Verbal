#!/usr/bin/env python3
"""
Bias-prompt echo — pure-logic assertion harness for dictionary.strip_prompt_echo.

Whisper's `prompt` is a CONTINUATION prompt: given silence or near-silence it
keeps writing the glossary we sent, and that echo used to be injected verbatim
("Glossary, M.T.:" landing in the user's editor). This harness pins both halves
of the contract:

  - EVERY shape of echo we have seen is removed (labelled, unlabelled, mid-way,
    trailing, wrapped by real speech), and an echo-only transcript becomes "".
  - Real dictation is NEVER damaged — including speech that legitimately uses the
    user's own vocabulary, or the words "glossary"/"files" themselves.

Pure logic — no network, no model. Same convention as context_grounding_fixtures.py.

Run:
  whisperflow/.venv/bin/python prompt_echo_fixtures.py

Exits 1 if any assertion fails.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from app import dictionary  # noqa: E402

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


def scrub(text, prompt=None):
    return dictionary.strip_prompt_echo(text, prompt if prompt is not None else PROMPT)


VOCAB = ["M.T.", "Shabbar", "Flume", "Verbal", "Groq", "Supabase"]
CFG = {"dictionary": {"vocabulary": VOCAB, "replacements": [], "snippets": []}}
PROMPT = dictionary.build_prompt(CFG)
# What the desktop actually sends inside an IDE: glossary + open-file names.
PROMPT_WITH_FILES = PROMPT + " Files: transcriber.py, dictionary.py."

print("== build_prompt ==")
check("prompt is the labelled glossary", PROMPT == "Glossary: M.T., Shabbar, Flume, Verbal, Groq, Supabase.")
check("empty vocabulary sends no prompt", dictionary.build_prompt({"dictionary": {}}) is None)
_big = {"dictionary": {"vocabulary": [f"term{i}" for i in range(400)]}}
_bigp = dictionary.build_prompt(_big)
check("oversized vocabulary is capped under Groq's 896-char limit", len(_bigp) <= 600)
check("cap keeps the NEWEST terms (Whisper conditions on the prompt tail)",
      "term399" in _bigp and "term0," not in _bigp)

print("\n== prompt_terms ==")
_terms = dictionary.prompt_terms(PROMPT_WITH_FILES)
check("labels are not treated as terms", "glossary" not in _terms and "files" not in _terms)
check("dotted terms normalize ('M.T.' -> 'm t')", "m t" in _terms)
check("file names normalize ('transcriber.py' -> 'transcriber py')", "transcriber py" in _terms)

print("\n== echo removal ==")
check("whole prompt echoed back -> silence", scrub("Glossary: M.T., Shabbar, Flume, Verbal, Groq, Supabase.") == "")
check("the reported shape ('Glossary, M.T.:') -> silence", scrub("Glossary, M.T.:") == "")
check("unlabelled tail echo -> silence", scrub("Flume, Verbal, Groq.") == "")
check("echo then real speech -> only the speech survives",
      scrub("Glossary: M.T., Shabbar. So today I wanted to talk about the release.")
      == "So today I wanted to talk about the release.")
check("real speech then trailing echo -> only the speech survives",
      scrub("That is the plan for today. Glossary: M.T., Shabbar.") == "That is the plan for today.")
check("speech wrapped around an echo keeps both real halves",
      scrub("Ship it today. Glossary: Flume, Verbal. Then we review.")
      == "Ship it today. Then we review.")
check("labelled prefix on real speech loses only the label",
      scrub("Glossary: so I was thinking we should ship.") == "so I was thinking we should ship.")
check("Files: echo from the file-tag fragment -> silence",
      scrub("Files: transcriber.py, dictionary.py.", PROMPT_WITH_FILES) == "")
check("echo of the file fragment before speech -> only the speech",
      scrub("Files: transcriber.py, dictionary.py. Open the settings panel.", PROMPT_WITH_FILES)
      == "Open the settings panel.")
check("punctuation-only remainder -> silence", scrub("Glossary: M.T., Shabbar. .") == "")

print("\n== bare heading echo (no terms after it) ==")
check("'Glossary. <speech>' -> only the speech survives",
      scrub("Glossary. So, the thing is, I only said this part.")
      == "So, the thing is, I only said this part.")
check("heading alone with a period -> silence", scrub("Glossary.") == "")
check("heading alone, no punctuation -> silence", scrub("Glossary") == "")
check("heading alone mid-transcript is dropped",
      scrub("That is the plan. Glossary. Then we ship.") == "That is the plan. Then we ship.")
check("'Files.' heading echo -> silence", scrub("Files.", PROMPT_WITH_FILES) == "")
check("a heading we never sent is left alone (no file list in this prompt)",
      scrub("Files. I need to check them before the demo.")
      == "Files. I need to check them before the demo.")
check("a lone 'Files' is speech when no file list was sent", scrub("Files") == "Files")

print("\n== real dictation is never damaged ==")
check("a single vocabulary word said on its own is kept", scrub("Flume") == "Flume")
check("a vocabulary word addressed to a person is kept",
      scrub("Shabbar, can you review this?") == "Shabbar, can you review this?")
check("a sentence using two vocabulary words is kept",
      scrub("Flume uses Groq for transcription.") == "Flume uses Groq for transcription.")
check("the word 'files' spoken naturally is kept",
      scrub("Files, I need to check them before the demo.")
      == "Files, I need to check them before the demo.")
check("...even when a file list WAS sent (the clause runs on, so it is speech)",
      scrub("Files, I need to check them before the demo.", PROMPT_WITH_FILES)
      == "Files, I need to check them before the demo.")
check("a label word leading a real sentence is kept when a file list was sent",
      scrub("Glossary entries keep getting lost.", PROMPT_WITH_FILES)
      == "Glossary entries keep getting lost.")
check("the word 'glossary' spoken naturally is kept",
      scrub("Glossary entries keep getting lost.") == "Glossary entries keep getting lost.")
check("ordinary speech is byte-identical", scrub("Hello there, how are you doing today?")
      == "Hello there, how are you doing today?")
check("a long transcript is untouched",
      scrub("We shipped the dictionary sync yesterday and it works on both devices now.")
      == "We shipped the dictionary sync yesterday and it works on both devices now.")

print("\n== fail-closed ==")
check("no prompt -> text untouched", dictionary.strip_prompt_echo("Glossary: M.T.", None) == "Glossary: M.T.")
check("empty prompt -> text untouched", dictionary.strip_prompt_echo("Glossary: M.T., Shabbar.", "") == "Glossary: M.T., Shabbar.")
check("empty text -> empty", scrub("") == "")
check("None text -> None", scrub(None) is None)
check("prompt with no terms -> text untouched", dictionary.strip_prompt_echo("hello", "Glossary: .") == "hello")

all_green = _failed == 0
print(f"\ntotal={_total} passed={_passed} failed={_failed} ALL_GREEN={all_green}")
sys.exit(0 if all_green else 1)
