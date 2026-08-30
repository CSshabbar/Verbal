"""
Custom dictionary — vocabulary biasing + replacement rules + snippets (desktop).

Three mechanisms, mirroring Wispr Flow:
  - vocabulary:   words/names/jargon injected into Whisper's `prompt` so the
                  model is biased toward recognizing/spelling them correctly.
  - replacements: exact find→replace rules applied AFTER transcription to fix
                  persistent mishearings (e.g. "shabar" → "Shabbar").
  - snippets:     a spoken trigger phrase that expands into a longer block of
                  text (a LinkedIn URL, an email signature, a disclaimer). A
                  generalization of a replacement rule: the "to" side is an
                  arbitrary block and matching is on a whole *phrase* (multi-word)
                  rather than a single token. Applied AFTER AI cleanup, immediately
                  BEFORE injection. See apply_snippets() for the exact algorithm.

Stored locally in config["dictionary"] and synced to the Supabase `dictionary`
table (one row per user). Kept deliberately lightweight: no per-transcription
network calls (the dictionary is loaded into config once per session), and
fetch/save only touch the network — reads write config only when it changed, so
they never spam save_config (which previously caused a write race).

TWO SETS, ONE PIPELINE (IDI-216 Phase 4). `get()` is the user's OWN dictionary and
is what every editor and save path touches. `effective()` is personal ∪ the team's
shared dictionary and is what build_prompt / known_terms / apply_replacements /
apply_snippets actually apply. Both read only local state; the team half comes
from `organizations.team_dictionary()`, a config-cache read, so the dictation path
still makes no network call. See the merge_with_team() block for the union rule.
"""
import logging
import re

logger = logging.getLogger("verbal.dictionary")

_MAX_PROMPT_TERMS = 80   # Whisper conditions on the LAST ~224 tokens of the prompt
_MAX_PROMPT_CHARS = 600  # leaves room for the file-tag fragment under Groq's 896 cap
_MAX_TRIGGER_CHARS = 40     # snippet trigger cap (matches the design mockups)
_MAX_EXPANSION_CHARS = 500  # snippet expansion cap (matches the design mockups)


def _now_iso():
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _short_id():
    import uuid
    return uuid.uuid4().hex[:12]


def _coerce_used(v):
    try:
        return max(0, int(v or 0))
    except Exception:
        return 0


def normalize(d):
    """Return a well-formed {'vocabulary': [...], 'replacements': [...], 'snippets': [...]}."""
    d = d if isinstance(d, dict) else {}
    vocab = [str(w).strip() for w in (d.get("vocabulary") or []) if str(w).strip()]
    reps = []
    for r in (d.get("replacements") or []):
        if isinstance(r, dict) and str(r.get("from", "")).strip() and str(r.get("to", "")).strip():
            rule = {"from": str(r["from"]).strip(), "to": str(r["to"]).strip()}
            # Preserve the optional auto-learn flag without breaking {from,to} rules.
            if r.get("auto"):
                rule["auto"] = True
            reps.append(rule)
    snippets = []
    seen_triggers = set()
    for s in (d.get("snippets") or []):
        if not isinstance(s, dict):
            continue
        trigger = str(s.get("trigger", "")).strip()[:_MAX_TRIGGER_CHARS].strip()
        expansion = str(s.get("expansion", "")).strip()[:_MAX_EXPANSION_CHARS]
        if not trigger or not expansion:
            continue
        key = trigger.lower()
        if key in seen_triggers:  # dedupe by trigger (case-insensitive)
            continue
        seen_triggers.add(key)
        now = _now_iso()
        snippets.append({
            "id": (str(s.get("id") or "").strip() or _short_id()),
            "trigger": trigger,
            "expansion": expansion,
            "label": str(s.get("label") or "").strip(),
            "used": _coerce_used(s.get("used")),
            "created_at": (str(s.get("created_at") or "").strip() or now),
            "updated_at": (str(s.get("updated_at") or "").strip() or now),
        })
    return {"vocabulary": vocab, "replacements": reps, "snippets": snippets}


def get(config):
    """The user's OWN dictionary. This is the editable surface — every save path
    (save/add_replacement/add_snippet/…) and the Dictionary + Snippets screens
    operate on exactly this. For what dictation should actually APPLY, see
    effective()."""
    return normalize(config.get("dictionary"))


# ── team dictionary (IDI-216 Phase 4) ─────────────────────────────────────────
# A user in a team dictates with personal ∪ team. The merge rule (IDI-216 open
# decision #3): the UNION is what applies — nothing is dropped from either set —
# and only a genuine same-key collision needs a tiebreak, where PERSONAL wins:
# identical vocabulary word (case-insensitive), identical replacement `from`,
# identical snippet `trigger`. Personal-wins is the non-destructive choice —
# joining a team can never silently change what your existing snippet trigger
# expands to, or how a word you taught Flume yourself is spelled.
#
# ORDERING is not incidental. Team entries are placed FIRST and personal entries
# LAST so that build_prompt's tail-keeping (Whisper conditions on the last ~224
# tokens, and trimming happens from the front) still protects the terms this user
# taught it most recently. Getting this backwards would mean joining a team
# quietly evicts your own vocabulary from the bias prompt.
#
# Fail-closed: any error returns the personal dictionary unchanged. A team lookup
# must never be able to break dictation (Hard Rule #1).

def _union_first_wins(team, personal, key_fn):
    """[team entries whose key is not in personal] + [personal entries]."""
    personal_keys = {key_fn(p) for p in personal}
    return [t for t in team if key_fn(t) not in personal_keys] + list(personal)


def merge_with_team(personal, team):
    """Pure (no config, no network) so the rule is fixture-testable on its own."""
    personal, team = normalize(personal), normalize(team)
    return {
        "vocabulary": _union_first_wins(
            team["vocabulary"], personal["vocabulary"], lambda w: str(w).strip().lower()),
        "replacements": _union_first_wins(
            team["replacements"], personal["replacements"],
            lambda r: str(r.get("from", "")).strip().lower()),
        "snippets": _union_first_wins(
            team["snippets"], personal["snippets"],
            lambda s: str(s.get("trigger", "")).strip().lower()),
    }


def effective(config):
    """What dictation applies: the user's dictionary merged with their team's.

    Pure local read — `organizations.team_dictionary()` reads the config cache and
    never touches the network, so this is safe on the hot path."""
    try:
        from app import organizations
        team = organizations.team_dictionary(config)
        if not (team["vocabulary"] or team["replacements"] or team["snippets"]):
            return get(config)
        return merge_with_team(get(config), team)
    except Exception as e:
        logger.debug("effective dictionary failed, using personal only: %s", e)
        return get(config)


def effective_snippets(config):
    """Snippets that should expand — personal ∪ team. The Snippets SCREEN uses
    get_snippets() (personal only); this is the apply-time set."""
    try:
        return effective(config)["snippets"]
    except Exception:
        return get(config)["snippets"]


def build_prompt(config):
    """A Whisper `prompt` string that biases toward the user's vocabulary.

    The LAST terms are kept, not the first: Whisper only conditions on the tail
    (~224 tokens) of the prompt, and the tail of the vocabulary list is what the
    user taught it most recently. An over-long glossary is not merely ignored —
    every extra term is another word the model can drop into an unrelated
    sentence, and another line it can parrot back (see strip_prompt_echo)."""
    vocab = effective(config)["vocabulary"]
    if not vocab:
        return None
    words = vocab[-_MAX_PROMPT_TERMS:]
    # Trim from the FRONT, never the back: clipping the assembled string would
    # throw away exactly the newest terms this ordering is meant to protect.
    while words and len("Glossary: " + ", ".join(words) + ".") > _MAX_PROMPT_CHARS:
        words.pop(0)
    if not words:
        return None
    return "Glossary: " + ", ".join(words) + "."


# ── bias-prompt echo ("Glossary, M.T.:" showing up in a transcript) ───────────
# Whisper's `prompt` is a CONTINUATION prompt, not an instruction: the model is
# conditioned on it as though it were the transcript so far. Handed short, quiet
# or speech-free audio, the likeliest continuation of "Glossary: a, b, c." is
# MORE glossary — so the bias list comes back as the "transcription" and gets
# injected into whatever the user was typing into. That echo is recognizable
# because every token in it is text we sent ourselves, so it is stripped here
# instead of injected; a transcript that was nothing BUT echo becomes "", which
# the caller reports as silence.

_BIAS_LABELS = ("glossary", "vocabulary", "files")
_ANY_LABEL_RE = re.compile(r"\b(" + "|".join(_BIAS_LABELS) + r")\b\s*:", re.IGNORECASE)
# Headings WE invented, which therefore can't be something the user said: a bare
# "Glossary" chunk is ours whatever punctuation follows it (see strip_prompt_echo's
# `owned` rule). "Files" is deliberately NOT here — "Files, I need to check them"
# is a sentence someone really dictates, and that guard is why the comma form was
# left alone in the first place.
_OWNED_LABELS = ("glossary", "vocabulary")
# Chunk on commas/semicolons/newlines and on SENTENCE periods (a period followed
# by whitespace) so "M.T." and "main.py" survive as single chunks.
_CHUNK_RE = re.compile(r"(\s*[,;]\s*|\s*\.\s+|\s*\n+\s*)")


def _norm_term(s):
    """Casefold and reduce every non-alphanumeric run to one space:
    'M.T.:' and 'm t' both become 'm t', so an echo matches the term we sent."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def prompt_labels(prompt):
    """The section labels this prompt ACTUALLY carries ('Glossary:', 'Files:').

    Only these words are treated as labels when scanning a transcript, which is
    what keeps a dictated "Files, I need to check them" intact on a run where no
    file list was ever sent — we can only be echoed text we spoke first."""
    return {m.group(1).lower() for m in _ANY_LABEL_RE.finditer(prompt or "")}


def _label_re(labels):
    """Matcher for a leading label; group(1) is the label WORD (which decides
    whether it is one of ours per _OWNED_LABELS) and group(2) marks the ':' that
    makes it ours regardless."""
    if not labels:
        return None
    return re.compile(r"^\s*(" + "|".join(sorted(labels)) + r")\b\s*(:)?\s*", re.IGNORECASE)


def prompt_terms(prompt):
    """The individual biasing terms of a bias prompt, normalized for comparison.
    Handles both sections we send: 'Glossary: a, b. Files: c.d, e.f.'"""
    label_re = _label_re(prompt_labels(prompt))
    out = set()
    for raw in _CHUNK_RE.split(prompt or ""):
        t = _norm_term(label_re.sub("", raw) if label_re else raw)
        if t:
            out.add(t)
    return out


def strip_prompt_echo(text, prompt):
    """Remove regurgitated bias-prompt text from a transcription.

    Only words we actually SENT as labels count as labels (see prompt_labels).
    Deletes every run of chunks that is the glossary talking back to us:
      - a run introduced by a bias LABEL ('Glossary:', 'Files:') that is either
        followed by terms we sent, or STANDS ALONE — as its own fragment
        ('Glossary. So, the thing is…') or, for a heading we invented
        (_OWNED_LABELS), on ANY punctuation, which is what catches the dominant
        real-world form 'Glossary, <real speech>'. The cost of that last rule is
        that a sentence genuinely opening with the word "glossary" loses it on a
        run where a glossary was sent; the benefit is that the leak stops; and
      - a bare comma-list of TWO OR MORE consecutive chunks that are each exactly
        a term we sent — real speech is not a list of one's own jargon.
    A lone dictionary term is never dropped: that is just the user saying a word
    they taught us, and a label that keeps going inside its own clause ('Files, I
    need to check them') is speech, not a heading. A colon-punctuated label prefix
    is stripped even when real speech follows it ('Glossary: so I was thinking' →
    'so I was thinking').

    Returns "" when the transcript was nothing but echo. Never raises — on any
    error the text comes back untouched, per the fail-closed pipeline rule."""
    try:
        if not text or not text.strip() or not prompt:
            return text
        terms = prompt_terms(prompt)
        if not terms:
            return text
        label_re = _label_re(prompt_labels(prompt))

        parts = _CHUNK_RE.split(text)
        chunks, seps = parts[0::2], parts[1::2] + [""]
        n = len(chunks)

        info = []
        for k, c in enumerate(chunks):
            m = label_re.match(c) if label_re else None
            norm = _norm_term(c[m.end():] if m else c)
            # A heading standing on its own — 'Glossary:' or a 'Glossary.' ending
            # the fragment — is ours. One that runs on inside its clause
            # ('Files, I need to…') is the user talking.
            ends_fragment = k == n - 1 or "." in seps[k] or "\n" in seps[k]
            # ...and a bare heading we INVENTED is ours whatever follows it. This
            # is the common real-world echo: Whisper emits 'Glossary, <speech>'
            # far more often than 'Glossary. <speech>', and the comma form used to
            # survive because the separator rules above treat a comma as "the
            # clause keeps going, so this is speech".
            owned = bool(m) and m.group(1).lower() in _OWNED_LABELS
            info.append({"label": bool(m), "term": norm in terms, "empty": not norm,
                         "alone": bool(m) and not norm
                                  and (bool(m.group(2)) or ends_fragment or owned)})
            # A label punctuated like a label ('Glossary:') is ours, never
            # speech — peel the prefix off even if the chunk survives. Without
            # the colon it may well be a word the user said, so the chunk is
            # left intact and only the run rules below can remove it.
            if m and m.group(2):
                chunks[k] = c[m.end():]

        drop = [False] * n
        i = 0
        while i < n:
            it = info[i]
            nxt = info[i + 1] if i + 1 < n else None
            start = (it["alone"] or
                     (it["label"] and it["term"]) or
                     (it["label"] and it["empty"] and nxt is not None and nxt["term"]) or
                     (it["term"] and nxt is not None and nxt["term"]))
            if not start:
                i += 1
                continue
            j = i
            while j < n and (info[j]["term"] or info[j]["empty"]):
                drop[j] = True
                j += 1
            i = max(j, i + 1)

        # Rebuild unconditionally: even with no run to delete, a 'Glossary:'
        # prefix may have been peeled off an otherwise real sentence above.
        out = "".join("" if drop[k] else (chunks[k] + seps[k]) for k in range(n))
        out = re.sub(r"\s{2,}", " ", out).strip()
        out = re.sub(r"^[\s,;:.–—-]+", "", out).strip()
        return out if _norm_term(out) else ""
    except Exception as e:
        logger.debug("strip_prompt_echo failed: %s", e)
        return text


def known_terms(config, limit=60):
    """Distinct user-specific terms for GROUNDING THE CLEANUP LLM (Phase 0, MER-44).

    Combines the dictionary vocabulary with the corrected ("to") side of every
    replacement rule — which includes auto-learned fixes (add_replacement(...,
    auto=True)), so the auto-learn → grounding loop closes locally with no extra
    plumbing. These are the names / IDs / jargon the formatter should prefer over a
    phonetically-similar guess. Deduped case-insensitively (first spelling wins),
    capped at `limit` to bound prompt size. Never raises.

    Distinct from build_prompt(): that feeds Whisper's transcription bias
    (vocabulary only); this grounds the post-transcription cleanup model."""
    try:
        d = effective(config)
        terms, seen = [], set()
        for w in d["vocabulary"] + [r.get("to", "") for r in d["replacements"]]:
            w = (w or "").strip()
            k = w.lower()
            if w and k not in seen:
                seen.add(k)
                terms.append(w)
        return terms[:limit]
    except Exception as e:
        logger.debug("known_terms failed: %s", e)
        return []


def apply_replacements(text, config):
    """Apply the user's find→replace rules to a transcription (word-boundary,
    case-insensitive; preserves capitalization of the replacement)."""
    if not text:
        return text
    for r in effective(config)["replacements"]:
        frm, to = r["from"], r["to"]
        try:
            text = re.sub(r"\b" + re.escape(frm) + r"\b", to, text, flags=re.IGNORECASE)
        except re.error:
            # fall back to a plain, case-insensitive substring replace
            text = re.sub(re.escape(frm), to, text, flags=re.IGNORECASE)
    return text


# ── persistence (local + cloud) ────────────────────────────────────────────────
def save(config, vocabulary, replacements, save_config_fn):
    """Write the dictionary to config + push to the cloud (best-effort).

    Preserves any existing snippets — this saves only the vocabulary/replacement
    surface, so it must not wipe the sibling snippets array off the shared row."""
    d = normalize({"vocabulary": vocabulary, "replacements": replacements,
                   "snippets": get(config)["snippets"]})
    config["dictionary"] = d
    save_config_fn(config)
    _push_remote(config, d, save_config_fn)
    return d


def add_replacement(config, frm, to, save_config_fn, auto=False):
    """Append one replacement rule (used by auto-learn on edits).

    `auto=True` tags the rule as auto-learned (surfaced with a ✨ marker in the
    audit list); it is preserved by normalize() and does not affect existing
    {from,to} rules."""
    d = get(config)
    frm, to = (frm or "").strip(), (to or "").strip()
    if not frm or not to or frm.lower() == to.lower():
        return d
    # de-dupe by 'from'
    d["replacements"] = [r for r in d["replacements"] if r["from"].lower() != frm.lower()]
    rule = {"from": frm, "to": to}
    if auto:
        rule["auto"] = True
    d["replacements"].append(rule)
    config["dictionary"] = d
    save_config_fn(config)
    _push_remote(config, d, save_config_fn)
    return d


# ── snippets (spoken trigger → longer text expansion) ──────────────────────────
def get_snippets(config):
    """Return the normalized snippets list for this config."""
    return get(config)["snippets"]


def add_snippet(config, trigger, expansion, label, save_config_fn):
    """Append one snippet (dedupe by trigger, case-insensitive). Mirrors
    add_replacement: generates a short id, appends, saves + pushes remote."""
    d = get(config)
    trigger = (trigger or "").strip()[:_MAX_TRIGGER_CHARS].strip()
    expansion = (expansion or "").strip()[:_MAX_EXPANSION_CHARS]
    label = (label or "").strip()
    if not trigger or not expansion:
        return d
    # de-dupe by trigger (case-insensitive)
    d["snippets"] = [s for s in d["snippets"] if s["trigger"].lower() != trigger.lower()]
    now = _now_iso()
    d["snippets"].append({
        "id": _short_id(),
        "trigger": trigger,
        "expansion": expansion,
        "label": label,
        "used": 0,
        "created_at": now,
        "updated_at": now,
    })
    config["dictionary"] = d
    save_config_fn(config)
    _push_remote(config, d, save_config_fn)
    return d


def update_snippet(config, id, save_config_fn, **fields):
    """Patch a snippet by id. Accepts trigger/expansion/label/used; ignores
    unknown keys. Bumps updated_at. Saves + pushes remote."""
    d = get(config)
    for s in d["snippets"]:
        if s["id"] == id:
            if fields.get("trigger") is not None:
                new_trigger = str(fields["trigger"]).strip()[:_MAX_TRIGGER_CHARS].strip()
                if new_trigger:
                    s["trigger"] = new_trigger
            if fields.get("expansion") is not None:
                new_expansion = str(fields["expansion"]).strip()[:_MAX_EXPANSION_CHARS]
                if new_expansion:
                    s["expansion"] = new_expansion
            if fields.get("label") is not None:
                s["label"] = str(fields["label"]).strip()
            if fields.get("used") is not None:
                s["used"] = _coerce_used(fields["used"])
            s["updated_at"] = _now_iso()
            break
    config["dictionary"] = d
    save_config_fn(config)
    _push_remote(config, d, save_config_fn)
    return d


def remove_snippet(config, id, save_config_fn):
    """Delete a snippet by id. Saves + pushes remote."""
    d = get(config)
    d["snippets"] = [s for s in d["snippets"] if s["id"] != id]
    config["dictionary"] = d
    save_config_fn(config)
    _push_remote(config, d, save_config_fn)
    return d


def apply_snippets(text, config, save_config_fn=None):
    """Expand spoken trigger phrases into their saved text.

    ALGORITHM (fully guarded / fail-closed — any error returns text unchanged):
      - Case-INSENSITIVE match of each trigger as a whole phrase on word
        boundaries; multi-word aware (internal whitespace matches any run of
        whitespace), unlike the single-token replacement rules.
      - LONGEST trigger wins first, so "my email address" beats "my email".
      - SINGLE pass only: an inserted expansion is NEVER re-scanned for further
        triggers (re.sub does not rescan replacement text) — no recursion/cascade.
      - On each match, increment that snippet's 'used' counter and persist
        (only when save_config_fn is supplied; guarded/best-effort).

    Runs AFTER AI cleanup, immediately BEFORE injection. Must never break the
    dictation pipeline."""
    try:
        if not text or not isinstance(text, str):
            return text
        snippets = effective_snippets(config)
        valid = [s for s in snippets
                 if str(s.get("trigger", "")).strip() and str(s.get("expansion", "")).strip()]
        if not valid:
            return text
        # Longest trigger first so alternation prefers the longer phrase at a
        # given position (Python regex tries alternatives left-to-right).
        valid.sort(key=lambda s: len(s["trigger"]), reverse=True)
        lookup = {}
        parts = []
        for s in valid:
            norm_key = re.sub(r"\s+", " ", s["trigger"].strip().lower())
            lookup.setdefault(norm_key, s)
            # Escape each word, join with \s+ so internal whitespace matches any
            # run of whitespace (multi-word aware) without escaping the spaces.
            tokens = s["trigger"].strip().split()
            escaped = r"\s+".join(re.escape(tok) for tok in tokens)
            parts.append(escaped)
        pattern = re.compile(
            r"(?<![A-Za-z0-9_])(" + "|".join(parts) + r")(?![A-Za-z0-9_])",
            re.IGNORECASE,
        )
        used_keys = []

        def _repl(m):
            matched = m.group(1)
            key = re.sub(r"\s+", " ", matched.strip().lower())
            s = lookup.get(key)
            if s is None:
                return matched
            used_keys.append(key)  # stable across normalize() (triggers are unique)
            return s["expansion"]

        result = pattern.sub(_repl, text)
        if used_keys and save_config_fn is not None:
            _bump_snippet_used(config, used_keys, save_config_fn)
        return result
    except Exception as e:
        logger.debug("apply_snippets failed: %s", e)
        return text


def _bump_snippet_used(config, keys, save_config_fn):
    """Increment 'used' for each matched snippet (once per occurrence) and
    persist. Matches on the normalized trigger key — stable across normalize()
    calls, unlike client-generated ids which may not yet be persisted.
    Guarded/best-effort — never raises into the pipeline."""
    try:
        d = get(config)
        by_key = {re.sub(r"\s+", " ", s["trigger"].strip().lower()): s for s in d["snippets"]}
        changed = False
        now = _now_iso()
        for k in keys:
            s = by_key.get(k)
            if s is not None:
                s["used"] = _coerce_used(s.get("used")) + 1
                s["updated_at"] = now
                changed = True
        if changed:
            config["dictionary"] = d
            save_config_fn(config)
            _push_remote(config, d, save_config_fn)
    except Exception as e:
        logger.debug("snippet used bump failed: %s", e)


# ── CAS merge helpers (IDI-174) ────────────────────────────────────────────────
# The dictionary is ONE row per user shared by every device, and the old push was
# a blind full-row upsert: last writer won and silently erased whatever the other
# device had added in between (add a word on the phone, add a word on the Mac,
# one of them is simply gone). Writes are compare-and-swap now — filtered on the
# `updated_at` we read — and a lost race is MERGED rather than overwritten.
#
# These three are PURE (no config, no network) so the merge rules are
# fixture-testable on their own.

def merge_vocabulary(local, remote):
    """Case-insensitive UNION. Remote order first (it is the row that won the
    race), then whatever this device adds. First spelling of a term wins."""
    out, seen = [], set()
    for w in list(remote or []) + list(local or []):
        w = str(w or "").strip()
        k = w.lower()
        if w and k not in seen:
            seen.add(k)
            out.append(w)
    return out


def merge_replacements(local, remote):
    """Keyed by `from` (case-insensitive); the NEWER write wins — i.e. this
    device's pending rule beats the one already in the row, because it is the
    edit the user just made. Remote-only rules are preserved."""
    by_key, order = {}, []
    for r in list(remote or []) + list(local or []):
        if not isinstance(r, dict):
            continue
        frm = str(r.get("from", "")).strip()
        if not frm or not str(r.get("to", "")).strip():
            continue
        k = frm.lower()
        if k not in by_key:
            order.append(k)
        by_key[k] = r          # later (= local) overwrites earlier (= remote)
    return [by_key[k] for k in order]


def merge_snippets(local, remote):
    """Union by trigger (case-insensitive); on a collision the snippet with the
    newer `updated_at` wins, ties going to the local (pending) edit."""
    by_key, order = {}, []
    for s in list(remote or []) + list(local or []):
        if not isinstance(s, dict):
            continue
        trigger = str(s.get("trigger", "")).strip()
        if not trigger:
            continue
        k = trigger.lower()
        if k not in by_key:
            by_key[k] = s
            order.append(k)
            continue
        cur = by_key[k]
        # >= so a tie (or two blank timestamps) resolves to the later entry,
        # which is always the local one given the concatenation order above.
        if str(s.get("updated_at") or "") >= str(cur.get("updated_at") or ""):
            by_key[k] = s
    return [by_key[k] for k in order]


def merge_dictionary(local, remote):
    """Merge a pending local dictionary with the row that beat it to the write."""
    local, remote = normalize(local), normalize(remote)
    return {
        "vocabulary":   merge_vocabulary(local["vocabulary"], remote["vocabulary"]),
        "replacements": merge_replacements(local["replacements"], remote["replacements"]),
        "snippets":     merge_snippets(local["snippets"], remote["snippets"]),
    }


# Last cloud-write outcome, so a caller (the dashboard) can TELL the user the
# save didn't reach the account instead of silently pretending it did.
_LAST_PUSH = {"ok": True, "error": ""}


def last_sync_error() -> str:
    return "" if _LAST_PUSH.get("ok") else (_LAST_PUSH.get("error") or "")


def _cloud_gate(config) -> bool:
    """May the dictionary sync for the current account?

    Three-part gate (IDI-170/171): an account id, the user's `sync_enabled`
    toggle (the dictionary is "sync", unlike meetings/recordings), and a real
    signed-in session — `sync_user_id` alone survived `sign_out()` and kept
    pushing this device's vocabulary into the ex-account. Fail-closed."""
    try:
        cfg = config or {}
        if not cfg.get("sync_user_id") or not cfg.get("sync_enabled"):
            return False
        from app import auth
        return bool(auth.cloud_allowed(cfg))
    except Exception:
        return False


def fetch_remote(config, save_config_fn):
    """Pull the cloud dictionary and merge into config. Writes config ONLY when
    something actually changed (avoids needless save_config churn)."""
    user_id = config.get("sync_user_id", "")
    if not user_id or not _cloud_gate(config):
        return get(config)
    try:
        import httpx
        from app.sync import SUPABASE_URL
        from app.auth import auth_header
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/dictionary",
            headers=auth_header(config),
            params={"user_id": f"eq.{user_id}", "select": "vocabulary,replacements,snippets", "limit": "1"},
            timeout=8,
        )
        if resp.status_code == 200 and resp.json():
            remote = normalize(resp.json()[0])
            if remote != get(config):
                config["dictionary"] = remote
                save_config_fn(config)
            return remote
    except Exception as e:
        logger.debug("dictionary fetch failed: %s", e)
    return get(config)


_DICT_SELECT = "updated_at,vocabulary,replacements,snippets"


def _read_row(config, user_id):
    """Current cloud row (or None). Raises on transport errors."""
    import httpx
    from app.sync import SUPABASE_URL
    from app.auth import auth_header
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/dictionary",
        headers=auth_header(config),
        params={"user_id": f"eq.{user_id}", "select": _DICT_SELECT, "limit": "1"},
        timeout=8,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"dictionary read failed ({resp.status_code})")
    rows = resp.json() or []
    return rows[0] if rows else None


def _cas_patch(config, user_id, d, prev_updated_at):
    """One compare-and-swap attempt. Writes ALL columns, but ONLY if the row's
    `updated_at` is still the one we read. Returns True when a row was actually
    written (0 rows back = we lost the race)."""
    import datetime as _dt
    import httpx
    from app.auth import auth_header
    from app.sync import SUPABASE_URL
    resp = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/dictionary",
        headers={**auth_header(config, json=True),
                 # representation, not minimal — 0 rows returned is the ONLY
                 # way to detect that the filter matched nothing (PostgREST
                 # answers 204 either way otherwise).
                 "Prefer": "return=representation"},
        params={"user_id": f"eq.{user_id}", "updated_at": f"eq.{prev_updated_at}"},
        json={"vocabulary": d["vocabulary"],
              "replacements": d["replacements"],
              "snippets": d.get("snippets", []),
              "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat()},
        timeout=10,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"dictionary write failed ({resp.status_code})")
    body = resp.json() or []
    return bool(body)


def _insert_row(config, user_id, d):
    """First-ever write for this account: there is no row to compare against."""
    import datetime as _dt
    import httpx
    from app.auth import auth_header
    from app.sync import SUPABASE_URL
    resp = httpx.post(
        f"{SUPABASE_URL}/rest/v1/dictionary?on_conflict=user_id",
        headers={**auth_header(config, json=True),
                 "Prefer": "resolution=merge-duplicates,return=minimal"},
        json={"user_id": user_id, "vocabulary": d["vocabulary"],
              "replacements": d["replacements"],
              "snippets": d.get("snippets", []),
              "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat()},
        timeout=10,
    )
    if resp.status_code not in (200, 201, 204):
        raise RuntimeError(f"dictionary insert failed ({resp.status_code})")
    return True


def _push_remote(config, d, save_config_fn=None):
    """Compare-and-swap push (IDI-174).

    read updated_at → PATCH filtered on it → on 0 rows, refetch + MERGE + ONE
    retry. Both attempts failing is REPORTED (see `last_sync_error`), never
    swallowed: a dictionary that silently didn't save is worse than one that
    says so, because the user keeps re-teaching the same word."""
    global _LAST_PUSH
    user_id = config.get("sync_user_id", "")
    if not user_id or not _cloud_gate(config):
        _LAST_PUSH = {"ok": True, "error": ""}      # not a failure: sync is off
        return _LAST_PUSH
    try:
        row = _read_row(config, user_id)
        if row is None:
            _insert_row(config, user_id, d)
            _LAST_PUSH = {"ok": True, "error": ""}
            return _LAST_PUSH

        if _cas_patch(config, user_id, d, row.get("updated_at")):
            _LAST_PUSH = {"ok": True, "error": ""}
            return _LAST_PUSH

        # Lost the race — another device wrote between our read and our write.
        logger.info("dictionary CAS conflict — merging and retrying once")
        fresh = _read_row(config, user_id)
        if fresh is None:                            # row vanished (account reset)
            _insert_row(config, user_id, d)
            _LAST_PUSH = {"ok": True, "error": ""}
            return _LAST_PUSH
        merged = merge_dictionary(d, fresh)
        if _cas_patch(config, user_id, merged, fresh.get("updated_at")):
            # Keep the local copy consistent with what we just published.
            config["dictionary"] = merged
            if save_config_fn is not None:
                try:
                    save_config_fn(config)
                except Exception as e:
                    logger.debug("merged dictionary save failed: %s", e)
            _LAST_PUSH = {"ok": True, "error": ""}
            return _LAST_PUSH

        _LAST_PUSH = {"ok": False, "merged": merged,
                      "error": "Your dictionary is being edited on another "
                               "device — saved here, not synced. Try again."}
        logger.warning("dictionary CAS failed twice — not synced")
        return _LAST_PUSH
    except Exception as e:
        logger.debug("dictionary push failed: %s", e)
        _LAST_PUSH = {"ok": False, "error": f"Could not sync the dictionary: {e}"}
        return _LAST_PUSH
