"""
Recording storage for the Mac app.

Every recording is saved locally (16 kHz mono WAV) the moment it's captured —
this is both the playback backup and the retry cache (so a failed transcription
can be retried from the saved audio). The primary copy is uploaded to Supabase
Storage so any device can play it; playback prefers the local file and falls
back to the cloud URL.
"""
import logging
import os
import subprocess
import uuid

import numpy as np
import soundfile as sf

from app.config import CONFIG_DIR
from app.sync import REST_URL, SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger("verbal.recordings")

RECORDINGS_DIR = CONFIG_DIR / "recordings"
BUCKET = "recordings"
STORAGE_URL = f"{SUPABASE_URL}/storage/v1"

MAX_LOCAL_FILES = 60  # keep the most recent N local WAVs


def ensure_dir():
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def path_for(rec_id: str) -> str:
    return str(RECORDINGS_DIR / f"{rec_id}.wav")


def save_wav(audio: np.ndarray, sample_rate: int, rec_id: str) -> str | None:
    """Save `audio` as a 16 kHz mono WAV. Returns the local path (or None)."""
    if audio is None or len(audio) == 0:
        return None
    ensure_dir()
    try:
        audio16 = _to_16k(audio, sample_rate)
        p = path_for(rec_id)
        sf.write(p, audio16, 16000)
        prune()
        return p
    except Exception as e:
        logger.error(f"save_wav failed: {e}")
        return None


def load_wav(path: str):
    """Return (audio float32, sample_rate) from a WAV, or (None, 0)."""
    try:
        data, sr = sf.read(path, dtype="float32")
        if getattr(data, "ndim", 1) > 1:
            data = data[:, 0]
        return data, sr
    except Exception as e:
        logger.error(f"load_wav failed: {e}")
        return None, 0


def _to_16k(audio: np.ndarray, orig_rate: int) -> np.ndarray:
    if orig_rate == 16000:
        return audio.astype(np.float32)
    try:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(int(orig_rate), 16000)
        return resample_poly(audio, 16000 // g, int(orig_rate) // g).astype(np.float32)
    except Exception:
        ratio = orig_rate / 16000
        idx = np.arange(0, len(audio), ratio).astype(int)
        idx = idx[idx < len(audio)]
        return audio[idx].astype(np.float32)


def prune(max_files: int = MAX_LOCAL_FILES):
    """Delete the oldest local WAVs beyond max_files."""
    try:
        files = sorted(
            (RECORDINGS_DIR / f for f in os.listdir(RECORDINGS_DIR) if f.endswith(".wav")),
            key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[max_files:]:
            try:
                p.unlink()
            except Exception:
                pass
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"prune failed: {e}")


# ── cloud (Supabase Storage) ───────────────────────────────────────────────────
def upload_cloud(local_path: str, user_id: str, rec_id: str) -> str | None:
    """Upload the WAV to the `recordings` bucket. Returns the bare object path
    (NOT a URL — the bucket is private, MER-27) or None."""
    if not user_id or not local_path or not os.path.exists(local_path):
        return None
    try:
        import httpx
        object_path = f"{user_id}/{rec_id}.wav"
        with open(local_path, "rb") as f:
            data = f.read()
        r = httpx.post(
            f"{STORAGE_URL}/object/{BUCKET}/{object_path}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "audio/wav",
                "x-upsert": "true",
            },
            content=data, timeout=30)
        if r.status_code in (200, 201):
            return object_path
        logger.warning(f"upload_cloud failed {r.status_code}: {r.text[:160]}")
    except Exception as e:
        logger.warning(f"upload_cloud error: {e}")
    return None


def extract_object_path(stored_value: str, bucket: str) -> str:
    """`stored_value` may be a bare object path (new writes, MER-27) or a legacy
    `.../object/public/<bucket>/<path>` URL (rows written before MER-27) — accept
    either so old rows keep working without a backfill migration."""
    marker = f"/object/public/{bucket}/"
    if stored_value and marker in stored_value:
        return stored_value.split(marker, 1)[1]
    return stored_value


def sign_url(bucket: str, object_path: str, expires_in: int = 180) -> str | None:
    """Generate a short-lived signed URL for a private-bucket object. Both
    buckets' storage.objects policies are `TO public` (Hard Rule #10), so the
    anon key is sufficient — desktop never has a per-user JWT."""
    try:
        import httpx
        r = httpx.post(
            f"{STORAGE_URL}/object/sign/{bucket}/{object_path}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json"},
            json={"expiresIn": expires_in}, timeout=15)
        if r.status_code == 200:
            signed = r.json().get("signedURL")
            if signed:
                return f"{STORAGE_URL}{signed}"
        logger.warning(f"sign_url failed {r.status_code}: {r.text[:160]}")
    except Exception as e:
        logger.warning(f"sign_url error: {e}")
    return None


def download(url: str, dest_path: str) -> bool:
    try:
        import httpx
        r = httpx.get(url, timeout=30)
        if r.status_code == 200:
            with open(dest_path, "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        logger.warning(f"download failed: {e}")
    return False


def play(path: str):
    """Play a local WAV without blocking (macOS afplay)."""
    try:
        subprocess.Popen(["afplay", path])
        return True
    except Exception as e:
        logger.error(f"play failed: {e}")
        return False
