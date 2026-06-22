import json
import os
import platform
from pathlib import Path

from dotenv import load_dotenv

APP_VERSION = "1.0.8"
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
}


def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


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
    tmp = CONFIG_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(config, f, indent=2)
    tmp.replace(CONFIG_FILE)


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


def add_to_history(config: dict, text: str, app_name: str = "") -> dict:
    from datetime import date as _date
    entry = {"text": text, "app": app_name, "ts": str(_date.today())}
    history = config.get("history", [])
    history.insert(0, entry)
    config["history"] = history[:50]
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
