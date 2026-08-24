"""
Verbal auto-updater — checks Supabase for new versions, downloads and installs.

Works on both Mac and Windows. Stores version metadata in the `app_versions`
Supabase table and release binaries in Supabase Storage.
"""

import hashlib
import logging
import os
import platform
import shlex
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
        # Don't check for updates in the first 30 seconds after launch
        # to avoid infinite auto-update loops
        import time
        if time.time() - getattr(sys, '_verbal_start_time', 0) < 30:
            return None

        # Reads the app_versions_latest VIEW, not the raw table.
        #
        # This used to be `app_versions?order=released_at.desc&limit=1`, which is
        # wrong whenever CI stamps released_at non-monotonically — and it does. Live
        # data had win 1.0.9 at 00:00:00 and win 1.0.8 at 09:13:24 on the SAME day,
        # so "newest" resolved to 1.0.8 and nobody on 1.0.7 could ever be offered
        # 1.0.9. The view orders by SEMVER (see semver_key) and returns one row per
        # platform, so the app and the public /download redirect can never disagree
        # about which build is current.
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/app_versions_latest",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            params={
                "platform": f"eq.{PLATFORM}",
                "select": "version,changelog,file_url,file_hash,file_size,released_at",
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
    max_retries = 3
    for attempt in range(max_retries):
        try:
            url = version_info["file_url"]
            expected_hash = version_info.get("file_hash")
            total_size = version_info.get("file_size", 0)

            suffix = ".exe" if PLATFORM == "win" else ".dmg"
            fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)

            with open(tmp_path, "wb") as f:
                with httpx.stream("GET", url, follow_redirects=True, timeout=60) as stream:
                    stream.raise_for_status()  # Raise an exception for bad status codes
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
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying download (attempt {attempt + 2}/{max_retries})")
                        continue
                    return None
                logger.info(f"Hash verified: {actual[:16]}...")

            return tmp_path
        except Exception as e:
            logger.error(f"Download failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
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
        _install_update_mac(file_path)
    sys.exit(0)


def _install_update_mac(dmg_path: str):
    """`open`-ing a .dmg only mounts it in Finder — nothing actually replaces
    the installed app or relaunches it, so "Update" looked like it did
    nothing (confirmed live, 2026-08-25: user reports "shows option to
    update but doesn't restart the update"). Spawn a detached helper script
    that waits for this process to fully exit, then mounts the dmg, copies
    the new .app over the CURRENTLY INSTALLED one (wherever that actually is
    — derived from sys.executable rather than assuming /Applications, so a
    dev/manually-relocated install still gets replaced in place), unmounts,
    and relaunches. Falls back to the old "just open the dmg" behavior at
    any step that fails, so a user can still finish the install by hand
    instead of being left with nothing.
    """
    # Frozen layout: <App>.app/Contents/MacOS/<exe> — walk up three levels.
    target_app = os.path.dirname(os.path.dirname(os.path.dirname(sys.executable)))
    if not target_app.endswith(".app") or not os.path.isdir(target_app):
        logger.warning(f"Can't resolve installed app bundle from {sys.executable!r}; "
                        "falling back to opening the dmg")
        subprocess.Popen(["open", dmg_path])
        return

    pid = os.getpid()
    mount_dir = tempfile.mkdtemp(prefix="flume_update_")
    dmg_q, mount_q, target_q = (shlex.quote(p) for p in (dmg_path, mount_dir, target_app))
    script = f"""
    while kill -0 {pid} 2>/dev/null; do sleep 0.3; done
    if hdiutil attach {dmg_q} -mountpoint {mount_q} -nobrowse -quiet; then
        SRC_APP=$(find {mount_q} -maxdepth 1 -name '*.app' -print -quit)
        if [ -n "$SRC_APP" ] && rm -rf {target_q} && ditto "$SRC_APP" {target_q}; then
            hdiutil detach {mount_q} -quiet
            rm -f {dmg_q}
            open {target_q}
            exit 0
        fi
        hdiutil detach {mount_q} -quiet
    fi
    open {dmg_q}
    """
    subprocess.Popen(["/bin/bash", "-c", script], start_new_session=True)


def _is_newer(remote: str, current: str) -> bool:
    try:
        # Handle version strings with different formats
        r_parts = [int(x) for x in remote.split(".")]
        c_parts = [int(x) for x in current.split(".")]
        
        # Pad shorter version with zeros
        while len(r_parts) < len(c_parts):
            r_parts.append(0)
        while len(c_parts) < len(r_parts):
            c_parts.append(0)
            
        return r_parts > c_parts
    except (ValueError, IndexError):
        # If we can't parse versions, assume remote is newer
        # This prevents getting stuck on a broken version
        logger.warning(f"Could not parse versions: remote={remote}, current={current}")
        return True


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
