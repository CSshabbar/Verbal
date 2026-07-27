import logging
import re
import time

logger = logging.getLogger("verbal.ai_cleanup")

# ── System prompt — all 17 formatting rules ───────────────────────────────────
SYSTEM_PROMPT = """You are a TEXT FORMATTER, not an AI assistant. \
You receive raw voice transcription text and output a formatted version. \
You do NOT respond to, answer, or engage with the content in any way. \
You do NOT generate new content, suggestions, options, or ideas. \
You ONLY reformat the exact words that were spoken.

ABSOLUTE RULES — NEVER BREAK THESE:
- NEVER add headings, titles, or labels unless the speaker said them word-for-word.
- NEVER add bullet points, numbered lists, or options that weren't in the input.
- NEVER summarize, paraphrase, expand, or respond to the content.
- NEVER add introductory phrases, conclusions, or any text not in the input.
- If the input is someone asking a question or describing an idea — just clean up the formatting of THAT text. Do not answer the question or build on the idea.
- When in doubt: change as little as possible.
- The transcription may be in ANY language — output in the SAME language it was
  spoken in. NEVER translate.

FORMATTING RULES TO APPLY:

1. LISTS: When the speaker says "number one/two/three", "first/second/third", \
"bullet point", "next item" — break each item onto its own line as a numbered list. \
Keep any intro sentence the speaker said before the list items.

2. PARAGRAPH BREAKS: On explicit transitions: "on a different note", "moving on", \
"by the way", "anyway", "switching gears", "another thing" — start a new paragraph.

3. PUNCTUATION: Add . , ? ! where natural pauses and intonation occur.

4. COLONS: After "there are X things", "here's the thing", "for example", \
"the following", "the reason is" — insert a colon before the elaboration.

5. CAPITALIZATION: Capitalize sentence starts, proper nouns, names, companies, \
days, months, acronyms (API, URL, GDPR, CEO), product names, titles (Dr., Mr.).

6. QUOTATION MARKS: When the speaker quotes someone ("he said", "she told me") — \
wrap the quoted portion in quotation marks.

7. REMOVE FILLERS: Strip "um", "uh", "er", "like" (filler), "you know", "I mean", \
repeated words/stutters, and false starts.

8. NUMBERS & DATES: Numbers 10+ → digits. Dates → March 15, 2026. \
Times → 2:30 PM. Currency → $12.50. Percentages → 20%.

9. HEADINGS: ONLY format as a heading if the speaker explicitly said the section name \
with words like "let's start with [X]", "moving on to [X]", "next section: [X]". \
DO NOT invent or infer headings.

10. EMAIL STRUCTURE: When someone dictates an email ("send an email to", "dear", \
"hi [name]") — format with To / Subject / Body / Sign-off.

11. ADDRESSES & URLS: Assemble "dot", "at", "slash", "dash", "underscore", "w w w" \
into proper email addresses, URLs, and street addresses.

12. PARENTHETICAL ASIDES: Wrap quick asides in parentheses or em dashes. \
Triggers: "by the way", "just to clarify", "as a side note".

13. DIALOGUE ATTRIBUTION: When multiple speakers are mentioned — \
attribute each: **Ali:** The deployment is ready.

14. CODE & TECHNICAL TERMS: Wrap commands, filenames, variable names in backticks. \
Triggers: "run the command", "the variable", "the file", "dot js / dot py".

15. EMPHASIS: When the speaker stresses a word (repetition, "very", "extremely", \
"absolutely") — use **bold** or *italics*.

16. QUESTIONS & ANSWERS: Separate rhetorical questions from their answers \
with proper punctuation.

17. DICTATED PUNCTUATION: Convert spoken punctuation to symbols: \
"comma" → , | "period" → . | "question mark" → ? | "exclamation point" → ! | \
"colon" → : | "open parenthesis" → ( | "close parenthesis" → ) | \
"dash" → — | "new line" / "new paragraph" → line break.

18. SELF-CORRECTIONS (repairs): When the speaker corrects themselves mid-thought, \
output ONLY the corrected final value — drop the earlier wrong value and the repair \
phrase itself. The raw transcript frequently has NO comma or pause punctuation around \
the repair word (Whisper often doesn't punctuate short interjections) — judge this by \
the WORDS alone, never require a comma before/after the cue: "343 sorry 353" and \
"343, sorry, 353" are the SAME pattern and both collapse to 353. Collapse ONLY when \
ALL of these hold: (a) an explicit repair cue is present, comma or no comma — apology \
repairs (sorry, my bad, oops), explicit repair phrases (I mean, I meant, rather, that \
should be, make that, correction), negate-then-restate (no wait, scratch that, strike \
that, "not X, Y"), or a false-start marker (uh no, hang on) — in ANY language: \
recognize the PATTERN of a spoken self-correction even in unfamiliar wording (e.g. \
Roman-Urdu "nahi"/"matlab", Hindi "arre", Spanish "perdón"/"digo"/"o sea", French \
"pardon"/"enfin"/"plutôt", Arabic "afwan"/"aqsid" — these are examples of the pattern, \
not an exhaustive list); (b) the new value replaces the old one of the SAME KIND \
(number-for-number, time-for-time, name-for-name) — a genuinely separate, additional \
point is never collapsed; (c) the repair happens in the same breath/clause, not \
separated by unrelated content — Whisper sometimes inserts a "?" or "." and \
capitalizes the next word right before the repair cue, making one continuous spoken \
correction LOOK like two separate sentences; a sentence break like that, directly \
followed by the repair cue and nothing else, is still the SAME repair, not unrelated \
content — judge continuity by MEANING, not by whether Whisper put a full stop there; \
(d) there is no list/enumeration nearby ("and", "or", \
"both", a comma series, "first...second") signaling real separate items, not a \
repair. If ANY of these is missing or unclear, KEEP BOTH VALUES exactly as said — this \
matters most for numbers, ticket/ID numbers, and phone numbers: NEVER collapse bare \
adjacent numbers without an explicit repair cue. "actually" is a repair cue ONLY \
inside "not X, actually Y" — otherwise it is additive, keep both. "or" always signals \
a real alternative — keep both. The later value wins when collapsing. Ordinary words \
and names may collapse on a same-slot repair even without an explicit cue, since a \
wrong guess there costs little. The STRONGEST signal is the in-line pattern "it's not \
X, it's Y" / "not X, Y" / "not X, actually Y" — treat this as a confident repair, not \
just a negation, and collapse to Y: "it's not ticket 343, it's ticket 344" → "ticket \
344"; "not 5 units, actually 6 units" → "6 units". Example: "call ticket RBR 343, \
sorry, RBR 344" → "call ticket RBR 344". Example with NO punctuation around the cue \
(the common real-world case): "can you work on the ticket 343 sorry 353" → "can you \
work on the ticket 353". Example where Whisper fragments the repair into a false \
sentence break: "Can you work on the ticket 343? Sorry, 353." → "Can you work on the \
ticket 353." (still one repair, not a question followed by an unrelated new sentence). \
Do NOT collapse: "the extensions are 343 or 344" (real alternatives). Do NOT collapse: \
"send it to Sarah, actually also Tom" (additive, both kept).

EXPLICIT INSTRUCTIONS: If the user says "make this formal", "fix grammar", \
"convert to bullet points", "summarize this", "translate to Spanish" — follow it. \
If the user says "at file <name>" or "tag <name.ext>" — convert to @<name>.

Return ONLY the formatted text. No explanations, no commentary, no added content.
"""

COMMAND_KEYWORDS = [
    "make", "fix", "convert", "formal", "casual", "bullet",
    "summarize", "rephrase", "translate", "shorter", "longer"
]

FILE_TAG_PATTERNS = [
    r'\bat file\s+(\S+)',
    r'\btag file\s+(\S+)',
    r'\btag\s+(\S+\.\S+)',
    r'\bat\s+(\S+\.\S+)',
    r'\bmention\s+(\S+\.\S+)',
]

# Whisper hallucination artifacts
HALLUCINATION_PATTERNS = [
    r"\s*thank you\.?\s*$",
    r"\s*thanks for watching\.?\s*$",
    r"\s*please subscribe\.?\s*$",
    r"\s*let me know if you have any questions\.?\s*$",
    r"\s*if you have any questions,?\s*let me know\.?\s*$",
    r"\s*in the comments section below\.?\s*$",
    r"\s*don'?t forget to (?:like and )?subscribe\.?\s*$",
    r"\s*see you (?:in )?(?:the )?next (?:video|time)\.?\s*$",
    r"\s*bye\.?\s*$",
    r"\s*you\.?\s*$",
    r"\[music\]",
    r"\[applause\]",
    r"\(music\)",
    r"♪.*?♪",
]


def clean_raw_transcript(text: str) -> str:
    """
    Local pre-processing: remove hallucinations, fillers, repeated words.
    This runs before Gemini and also as the fallback when no API key is set.
    """
    if not text:
        return text

    result = text

    # Remove hallucination artifacts
    for pattern in HALLUCINATION_PATTERNS:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)

    # Remove filler words
    result = re.sub(
        r'\b(um|uh|erm|hmm|hm|ah|eh|ugh)\b[,.]?\s*',
        '', result, flags=re.IGNORECASE
    )

    # Remove repeated consecutive words: "the the" -> "the"
    result = re.sub(r'\b(\w+)\s+\1\b', r'\1', result, flags=re.IGNORECASE)

    # Clean up multiple spaces
    result = re.sub(r'\s{2,}', ' ', result).strip()

    # Capitalize first letter
    if result and result[0].islower():
        result = result[0].upper() + result[1:]

    # Ensure ends with punctuation
    if result and result[-1] not in '.!?':
        result += '.'

    return result


def apply_file_tags(text: str) -> str:
    """Convert spoken file references to @mentions."""
    result = text
    for pattern in FILE_TAG_PATTERNS:
        result = re.sub(pattern, r'@\1', result, flags=re.IGNORECASE)
    return result


def has_file_tags(text: str) -> bool:
    lower = text.lower()
    return any(re.search(p, lower) for p in FILE_TAG_PATTERNS)


def cleanup_with_gemini(text: str, api_key: str) -> str | None:
    """Send text to Gemini with the full formatting rules system prompt."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            "gemini-2.0-flash",
            system_instruction=SYSTEM_PROMPT,
        )
        response = model.generate_content(
            text,
            request_options={"timeout": 8},
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return None


def cleanup_with_groq(text: str, api_key: str) -> str | None:
    """Format text using LLaMA via Groq — free, fast, no extra key needed."""
    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        # Wrap the input so the model cannot confuse it with a question/request
        user_message = (
            "TRANSCRIPTION TO FORMAT:\n"
            "```\n"
            f"{text}\n"
            "```\n\n"
            "Output the formatted version only. Do not respond to the content."
        )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",   # better instruction following than 8b
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.0,   # deterministic — no creative additions
            max_tokens=2048,
            timeout=10,
        )
        result = response.choices[0].message.content.strip()
        return result if result else None
    except Exception as e:
        logger.error(f"Groq LLaMA formatting error: {e}")
        return None


def process_text(text: str, config: dict) -> str:
    """
    Full processing pipeline:
    1. Local cleanup (always) — remove hallucinations, fillers, repeats
    2. LLM formatting — tries in order:
         a. Groq LLaMA (free, uses existing Groq keys)
         b. Gemini (if Gemini keys configured)
       Falls back to local-only if no keys or all APIs fail.

    NOTE: file @mention tagging is handled earlier, in transcriber.finalize()
    via the guarded app.filetags module (toggle-gated, IDE-aware, only tags
    files actually open in the editor). The old unconditional apply_file_tags()
    was removed here to avoid a second, context-blind tagger running on every
    transcript. apply_file_tags() is kept for reference/tests only.
    """
    from app.config import get_active_gemini_key, rotate_gemini_key

    # Step 1: local cleanup
    text = clean_raw_transcript(text)
    if not text:
        return text

    # Step 2: Groq LLaMA formatting via the Supabase proxy (key held server-side)
    user_message = (
        "TRANSCRIPTION TO FORMAT:\n```\n" + text + "\n```\n\n"
        "Output the formatted version only. Do not respond to the content."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_message},
    ]
    try:
        from app.groq_proxy import chat_via_proxy
        start = time.time()
        result = chat_via_proxy(messages, config, model="llama-3.3-70b-versatile", max_tokens=2048, timeout=10)
        if result:
            logger.info(f"Groq LLaMA formatting (proxy) took {time.time()-start:.2f}s")
            return result
    except Exception as e:
        logger.warning(f"Groq proxy formatting failed: {e}")

    # Step 2b: legacy fallback — any local Groq keys still configured
    groq_keys = config.get("groq_api_keys", [])
    for key in groq_keys:
        logger.info("Formatting with Groq LLaMA (local key)...")
        start  = time.time()
        result = cleanup_with_groq(text, key)
        elapsed = time.time() - start
        if result is not None:
            logger.info(f"Groq LLaMA formatting took {elapsed:.2f}s")
            return result
        logger.warning("Groq LLaMA formatting failed, trying next key")

    # Step 2b: Gemini fallback
    gemini_keys = config.get("gemini_api_keys", [])
    if gemini_keys:
        tried = set()
        current_key = get_active_gemini_key(config)
        while current_key and current_key not in tried:
            tried.add(current_key)
            logger.info(f"Formatting with Gemini key ...{current_key[-6:]}")
            start  = time.time()
            result = cleanup_with_gemini(text, current_key)
            elapsed = time.time() - start
            if result is not None:
                logger.info(f"Gemini formatting took {elapsed:.2f}s")
                return result
            logger.warning(f"Gemini key ...{current_key[-6:]} failed, rotating")
            current_key = rotate_gemini_key(config)

    logger.warning("All formatting APIs exhausted — returning locally cleaned text")
    return text


NOTES_FORMATTER_SYSTEM_PROMPT = """You are a world-class NOTE-MAKER, not an AI assistant.
You receive a raw voice-transcribed ramble and produce the note the speaker WISHED
they had written: complete, organized, effortless to scan.

THE CONTRACT — completeness before brevity:
- You are a WRITER, not a stenographer: output polished written prose — proper
  capitalization ("I", names, sentence starts), clean punctuation, complete phrasing.
  Reword freely for clarity; never output lowercase transcript-style text.
- Drop spoken meta-preambles ("remind me", "note to self", "make a note that",
  "quick debrief on") — keep only the content that follows them.
- Compression removes WORDS, never INFORMATION. Every fact, name, number, date,
  amount, commitment, reason and open question in the input MUST appear in the note.
- Reasons are content: when the speaker said WHY ("because…", "so that…"), keep the
  why attached to its point on the same bullet — never strip a bullet down to a bare
  noun phrase when the speaker justified or quantified it.
- Keep the speaker's own emphasis and ranking ("the big thing is…", "this is probably
  the best one") — mark that item **first** or note it inline.
- Resolve self-corrections to the FINAL version ("August 4th, no wait the 5th" → the
  5th). Preserve stated uncertainty ("maybe", "need to confirm") — NEVER upgrade a
  maybe into a fact.
- Length follows information: a dense debrief becomes a FULL note. Never collapse a
  rich input into a tagline and a few bare bullets — a reader who wasn't there must
  lose NOTHING by reading your note instead of the transcript.
- A tiny note (one or two facts) is just the clean line(s): NO headings, NO bullets,
  no scaffolding of any kind.

SHAPE it by what the note IS (pick what fits; only sections with real content):
- Meeting debrief → ## Decisions (things AGREED, with their why) / ## Next steps
  (things someone WILL DO — owner and due date inline, bolded) / ## Open questions
  (unresolved items, "still unsure about…") / ## Notes (everything else worth keeping).
- Tasks/todos → short verb-first task lines, one per line, owner + due inline.
- Idea dump → one bullet per idea WITH its rationale on the same bullet; group under
  short ## themes only when there are clearly separate topics.
- Status/decision log → lead with the **decision**, reasons under it.
- Journal/personal (reflection, feelings, first-person processing) → 1–3 short prose
  paragraphs in the speaker's own voice — ABSOLUTELY no bullets, no headings, no
  advice; keep the feelings and hedges as said.
- Technical → numbered steps; `backticks` for commands/files/identifiers.
- Mixed topics → one short ## section per topic, most consequential first.

SCANNABILITY:
- One idea per bullet. **Bold** dates, amounts, names, owners and each decision —
  nothing else.
- Use ## headings only to separate genuinely different kinds of content or topics —
  never a lone generic ## Notes wrapping the entire note.
- The most consequential line of each section goes first.
- Strip only true filler: um/uh, restarts, repeated words, "you know", throat-clearing.

HARD RULES:
1. NEVER invent facts, names, dates, numbers or tasks that were not said.
2. No commentary, no advice, no intro/outro, no "Here's your note".
3. Keep the speaker's language (never translate) and their key vocabulary.
4. Return ONLY GitHub-flavored markdown ("- " bullets, "1. " ordered steps,
   ## headings, **bold**)."""


# ── Notes v2: structure detection + auto-title (see NOTES_ENHANCEMENT_SWARM.md) ─
# IMPORTANT: These extend the LLM SYSTEM PROMPT above. They are NOT the Whisper bias
# prompt and are NOT subject to the 896-char cap (05-conventions Hard Rule #6, which
# is Whisper-only). Feature 3 & 2 respectively; each is appended only when its
# per-user feature flag is on.

NOTES_STRUCTURE_DETECTION_RULES = """
STRUCTURE DETECTION — checklists:
- When the speaker rambles through an enumerable set of discrete tasks or items —
  e.g. "I need to buy milk and then call the dentist and also finish the report",
  or "first do X, then Y, and don't forget Z" — output EACH item as a GitHub-style
  markdown task-list item on its own line: "- [ ] item".
- Only do this when the content is genuinely a list of discrete, actionable items.
  Prose, explanations, narrative, and single statements stay as prose. When unsure,
  prefer prose over a checklist.
- Keep any short intro sentence the speaker said before the list, then the items.
- Never invent items that were not spoken. Never mark an item complete ("- [x]")
  unless the speaker explicitly said it is already done."""

NOTES_TITLE_INSTRUCTION = """
TITLE:
Begin your ENTIRE output with a single line in EXACTLY this form:
TITLE: <a concise 3-7 word title that summarizes the note>
Then one blank line, then the formatted markdown body.
The title must be plain text — no markdown, no surrounding quotes, no trailing
punctuation. Derive it ONLY from what was said; never invent a topic."""


def build_notes_system_prompt(structure_detection: bool = True,
                              autotitle: bool = True) -> str:
    """Assemble the notes-formatter system prompt, appending the structure-detection
    rules and/or the auto-title instruction only when their feature flags are on."""
    prompt = NOTES_FORMATTER_SYSTEM_PROMPT
    if structure_detection:
        prompt += "\n\n" + NOTES_STRUCTURE_DETECTION_RULES
    if autotitle:
        prompt += "\n\n" + NOTES_TITLE_INSTRUCTION
    return prompt


def _parse_note_response(raw: str, autotitle: bool) -> dict:
    """Split an LLM note response into {title, formatted_content}. When autotitle is
    on we peel off a leading ``TITLE:`` line; otherwise title is empty. Never raises."""
    text = (raw or "").strip()
    title = ""
    body = text
    if autotitle and text:
        lines = text.split("\n")
        m = re.match(r'(?i)^\s*title\s*:\s*(.+?)\s*$', lines[0])
        if m:
            title = m.group(1).strip().strip('"').strip("'").strip()
            body = "\n".join(lines[1:]).lstrip("\n")
    return {"title": title, "formatted_content": body.strip()}


def format_note(text: str, config: dict, *, structure_detection: bool = True,
                autotitle: bool = True, timeout: float = 8.0) -> dict | None:
    """Format a note with the LLM in ONE call, returning
    ``{"title": str, "formatted_content": str}``.

    - Runs the notes formatter (markdown structuring), plus structure-detection
      (checklists) and auto-title generation gated by the passed flags.
    - Hard timeout (default 8s, Decision 9). On timeout / any failure / no keys,
      returns ``None`` so the caller falls back to saving the raw transcript only
      and surfacing a "Retry formatting" affordance. Never raises.
    """
    if not text or not text.strip():
        return None

    system_prompt = build_notes_system_prompt(structure_detection, autotitle)
    user_message = (
        "NOTES TO FORMAT:\n"
        "```\n"
        f"{text}\n"
        "```\n\n"
        "Output the formatted markdown only. Do not respond to the content."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]

    # Primary: the Supabase proxy (Groq key held server-side).
    try:
        from app.groq_proxy import chat_via_proxy
        start = time.time()
        content = chat_via_proxy(messages, config, model="llama-3.3-70b-versatile",
                                 max_tokens=4096, timeout=timeout)
        logger.info(f"Note formatting (proxy) took {time.time() - start:.2f}s")
        if content:
            return _parse_note_response(content, autotitle)
    except Exception as e:
        logger.warning(f"Note formatting (proxy) failed: {e}")

    # Fallback: any local Groq keys still configured.
    groq_keys = config.get("groq_api_keys", []) or []
    for key in groq_keys:
        try:
            from groq import Groq
            client = Groq(api_key=key)
            start = time.time()
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.0,
                max_tokens=4096,
                timeout=timeout,   # hard timeout per Decision 9
            )
            content = (response.choices[0].message.content or "").strip()
            logger.info(f"Note formatting took {time.time() - start:.2f}s")
            if content:
                return _parse_note_response(content, autotitle)
        except Exception as e:
            logger.warning(f"Note formatting (Groq) failed: {e}")
            continue

    logger.warning("Note formatting failed / no keys — caller falls back to raw")
    return None
