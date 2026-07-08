"""
Custom dictionary — vocabulary biasing + replacement rules (desktop).

Two mechanisms, mirroring Wispr Flow:
  - vocabulary:   words/names/jargon injected into Whisper's `prompt` so the
                  model is biased toward recognizing/spelling them correctly.
  - replacements: exact find→replace rules applied AFTER transcription to fix
                  persistent mishearings (e.g. "shabar" → "Shabbar").

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


def normalize(d):
    """Return a well-formed {'vocabulary': [...], 'replacements': [...]}."""
    d = d if isinstance(d, dict) else {}
    vocab = [str(w).strip() for w in (d.get("vocabulary") or []) if str(w).strip()]
    reps = []
    for r in (d.get("replacements") or []):
        if isinstance(r, dict) and str(r.get("from", "")).strip() and str(r.get("to", "")).strip():
            reps.append({"from": str(r["from"]).strip(), "to": str(r["to"]).strip()})
    return {"vocabulary": vocab, "replacements": reps}


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
    """Write the dictionary to config + push to the cloud (best-effort)."""
    d = normalize({"vocabulary": vocabulary, "replacements": replacements})
    config["dictionary"] = d
    save_config_fn(config)
    _push_remote(config, d)
    return d


def add_replacement(config, frm, to, save_config_fn):
    """Append one replacement rule (used by auto-learn on edits)."""
    d = get(config)
    frm, to = (frm or "").strip(), (to or "").strip()
    if not frm or not to or frm.lower() == to.lower():
        return d
    # de-dupe by 'from'
    d["replacements"] = [r for r in d["replacements"] if r["from"].lower() != frm.lower()]
    d["replacements"].append({"from": frm, "to": to})
    config["dictionary"] = d
    save_config_fn(config)
    _push_remote(config, d)
    return d


def fetch_remote(config, save_config_fn):
    """Pull the cloud dictionary and merge into config. Writes config ONLY when
    something actually changed (avoids needless save_config churn)."""
    user_id = config.get("sync_user_id", "")
    if not user_id:
        return get(config)
    try:
        import httpx
        from app.sync import SUPABASE_KEY, SUPABASE_URL
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/dictionary",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"user_id": f"eq.{user_id}", "select": "vocabulary,replacements", "limit": "1"},
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


def _push_remote(config, d):
    user_id = config.get("sync_user_id", "")
    if not user_id:
        return
    try:
        import datetime as _dt
        import httpx
        from app.sync import SUPABASE_KEY, SUPABASE_URL
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/dictionary?on_conflict=user_id",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json",
                     "Prefer": "resolution=merge-duplicates,return=minimal"},
            json={"user_id": user_id, "vocabulary": d["vocabulary"],
                  "replacements": d["replacements"],
                  "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat()},
            timeout=10,
        )
    except Exception as e:
        logger.debug("dictionary push failed: %s", e)
