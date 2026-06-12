"""
Verbal auto-updater — checks Supabase for new versions, downloads and installs.

Works on both Mac and Windows. Stores version metadata in the `app_versions`
Supabase table and release binaries in Supabase Storage.
"""

import hashlib
import logging
import os
import platform
import subprocess
import sys
import tempfile

import httpx

from app.config import APP_VERSION, PLATFORM
from app.sync import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger("verbal.updater")


def check_for_update() -> dict | None:
    """Poll Supabase for the latest version. Returns info dict or None."""
    try:
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/app_versions",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            params={
                "platform": f"eq.{PLATFORM}",
                "select": "version,changelog,file_url,file_hash,file_size,released_at",
                "order": "released_at.desc",
                "limit": "1",
            },
            timeout=5,
        )
        if resp.status_code != 200:
            logger.debug(f"Update check returned {resp.status_code}")
            return None
        data = resp.json()
        if not data:
            return None
        latest = data[0]
        if _is_newer(latest["version"], APP_VERSION):
            logger.info(f"Update available: {APP_VERSION} -> {latest['version']}")
            return latest
        return None
    except Exception as e:
        logger.debug(f"Update check failed: {e}")
        return None


def download_update(version_info: dict, on_progress=None) -> str | None:
    """Download the installer to a temp file. Returns local path or None."""
    try:
        url = version_info["file_url"]
        expected_hash = version_info.get("file_hash")
        total_size = version_info.get("file_size", 0)

        suffix = ".exe" if PLATFORM == "win" else ".dmg"
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)

        with open(tmp_path, "wb") as f:
            with httpx.stream("GET", url, follow_redirects=True, timeout=60) as stream:
                downloaded = 0
                for chunk in stream.iter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size and on_progress:
                        on_progress(downloaded / total_size)

        if expected_hash:
            actual = _sha256(tmp_path)
            if actual != expected_hash:
                logger.error(f"Hash mismatch: expected {expected_hash}, got {actual}")
                os.unlink(tmp_path)
                return None
            logger.info(f"Hash verified: {actual[:16]}...")

        return tmp_path
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return None


def install_update(file_path: str, silent: bool = False):
    """Launch the installer and exit the current app."""
    logger.info(f"Installing update from {file_path}")
    if PLATFORM == "win":
        args = [file_path, "/SILENT", "/CLOSEAPPLICATIONS", "/SUPPRESSMSGBOXES", "/NORESTART"]
        if silent:
            args.append("/VERYSILENT")
        subprocess.Popen(
            args,
            creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        )
    else:
        subprocess.Popen(["open", file_path])
    sys.exit(0)


def _is_newer(remote: str, current: str) -> bool:
    try:
        r = [int(x) for x in remote.split(".")]
        c = [int(x) for x in current.split(".")]
        return r > c
    except (ValueError, IndexError):
        return False


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
