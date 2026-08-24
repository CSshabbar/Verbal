"""
Paste-blocked detection + the one-click fix popup (macOS and Windows).

WHY THIS EXISTS — the silent-paste bug. On macOS the injected paste is a
synthetic Cmd-V posted with `CGEventPost`, and **without the Accessibility grant
that call does nothing at all**: no exception, no error code, no notification.
`injector.inject_text()` therefore copied the text, logged "Pasted", and
returned True while the user watched their transcription never arrive. Worse,
the text *was* on the clipboard, so pressing Cmd-V by hand worked — which reads
as "Verbal's paste is broken", not "Verbal is missing a permission", so nobody
thinks to look in System Settings.

The Windows equivalent is **UIPI**: `SendInput` refuses to deliver keystrokes to
a window owned by a higher-integrity process (anything launched as
administrator) and reports 0 events inserted — a return value the old
`pyautogui.hotkey("ctrl", "v")` call discarded, producing the same silent
nothing. Note that Windows has **no paste permission to grant**; the only fix is
to run Verbal at the same integrity level as the target, i.e. as administrator.
That asymmetry is deliberate and is why `can_paste()` is a real pre-flight on
macOS and always True on Windows (see its docstring).

CONTRACT
  - The transcription is ALWAYS on the clipboard before anything here runs, so a
    blocked paste is never lost. This module only explains it and offers the fix.
  - Nothing here may raise into the dictation path: every entry point is
    wrapped, and a failure degrades to "no popup", never to a lost recording
    (CLAUDE.md hard rule #1 — peripheral features fail closed).
  - The popup appears at most ONCE per reason per app run, and re-arms if the
    permission is granted and later revoked. Prompting on every dictation would
    be worse than the silent failure it replaces.
"""
import logging
import sys

logger = logging.getLogger("verbal.paste_guard")

REASON_ACCESSIBILITY = "accessibility"   # macOS: AXIsProcessTrusted() is false
REASON_UIPI = "uipi"                     # Windows: SendInput was refused

_IS_WIN = sys.platform == "win32"

_prompt_hook = None       # set by main.py / win_main.py — they own the UI toolkit
_prompted = set()         # reasons already surfaced this run (the throttle)
_last_ok = None           # last known can_paste() result, for re-arming


def set_prompt_hook(fn):
    """Register the platform's popup, called once at startup.

    The hook is invoked as `fn(reason, target_app)`. It lives in main.py /
    win_main.py because those own the UI toolkit (rumps on macOS, tkinter on
    Windows) and the main-thread hop that this module deliberately knows
    nothing about.
    """
    global _prompt_hook
    _prompt_hook = fn


def _note_state(ok):
    """Re-arm the popup when the grant flips.

    Granting the permission clears the throttle, so a later revoke (or a macOS
    upgrade resetting TCC, which does happen) is reported again instead of being
    swallowed by a stale "already prompted" flag.
    """
    global _last_ok
    if ok and _last_ok is False:
        _prompted.discard(REASON_ACCESSIBILITY)
    _last_ok = ok


def can_paste() -> bool:
    """True when a synthetic paste can actually be delivered.

    macOS: a real pre-flight. `AXIsProcessTrusted()` is exactly the bit
    `CGEventPost` checks, and it is a cheap TCC cache read, so it runs on every
    dictation rather than being cached once — the user can grant the permission
    while Verbal is running and the very next dictation must work.

    Windows: there is nothing to pre-flight. UIPI depends on the FOREGROUND
    window's integrity level, not on us, so it can only be detected from
    `SendInput`'s return value after the attempt. Always True here;
    `win_injector` reports after the fact instead.

    An 'unknown' probe result counts as OK: if we cannot tell, let the paste try
    rather than blocking a working setup on a failed permission read.
    """
    if _IS_WIN:
        return True
    try:
        from app import permissions
        ok = permissions.check_accessibility() != "denied"
    except Exception as e:
        logger.debug("accessibility probe failed (%s) — assuming paste works", e)
        return True
    _note_state(ok)
    return ok


def title(reason) -> str:
    if reason == REASON_UIPI:
        return "Verbal can't type into that app"
    return "Flume needs Accessibility to paste"


def buttons(reason):
    """(confirm, dismiss) labels for the popup."""
    if reason == REASON_UIPI:
        return ("Restart as administrator", "Not now")
    return ("Open Settings", "Not now")


def message(reason, target_app="") -> str:
    where = f" into {target_app}" if target_app else ""
    if reason == REASON_UIPI:
        return (
            f"Windows blocked Verbal from typing{where}.\n\n"
            "That app is running as administrator, so Windows refuses "
            "keystrokes from Verbal, which isn't.\n\n"
            "Your transcription is on the clipboard — press Ctrl+V to paste it "
            "right now.\n\n"
            "Restart Verbal as administrator so this stops happening?"
        )
    return (
        f"Flume could not paste{where}.\n\n"
        "macOS requires the Accessibility permission before Flume can paste "
        "into other apps. Until it's on, every dictation will land on the "
        "clipboard but never appear.\n\n"
        "Your transcription is on the clipboard — press ⌘V to paste it "
        "right now.\n\n"
        "Open System Settings to turn Accessibility on?"
    )


def report_blocked(reason, target_app=""):
    """Announce a paste the OS refused. Throttled to once per reason per run.

    Always safe to call from the dictation worker thread — the hook owns its own
    main-thread hop.
    """
    try:
        logger.warning(
            "paste blocked (%s) target=%r — transcription left on the clipboard",
            reason, target_app or "?")
        if reason == REASON_ACCESSIBILITY:
            _note_state(False)
        if reason in _prompted:
            return
        _prompted.add(reason)
        hook = _prompt_hook
        if hook is None:
            logger.debug("no paste-blocked prompt hook registered")
            return
        hook(reason, target_app or "")
    except Exception as e:
        # A failed popup must never turn into a failed dictation.
        logger.debug("paste-blocked report failed: %s", e)


def open_fix(reason=REASON_ACCESSIBILITY) -> bool:
    """Perform the fix the popup offered.

    Returns True when Verbal must now QUIT (the Windows elevated relaunch has
    started), False when the fix happens in place (the macOS Settings pane).
    """
    try:
        if reason == REASON_UIPI:
            return _relaunch_elevated()
        from app import permissions
        # Fires the TCC prompt AND opens Privacy & Security > Accessibility, so
        # the user lands on the exact row they need to toggle.
        permissions.request_accessibility()
    except Exception as e:
        logger.error("could not apply the paste fix (%s): %s", reason, e)
    return False


# ── Windows: relaunch elevated ────────────────────────────────────────────

def _close_singleton_mutex():
    """Free the single-instance mutex name so the elevated copy can start.

    win_main stashes the handle on `sys._verbal_singleton_mutex`. It was created
    with `bInitialOwner=False`, so this process never *owned* the mutex —
    closing the handle (not ReleaseMutex) is what releases the NAME, and the
    name is what `_acquire_single_instance_mutex()` checks. Without this the
    elevated Verbal starts, sees ERROR_ALREADY_EXISTS, and exits immediately.
    """
    import ctypes
    handle = getattr(sys, "_verbal_singleton_mutex", None)
    if not handle:
        return
    try:
        ctypes.windll.kernel32.CloseHandle(handle)
        sys._verbal_singleton_mutex = None
    except Exception as e:
        logger.debug("singleton mutex release failed: %s", e)


def _relaunch_elevated() -> bool:
    """Re-launch Verbal with elevation via ShellExecuteW's "runas" verb.

    Returns True when the elevated process was launched and this one should
    quit. A declined UAC prompt returns False and leaves everything as it was —
    including the singleton mutex, which is re-acquired so a second Verbal can't
    slip in through the window we just opened.
    """
    import ctypes
    exe = sys.executable
    if not exe:
        logger.error("no sys.executable — cannot relaunch elevated")
        return False
    # A frozen build IS the app and takes no arguments; a dev run is
    # `python -m app.win_main` and needs the module back on the command line.
    params = "" if getattr(sys, "frozen", False) else "-m app.win_main"

    _close_singleton_mutex()
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params, None, 1)  # 1 = SW_SHOWNORMAL
    except Exception as e:
        logger.error("elevated relaunch failed: %s", e)
        _reacquire_singleton_mutex()
        return False

    # ShellExecuteW returns a value <= 32 for every failure, including the user
    # declining UAC (SE_ERR_ACCESSDENIED = 5).
    if rc <= 32:
        logger.info("elevated relaunch declined or failed (rc=%s)", rc)
        _reacquire_singleton_mutex()
        return False
    logger.info("elevated Verbal launched — this instance must exit")
    return True


def _reacquire_singleton_mutex():
    """Re-take the singleton after a declined UAC prompt.

    We released it *before* asking (the elevated copy needs the name free), so
    leaving it released would let a second Verbal start and stack tray icons,
    overlays and hotkeys — exactly what the mutex exists to prevent.
    """
    try:
        from app.win_main import _acquire_single_instance_mutex
        _acquire_single_instance_mutex()
    except Exception as e:
        logger.debug("singleton mutex re-acquire failed: %s", e)
