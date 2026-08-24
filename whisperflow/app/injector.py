import logging
import re
import time
import subprocess
import pyperclip
import Quartz
from AppKit import NSWorkspace, NSRunningApplication

from app import paste_guard

logger = logging.getLogger("verbal.injector")

VK_V = 0x09
VK_RETURN = 0x24
VK_COMMAND = 0x37  # left Command key

# An '@name.ext' file tag produced by app.filetags.tag(). Used to drive Cursor's
# @-mention picker so the reference becomes a real chip, not literal text. The
# lookbehind requires the '@' to start a word (as tags always do) so an email
# like 'foo@gmail.com' is NOT mistaken for a file tag.
_MENTION_RE = re.compile(r'(?<![\w@])@[A-Za-z0-9_.\-]+\.[A-Za-z0-9]+')

# Store the app the user was in before recording
_previous_app_pid    = None
_previous_app_name   = ""
_previous_app_bundle = ""


def save_focused_app():
    """Call this BEFORE recording starts to remember where user was."""
    global _previous_app_pid, _previous_app_name, _previous_app_bundle
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app and app.bundleIdentifier() != "com.verbal.app":
            _previous_app_pid    = app.processIdentifier()
            _previous_app_name   = app.localizedName() or ""
            _previous_app_bundle = app.bundleIdentifier() or ""
            logger.info(f"Saved focused app: {_previous_app_name} (PID {_previous_app_pid})")
    except Exception as e:
        logger.warning(f"Could not save focused app: {e}")


def get_focused_app_name() -> str:
    """Return the name of the app that was focused when recording started."""
    return _previous_app_name


def get_focused_app_pid():
    """PID of the app focused when recording started (None if unknown). This is
    the dictation TARGET — use it (not the live frontmost app, which may be the
    overlay by transcription time) for file-tagging AX reads."""
    return _previous_app_pid


def get_focused_app_bundle() -> str:
    """Bundle id of the app focused when recording started ('' if unknown)."""
    return _previous_app_bundle


def restore_focused_app():
    """Restore focus to the app the user was in before recording."""
    global _previous_app_pid
    if _previous_app_pid is None:
        return
    try:
        apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_("")
        # Get all running apps and find ours
        ws = NSWorkspace.sharedWorkspace()
        for app in ws.runningApplications():
            if app.processIdentifier() == _previous_app_pid:
                app.activateWithOptions_(1 << 1)  # NSApplicationActivateIgnoringOtherApps
                logger.info(f"Restored focus to: {app.localizedName()}")
                return
    except Exception as e:
        logger.warning(f"Could not restore focused app: {e}")


def _await_focus(pid, timeout=0.2, poll=0.005) -> float:
    """Block until `pid` is actually frontmost. Returns the seconds waited.

    `activateWithOptions_` is ASYNCHRONOUS — it asks the window server to switch and
    returns immediately, which is why this used to be a flat `time.sleep(0.2)`: a
    guess at how long the switch takes, paid in full on every single dictation even
    when the switch landed in 20ms. Pasting before focus arrives sends Cmd-V to the
    wrong app, so the wait is real — but it should end when focus actually arrives.
    The timeout keeps the old 200ms as a ceiling, so this is never slower than before.
    """
    if pid is None:
        return 0.0
    t0 = time.time()
    try:
        ws = NSWorkspace.sharedWorkspace()
        while time.time() - t0 < timeout:
            front = ws.frontmostApplication()
            if front is not None and front.processIdentifier() == pid:
                return time.time() - t0
            time.sleep(poll)
    except Exception as e:
        # Never let a focus probe break injection — fall back to the old behaviour.
        logger.debug("focus probe failed (%s) — using the fixed wait", e)
        remaining = timeout - (time.time() - t0)
        if remaining > 0:
            time.sleep(remaining)
    return time.time() - t0


def _await_clipboard(text, timeout=0.05, poll=0.002) -> float:
    """Block until the clipboard actually reports `text`. Returns seconds waited.

    Measured on this machine: the value is readable in 0.7ms median, 8.4ms worst
    over 30 trials — so the old flat 50ms sleep was roughly 7x the worst case and
    pure latency on every dictation. Same ceiling as before if the pasteboard stalls.
    """
    t0 = time.time()
    try:
        while time.time() - t0 < timeout:
            if pyperclip.paste() == text:
                return time.time() - t0
            time.sleep(poll)
    except Exception:
        pass
    return time.time() - t0


def _paste_via_cgevent():
    """Simulate Cmd+V using Quartz CGEvents.

    Posts a BALANCED left-Command key down/up around the V, and clears the flags
    on the final Command-up event. The old approach set only the Command *flag*
    on the V events (with an HID-system-state source) and never posted a matching
    Command key up — which could leave a phantom Command modifier in the session
    state and break the user's own real Cmd+V afterward (right-click Paste still
    worked because it doesn't use the keyboard). Left Command (0x37) is used so it
    never collides with the default Right-Command (0x36) recording hotkey.
    """
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    tap = Quartz.kCGAnnotatedSessionEventTap
    cmd = Quartz.kCGEventFlagMaskCommand

    def _post(vk, down, flags):
        e = Quartz.CGEventCreateKeyboardEvent(src, vk, down)
        Quartz.CGEventSetFlags(e, flags)
        Quartz.CGEventPost(tap, e)

    _post(VK_COMMAND, True, cmd)     # Command down
    _post(VK_V, True, cmd)           # V down (Command held)
    time.sleep(0.03)
    _post(VK_V, False, cmd)          # V up
    _post(VK_COMMAND, False, 0)      # Command up — flags cleared, no phantom modifier


def _event_source():
    return Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)


def _type_unicode(src, s, per_char=0.012):
    """Type a string as real keyboard input via unicode events (layout-agnostic)."""
    tap = Quartz.kCGAnnotatedSessionEventTap
    for ch in s:
        down = Quartz.CGEventCreateKeyboardEvent(src, 0, True)
        Quartz.CGEventKeyboardSetUnicodeString(down, len(ch), ch)
        Quartz.CGEventPost(tap, down)
        up = Quartz.CGEventCreateKeyboardEvent(src, 0, False)
        Quartz.CGEventKeyboardSetUnicodeString(up, len(ch), ch)
        Quartz.CGEventPost(tap, up)
        time.sleep(per_char)


def _tap_key(src, vk):
    tap = Quartz.kCGAnnotatedSessionEventTap
    down = Quartz.CGEventCreateKeyboardEvent(src, vk, True)
    Quartz.CGEventPost(tap, down)
    time.sleep(0.02)
    up = Quartz.CGEventCreateKeyboardEvent(src, vk, False)
    Quartz.CGEventPost(tap, up)


def _paste_chunk(text: str):
    """Clipboard-paste a plain text chunk (fast, reliable for arbitrary text)."""
    if not text:
        return
    pyperclip.copy(text)
    time.sleep(0.04)
    _paste_via_cgevent()
    time.sleep(0.06)


def _inject_with_mentions(text: str) -> bool:
    """Inject `text` into Cursor/Windsurf so each '@name.ext' becomes a REAL
    file reference: plain chunks are pasted; each tag is TYPED ('@' + filename)
    to open the editor's file-picker, then Enter selects the highlighted match.
    """
    restore_focused_app()
    time.sleep(0.25)
    src = _event_source()

    plain_parts = _MENTION_RE.split(text)      # N+1 plain chunks
    mentions = _MENTION_RE.findall(text)       # N '@name.ext' tokens

    for i, chunk in enumerate(plain_parts):
        _paste_chunk(chunk)
        if i < len(mentions):
            query = mentions[i][1:]            # drop leading '@'
            _type_unicode(src, "@")            # open the mention picker
            time.sleep(0.18)
            _type_unicode(src, query)          # filter to the file
            time.sleep(0.35)                   # let the picker populate/highlight
            _tap_key(src, VK_RETURN)           # accept the top match -> real chip
            time.sleep(0.14)
    logger.info(f"Injected with {len(mentions)} mention(s): '{text[:40]}...'")
    return True


def inject_text(text: str, allow_mentions: bool = False) -> bool:
    # Pre-flight the Accessibility grant. WITHOUT it every CGEventPost below is a
    # silent no-op: the paste "succeeds", returns True, logs "Pasted" — and
    # nothing arrives in the target app. That produced a bug that looked like
    # broken dictation rather than a missing permission, because ⌘V by hand
    # worked fine (the text really is on the clipboard). See app/paste_guard.py.
    # This runs before the mention path too — that path posts CGEvents as well,
    # so it fails exactly the same way.
    try:
        if not paste_guard.can_paste():
            try:
                pyperclip.copy(text)
            except Exception as e:
                logger.error(f"clipboard copy failed while paste was blocked: {e}")
            # Put the user back in their app so the ⌘V the popup tells them
            # about lands in the right place.
            restore_focused_app()
            paste_guard.report_blocked(
                paste_guard.REASON_ACCESSIBILITY, _previous_app_name)
            return False
    except Exception as e:
        # The guard must never be what stops a dictation — fall through and try.
        logger.debug("paste guard skipped: %s", e)

    # When file-tagging is on and the dictation target is Cursor/Windsurf, drive
    # the @-mention picker so tags become real references. Any failure falls back
    # to a plain paste so a recording is never lost.
    if allow_mentions and _MENTION_RE.search(text or ""):
        try:
            from app import filetags
            ide = filetags.supported_ide(_previous_app_bundle, _previous_app_name)
            _tagging = ide in filetags.TAGGING_IDES
        except Exception:
            _tagging = False
        if _tagging:
            try:
                return _inject_with_mentions(text)
            except Exception as e:
                logger.error(f"Mention injection failed, falling back to paste: {e}")

    try:
        # Both waits were flat sleeps (50ms + 200ms = 250ms on EVERY dictation, after
        # the transcript was already in hand). They are now event-driven with the old
        # values as ceilings, so this path can only be faster, never slower.
        pyperclip.copy(text)
        _clip_ms = _await_clipboard(text) * 1000

        # Restore focus to the app user was typing in
        restore_focused_app()
        _focus_ms = _await_focus(_previous_app_pid) * 1000

        # Paste via CGEvent
        _paste_via_cgevent()
        logger.info("Pasted: '%s...' (clipboard %.0fms + focus %.0fms = %.0fms, was a flat 250ms)",
                    text[:40], _clip_ms, _focus_ms, _clip_ms + _focus_ms)
        return True

    except Exception as e:
        logger.error(f"Paste failed (text in clipboard): {e}")
        return False


def request_accessibility():
    """Prompt user for accessibility permission."""
    from ApplicationServices import AXIsProcessTrustedWithOptions
    AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True})
