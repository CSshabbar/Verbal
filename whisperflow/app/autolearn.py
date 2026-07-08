"""
Auto-learn dictionary — PURE INTELLIGENCE CORE (stdlib only).

Implements the §2 "correction vs. everything else" pipeline from
AUTOLEARN_DICTIONARY_SWARM.md. This module is intentionally dependency-free
(standard library only): NO Accessibility (AX), NO mic, NO UI, NO config I/O
beyond reading/mutating a plain dict. Everything here is deterministic and
fully unit-testable without a machine.

Public API
----------
  align(t_tokens, e_tokens) -> (ops, changed_ratio)
      Token-level Needleman-Wunsch alignment. `ops` is a list of
      {type: 'match'|'substitute'|'insert'|'delete', old, new, pos}.

  classify(inserted_text, edited_text, config) -> Decision
      The full §2 pipeline. Decision = {action, old, new, confidence,
      is_proper_noun, reason}. `action` is 'offer'|'silent_learn'|'ignore'.

  record_offered(config, word) / record_declined(config, word) / is_declined(config, word)
      Per-word memory stored under config['autolearn_declined'] (F9).

  apply_observation_guard(decision, keystrokes_observed, ms_since_insert)
      F10 anti-false-attribution: downgrade to 'ignore' when a value change
      arrived <300ms after insertion with no observed keystrokes (OS autocorrect).

Vendored (tiny, no heavy deps): Double Metaphone, Levenshtein, and a compact
common-English-word frequency set.
"""

import logging
import re
import threading
import time

logger = logging.getLogger("verbal.autolearn")

__all__ = [
    "align",
    "classify",
    "tokenize",
    "double_metaphone",
    "phonetic_match",
    "levenshtein",
    "record_offered",
    "record_declined",
    "is_declined",
    "apply_observation_guard",
    "COMMON_WORDS",
    "EditWatcher",
]

# ── tuning thresholds (§2 defaults) ──────────────────────────────────────────
_RATIO_VERY_SHORT_TOKENS = 2      # <= this many tokens: allow a lone-word sub
_RATIO_SHORT_TOKENS = 6           # <= this many tokens: use the relaxed ratio
_RATIO_SHORT = 0.5
_RATIO_NORMAL = 0.3
_LEV_ABS = 2                      # accept orthographically if dist <= 2 ...
_LEV_SHORT_WORD = 6              #   for words up to this length ...
_LEV_PCT = 0.30                   # ... or dist <= 30% of max(len)
_F10_MS = 300                     # F10 window: changes sooner than this w/o keys


# ── token helpers ────────────────────────────────────────────────────────────
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*")


def tokenize(text):
    """Split text into word tokens (case preserved, punctuation dropped).

    Dropping standalone punctuation means pure punctuation/whitespace edits
    collapse to no-ops at the token level, and only real word changes surface
    as align ops (§2.5 punctuation filter is thereby mostly free)."""
    if not text:
        return []
    return _TOKEN_RE.findall(text)


# ── (1) token alignment: Needleman-Wunsch / token Levenshtein ────────────────
def align(t_tokens, e_tokens):
    """Align two token lists and return (ops, changed_ratio).

    Uses an O(n*m) edit-distance DP with unit costs (substitution = insertion =
    deletion = 1, match = 0) and a deterministic traceback that prefers the
    diagonal (match/substitute), then delete, then insert. Position anchoring
    falls out of the DP: repeated words (e.g. "the the") are aligned by their
    slot, so an extra copy shows up as a single delete rather than a spurious
    substitution.

    Each op: {type, old, new, pos}. `pos` is the position in the EDITED token
    stream (the insertion point for a delete), which is what the classifier uses
    to detect sentence-start capitalization.
    """
    t = list(t_tokens)
    e = list(e_tokens)
    n, m = len(t), len(e)

    # dp[i][j] = edit distance between t[:i] and e[:j]
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
    for j in range(1, m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        ti = t[i - 1]
        for j in range(1, m + 1):
            cost = 0 if ti == e[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j - 1] + cost,   # match / substitute
                dp[i - 1][j] + 1,          # delete t[i-1]
                dp[i][j - 1] + 1,          # insert e[j-1]
            )

    ops = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            cost = 0 if t[i - 1] == e[j - 1] else 1
            if dp[i][j] == dp[i - 1][j - 1] + cost:
                if cost == 0:
                    ops.append({"type": "match", "old": t[i - 1],
                                "new": e[j - 1], "pos": j - 1})
                else:
                    ops.append({"type": "substitute", "old": t[i - 1],
                                "new": e[j - 1], "pos": j - 1})
                i -= 1
                j -= 1
                continue
        if i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            # token present in T, absent in E → deletion
            ops.append({"type": "delete", "old": t[i - 1], "new": None,
                        "pos": j})
            i -= 1
            continue
        # otherwise insertion (token present in E, absent in T)
        ops.append({"type": "insert", "old": None, "new": e[j - 1],
                    "pos": j - 1})
        j -= 1

    ops.reverse()

    changed = sum(1 for op in ops if op["type"] != "match")
    denom = max(n, m, 1)
    changed_ratio = changed / denom
    return ops, changed_ratio


# ── vendored Levenshtein (character level) ───────────────────────────────────
def levenshtein(a, b):
    """Classic character-level edit distance."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


# ── vendored (small) Double Metaphone ────────────────────────────────────────
# A compact, pragmatic Double Metaphone. Not a byte-for-byte reproduction of
# Philips' reference, but it produces stable (primary, secondary) consonant
# codes good enough for the phonetic gate — and the orthographic gate is the
# belt-and-suspenders backstop (§2.4).
_VOWELS = "AEIOUY"


def double_metaphone(word):
    """Return (primary, secondary) phonetic codes for `word`."""
    w = "".join(ch for ch in (word or "").upper() if ch.isalpha())
    if not w:
        return ("", "")
    length = len(w)

    def at(i):
        return w[i] if 0 <= i < length else ""

    def sub(i, j):
        return w[max(i, 0):j]

    primary = []
    secondary = []
    pos = 0

    # silent leading clusters
    if w[:2] in ("GN", "KN", "PN", "WR", "PS"):
        pos = 1
    if at(0) == "X":            # initial X sounds like S ("Xavier")
        primary.append("S")
        secondary.append("S")
        pos = 1

    while pos < length:
        c = w[pos]
        adv = 1
        nxt = at(pos + 1)

        if c in _VOWELS:
            if pos == 0:
                primary.append("A")
                secondary.append("A")
            # non-initial vowels contribute nothing
        elif c == "B":
            primary.append("P")
            secondary.append("P")
            if nxt == "B":
                adv = 2
        elif c == "C":
            if nxt == "H":
                primary.append("X")
                secondary.append("X")
                adv = 2
            elif nxt in "IEY":
                primary.append("S")
                secondary.append("S")
                adv = 2
            else:
                primary.append("K")
                secondary.append("K")
                if nxt == "C":
                    adv = 2
        elif c == "D":
            if sub(pos, pos + 2) == "DG":
                primary.append("J")
                secondary.append("J")
                adv = 2
            else:
                primary.append("T")
                secondary.append("T")
                if nxt == "D":
                    adv = 2
        elif c == "F":
            primary.append("F")
            secondary.append("F")
            if nxt == "F":
                adv = 2
        elif c == "G":
            if nxt == "H":
                primary.append("K")
                secondary.append("K")
                adv = 2
            elif nxt == "N":
                primary.append("K")
                secondary.append("K")
                adv = 2
            elif nxt in "IEY":
                primary.append("J")
                secondary.append("J")
                adv = 2
            else:
                primary.append("K")
                secondary.append("K")
                if nxt == "G":
                    adv = 2
        elif c == "H":
            # H is only sounded between vowels or at a vowel onset
            if (pos == 0 or at(pos - 1) in _VOWELS) and nxt in _VOWELS:
                primary.append("H")
                secondary.append("H")
        elif c == "J":
            primary.append("J")
            secondary.append("J")
            if nxt == "J":
                adv = 2
        elif c == "K":
            primary.append("K")
            secondary.append("K")
            if nxt == "K":
                adv = 2
        elif c == "L":
            primary.append("L")
            secondary.append("L")
            if nxt == "L":
                adv = 2
        elif c == "M":
            primary.append("M")
            secondary.append("M")
            if nxt == "M":
                adv = 2
        elif c == "N":
            primary.append("N")
            secondary.append("N")
            if nxt == "N":
                adv = 2
        elif c == "P":
            if nxt == "H":
                primary.append("F")
                secondary.append("F")
                adv = 2
            else:
                primary.append("P")
                secondary.append("P")
                if nxt == "P":
                    adv = 2
        elif c == "Q":
            primary.append("K")
            secondary.append("K")
            if nxt == "Q":
                adv = 2
        elif c == "R":
            primary.append("R")
            secondary.append("R")
            if nxt == "R":
                adv = 2
        elif c == "S":
            if nxt == "H":
                primary.append("X")
                secondary.append("X")
                adv = 2
            elif sub(pos, pos + 3) in ("SIO", "SIA"):
                primary.append("S")
                secondary.append("X")
            else:
                primary.append("S")
                secondary.append("S")
                if nxt == "S":
                    adv = 2
        elif c == "T":
            if nxt == "H":
                primary.append("0")   # 'th' → theta
                secondary.append("T")
                adv = 2
            elif sub(pos, pos + 3) in ("TIO", "TIA"):
                primary.append("X")
                secondary.append("X")
            else:
                primary.append("T")
                secondary.append("T")
                if nxt == "T":
                    adv = 2
        elif c == "V":
            primary.append("F")
            secondary.append("F")
            if nxt == "V":
                adv = 2
        elif c == "W":
            if nxt in _VOWELS:
                primary.append("W")
                secondary.append("F")   # W↔V loanword variant
        elif c == "X":
            primary.append("K")
            primary.append("S")
            secondary.append("K")
            secondary.append("S")
            if nxt == "X":
                adv = 2
        elif c == "Z":
            primary.append("S")
            secondary.append("S")
            if nxt == "Z":
                adv = 2
        # any other char: ignore
        pos += adv

    return ("".join(primary), "".join(secondary))


def phonetic_match(old, new):
    """True if `old` and `new` plausibly sound the same (§2.3).

    Accept when any of the primary/secondary code pairs are equal, or when the
    primary codes are within a code-Levenshtein of 1."""
    p1, s1 = double_metaphone(old)
    p2, s2 = double_metaphone(new)
    if not (p1 or s1) or not (p2 or s2):
        return False
    codes1 = {c for c in (p1, s1) if c}
    codes2 = {c for c in (p2, s2) if c}
    if codes1 & codes2:
        return True
    if p1 and p2 and levenshtein(p1, p2) <= 1:
        return True
    return False


def _orthographically_close(old, new):
    """§2.4 orthographic gate: small character edit distance."""
    dist = levenshtein(old, new)
    max_len = max(len(old), len(new), 1)
    if max_len <= _LEV_SHORT_WORD:
        return dist <= _LEV_ABS
    return dist <= _LEV_ABS or dist <= _LEV_PCT * max_len


# ── proper-noun / common-word signals (§2.6) ─────────────────────────────────
_CAMEL_RE = re.compile(r"[a-z][A-Z]")


def _is_camel_case(word):
    return bool(_CAMEL_RE.search(word))


def _is_all_caps(word):
    return len(word) > 1 and word.isupper() and word.isalpha()


def _proper_noun_signal(word, pos):
    """Strong proper-noun signals: camelCase, ALL-CAPS acronym, or a
    capitalized word that is NOT at the start of the field (sentence-start
    capitalization is ambiguous)."""
    if _is_camel_case(word):
        return True
    if _is_all_caps(word):
        return True
    if word[:1].isupper() and not word.isupper() and pos > 0:
        return True
    return False


# ── memory helpers (F9) ──────────────────────────────────────────────────────
def _declined_list(config):
    lst = config.get("autolearn_declined")
    if not isinstance(lst, list):
        lst = []
        config["autolearn_declined"] = lst
    return lst


def record_declined(config, word, save_config_fn=None):
    """Remember that the user declined (or was already offered) `word`, so we
    never nag again. Stored under config['autolearn_declined']."""
    w = (word or "").strip()
    if not w:
        return
    lst = _declined_list(config)
    if w.lower() not in {str(x).lower() for x in lst}:
        lst.append(w)
        if save_config_fn:
            try:
                save_config_fn(config)
            except Exception:
                pass


# record_offered is an alias: once we've offered a word we suppress future
# offers for it unless/until the user acts, keeping the flow non-spammy (F9).
def record_offered(config, word, save_config_fn=None):
    """Alias of record_declined — mark `word` handled so it is not re-offered."""
    record_declined(config, word, save_config_fn)


def is_declined(config, word):
    """True if `word` was previously offered/declined (case-insensitive)."""
    w = (word or "").strip().lower()
    if not w:
        return False
    return w in {str(x).strip().lower() for x in _declined_list(config)}


# ── F10 anti-false-attribution downgrade ─────────────────────────────────────
def apply_observation_guard(decision, keystrokes_observed, ms_since_insert):
    """Downgrade a Decision to 'ignore' if the change looks system-generated.

    F10: a value change that arrives within `_F10_MS` of our insertion with no
    observed user keystrokes is almost certainly OS autocorrect / an app
    reformatting our text, not a deliberate correction — never credit it."""
    if decision.get("action") == "ignore":
        return decision
    try:
        soon = ms_since_insert is not None and ms_since_insert < _F10_MS
    except TypeError:
        soon = False
    if soon and not keystrokes_observed:
        decision = dict(decision)
        decision["action"] = "ignore"
        decision["reason"] = (
            "F10: value changed <%dms after insert with no keystrokes "
            "(likely OS autocorrect / reformat)" % _F10_MS
        )
    return decision


# ── decision helper ──────────────────────────────────────────────────────────
def _decision(action, old, new, confidence, is_proper_noun, reason):
    return {
        "action": action,
        "old": old,
        "new": new,
        "confidence": round(float(confidence), 3),
        "is_proper_noun": bool(is_proper_noun),
        "reason": reason,
    }


# ── (2) the classifier — the §2 pipeline ─────────────────────────────────────
def classify(inserted_text, edited_text, config=None):
    """Classify an edit T→E. Returns a Decision (see module docstring).

    Pipeline (§2b): tokenize → align → edit-shape gate → phonetic gate →
    orthographic gate → case/punct filter → common-word/proper-noun filter.
    Every reject sets a clear, human-readable `reason`."""
    config = config if isinstance(config, dict) else {}

    inserted_text = inserted_text or ""
    edited_text = edited_text or ""

    if inserted_text == edited_text:
        return _decision("ignore", "", "", 0.0, False, "no change")

    t_tokens = tokenize(inserted_text)
    e_tokens = tokenize(edited_text)

    if not t_tokens or not e_tokens:
        return _decision("ignore", "", "", 0.0, False,
                         "empty token stream after tokenization")

    ops, changed_ratio = align(t_tokens, e_tokens)

    subs = [op for op in ops if op["type"] == "substitute"]
    inserts = [op for op in ops if op["type"] == "insert"]
    deletes = [op for op in ops if op["type"] == "delete"]

    # ── edit-shape gate (§2.2): exactly one substitution, no ins/del ─────────
    if inserts and not subs and not deletes:
        return _decision("ignore", "", "", 0.0, False,
                         "insertion (word added), not a correction")
    if deletes and not subs and not inserts:
        return _decision("ignore", "", "", 0.0, False,
                         "deletion (word removed), not a correction")
    if inserts or deletes:
        return _decision("ignore", "", "", 0.0, False,
                         "mixed insert/delete edit, not a single-word correction")
    if len(subs) == 0:
        return _decision("ignore", "", "", 0.0, False,
                         "no word-level change (case/punctuation only)")
    if len(subs) > 1:
        return _decision("ignore", "", "", 0.0, False,
                         "multiple words changed (rephrase, not a correction)")

    max_tokens = max(len(t_tokens), len(e_tokens))
    if max_tokens <= _RATIO_VERY_SHORT_TOKENS:
        ratio_thresh = 1.0
    elif max_tokens <= _RATIO_SHORT_TOKENS:
        ratio_thresh = _RATIO_SHORT
    else:
        ratio_thresh = _RATIO_NORMAL
    if changed_ratio > ratio_thresh:
        return _decision("ignore", "", "", 0.0, False,
                         "changed-token ratio %.2f > %.2f (too much changed)"
                         % (changed_ratio, ratio_thresh))

    op = subs[0]
    old = op["old"]
    new = op["new"]
    new_pos = op["pos"]

    # ── declined memory (F9) — never re-offer ────────────────────────────────
    if is_declined(config, new):
        return _decision("ignore", old, new, 0.0, False,
                         "word previously offered/declined (no re-offer)")

    # ── case/punct-only detection (§2.5) ─────────────────────────────────────
    case_only = old.lower() == new.lower() and old != new

    # ── phonetic + orthographic gates (§2.3–2.4) ─────────────────────────────
    phon = phonetic_match(old, new)
    ortho = _orthographically_close(old, new)
    if case_only:
        phon = True   # identical letters, differing only in case → sounds same
    if not phon and not ortho:
        return _decision("ignore", old, new, 0.0, False,
                         "'%s'→'%s' not phonetically or orthographically similar "
                         "(word swap / rephrase)" % (old, new))

    # ── proper-noun / common-word filter (§2.6) ──────────────────────────────
    strong_pn = _proper_noun_signal(new, new_pos)
    absent_from_wordlist = new.lower() not in COMMON_WORDS
    is_proper_noun = strong_pn or absent_from_wordlist

    if (new.lower() in COMMON_WORDS) and not strong_pn:
        return _decision("ignore", old, new, 0.0, is_proper_noun,
                         "'%s' is a common English word (grammar/homophone, "
                         "not new vocabulary)" % new)

    # ── accept → build confidence ────────────────────────────────────────────
    confidence = 0.5
    if phon:
        confidence += 0.2
    if strong_pn:
        confidence += 0.2
    if ortho and levenshtein(old, new) <= _LEV_ABS:
        confidence += 0.1
    if case_only:
        confidence -= 0.05   # capitalization rules are lower value
    confidence = max(0.0, min(1.0, confidence))

    if case_only:
        reason = ("capitalization fix '%s'→'%s' on a proper-noun-like token"
                  % (old, new))
    else:
        reason = ("single-word correction '%s'→'%s' (%s%s)"
                  % (old, new,
                     "phonetic" if phon else "orthographic",
                     ", proper-noun" if strong_pn else ""))

    return _decision("offer", old, new, confidence, is_proper_noun, reason)


# ── compact common-English-word set (§2.6 frequency filter) ──────────────────
# Not the full 30-50k list (that would bloat the source); this is a compact set
# of the most common function + content words, which is what actually drives the
# homophone/common-word rejections ("the", "there", "their", "to", "too", ...).
_COMMON_WORDS_TEXT = """
the be to of and a in that have i it for not on with he as you do at this but his
by from they we say her she or an will my one all would there their what so up out
if about who get which go me when make can like time no just him know take people
into year your good some could them see other than then now look only come its over
think also back after use two how our work first well way even new want because any
these give day most us is are was were been being am has had did does doing said
went gone made making went get got getting give given go going come came seem seems
seemed feel felt keep kept let put set say says saying tell told ask asked need needed
try tried call called move moved live lived believe believed hold held bring brought
happen happened write wrote written provide provided sit sat stand stood lose lost pay
paid meet met include included continue continued set learn learned change changed lead
led understand understood watch watched follow followed stop stopped create created speak
spoke read allow allowed add added spend spent grow grew open opened walk walked win won
offer offered remember remembered love loved consider considered appear appeared buy bought
wait waited serve served die died send sent build built stay stayed fall fell cut reach
kill remain suggest raise pass sell require report decide pull return explain hope develop
carry break receive agree support hit produce eat cover catch draw choose cause point
man woman child world school state family student group country problem hand part place
case week company system program question work government number night point home water
room mother area money story fact month lot right study book eye job word business issue
side kind head house service friend father power hour game line end member law car city
community name president team minute idea body information back parent face others level
office door health person art war history party result change morning reason research girl
guy moment air teacher force education foot boy age policy process music market sense
nation plan college interest death experience effect use class control care field
development role effort rate heart drug show leader light voice wife whole police mind
finally pull return free military price report less according decision son hope develop
view relationship carry town road drive arm true federal break better difference thank
receive value international building action full model join season society tax director
position player record pain end paper space available recent term available available
red form data economy movie shoulder economic key hair section environment table court
easy human though win red green blue black white small large great little own other old
high different big possible young important few public bad same able hot cold hard true
false light dark early late long short full empty happy sad fast slow near far deep here
where when why how what who which whom whose all any both each few many some such no nor
not only own same so than too very can will just should now yes maybe okay ok please
hello hi hey bye goodbye thanks thank welcome sorry excuse pardon really actually well
you're your youre they're theyre there here hear where were we're weve i'm im it's its
he's she's that's whats lets dont cant wont isnt arent wasnt werent hasnt havent didnt
doesnt wouldnt couldnt shouldnt
one two three four five six seven eight nine ten first second third next last another
each every another either neither
""".split()

def _load_common_words():
    """Common/real-English-word set for the §2.6 filter.

    Primary source is the macOS system dictionary (~235k words, present on every
    macOS install) so ordinary words (cat, desert, dessert, plume, loose) are
    recognized as common and NOT offered as new vocabulary — proper nouns and
    jargon (Shabbar, iDiaz, Kubectl) are absent and still offered. The compact
    inline set is always unioned in as a guaranteed fallback if the system
    dictionary is unavailable.
    """
    words = set(w.lower() for w in _COMMON_WORDS_TEXT)
    for path in ("/usr/share/dict/words", "/usr/share/dict/web2"):
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    w = line.strip().lower()
                    if len(w) >= 2 and w.isalpha():
                        words.add(w)
            break
        except Exception:
            continue
    return frozenset(words)


COMMON_WORDS = _load_common_words()


# ══════════════════════════════════════════════════════════════════════════════
# A2 — EditWatcher: the thin AX read-back layer (§3 / §6 A2)
# ══════════════════════════════════════════════════════════════════════════════
#
# Everything above this line is the PURE, dependency-free intelligence core that
# the A9 fixtures exercise. NOTHING below is imported at module load beyond the
# stdlib already imported at the top: every Accessibility (AX) / PyObjC symbol is
# imported LAZILY inside methods, so `import app.autolearn` never fails and the
# pure core stays testable without a Mac, a mic, or the Accessibility framework.
#
# OBSERVATION STRATEGY — POLLING (chosen deliberately). The spec allows either an
# AXObserver on kAXValueChangedNotification + kAXFocusedUIElementChanged, OR a
# bounded polling fallback, and says: "pick the most robust option and note
# which." We use POLLING because AXObserver from PyObjC is fragile in practice:
# it requires (a) a C-signature AXObserverCallback bridged through PyObjC,
# (b) a live CFRunLoop pumped on this very daemon thread (CFRunLoopRun), and
# (c) the observed element to survive re-layout — any of which can wedge or crash
# the thread. A short-interval poll of AXValue on the ORIGINAL element, bounded
# by a per-call messaging timeout and an overall wall-clock deadline, achieves
# the same "quiescence then read" behaviour with far fewer moving parts and can
# never hang the process. The ~700ms debounce (spec: 600-1000ms) is realised as
# "value unchanged for DEBOUNCE seconds after a change was seen."
#
# HARD GUARANTEES (§1d / §6 A2):
#   - Runs on a daemon thread, OFF the recording/injection critical path.
#   - NEVER touches the clipboard or the injection path (this module has no
#     reference to pyperclip / injector.inject_text and never will).
#   - Every AX call is wrapped in try/except AND bounded by an AX messaging
#     timeout, so an unresponsive target can never stall us.
#   - Skips AXSecureTextField / password fields (F3) — never reads secrets.
#   - Skips terminals via filetags.focus_is_terminal() + a bundle denylist (F12).
#   - Sanity-checks that the INITIAL read contains our inserted text before it
#     will diff anything (F13) — a stale/flaky/wrong Electron read yields nothing.
#   - Reuses filetags._ax_attr + AXUIElementCreateApplication (pid comes from
#     injector.get_focused_app_pid() at the call site) — no forked AX toolkit.

# Poll/debounce/deadline tuning (seconds).
_EW_POLL_INTERVAL = 0.15       # how often we sample AXValue
_EW_DEBOUNCE = 0.7            # value must be stable this long after a change
_EW_OVERALL_DEADLINE = 30.0    # stop watching after this (bad-path safety valve)
_EW_SETTLE_BEFORE_BASELINE = 0.12  # let the paste land before the first read
_EW_AX_MSG_TIMEOUT = 0.5       # per-element AX messaging timeout (hard cap)

# Bundles whose AX text semantics are absent/misleading — never watch them (F12).
_EW_DENYLIST_BUNDLES = frozenset({
    "com.apple.Terminal",
    "com.googlecode.iterm2",
    "co.zeit.hyper",
    "net.kovidgoyal.kitty",
    "io.alacritty",
    "com.github.wez.wezterm",
    "dev.warp.Warp-Stable",
    "dev.warp.Warp",
})

# Roles/subroles we must never read from (privacy — F3).
_EW_SECURE_SUBROLES = frozenset({"AXSecureTextField"})


class EditWatcher:
    """Arms an AX read-back after injection and detects the user's edit.

    Usage (from main.py, right AFTER inject_text(...), on a background thread):

        from app import autolearn, injector
        watcher = autolearn.EditWatcher()
        watcher.arm(
            pid=injector.get_focused_app_pid(),
            bundle=injector.get_focused_app_bundle(),
            inserted_text=result,
            on_decision_callback=lambda decision: ...,  # e.g. show the widget
        )

    arm() returns immediately; all AX work happens on an internal daemon thread.
    The callback is invoked at most once per arm(), with a Decision dict (the same
    shape classify() returns) that has already been through apply_observation_guard
    (F10). Calling arm() again cancels any in-flight watch first (no stacking).

    The watcher fails CLOSED: on any unreadable / secure / terminal / flaky
    target, or any exception, it simply never calls the callback. It never raises
    into the caller and never affects transcription.
    """

    def __init__(self):
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()

    # ── public API ───────────────────────────────────────────────────────────
    def arm(self, pid, bundle, inserted_text, on_decision_callback):
        """Start watching the target field for an edit to `inserted_text`.

        pid    : PID of the dictation target (injector.get_focused_app_pid()).
        bundle : bundle id of the target (injector.get_focused_app_bundle()).
        inserted_text : the exact text we just injected (T).
        on_decision_callback : callable(decision_dict) — invoked at most once when
                 a finalized edit is classified; never called for a no-op target.

        Non-blocking. Returns True if a watch thread was started, else False
        (bad/empty args → silent no-op, transcription unaffected).
        """
        try:
            if not pid or not inserted_text or not callable(on_decision_callback):
                return False
            inserted_text = str(inserted_text)
            if not inserted_text.strip():
                return False

            # Cancel any previous watch so we never stack observers/threads.
            self.cancel()

            with self._lock:
                self._stop = threading.Event()
                stop_event = self._stop
                self._thread = threading.Thread(
                    target=self._run,
                    args=(pid, bundle or "", inserted_text,
                          on_decision_callback, stop_event),
                    name="autolearn-editwatcher",
                    daemon=True,
                )
                self._thread.start()
            return True
        except Exception as e:  # arm() must never raise into the caller
            logger.debug("[autolearn] arm failed: %s", e)
            return False

    def cancel(self):
        """Signal any in-flight watch to stop (best-effort, non-blocking)."""
        try:
            with self._lock:
                if self._stop is not None:
                    self._stop.set()
        except Exception:
            pass

    # ── AX helpers (all guarded; reuse filetags._ax_attr) ─────────────────────
    @staticmethod
    def _ax_attr(element, attr):
        """Guarded AXUIElementCopyAttributeValue — delegates to filetags._ax_attr
        so we share one hardened implementation (§1c reuse)."""
        try:
            from app import filetags
            return filetags._ax_attr(element, attr)
        except Exception:
            return None

    @staticmethod
    def _set_messaging_timeout(element, seconds):
        """Bound every AX message to `seconds` so an unresponsive app can't hang
        us. Best-effort — a missing symbol just means we rely on the poll loop's
        overall deadline instead."""
        try:
            from ApplicationServices import AXUIElementSetMessagingTimeout
            AXUIElementSetMessagingTimeout(element, float(seconds))
        except Exception:
            pass

    def _app_element(self, pid):
        try:
            from ApplicationServices import AXUIElementCreateApplication
            el = AXUIElementCreateApplication(pid)
            if el is not None:
                self._set_messaging_timeout(el, _EW_AX_MSG_TIMEOUT)
            return el
        except Exception:
            return None

    def _focused_element(self, app_el):
        """The element the user is typing in = the dictation target field."""
        el = self._ax_attr(app_el, "AXFocusedUIElement")
        if el is not None:
            self._set_messaging_timeout(el, _EW_AX_MSG_TIMEOUT)
        return el

    def _is_secure(self, element):
        """F3: never read password / secure fields."""
        try:
            role = self._ax_attr(element, "AXRole")
            subrole = self._ax_attr(element, "AXSubrole")
            for tok in (role, subrole):
                if tok and str(tok) in _EW_SECURE_SUBROLES:
                    return True
        except Exception:
            return True  # unsure → treat as secure and bail (fail closed)
        return False

    def _read_value(self, element):
        """Read AXValue as a str, or None. Guarded + bounded by the messaging
        timeout set on `element`."""
        try:
            val = self._ax_attr(element, "AXValue")
            if val is None:
                return None
            return str(val)
        except Exception:
            return None

    def _caret_location(self, element):
        """Best-effort caret index from AXSelectedTextRange (used to disambiguate
        WHERE our text landed when it occurs more than once — F6/F11). Returns an
        int location or None. Fully guarded; AXValueGetValue can be flaky."""
        try:
            rng_val = self._ax_attr(element, "AXSelectedTextRange")
            if rng_val is None:
                return None
            from ApplicationServices import AXValueGetValue, kAXValueCFRangeType
            ok, rng = AXValueGetValue(rng_val, kAXValueCFRangeType, None)
            if not ok or rng is None:
                return None
            # Right after a paste the selection is empty and the caret sits at the
            # END of the inserted text; location + length is that end offset.
            return int(rng.location) + int(rng.length)
        except Exception:
            return None

    # ── the watch loop (daemon thread) ────────────────────────────────────────
    def _run(self, pid, bundle, inserted_text, callback, stop_event):
        try:
            # F12: bundle denylist + terminal focus check up front.
            if bundle in _EW_DENYLIST_BUNDLES:
                logger.debug("[autolearn] skip denylisted bundle %s", bundle)
                return
            try:
                from app import filetags
                if filetags.focus_is_terminal():
                    logger.debug("[autolearn] skip: focus is a terminal")
                    return
            except Exception:
                pass  # can't tell → proceed; other gates still protect us

            app_el = self._app_element(pid)
            if app_el is None:
                return

            # Let the paste land, then grab the focused target element ONCE. We
            # diff only against THIS original element for the whole watch (F4).
            time.sleep(_EW_SETTLE_BEFORE_BASELINE)
            if stop_event.is_set():
                return
            element = self._focused_element(app_el)
            if element is None:
                return

            # F3: never touch secure/password fields.
            if self._is_secure(element):
                logger.debug("[autolearn] skip: secure text field")
                return

            # ── baseline read + F13 sanity check ─────────────────────────────
            # Try a few quick reads to let the value settle after paste.
            baseline = None
            deadline0 = time.monotonic() + 2.0
            while time.monotonic() < deadline0 and not stop_event.is_set():
                v = self._read_value(element)
                if v is not None and inserted_text in v:
                    baseline = v
                    break
                time.sleep(_EW_POLL_INTERVAL)

            if baseline is None:
                # F13: the field never contained our inserted text — wrong/stale/
                # flaky (Electron, web) read. Prefer under-triggering: do nothing.
                logger.debug("[autolearn] skip: inserted text not found in field "
                             "(F13 sanity check failed)")
                return

            # Locate WHERE our text sits, disambiguating repeats via the caret
            # (F6/F11) so we can bound the diff to just the insertion window.
            base_idx = self._locate_inserted(baseline, inserted_text, element)
            prefix = baseline[:base_idx]
            suffix = baseline[base_idx + len(inserted_text):]

            arm_ts = time.monotonic()
            overall_deadline = arm_ts + _EW_OVERALL_DEADLINE
            last_value = baseline
            last_change_ts = None
            first_change_ts = None   # F10: when the field FIRST changed after settle

            # ── poll until quiescence-after-change, or deadline ──────────────
            while not stop_event.is_set() and time.monotonic() < overall_deadline:
                time.sleep(_EW_POLL_INTERVAL)
                cur = self._read_value(element)
                if cur is None:
                    # Element likely went away / focus lost — finalize what we saw.
                    break
                now = time.monotonic()
                if cur != last_value:
                    last_value = cur
                    last_change_ts = now
                    if first_change_ts is None:
                        first_change_ts = now
                    continue
                # value stable: has it been stable long enough AFTER a change?
                if (last_change_ts is not None
                        and (now - last_change_ts) >= _EW_DEBOUNCE
                        and cur != baseline):
                    self._finalize(inserted_text, cur, prefix, suffix,
                                   arm_ts, first_change_ts, callback, stop_event)
                    return

            if stop_event.is_set():
                return
            # Deadline / focus-loss exit: finalize the last-good value if it moved.
            if last_value != baseline:
                self._finalize(inserted_text, last_value, prefix, suffix,
                               arm_ts, first_change_ts, callback, stop_event)
        except Exception as e:  # the watch thread must never crash the app
            logger.debug("[autolearn] watch thread error: %s", e)

    def _locate_inserted(self, baseline, inserted_text, element):
        """Index of our inserted text inside `baseline`. Uses the caret to pick
        the right occurrence when the text appears more than once (F6)."""
        first = baseline.find(inserted_text)
        # Only bother disambiguating if there IS more than one occurrence.
        if first < 0:
            return 0
        if baseline.find(inserted_text, first + 1) < 0:
            return first
        caret = self._caret_location(element)
        if caret is not None:
            cand = caret - len(inserted_text)
            if (0 <= cand <= len(baseline) - len(inserted_text)
                    and baseline[cand:cand + len(inserted_text)] == inserted_text):
                return cand
        return first

    def _finalize(self, inserted_text, new_value, prefix, suffix,
                  arm_ts, first_change_ts, callback, stop_event):
        """Bound the read to the insertion region, classify, apply the F10 guard,
        and emit the Decision via the callback. Fully guarded."""
        try:
            if stop_event.is_set():
                return

            # Bound the diff to the insertion window (F11): strip the known
            # prefix/suffix that lie OUTSIDE where we inserted, so a small edit in
            # a huge document diffs T against just the edited region — not the
            # whole doc. If the surrounding text no longer matches (edit happened
            # elsewhere, or the doc changed around us), fall back to a full diff;
            # classify()'s changed-ratio gate keeps that safe.
            if (new_value.startswith(prefix)
                    and new_value.endswith(suffix)
                    and len(new_value) >= len(prefix) + len(suffix)):
                edited_region = new_value[len(prefix):
                                          len(new_value) - len(suffix)
                                          if suffix else len(new_value)]
                old_region = inserted_text
            else:
                edited_region, old_region = new_value, inserted_text

            decision = classify(old_region, edited_region)

            # F10: use the delay from the settled insertion (baseline, arm_ts) to
            # the FIRST observed change as the system-vs-user proxy. A change that
            # appears within _F10_MS of a settled paste, with no human reaction
            # time, is treated as an OS autocorrect / reformat and downgraded to
            # 'ignore'. We cannot truly observe keystrokes, so keystrokes_observed
            # is False and timing is the sole (honest) signal; genuine human edits
            # occur well after _F10_MS and pass.
            ms_since_insert = ((first_change_ts - arm_ts) * 1000.0
                               if first_change_ts is not None else None)
            decision = apply_observation_guard(
                decision, keystrokes_observed=False,
                ms_since_insert=ms_since_insert)

            if stop_event.is_set():
                return
            try:
                callback(decision)
            except Exception as e:
                logger.debug("[autolearn] decision callback error: %s", e)
        except Exception as e:
            logger.debug("[autolearn] finalize error: %s", e)
