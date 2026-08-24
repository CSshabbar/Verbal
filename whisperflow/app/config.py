import json
import os
import platform
import tempfile
import threading
from pathlib import Path

from dotenv import load_dotenv

# Serializes config writes so concurrent threads (sync, dictionary, device
# refresh, dashboard) never race on the same temp file.
_config_lock = threading.Lock()

APP_VERSION = "1.0.16"
PLATFORM = "mac" if platform.system() == "Darwin" else "win" if platform.system() == "Windows" else "linux"

CONFIG_DIR = Path.home() / ".verbal"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_DIR = CONFIG_DIR / "logs"
ENV_FILE = Path(__file__).parent.parent / ".env"

DEFAULT_CONFIG = {
    "whisper_model": "base",
    "hotkey": "cmd_r",
    "groq_api_keys": [],
    "gemini_api_keys": [],
    "active_gemini_key_index": 0,
    "command_keywords": [
        "make", "fix", "convert", "formal", "casual", "bullet",
        "summarize", "rephrase", "translate", "shorter", "longer"
    ],
    "recording_mode": "toggle",
    "hotkey_hold": 54 if PLATFORM == "mac" else "alt_r",
    "hotkey_toggle": 54 if PLATFORM == "mac" else "alt_r",
    "history": [],       # list of {"text": str, "app": str, "ts": str}
    "pinned": [],        # list of {"text": str, "app": str, "ts": str}
    "daily": {"date": "", "words": 0},
    "auto_update": True,
    "sync_user_id":     "",
    "sync_device_name": "",
    # Notes v2 per-user feature flags (default ON, toggleable in Settings).
    # Each gates one of the four Notes-enhancement features; see
    # NOTES_ENHANCEMENT_SWARM.md Decision 4.
    "notes_search_enabled": True,
    "notes_autotitle_enabled": True,
    "notes_structure_detection_enabled": True,
    "notes_audio_linkage_enabled": True,
    # Meetings (MEETINGS_DESIGN_HANDOFF.md). Metadata lives in config["meetings"]
    # as a bounded list (cap MEETINGS_CAP, like history); full transcripts live in
    # the Supabase `meetings` row + local per-meeting audio files.
    "meetings_enabled": True,
    "meetings_keep_audio": True,          # keep the meeting WAV on disk / in cloud
    "meetings_keep_audio_days": 0,        # 7 | 30 | 90 | 0 (= never delete, default — MER-31 reaper is opt-in)
    "meetings_max_minutes": 120,          # 30 | 60 | 120 | 180 | 360 | 0 (= no limit)
    "meetings_hud_enabled": True,         # floating HUD when the window loses focus
    "meetings_speaker_labels": True,      # source-based Speaker 1..N labeling
    "meetings_sync_enabled": False,       # push meetings to other devices (default off)
    "meetings_notes_language": "en",      # summary/notes output language: "en" (always
                                           # English) | "auto" (match the meeting's spoken
                                           # language) — independent of transcription language
    "meetings": [],                       # [{id,title,started_at,duration_seconds,status,...}]
    # Transform (TRANSFORM_SWARM.md) — voice/prompt-driven text reshaping.
    # Master default OFF (like autolearn); Mode A = trailing "…so Flume, …"
    # instruction on a dictation; Mode B = selection transform via Cmd+Shift+T.
    "transform_enabled": False,
    "transform_inline_enabled": True,     # Mode A (gated by master)
    "transform_selection_enabled": True,  # Mode B (gated by master)
    "transform_trigger_words": ["flume", "flumes", "flu me", "plume", "bloom"],
    "transform_hotkey": 17,               # keycode for T — fires on Cmd+Shift+T
    "transform_hotkey_label": "T",
    # Spoken language for transcription (dictation + meetings). ISO-639-1 code
    # or "auto". Default "en" preserves the original pinned-English behavior;
    # non-English pins route Groq to full whisper-large-v3.
    "spoken_language": "en",
    "hotkey_label": "Right ⌘",            # display label for the dictation key
    # Context grounding (MER-44 Phase 0). Feeds the user's dictionary terms +
    # active-app hint into the cleanup LLM so it grounds identifiers/names instead
    # of guessing. Default ON — it's low-risk grounding DATA (never a directive to
    # collapse), fail-closed, and adds only a small bounded token cost per call.
    "context_grounding_enabled": True,
    # Latency pass (2026-08-14). ONE master switch so old-vs-new can be A/B'd by
    # flipping a single value, and so "old" is always reachable. Default False =
    # byte-identical to the measured v1.1.0-baseline behaviour.
    #
    # When True, four things change, all in the post-transcription path:
    #   1. transcripts of <= _SKIP_CLEANUP_MAX_WORDS words skip the LLM entirely
    #      (17% of real dictations are under 3s and were paying a full round trip)
    #   2. the 18-rule SYSTEM_PROMPT (~2,476 tokens of prefill on EVERY call) is
    #      replaced by LEAN_SYSTEM_PROMPT
    #   3. formatting runs on a faster model (see SPEED_CLEANUP_MODEL)
    #   4. fixed sleeps in the record->inject path are skipped
    # Measured baseline it is being compared against: 1.02s ASR + ~1.2s formatting.
    "speed_mode": False,
    # Chained transcription (2026-08-14). INDEPENDENT of speed_mode, so the two
    # can be measured separately — this one changes only the network path, not
    # the prompt, the model, or the output.
    #
    # Off: Mac -> proxy -> Groq (hear), then Mac -> proxy -> Groq (format).
    #      Two round trips, 8 internet crossings for ~370ms of model work.
    # On:  Mac -> proxy -> Groq (hear) -> Groq (format) -> Mac.
    #      One round trip; the hand-off happens inside the edge function, which
    #      sits next to Groq. Measured saving: 0.57s, CI [+0.38, +0.80].
    #
    # The client still supplies the system prompt and user message, so WHICH
    # prompt and model get used is still decided by speed_mode — chaining moves
    # the call, it does not change it. Fails closed: if the server-side format
    # step errors it returns chain.ok=false and the client formats locally, so
    # a chain failure costs latency, never a dictation.
    "chained_mode": False,
    # Which Groq Whisper model transcribes. "auto" keeps the long-standing routing
    # (turbo for English, full large-v3 for any pinned non-English language, because
    # the distil is measurably weaker on lower-resource languages) — anything else is
    # an explicit override that applies to every language.
    #
    # Only Groq models are selectable here, and that is deliberate: every other provider
    # evaluated (ElevenLabs, AssemblyAI, NVIDIA, Qwen) would need its key held by the
    # `groq-proxy` Edge Function to satisfy Hard Rule #15 — no client-side provider
    # keys, ever. Until that exists they are lab-only.
    "asr_model": "auto",
    # Hybrid (2026-08-15). Streams audio to `asr-stream` WHILE you speak, then uses
    # the streamed transcript for takes at/over asr_stream.HYBRID_THRESHOLD_SEC and
    # falls back to the ordinary chained path for shorter ones (Groq is faster there).
    # Implies chained_mode for the short branch. Default False; every failure path
    # degrades to the normal upload, so this can only ever cost latency.
    "hybrid_mode": False,
    # Post-meeting speaker diarization (2026-08-16). The live 90s-gap heuristic can
    # only split remote speakers across long silences; this re-partitions them from
    # real who-spoke-when (AssemblyAI, via the proxy, on the already-uploaded WAV)
    # before voiceprint and the summary run. Default ON because the correction is
    # exactly what meeting notes exist for; fails closed to the gap labels.
    "meetings_diarize_enabled": True,
}

# Settings the dashboard may flip individually. Same "only overwrite when present"
# discipline as NOTES_FEATURE_FLAGS: a partial payload must never reset a sibling.
PIPELINE_FLAGS = (
    "speed_mode",
    "chained_mode",
    "hybrid_mode",
)

# Bounded local meeting-metadata list (mirrors the history cap pattern).
MEETINGS_CAP = 30

# The four Notes v2 feature flags, in one place so callers can iterate them.
NOTES_FEATURE_FLAGS = (
    "notes_search_enabled",
    "notes_autotitle_enabled",
    "notes_structure_detection_enabled",
    "notes_audio_linkage_enabled",
)


def feature_flag(config: dict, name: str, default: bool = True) -> bool:
    """Read a per-user boolean feature flag, defaulting to ``default`` (True) when
    absent or malformed. Never raises."""
    try:
        val = config.get(name, default)
    except Exception:
        return default
    return bool(val) if isinstance(val, bool) else default


def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "recordings").mkdir(parents=True, exist_ok=True)


def get_device_id(config: dict) -> str:
    """This install's STABLE device identity (IDI-177). `platform.node()` was
    the old id — two Macs sharing a hostname collided in the `devices` table
    and (post-IDI-173) dropped each other's canvas updates. Minted once per
    install, persisted in config, independent of hostname/account/rename.
    Never raises; falls back to the hostname if config can't be saved."""
    try:
        did = (config.get("device_uuid") or "").strip()
        if did:
            return did
        import uuid
        did = f"dev_{uuid.uuid4().hex[:12]}"
        config["device_uuid"] = did
        save_config(config)
        return did
    except Exception:
        import platform
        return platform.node() or "desktop"


def load_config() -> dict:
    ensure_dirs()
    load_dotenv(ENV_FILE)

    config = None
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
        except (json.JSONDecodeError, Exception):
            backup = CONFIG_FILE.with_suffix(".json.bak")
            CONFIG_FILE.rename(backup)

    if config is None:
        config = dict(DEFAULT_CONFIG)
    else:
        # Migration: if old hotkey exists and new ones don't
        if "hotkey" in config and "hotkey_hold" not in config:
            old = config["hotkey"]
            # Convert known legacy strings to keycodes/names
            if old == "cmd_r":   val = 54
            elif old == "alt_r":  val = "alt_r"
            else: val = old
            config["hotkey_hold"] = val
            config["hotkey_toggle"] = val

        for key, val in DEFAULT_CONFIG.items():
            config.setdefault(key, val)

    env_key = os.getenv("GEMINI_API_KEY", "").strip()
    if env_key and env_key not in config["gemini_api_keys"]:
        config["gemini_api_keys"].insert(0, env_key)

    save_config(config)
    return config


def save_config(config: dict):
    ensure_dirs()
    # Unique temp file per write + a lock → safe under concurrent writers
    # (a shared "config.tmp" name caused rename races: config.tmp -> config.json).
    with _config_lock:
        fd, tmp_path = tempfile.mkstemp(dir=str(CONFIG_DIR), prefix=".config-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(config, f, indent=2)
            os.replace(tmp_path, CONFIG_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


def add_gemini_key(config: dict, key: str) -> dict:
    key = key.strip()
    if key and key not in config["gemini_api_keys"]:
        config["gemini_api_keys"].append(key)
        save_config(config)
    return config


def remove_gemini_key(config: dict, index: int) -> dict:
    if 0 <= index < len(config["gemini_api_keys"]):
        config["gemini_api_keys"].pop(index)
        if config["active_gemini_key_index"] >= len(config["gemini_api_keys"]):
            config["active_gemini_key_index"] = max(0, len(config["gemini_api_keys"]) - 1)
        save_config(config)
    return config


def get_active_gemini_key(config: dict) -> str | None:
    keys = config.get("gemini_api_keys", [])
    if not keys:
        return None
    idx = config.get("active_gemini_key_index", 0)
    if idx >= len(keys):
        idx = 0
    return keys[idx]


def rotate_gemini_key(config: dict) -> str | None:
    keys = config.get("gemini_api_keys", [])
    if len(keys) <= 1:
        return None
    idx = config.get("active_gemini_key_index", 0)
    new_idx = (idx + 1) % len(keys)
    config["active_gemini_key_index"] = new_idx
    save_config(config)
    return keys[new_idx]


def add_to_history(config: dict, text: str, app_name: str = "",
                   entry_id: str = "", audio: str = "", audio_url: str = "",
                   status: str = "done") -> dict:
    from datetime import date as _date
    import uuid
    entry = {
        "id": entry_id or uuid.uuid4().hex[:16],
        "text": text,
        "app": app_name,
        "ts": str(_date.today()),
        "audio": audio,          # local WAV path (backup + retry cache)
        "audio_url": audio_url,  # cloud URL (primary, cross-device)
        "status": status,        # 'done' | 'failed'
    }
    history = config.get("history", [])
    history.insert(0, entry)
    config["history"] = history[:50]
    save_config(config)
    return config


def update_history_entry(config: dict, entry_id: str, **fields) -> dict:
    """Update fields on the history entry with the given id (by identity)."""
    for e in config.get("history", []):
        if isinstance(e, dict) and e.get("id") == entry_id:
            e.update(fields)
            break
    save_config(config)
    return config


def update_daily_words(config: dict, word_count: int) -> dict:
    from datetime import date as _date
    today = str(_date.today())
    daily = config.get("daily", {"date": "", "words": 0})
    if daily.get("date") != today:
        daily = {"date": today, "words": 0}
    daily["words"] = daily.get("words", 0) + word_count
    config["daily"] = daily
    save_config(config)
    return config


def get_daily_words(config: dict) -> int:
    from datetime import date as _date
    daily = config.get("daily", {"date": "", "words": 0})
    if daily.get("date") != str(_date.today()):
        return 0
    return daily.get("words", 0)


def _entry_text(entry) -> str:
    """Safely extract text from a history entry (str or dict)."""
    if isinstance(entry, dict):
        return entry.get("text", "")
    return str(entry)


def _entry_app(entry) -> str:
    """Safely extract app name from a history entry."""
    if isinstance(entry, dict):
        return entry.get("app", "")
    return ""
