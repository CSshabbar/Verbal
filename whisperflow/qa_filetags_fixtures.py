"""A8 Adversarial QA fixtures for app.filetags.

Standalone, no mic / no live IDE / no real AX. Tests the PURE pieces:
  - filetags.tag(...) across the required matrix + adversarial breakers.
  - supported_ide()-classification-logic via the pure _classify() helper.
  - read_open_files(): only that it returns a list and never raises when called.

Run:  /Users/muhammadshabbar/Work/Verbal/whisperflow/.venv/bin/python qa_filetags_fixtures.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import filetags  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []
HOLES = []


def check(desc, cond, expected=None, actual=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS: %s" % desc)
    else:
        FAIL += 1
        msg = desc
        if expected is not None or actual is not None:
            msg += "  | expected=%r actual=%r" % (expected, actual)
        FAILURES.append(msg)
        print("  FAIL: %s" % msg)


def tag(text, files, dict_applied=False, is_terminal=False):
    return filetags.tag(text, files, dict_applied=dict_applied, is_terminal=is_terminal)


# ── (a)–(i) required matrix ────────────────────────────────────────────────
print("\n[required matrix]")

# (a) 'open main dot py' + [main.py,useAuth.ts] -> contains @main.py
out = tag("open main dot py", ["main.py", "useAuth.ts"])
check("(a) 'open main dot py' -> contains @main.py", "@main.py" in out, "@main.py in out", out)
check("(a) does not spuriously tag useAuth", "@useAuth.ts" not in out, "no @useAuth.ts", out)

# (b) bare multi-word stem tags ONLY when the utterance shows file intent
#     (a trigger word like 'open'/'file' present). Without a trigger, ordinary
#     speech must be left alone (see hole assertions below).
out = tag("open the project and check use auth please", ["useAuth.ts"])
check("(b) 'open ... check use auth' (trigger) -> @useAuth.ts", "@useAuth.ts" in out, "@useAuth.ts in out", out)
out = tag("check use auth please", ["useAuth.ts"])
check("(b) bare 'check use auth' (no trigger) -> NOT tagged", "@useAuth.ts" not in out, "no @useAuth.ts", out)

# (c) unknown file 'open server.rs' + [main.py] -> NO tag
out = tag("open server.rs", ["main.py"])
check("(c) unknown file not tagged (no '@')", "@" not in out, "no '@'", out)
check("(c) text unchanged", out == "open server.rs", "open server.rs", out)

# (d) dict_applied=True -> unchanged
src = "open main dot py"
out = tag(src, ["main.py"], dict_applied=True)
check("(d) dict_applied=True -> unchanged", out == src, src, out)

# (e) is_terminal=True -> unchanged
out = tag(src, ["main.py"], is_terminal=True)
check("(e) is_terminal=True -> unchanged", out == src, src, out)

# (f) a file WITHOUT extension is never produced
#     known set has extension-less entries; tag must never emit them.
for badset, text in (
    (["Makefile"], "open makefile"),
    (["README"], "open readme"),
    (["main"], "open main"),          # bare word, no ext in known set
    (["Dockerfile"], "at file dockerfile"),
):
    out = tag(text, badset)
    check("(f) no ext -> not tagged for %r" % badset, "@" not in out, "no '@'", out)
    # And structurally: any '@token' produced must carry a '.ext'
import re as _re
for goodset, text in ([("main.py",), "open main dot py"],):
    out = tag(text, list(goodset))
    tags = _re.findall(r"@(\S+)", out)
    check("(f) every produced tag has a dot-ext (%r)" % (out,),
          all("." in t and t.rsplit(".", 1)[1] for t in tags), "all have .ext", tags)

# (g) already-tagged '@main.py' -> not double tagged
out = tag("@main.py", ["main.py"])
check("(g) '@main.py' not double-tagged", out == "@main.py", "@main.py", out)
out2 = tag("see @main.py here", ["main.py"])
check("(g) '@main.py' in sentence untouched", out2 == "see @main.py here", "see @main.py here", out2)

# (h) plain text with no filename -> unchanged
for text in ("hello world how are you", "let us discuss the plan today", ""):
    out = tag(text, ["main.py", "useAuth.ts"])
    check("(h) plain text unchanged %r" % text, out == text, text, out)

# (i) multiple files in one sentence both tagged
out = tag("open main dot py and check use auth", ["main.py", "useAuth.ts"])
check("(i) main.py tagged", "@main.py" in out, "@main.py in out", out)
check("(i) useAuth.ts tagged", "@useAuth.ts" in out, "@useAuth.ts in out", out)


# ── ADVERSARIAL: try to break it ──────────────────────────────────────────
print("\n[adversarial breakers]")

# substring: 'maintenance' must NOT match 'main' (main.py known)
out = tag("we scheduled maintenance for the server", ["main.py"])
check("substring 'maintenance' !-> @main.py", "@" not in out, "no '@'", out)

# substring: 'domain' contains 'main'
out = tag("the domain expired yesterday", ["main.py"])
check("substring 'domain' !-> tag", "@" not in out, "no '@'", out)

# 'use authentication' must NOT match multi-word stem 'useAuth' (trailing \w)
out = tag("we should use authentication everywhere", ["useAuth.ts"])
check("'use authentication' !-> @useAuth.ts", "@useAuth.ts" not in out, "no @useAuth.ts", out)

# 'reuse' prefix must not trigger 'use' portion (word-boundary lookbehind)
out = tag("please reuse authstate later", ["useAuth.ts"])
check("'reuse auth...' lookbehind holds", "@useAuth.ts" not in out, "no @useAuth.ts", out)

# casing: all caps
out = tag("OPEN MAIN DOT PY NOW", ["main.py"])
check("uppercase 'MAIN DOT PY' -> @main.py", "@main.py" in out, "@main.py in out", out)

# mixed case file, lowercase speech
out = tag("open use auth", ["useAuth.ts"])
check("mixed-case file matched from lower speech", "@useAuth.ts" in out, "@useAuth.ts in out", out)

# homophone extension: 'pie'
out = tag("open main dot pie", ["main.py"])
check("homophone ext 'pie' -> @main.py", "@main.py" in out, "@main.py in out", out)

# punctuation adjacency: comma right after
out = tag("open main.py, then run it", ["main.py"])
check("'main.py,' tagged, comma preserved", "@main.py," in out, "@main.py, present", out)

# bare filename with real extension (no prefix, no 'dot')
out = tag("main.py has a bug", ["main.py"])
check("bare 'main.py' -> @main.py", out.startswith("@main.py"), "@main.py ...", out)

# empty known set -> unchanged even with dotted words
out = tag("open main dot py", [])
check("empty file set -> unchanged", out == "open main dot py", "open main dot py", out)

# None text -> returned as-is, no crash
try:
    out = tag(None, ["main.py"])
    check("None text -> no crash, returns None", out is None, None, out)
except Exception as e:
    check("None text -> no crash", False, "no exception", repr(e))

# None files -> no crash
try:
    out = tag("open main dot py", None)
    check("None files -> no crash", out == "open main dot py", "open main dot py", out)
except Exception as e:
    check("None files -> no crash", False, "no exception", repr(e))

# garbage / non-str entries in files -> no crash
try:
    out = tag("open main dot py", ["main.py", None, 123, {"x": 1}, "bad file no ext"])
    check("garbage file entries tolerated", "@main.py" in out, "@main.py in out", out)
except Exception as e:
    check("garbage file entries -> no crash", False, "no exception", repr(e))

# extension-only word that is a common english word must not over-match
# file 'go.go' -> 'go' homophone. "let us go dot go"? distinctive. but plain "go"
out = tag("let us go home now", ["go.go"])
check("plain 'go' (single-token, no ext) !-> tag", "@" not in out, "no '@'", out)

# strong-prefix bare stem: 'file main' -> @main.py (documented behavior)
out = tag("open the file main here", ["main.py"])
check("strong prefix 'file main' -> @main.py", "@main.py" in out, "@main.py in out", out)

# ── Pass 2b: '<stem> file' suffix (natural 'the README file' phrasing) ──────
print("\n[stem-then-file suffix]")
out = tag("go over the README file and tell me what is inside it", ["README.md"])
check("'the README file' -> @README.md", "@README.md" in out, "@README.md in out", out)
out = tag("the main file has a bug", ["main.py"])
check("'the main file' -> @main.py", "@main.py" in out, "@main.py in out", out)
# 'file' as a verb / no matching open stem before it -> no tag
out = tag("I need to file a report", ["main.py"])
check("'file a report' (verb) !-> tag", "@" not in out, "no '@'", out)
out = tag("open the settings file", ["main.py"])  # settings.* not open
check("'settings file' not open !-> tag", "@" not in out, "no '@'", out)

# ── read_open_files must return a list and never raise ─────────────────────
print("\n[read_open_files smoke]")
try:
    r = filetags.read_open_files()
    check("read_open_files() returns a list", isinstance(r, list), "list", type(r).__name__)
except Exception as e:
    check("read_open_files() never raises", False, "no exception", repr(e))
try:
    r = filetags.read_open_files(pid=999999999)  # bogus pid
    check("read_open_files(bogus pid) returns a list", isinstance(r, list), "list", type(r).__name__)
except Exception as e:
    check("read_open_files(bogus pid) never raises", False, "no exception", repr(e))

# ── supported_ide classification logic (pure _classify) ────────────────────
print("\n[classification logic]")
cases = [
    ("com.todesktop.230313mzl4w4u92", "Cursor", "cursor"),
    (None, "Cursor", "cursor"),
    ("com.exafunction.windsurf", "Windsurf", "windsurf"),
    ("com.codeium.windsurf", "Windsurf", "windsurf"),
    (None, "Codeium Windsurf", "windsurf"),
    ("com.microsoft.VSCode", "Code", "vscode"),
    ("com.microsoft.VSCodeInsiders", "Visual Studio Code - Insiders", "vscode"),
    (None, "Code", "vscode"),
    ("com.apple.Safari", "Safari", None),
    ("com.tinyspeck.slackmacgap", "Slack", None),
    (None, None, None),
    ("", "", None),
]
for bid, name, expected in cases:
    got = filetags._classify(bid, name)
    check("_classify(%r, %r) -> %r" % (bid, name, expected), got == expected, expected, got)

# supported_ide() itself must never raise (frontmost app may be anything)
try:
    got = filetags.supported_ide()
    check("supported_ide() never raises (got %r)" % got,
          got in (None, "cursor", "windsurf", "vscode"), "valid class/None", got)
except Exception as e:
    check("supported_ide() never raises", False, "no exception", repr(e))

# focus_is_terminal() must never raise
try:
    got = filetags.focus_is_terminal()
    check("focus_is_terminal() returns bool", isinstance(got, bool), "bool", type(got).__name__)
except Exception as e:
    check("focus_is_terminal() never raises", False, "no exception", repr(e))


# ── FALSE-POSITIVE GUARDS (regression tests for hardened tag()) ─────────────
print("\n[false-positive guards]")
# multi-word common stem must NOT false-positive in ordinary speech (no trigger)
out = tag("update my config before lunch", ["myConfig.json"])
check("bare 'my config' (no trigger) !-> @myConfig.json", "@myConfig.json" not in out, "no @myConfig.json", out)

# literal 'dot' in unrelated speech must not tag
out = tag("the main dot on the map is red", ["main.py"])
check("'main dot on' !-> @main.py", "@main.py" not in out, "no @main.py", out)

# 'pi' is no longer a .py homophone -> math/greek speech is safe
out = tag("compute main dot pi value", ["main.py"])
check("'main dot pi' (pi not a homophone) !-> @main.py", "@main.py" not in out, "no @main.py", out)

# but the WITH-trigger variant of the same stem still tags (intent preserved)
out = tag("open my config", ["myConfig.json"])
check("'open my config' (trigger) -> @myConfig.json", "@myConfig.json" in out, "@myConfig.json in out", out)

# 'see' homophone for .c: ordinary "and see" must not tag (no trigger, single word)
out = tag("go and see the results", ["go.c"])
check("'go and see' !-> tag", "@" not in out, "no '@'", out)

# text homophone for .txt: ordinary speech, no trigger -> untouched
out = tag("send the text message", ["notes.txt"])
check("bare 'text message' (no trigger) !-> @notes.txt", "@notes.txt" not in out, "no @notes.txt", out)


# ── summary ────────────────────────────────────────────────────────────────
total = PASS + FAIL
print("\n==== SUMMARY ====")
print("total=%d passed=%d failed=%d" % (total, PASS, FAIL))
if FAILURES:
    print("FAILING:")
    for f in FAILURES:
        print("  - " + f)
if HOLES:
    print("HOLES:")
    for h in HOLES:
        print("  - " + h)
print("ALL_GREEN=%s" % (FAIL == 0))
