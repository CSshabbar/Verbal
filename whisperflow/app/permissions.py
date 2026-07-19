"""
macOS permission checks + requests for the onboarding "Get started" step.

status values: 'granted' | 'denied' | 'unknown'
"""
import logging
import subprocess

logger = logging.getLogger("verbal.permissions")


def _open_settings(anchor):
    try:
        subprocess.Popen(
            ["open", f"x-apple.systempreferences:com.apple.preference.security?{anchor}"])
    except Exception as e:
        logger.debug("open settings failed: %s", e)


# ── Accessibility (needed to paste) ────────────────────────────────────────────
def check_accessibility():
    try:
        from ApplicationServices import AXIsProcessTrusted
        return "granted" if AXIsProcessTrusted() else "denied"
    except Exception:
        try:
            from HIServices import AXIsProcessTrusted
            return "granted" if AXIsProcessTrusted() else "denied"
        except Exception:
            return "unknown"


def request_accessibility():
    try:
        from ApplicationServices import (
            AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt)
        AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
    except Exception:
        pass
    _open_settings("Privacy_Accessibility")


# ── Microphone (needed to record) ──────────────────────────────────────────────
def check_microphone():
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
        st = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
        return {3: "granted", 2: "denied", 1: "denied"}.get(st, "unknown")  # 0 = not determined
    except Exception:
        return "unknown"


def request_microphone():
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
        AVCaptureDevice.requestAccessForMediaType_completionHandler_(
            AVMediaTypeAudio, lambda granted: None)
        return
    except Exception:
        pass
    _open_settings("Privacy_Microphone")


# ── System audio (meeting recording — screen-capture permission) ────────────────
def check_system_audio():
    try:
        from Quartz import CGPreflightScreenCaptureAccess
        return "granted" if CGPreflightScreenCaptureAccess() else "denied"
    except Exception:
        return "unknown"


def request_system_audio():
    try:
        from Quartz import CGRequestScreenCaptureAccess
        CGRequestScreenCaptureAccess()
    except Exception:
        pass
    _open_settings("Privacy_ScreenCapture")


# ── Notifications (optional) ───────────────────────────────────────────────────
def check_notifications():
    return "unknown"


def request_notifications():
    _open_settings("Privacy_Notifications")


def all_status():
    return {
        "accessibility": check_accessibility(),
        "microphone": check_microphone(),
        "system_audio": check_system_audio(),
        "notifications": check_notifications(),
    }


# ── Meetings (MEETINGS_DESIGN_HANDOFF.md 31h) ───────────────────────────────────
def system_audio_capture_supported():
    """True when the ScreenCaptureKit audio path is importable on this machine
    (macOS 13+ with the pyobjc wrappers installed). Fail-closed: any error
    means 'not supported' — meetings then run mic-only."""
    try:
        from app.system_audio import is_supported
        return bool(is_supported())
    except Exception:
        return False


def meeting_permissions():
    """Aggregate status for the meeting permission checklist (screen 31h).

    Steps map to the modal: 1 = capture support present, 2 = Screen Recording
    (gates ScreenCaptureKit audio), 3 = microphone.
    """
    sys_audio = check_system_audio()
    mic = check_microphone()
    supported = system_audio_capture_supported()
    return {
        "supported": supported,
        "system_audio": sys_audio,
        "microphone": mic,
        "ready": supported and sys_audio == "granted" and mic == "granted",
        "steps": [
            {"id": "support", "done": supported},
            {"id": "system_audio", "done": sys_audio == "granted",
             "denied": sys_audio == "denied"},
            {"id": "microphone", "done": mic == "granted",
             "denied": mic == "denied"},
        ],
    }


def request(which):
    {
        "accessibility": request_accessibility,
        "microphone": request_microphone,
        "system_audio": request_system_audio,
        "notifications": request_notifications,
    }.get(which, lambda: None)()
    return all_status()
