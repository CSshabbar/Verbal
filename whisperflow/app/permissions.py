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


def request(which):
    {
        "accessibility": request_accessibility,
        "microphone": request_microphone,
        "system_audio": request_system_audio,
        "notifications": request_notifications,
    }.get(which, lambda: None)()
    return all_status()
