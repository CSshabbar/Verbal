"""
Transform — voice/prompt-driven text reshaping (TRANSFORM_SWARM.md).

Two modes, one engine:
  Mode A (inline):    "…so Flume, make this formal" at the end of a dictation →
                      split body/instruction, transform, paste. Hooked BEFORE
                      ai_cleanup.process_text in main's transcribe worker.
  Mode B (selection): dedicated hotkey → capture the current selection via the
                      clipboard → TransformWidget pill (Improvise / spoken or
                      typed prompt) → PREVIEW → Replace/Cancel (+ Undo).

HARD GUARANTEES (Rule #1):
  - never breaks record→transcribe→inject: every Mode A entry point returns
    None / falls through so the caller runs the normal process_text path;
  - Mode B never enters the dictation core — separate hotkey, separate widget;
  - clipboard save/restore is try/finally — the user's clipboard survives.

Transform is a SEPARATE prompt from ai_cleanup.SYSTEM_PROMPT (which is a
formatter that must NOT follow instructions). Never merge the two.
"""
import logging
import re
import time

logger = logging.getLogger("verbal.transform")

# Mode A trigger words — tuned from real logs; "Flume" mis-transcribes, so the
# set carries known homophones. Keep TIGHT: bias toward MISSING an instruction
# (user re-dictates) over STEALING dictated content.
DEFAULT_TRIGGER_WORDS = ["flume", "flumes", "flu me", "plume", "bloom"]

MAX_SELECTION_CHARS = 12000     # Mode B cap (LLM chat content, latency/cost)
MAX_INSTRUCTION_CHARS = 200     # a trailing instruction is a phrase, not an essay
MIN_BODY_WORDS = 3              # "Flume make a note" alone must NOT fire

# The instruction must START with an editing verb — this is what keeps
# "I rode the flume today and it was fun" from being eaten as an instruction.
# Bias toward MISSING (user re-dictates) over STEALING content.
INSTRUCTION_VERBS = {
    "make", "turn", "rewrite", "reword", "rephrase", "convert", "translate",
    "summarize", "summarise", "shorten", "lengthen", "expand", "tighten",
    "fix", "clean", "format", "change", "improve", "polish", "simplify",
    "formalize", "formalise", "capitalize", "capitalise", "bullet",
    "condense", "soften", "professionalize", "casualize", "write", "redo",
}
_LEADING_FILLER = {"and", "please", "just", "can", "you", "could", "now"}

TRANSFORM_SYSTEM_PROMPT = (
    "You transform the user's text according to their instruction.\n"
    "Rules:\n"
    "- Return ONLY the transformed text. No preamble, no explanation, no quotes, "
    "no markdown fences.\n"
    "- Never add facts, names, numbers or claims that are not in the original text.\n"
    "- Preserve the language of the original text unless the instruction says to translate.\n"
    "- Keep meaning intact unless the instruction explicitly asks to change it.\n"
    "- If the instruction is unclear or impossible, return the original text lightly "
    "cleaned up (punctuation, casing) instead."
)

IMPROVISE_SYSTEM_PROMPT = (
    "You are a precision editor. Rewrite the user's text to be clearer and tighter.\n"
    "Rules:\n"
    "- Return ONLY the rewritten text. No preamble, no explanation, no quotes, "
    "no markdown fences.\n"
    "- Preserve the meaning, facts, tone register and language. Never add content.\n"
    "- Fix grammar, punctuation and awkward phrasing; break up run-ons; remove filler.\n"
    "- Keep the original structure (paragraphs, lists, greetings/sign-offs) intact.\n"
    "- Do not shorten by more than ~20% unless the text is redundant."
)


# ── Mode A gate (pure, no LLM, no side effects) ──────────────────────────────

def _trigger_regex(trigger_words):
    words = [w for w in (trigger_words or DEFAULT_TRIGGER_WORDS) if str(w).strip()]
    if not words:
        words = DEFAULT_TRIGGER_WORDS
    alts = "|".join(re.escape(str(w).strip().lower()) for w in words)
    # … <sep> [so|hey|ok|okay|now|and|please] <trigger>[,|:] <instruction>$
    return re.compile(
        r"[,.;!?\s]+(?:so|hey|ok|okay|now|and|please)?[\s,]*(?:" + alts + r")\s*[,:]?\s+(.+)$",
        re.IGNORECASE | re.DOTALL)


def detect_trailing_instruction(raw_transcript, trigger_words=None):
    """Cheap tail gate. Returns (body, instruction) or None.

    None for the overwhelming majority of dictations — this must stay free.
    The LLM does the *smart* split later; this only decides whether to engage.
    """
    try:
        text = (raw_transcript or "").strip()
        if len(text) < 20:
            return None
        m = _trigger_regex(trigger_words).search(text)
        if not m:
            return None
        body = text[: m.start()].strip()
        instruction = m.group(1).strip().rstrip(".!?, ")
        if len(body.split()) < MIN_BODY_WORDS:
            return None                       # no real content before the trigger
        if not instruction or len(instruction) > MAX_INSTRUCTION_CHARS:
            return None
        if len(instruction.split()) < 2:
            return None                       # "so Flume." → not an instruction
        words = [w.strip(",.").lower() for w in instruction.split()]
        lead = next((w for w in words if w not in _LEADING_FILLER), "")
        if lead not in INSTRUCTION_VERBS:
            return None                       # tail isn't an edit command → content
        return body, instruction
    except Exception as e:
        logger.debug("detect_trailing_instruction failed closed: %s", e)
        return None


# ── LLM steps (shared by both modes) ─────────────────────────────────────────

def _strip_wrapping(out, original):
    """Models occasionally wrap output in quotes/fences despite the prompt."""
    s = (out or "").strip()
    if s.startswith("```"):
        s = s.strip("`").strip()
        for lang in ("text", "markdown", "md"):
            if s.lower().startswith(lang + "\n"):
                s = s[len(lang) + 1:]
    if len(s) > 1 and s[0] in "\"'“" and s[-1] in "\"'”" and original and original[0] not in "\"'“":
        s = s[1:-1].strip()
    return s


# Ollama Cloud fallback model (open-weight, served via the same groq-proxy with
# provider="ollama"). It's a SEPARATE quota from Groq with a server-held key, so it
# survives Groq's daily-token cap — the same path meeting-notes already uses.
OLLAMA_FALLBACK_MODEL = "gpt-oss:120b"


def _chat(system, user, config, max_tokens=2048):
    """Transform's LLM call. Primary = Groq llama-3.3 via the shared proxy; on any
    failure (including Groq's daily-token 429) it retries the SAME proxy against
    Ollama Cloud (provider="ollama") — a separate quota — so Transform keeps working
    when the shared Groq key is exhausted. Returns text or None; fully fail-closed
    (Mode B is outside the dictation core, so None just shows 'try again')."""
    from app.groq_proxy import chat_via_proxy
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    try:
        raw = chat_via_proxy(messages, config, max_tokens=max_tokens, timeout=30.0)
        if (raw or "").strip():
            return raw
    except Exception as e:
        logger.warning("transform Groq chat failed: %s", e)
    # Fallback: Ollama Cloud (separate quota) — survives Groq daily-cap exhaustion.
    try:
        logger.info("transform: Groq empty/failed — falling back to Ollama %s", OLLAMA_FALLBACK_MODEL)
        raw = chat_via_proxy(messages, config, model=OLLAMA_FALLBACK_MODEL,
                             provider="ollama", max_tokens=max_tokens, timeout=60.0)
        if (raw or "").strip():
            return raw
    except Exception as e:
        logger.warning("transform Ollama fallback failed: %s", e)
    return None


def apply_instruction(text, instruction, config):
    """Transform `text` per `instruction`. Returns the rewrite, or None on any
    failure (caller falls back to the normal path)."""
    try:
        text = (text or "").strip()
        if not text:
            return None
        user = f"INSTRUCTION: {instruction}\n\nTEXT:\n{text[:MAX_SELECTION_CHARS]}"
        out = _strip_wrapping(_chat(TRANSFORM_SYSTEM_PROMPT, user, config), text)
        logger.info("transform apply: %d chars in -> %s chars out (%r)",
                    len(text), len(out) if out else 0, instruction[:48])
        return out or None
    except Exception as e:
        logger.warning("apply_instruction failed closed: %s", e)
        return None


def improvise(text, config):
    """Mode B's one-tap clarity pass. Returns the rewrite or None."""
    try:
        text = (text or "").strip()
        if not text:
            return None
        out = _strip_wrapping(_chat(IMPROVISE_SYSTEM_PROMPT, text[:MAX_SELECTION_CHARS], config), text)
        logger.info("transform improvise: %d chars in -> %s chars out",
                    len(text), len(out) if out else 0)
        return out or None
    except Exception as e:
        logger.warning("improvise failed closed: %s", e)
        return None


# ── Mode B selection capture (clipboard route) ───────────────────────────────

def _synth_combo(vk, flags_mask):
    """Balanced modifier+key synth (same discipline as injector._paste_via_cgevent)."""
    import Quartz
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    tap = Quartz.kCGAnnotatedSessionEventTap

    def post(code, down, flags):
        e = Quartz.CGEventCreateKeyboardEvent(src, code, down)
        Quartz.CGEventSetFlags(e, flags)
        Quartz.CGEventPost(tap, e)

    VK_LCMD = 0x37
    post(VK_LCMD, True, flags_mask)
    post(vk, True, flags_mask)
    time.sleep(0.03)
    post(vk, False, flags_mask)
    post(VK_LCMD, False, 0)


def capture_selection():
    """Read the current selection via save-clipboard → Cmd+C → read → restore.

    Returns the selected string or None. The clipboard is ALWAYS restored
    (try/finally), mirroring injector's focus save/restore discipline.
    """
    import Quartz
    from AppKit import NSPasteboard, NSStringPboardType
    pb = NSPasteboard.generalPasteboard()
    saved = None
    try:
        saved = pb.stringForType_(NSStringPboardType)
    except Exception:
        pass
    before = pb.changeCount()
    try:
        VK_C = 0x08
        _synth_combo(VK_C, Quartz.kCGEventFlagMaskCommand)
        # wait (bounded) for the pasteboard to actually change
        for _ in range(30):
            time.sleep(0.02)
            if pb.changeCount() != before:
                break
        if pb.changeCount() == before:
            return None                       # nothing selected / copy blocked
        sel = pb.stringForType_(NSStringPboardType)
        sel = str(sel) if sel else None
        return sel if sel and sel.strip() else None
    except Exception as e:
        logger.debug("capture_selection failed closed: %s", e)
        return None
    finally:
        try:
            if saved is not None:
                pb.clearContents()
                pb.setString_forType_(saved, NSStringPboardType)
        except Exception:
            pass


def undo_in_target():
    """One-step undo after Replace: the target app's own Cmd+Z undoes the paste."""
    import Quartz
    try:
        VK_Z = 0x06
        _synth_combo(VK_Z, Quartz.kCGEventFlagMaskCommand)
        return True
    except Exception as e:
        logger.debug("undo synth failed: %s", e)
        return False


# ── Windows platform shim ────────────────────────────────────────────────
# On Windows the Mac Quartz/AppKit selection-capture and undo synth paths
# above can't run. Override `capture_selection` and `undo_in_target` with
# SendInput-based equivalents (Ctrl+C to copy the selection out via
# pyperclip's clipboard, Ctrl+Z to undo the Replace paste). Same fail-
# closed contract: any error returns None / False and the user's clipboard
# is always restored.
import sys as _sys
if _sys.platform == "win32":  # pragma: no cover — platform gate
    def _win_send_ctrl_key(vk):
        """Fire a clean Ctrl+<vk> even if the user is still holding the
        transform chord (Ctrl+Shift+T) when the callback runs.

        pynput fires the callback on key-DOWN, so by the time we
        synthesize the copy the user is typically still physically
        pressing Ctrl+Shift+T. If we send Ctrl+C now the target app
        sees `Ctrl+Shift+T+C` — not the copy command. We must
        force-release every key that would interfere (Shift, Alt, the
        Transform key T, and Ctrl itself so we can re-press it cleanly),
        send Ctrl+<vk>, then put back whatever the user was holding so
        the OS's key-state model doesn't drift.

        vk is the virtual-key code (e.g. 0x43=C, 0x5A=Z)."""
        import ctypes
        import ctypes.wintypes as wt

        INPUT_KEYBOARD    = 1
        KEYEVENTF_KEYUP   = 0x0002
        VK_CONTROL        = 0x11
        VK_LCONTROL       = 0xA2
        VK_RCONTROL       = 0xA3
        VK_SHIFT          = 0x10
        VK_LSHIFT         = 0xA0
        VK_RSHIFT         = 0xA1
        VK_MENU           = 0x12
        VK_LMENU          = 0xA4
        VK_RMENU          = 0xA5
        ULONG_PTR = ctypes.c_size_t
        user32 = ctypes.windll.user32

        class _KI(ctypes.Structure):
            _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD),
                        ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                        ("dwExtraInfo", ULONG_PTR)]

        # MOUSEINPUT must be present even though we never use it: the
        # INPUT union is sized to its LARGEST member, and Windows
        # validates the `cbSize` we pass to SendInput against the real
        # x64 layout (40 bytes = 4 type + 4 pad + 32 MOUSEINPUT). With
        # only KEYBDINPUT declared, ctypes computes 32 and every call
        # fails with ERROR_INVALID_PARAMETER (87), silently injecting
        # nothing.
        class _MI(ctypes.Structure):
            _fields_ = [("dx", wt.LONG), ("dy", wt.LONG),
                        ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                        ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class _HI(ctypes.Structure):
            _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD),
                        ("wParamH", wt.WORD)]

        class _U(ctypes.Union):
            _fields_ = [("ki", _KI), ("mi", _MI), ("hi", _HI)]

        class _I(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", wt.DWORD), ("u", _U)]

        def evt(vk_code, up=False):
            i = _I()
            i.type = INPUT_KEYBOARD
            i.ki = _KI(wVk=vk_code, wScan=0,
                       dwFlags=(KEYEVENTF_KEYUP if up else 0),
                       time=0, dwExtraInfo=0)
            return i

        def held(vkey):
            return bool(user32.GetAsyncKeyState(vkey) & 0x8000)

        # Snapshot every side-key we may need to release/restore. Left/
        # right variants are distinct: we release exactly what's down.
        holds = {
            VK_LSHIFT:  held(VK_LSHIFT),
            VK_RSHIFT:  held(VK_RSHIFT),
            VK_LMENU:   held(VK_LMENU),
            VK_RMENU:   held(VK_RMENU),
            VK_LCONTROL: held(VK_LCONTROL),
            VK_RCONTROL: held(VK_RCONTROL),
        }
        # Also release the Transform trigger key itself if it's down —
        # otherwise the target sees Ctrl+<vk>+<T> and may not interpret
        # it as copy. Skip if the caller-passed `vk` IS the trigger key,
        # since we're about to press it below anyway.
        trigger_vks = [0x54]  # 'T' (default transform_hotkey_char)
        for tk_ in trigger_vks:
            if tk_ != vk and held(tk_):
                holds[tk_] = True

        def send(inputs):
            arr = (_I * len(inputs))(*inputs)
            return user32.SendInput(len(inputs), arr, ctypes.sizeof(_I))

        # Phase 1 — release every held key that could interfere.
        release_seq = [evt(k, up=True) for k, down in holds.items() if down]
        if release_seq:
            send(release_seq)
            # A single frame delay so the target's message loop
            # processes the releases before we press Ctrl+<vk>.
            time.sleep(0.03)

        # Phase 2 — a completely clean Ctrl+<vk>. Even if the user is
        # still physically holding Ctrl, we synthesize a fresh Ctrl press
        # so the target sees an unambiguous chord. The return value is the
        # number of events Windows accepted: 0 means the injection was
        # BLOCKED (UIPI — the foreground app is elevated and we are not).
        sent = send([evt(VK_CONTROL, up=False),
                     evt(vk, up=False),
                     evt(vk, up=True),
                     evt(VK_CONTROL, up=True)])
        time.sleep(0.03)

        # Phase 3 — restore whatever the user was actually holding so
        # their key-state model stays coherent (else GetAsyncKeyState
        # would report Ctrl-up when the user hasn't physically released).
        restore_seq = [evt(k, up=False) for k, down in holds.items() if down]
        if restore_seq:
            send(restore_seq)
        return sent

    def _win_wait_modifiers_up(timeout=3.0):
        """Wait until Ctrl, Shift and Alt are ALL physically released.

        The Transform chord fires its callback on key-DOWN, so the user is
        still holding Ctrl+Shift when capture starts. Synthesizing Ctrl+C
        at that moment is unreliable no matter what we inject: Windows
        auto-repeat on the physically-held Shift re-asserts "Shift down"
        right after any injected Shift-up, so the target keeps seeing
        Ctrl+Shift+C. Injected events can't outrace physical auto-repeat —
        the only correct move is to WAIT for the real release (which
        happens naturally within a few hundred ms of the user pressing
        the chord), then send a clean Ctrl+C with nothing held."""
        import ctypes
        VK_CONTROL = 0x11
        VK_SHIFT   = 0x10
        VK_MENU    = 0x12  # Alt
        u = ctypes.windll.user32
        deadline = time.time() + timeout
        # Require a couple of consecutive all-up samples so a mid-release
        # bounce doesn't fool us.
        clear_streak = 0
        while time.time() < deadline:
            ctrl = u.GetAsyncKeyState(VK_CONTROL) & 0x8000
            shift = u.GetAsyncKeyState(VK_SHIFT) & 0x8000
            alt = u.GetAsyncKeyState(VK_MENU) & 0x8000
            if not ctrl and not shift and not alt:
                clear_streak += 1
                if clear_streak >= 2:
                    return True
            else:
                clear_streak = 0
            time.sleep(0.015)
        return False

    def _win_read_clipboard_text():
        """Read CF_UNICODETEXT directly from the Win32 clipboard.

        Avoids pyperclip here: pyperclip opens/closes the clipboard on
        every call and can race the target app that is mid-write from our
        synthesized Ctrl+C.

        NOTE on ctypes: GetClipboardData and GlobalLock return HANDLE /
        LPVOID. Without an explicit `restype` ctypes assumes `c_int` and
        TRUNCATES the value to 32 bits on x64 — the resulting bogus
        pointer raises an access violation inside wstring_at. Declaring
        the signatures is mandatory, not cosmetic."""
        import ctypes
        import ctypes.wintypes as wt
        CF_UNICODETEXT = 13
        u = ctypes.windll.user32
        k = ctypes.windll.kernel32

        u.GetClipboardData.restype = ctypes.c_void_p
        u.GetClipboardData.argtypes = [wt.UINT]
        k.GlobalLock.restype = ctypes.c_void_p
        k.GlobalLock.argtypes = [ctypes.c_void_p]
        k.GlobalUnlock.argtypes = [ctypes.c_void_p]
        k.GlobalSize.restype = ctypes.c_size_t
        k.GlobalSize.argtypes = [ctypes.c_void_p]

        # The clipboard is a shared, singly-owned resource — another app
        # may hold it briefly. Retry a few times rather than failing.
        for _ in range(10):
            if u.OpenClipboard(0):
                try:
                    if not u.IsClipboardFormatAvailable(CF_UNICODETEXT):
                        return None
                    h = u.GetClipboardData(CF_UNICODETEXT)
                    if not h:
                        return None
                    p = k.GlobalLock(h)
                    if not p:
                        return None
                    try:
                        # Bound the read by the real allocation size so a
                        # block without a NUL terminator can't over-read.
                        nbytes = k.GlobalSize(h)
                        max_chars = max(0, int(nbytes // 2) - 1) if nbytes else 0
                        if not max_chars:
                            return None
                        return ctypes.wstring_at(p, max_chars).rstrip("\x00")
                    finally:
                        k.GlobalUnlock(h)
                finally:
                    u.CloseClipboard()
            time.sleep(0.01)
        return None

    def _win_foreground_desc():
        """(hwnd, title, exe) of the foreground window — for logging so we
        can tell WHERE our Ctrl+C is being delivered."""
        import ctypes
        import ctypes.wintypes as wt
        import os
        u = ctypes.windll.user32
        k = ctypes.windll.kernel32
        try:
            hwnd = u.GetForegroundWindow()
            n = u.GetWindowTextLengthW(hwnd) + 1
            b = ctypes.create_unicode_buffer(n)
            u.GetWindowTextW(hwnd, b, n)
            pid = wt.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            exe = ""
            h = k.OpenProcess(0x1000, False, int(pid.value))
            if h:
                try:
                    size = wt.DWORD(1024)
                    eb = ctypes.create_unicode_buffer(size.value)
                    if k.QueryFullProcessImageNameW(h, 0, eb, ctypes.byref(size)):
                        exe = os.path.basename(eb.value)
                finally:
                    k.CloseHandle(h)
            return hwnd, b.value, exe
        except Exception:
            return 0, "", ""

    def _win_capture_selection():
        """Read the current selection: wait for the chord to clear →
        snapshot clipboard → Ctrl+C → wait for the clipboard SEQUENCE
        NUMBER to change → read → restore the original clipboard.

        Uses GetClipboardSequenceNumber rather than comparing text: it is
        the authoritative "someone wrote to the clipboard" signal and
        doesn't false-negative when the copied text happens to equal what
        was already there."""
        import ctypes
        import pyperclip
        u = ctypes.windll.user32

        released = _win_wait_modifiers_up(timeout=3.0)
        hwnd, title, exe = _win_foreground_desc()
        logger.info("transform capture: modifiers released=%s target=%r (%s)",
                    released, title[:60], exe)

        try:
            saved = pyperclip.paste()
        except Exception:
            saved = None

        seq_before = u.GetClipboardSequenceNumber()
        try:
            sent = _win_send_ctrl_key(0x43)   # 'C'
            if sent is not None and sent == 0:
                logger.warning(
                    "transform capture: SendInput was BLOCKED (0 events). "
                    "The target app is likely running elevated while Verbal "
                    "is not — Windows UIPI forbids input injection into "
                    "higher-integrity windows. Run Verbal as administrator "
                    "to transform text in that app.")
                return None

            got = None
            # Poll the sequence number for up to ~1.2s — Electron apps
            # (Cursor/VS Code/Slack) can take 300-600ms to service Ctrl+C.
            for _ in range(48):
                time.sleep(0.025)
                if u.GetClipboardSequenceNumber() != seq_before:
                    got = _win_read_clipboard_text()
                    break

            if got is None:
                logger.info("transform capture: clipboard never changed "
                            "(target ignored Ctrl+C or nothing selected)")
                return None
            logger.info("transform capture: got=%d chars", len(got))
            if not got.strip():
                return None
            return got
        except Exception as e:
            logger.debug("win capture_selection failed closed: %s", e)
            return None
        finally:
            try:
                if saved is not None:
                    pyperclip.copy(saved)
            except Exception:
                pass

    def _win_undo_in_target():
        """One-step undo after Replace: fire Ctrl+Z in the target app."""
        try:
            _win_send_ctrl_key(0x5A)   # 'Z'
            return True
        except Exception as e:
            logger.debug("win undo synth failed: %s", e)
            return False

    # Overwrite the Mac symbols with the Windows equivalents so all callers
    # (transform_widget / win_transform_widget) work unchanged.
    capture_selection = _win_capture_selection    # noqa: F811
    undo_in_target    = _win_undo_in_target       # noqa: F811
