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
"""
import logging
import re

logger = logging.getLogger("verbal.dictionary")

_MAX_PROMPT_WORDS = 180  # Whisper prompt is ~224 tokens; stay well under
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
    return normalize(config.get("dictionary"))


def build_prompt(config):
    """A Whisper `prompt` string that biases toward the user's vocabulary."""
    vocab = get(config)["vocabulary"]
    if not vocab:
        return None
    words = vocab[:200]
    prompt = "Glossary: " + ", ".join(words) + "."
    # keep it short
    parts = prompt.split()
    if len(parts) > _MAX_PROMPT_WORDS:
        prompt = " ".join(parts[:_MAX_PROMPT_WORDS])
    return prompt


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
        d = get(config)
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
    for r in get(config)["replacements"]:
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
        snippets = get_snippets(config)
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
