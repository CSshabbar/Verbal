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


def _chat(system, user, config, max_tokens=2048):
    from app.groq_proxy import chat_via_proxy
    raw = chat_via_proxy(
        [{"role": "system", "content": system},
         {"role": "user", "content": user}],
        config, max_tokens=max_tokens, timeout=30.0)
    return raw


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
