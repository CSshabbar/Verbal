import copy
import errno
import json
import logging
import os
import platform
import shutil
import stat
import tempfile
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("verbal.config")

# Serializes config reads AND writes so concurrent threads (sync, dictionary,
# device refresh, dashboard) never race on the same file. RLock because
# load_config() may call save_config() while still holding it.
# (a shared "config.tmp" name caused a rename race: config.tmp -> config.json).
_config_lock = threading.RLock()

# Backoff between attempts when Windows refuses a file op because another handle
# holds config.json (Defender/Search Indexer/an external reader): 20 ms doubling
# to 320 ms, ~620 ms worst case before we give up on THAT strategy.
_RETRY_BACKOFF = (0.02, 0.04, 0.08, 0.16, 0.32)

# The config text this process last read or wrote successfully. Consulted only
# when config.json EXISTS but cannot be read after retries (an out-of-process
# lock). Before 2026-08-26 that transient failure was handled like a corrupt
# file: config.json was moved to .bak and DEFAULT_CONFIG was saved over it, so an
# antivirus scan could silently sign the user out and drop their history.
_last_good_json: str | None = None
# True while this process runs on DEFAULT_CONFIG only because config.json exists
# but stayed unreadable on the first load (no in-memory copy to fall back on).
# The dict load_config hands out in that state is a factory reset that callers
# mutate and pass straight back to save_config (win_main migrates
# `hotkey_label` on startup, get_device_id mints an id, sync writes tokens) —
# and save_config alone cannot tell that dict from a trusted one. So save_config
# refuses to write anything while this is set; only a later load_config that
# actually reads the file clears it (2026-08-26 review of the Defender-lock fix).
_serving_unread_defaults = False
_last_tmp_sweep = 0.0

APP_VERSION = "1.0.38"
PLATFORM = "mac" if platform.system() == "Darwin" else "win" if platform.system() == "Windows" else "linux"

CONFIG_DIR = Path.home() / ".verbal"
CONFIG_FILE = CONFIG_DIR / "config.json"
# Marker key placed on a defaults dict served while config.json was unreadable
# (see load_config); save_config refuses to persist such a dict.
UNREAD_DEFAULTS_KEY = "__unread_defaults__"
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
    # Windows only: put the user's previous clipboard TEXT back after a dictation
    # paste has been consumed (win_injector.inject_text). Never restores on the
    # fallback path where the transcript is left on the clipboard because the
    # paste itself was blocked. macOS does not restore (yet).
    "restore_clipboard": True,
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


def _is_lock_error(e: OSError) -> bool:
    """True for the Windows 'someone else has this file' family — WinError 5
    ACCESS_DENIED (os.replace onto an open destination), 32 SHARING_VIOLATION,
    33 LOCK_VIOLATION — i.e. failures worth retrying, as opposed to a missing
    directory or a genuinely read-only location."""
    if isinstance(e, PermissionError):
        return True
    return getattr(e, "winerror", None) in (5, 32, 33) or e.errno in (5, 13)


def _sweep_stale_tmps(force: bool = False):
    """Remove orphaned `.config-*.tmp` files: a save that died between mkstemp
    and os.replace (crash, or the os._exit quit path in win_main) leaves one
    behind forever. Only files older than 60 s go, so a second process that is
    mid-write is never disturbed; throttled to once per 10 min unless forced.
    Best-effort — never raises."""
    global _last_tmp_sweep
    now = time.time()
    if not force and now - _last_tmp_sweep < 600:
        return
    _last_tmp_sweep = now
    try:
        for p in CONFIG_DIR.glob(".config-*.tmp"):
            try:
                if now - p.stat().st_mtime > 60:
                    p.unlink()
            except OSError:
                pass
    except Exception:
        pass


def _read_config_text() -> tuple[bytes | None, OSError | None]:
    """Read config.json, retrying Windows lock collisions with backoff.
    Returns (raw_bytes, None) on success, (None, None) if the file does not
    exist, (None, err) if it exists but stayed unreadable. Caller holds the lock.

    Returns BYTES on purpose: decoding happens in load_config's corrupt-file
    handler. A UnicodeDecodeError is a ValueError, not an OSError — a
    config.json cut mid-emoji (process killed during an in-place fallback write
    of non-ASCII history) used to escape here and crash VerbalWinApp.__init__
    on every launch, with the .prev safety net never consulted."""
    err = None
    for delay in _RETRY_BACKOFF + (None,):
        try:
            return CONFIG_FILE.read_bytes(), None
        except FileNotFoundError:
            return None, None
        except OSError as e:
            err = e
            if delay is None or not _is_lock_error(e):
                break
            time.sleep(delay)
    return None, err


def _recover_from_prev() -> dict | None:
    """`config.json.prev` exists only while an in-place fallback write is in
    flight (see _write_in_place). If config.json is corrupt and .prev parses,
    the process died mid-write and .prev is the last good state."""
    prev = CONFIG_FILE.with_suffix(".json.prev")
    try:
        if prev.exists():
            cfg = json.loads(prev.read_bytes().decode("utf-8-sig"))
            if isinstance(cfg, dict):
                logger.warning("config.json was corrupt; restored from config.json.prev")
                return cfg
    except Exception:
        pass
    return None


def load_config() -> dict:
    global _last_good_json, _serving_unread_defaults
    ensure_dirs()
    load_dotenv(ENV_FILE)

    config = None
    persist = True    # False = we could not read the file; never write defaults over it
    restored = False  # True = recovered after corruption; config.json is gone, re-persist
    with _config_lock:
        _sweep_stale_tmps()
        raw, err = _read_config_text()
        if raw is not None:
            try:
                # Decode INSIDE the handler: UnicodeDecodeError is a ValueError,
                # so a torn UTF-8 file takes the corrupt path below instead of
                # propagating out of load_config.
                # utf-8-sig: a config.json saved by an editor/PowerShell with a
                # UTF-8 BOM is NOT corrupt — treating it so moved the file aside
                # and reset the user to defaults (signed out, auto_update back
                # on), seen live 2026-08-28.
                text = raw.decode("utf-8-sig")
                config = json.loads(text)
                if not isinstance(config, dict):
                    raise ValueError("config root is not a JSON object")
                _last_good_json = text
                _serving_unread_defaults = False
                # A .prev left behind by a fallback write that completed but
                # did not get to unlink it (or was superseded by a later
                # atomic save): config.json is fine, so it is just litter.
                try:
                    CONFIG_FILE.with_suffix(".json.prev").unlink()
                except OSError:
                    pass
            except ValueError as e:
                # Genuinely corrupt on disk (JSON/UTF-8 error). Move it aside as
                # config.json.bak. os.replace, NOT Path.rename: os.rename on
                # Windows fails with WinError 183 when a previous .bak exists
                # ("Cannot create a file when that file already exists",
                # 2026-08-26 user log). Then prefer the .prev safety copy over a
                # factory reset.
                logger.warning("config.json is corrupt (%s); moving it to config.json.bak", e)
                try:
                    os.replace(CONFIG_FILE, CONFIG_FILE.with_suffix(".json.bak"))
                except OSError as e2:
                    logger.warning("could not move corrupt config.json aside: %s", e2)
                # Best surviving state first: what THIS process last read/wrote
                # (something external trashed the file), else the .prev snapshot
                # of an interrupted in-place write, else a factory reset.
                if _last_good_json is not None:
                    try:
                        config = json.loads(_last_good_json)
                        logger.warning("restored config from in-memory copy")
                    except ValueError:
                        config = None
                if config is None:
                    config = _recover_from_prev()
                if config is not None:
                    restored = True
                # Whatever we end up with, the on-disk file is gone (.bak), so
                # this process now owns the state and may persist it.
                _serving_unread_defaults = False
        elif err is not None:
            # The file exists but another handle kept it unreadable for the whole
            # retry window. This is NOT corruption — do not touch the file on
            # disk. Serve the last copy this process read/wrote; if there is none
            # (first load of the process), run on defaults but refuse to persist
            # them — here AND in every later save_config (see
            # _serving_unread_defaults): the caller will mutate this dict and
            # hand it back, and writing it would be a factory reset over the
            # real config.
            if _last_good_json is not None:
                try:
                    config = json.loads(_last_good_json)
                    logger.warning("config.json unreadable (%s); using last in-memory copy", err)
                except ValueError:
                    config = None
            if config is None:
                logger.error("config.json unreadable (%s) and no in-memory copy; "
                             "running on defaults WITHOUT persisting them", err)
                persist = False
                _serving_unread_defaults = True
                # The dict itself is marked too: the module flag clears as soon
                # as ANY later load_config() reads the file cleanly (auth.py and
                # the dashboard call it constantly), but VerbalWinApp.config
                # still holds THIS factory-default dict and would then save it
                # over the user's real file (signed out, history gone).
                # save_config refuses the marked dict regardless of the flag
                # (the marker is applied below, once the defaults dict exists).
        else:
            # No config.json at all: a genuine first run, defaults are legitimate.
            _serving_unread_defaults = False

        changed = False
        if config is None:
            # Deep copy: DEFAULT_CONFIG holds mutable lists (history, meetings, …) and
            # a shallow dict() would let the first append leak into the defaults.
            config = copy.deepcopy(DEFAULT_CONFIG)
            if _serving_unread_defaults:
                config[UNREAD_DEFAULTS_KEY] = True
            changed = True
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
                changed = True

            for key, val in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = copy.deepcopy(val)
                    changed = True

        env_key = os.getenv("GEMINI_API_KEY", "").strip()
        if env_key and env_key not in config["gemini_api_keys"]:
            config["gemini_api_keys"].insert(0, env_key)
            changed = True

        # Still under _config_lock (RLock: save_config re-enters it). The
        # read -> decide -> persist sequence must be one critical section:
        # before 2026-08-28 the lock was released above and re-taken inside
        # save_config, so another thread's save could land in the gap and be
        # overwritten by this thread's just-loaded copy (lost update — seen as a
        # risk at Windows startup where win_main, auth and sync all load/save
        # within the first second). Nothing below sleeps except save_config's own
        # Windows-lock retries, which were already lock-held.
        if (changed or restored) and persist:
            save_config(config)
            if restored:
                # The recovered state is back on disk atomically; the .prev
                # snapshot has served its purpose. Under the lock: another thread's
                # save_config may be mid _write_in_place, and its freshly made .prev
                # is the only copy of config.json while that file sits truncated.
                try:
                    CONFIG_FILE.with_suffix(".json.prev").unlink()
                except OSError:
                    pass
    return config


def _replace_config(tmp_path: str) -> bool:
    """Atomically move the temp file onto config.json. True on success; False
    when Windows kept refusing for the whole retry window (the caller then
    falls back to an in-place write). Any non-lock OSError propagates.

    On Windows, `os.replace` of a destination another handle still has open
    without FILE_SHARE_DELETE (Defender/Search Indexer scanning it, or any
    external reader) raises WinError 5 Access Denied — 2026-08-25/26 user logs
    show ~12 of them per session, each of which used to discard the save and
    drop auth to the anon key. In-process readers take `_config_lock`, so every
    remaining collision is out-of-process and short-lived: retry with backoff.
    """
    if os.name == "nt" and CONFIG_FILE.exists():
        try:
            os.chmod(CONFIG_FILE, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass
    last = None
    for delay in _RETRY_BACKOFF + (None,):
        try:
            os.replace(tmp_path, CONFIG_FILE)
            return True
        except OSError as e:
            if not _is_lock_error(e):
                raise
            last = e
            if delay is None:
                break
            time.sleep(delay)
    logger.warning("os.replace onto config.json kept failing (%s); writing in place", last)
    return False


def _write_in_place(data: str):
    """Last resort when os.replace cannot win: overwrite config.json where it
    stands. A handle that blocks a rename (no FILE_SHARE_DELETE) normally still
    allows writes (Python and most scanners open with FILE_SHARE_READ|WRITE), so
    this succeeds where the rename could not — the save is preserved instead of
    lost. It is NOT atomic, so the current file is first copied to
    config.json.prev; load_config restores from .prev if a crash mid-write
    leaves config.json truncated, and .prev is removed once the write lands.
    """
    prev = CONFIG_FILE.with_suffix(".json.prev")
    if CONFIG_FILE.exists():
        try:
            shutil.copyfile(CONFIG_FILE, prev)
        except OSError as e:
            logger.warning("could not snapshot config.json to .prev before in-place write: %s", e)
    for delay in _RETRY_BACKOFF + (None,):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            break
        except OSError as e:
            if delay is None or not _is_lock_error(e):
                raise
            time.sleep(delay)
    try:
        prev.unlink()
    except OSError:
        pass


def _refuse_untrusted_save():
    """Called under the lock when this process is still running on the defaults
    load_config served because config.json was unreadable. The dict a caller
    wants saved descends from that factory reset, so writing it — atomically or
    in place — would wipe the user's real sign-in and history the moment the
    external lock lets go. Raise OSError (the contract save_config already had
    when os.replace gave up), so peripheral callers' except blocks fail closed
    and the real file is left untouched until a load_config can read it."""
    raw, err = _read_config_text()
    if raw is not None:
        # The file is readable again, but the caller's dict is still the stale
        # defaults; only a fresh load_config may hand out a writable config.
        raise OSError(
            errno.EACCES,
            "save_config refused: this process is running on unread defaults; "
            "config.json is readable again - reload it before saving")
    raise OSError(
        errno.EACCES,
        "save_config refused: this process is running on unread defaults and "
        "config.json is still unreadable (%s)" % (err,))


def save_config(config: dict):
    """Persist config. Atomic (unique tempfile + os.replace) under `_config_lock`;
    on Windows, falls back to an in-place write rather than losing the save when
    an external handle blocks the rename. The temp file is always removed.
    Raises OSError without touching the file while `_serving_unread_defaults`."""
    global _last_good_json
    ensure_dirs()
    # Unique temp file per write + a lock → safe under concurrent writers
    # (a shared "config.tmp" name caused rename races: config.tmp -> config.json).
    with _config_lock:
        if _serving_unread_defaults or (isinstance(config, dict) and config.get(UNREAD_DEFAULTS_KEY)):
            _refuse_untrusted_save()
        _sweep_stale_tmps()
        data = json.dumps(config, indent=2)
        fd, tmp_path = tempfile.mkstemp(dir=str(CONFIG_DIR), prefix=".config-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            if not _replace_config(tmp_path):
                _write_in_place(data)
                _sweep_stale_tmps(force=True)
            _last_good_json = data
        finally:
            # Replaced (already gone), fell back, or failed: never leave
            # `.config-*.tmp` litter in ~/.verbal.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


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
