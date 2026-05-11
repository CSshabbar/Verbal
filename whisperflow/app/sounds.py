import logging
import subprocess

logger = logging.getLogger("verbal.sounds")


def play_start():
    """Play start sound using afplay (safe from any thread)."""
    try:
        subprocess.Popen(
            ["afplay", "-v", "0.3", "/System/Library/Sounds/Tink.aiff"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.debug(f"Sound error: {e}")


def play_stop():
    """Play stop sound using afplay (safe from any thread)."""
    try:
        subprocess.Popen(
            ["afplay", "-v", "0.3", "/System/Library/Sounds/Pop.aiff"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.debug(f"Sound error: {e}")


def play_done():
    """Play done sound using afplay (safe from any thread)."""
    try:
        subprocess.Popen(
            ["afplay", "-v", "0.2", "/System/Library/Sounds/Glass.aiff"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.debug(f"Sound error: {e}")
