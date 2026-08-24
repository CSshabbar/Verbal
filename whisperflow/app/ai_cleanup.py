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

7. REMOVE FILLERS: Strip "um", "uh", "er", "like" (filler), "you know", \
repeated words/stutters, and false starts that are NOT self-corrections (see rule 18: \
a repair cue is never filler — rule 18 governs "I mean", "sorry", "no wait", "scratch \
that" and similar corrective language, and is evaluated BEFORE this rule whenever one \
of those cues is present).

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
phrase itself. PRECEDENCE: this rule is judged BEFORE rule 7's filler-stripping — a \
repair cue is never generic filler. The raw transcript frequently has NO comma or \
pause punctuation around the repair word (Whisper often doesn't punctuate short \
interjections) — judge this by the WORDS alone, never require a comma before/after \
the cue: "343 sorry 353" and "343, sorry, 353" are the SAME pattern and both collapse \
to 353.

Collapse ONLY when ALL FOUR of these hold: \
(a) an explicit repair cue is present, comma or no comma. Cue families (illustrative \
patterns, not an exhaustive word list — recognize the PATTERN in unfamiliar wording \
too, in ANY language): apology repairs (sorry, my bad, oops, whoops, my mistake, \
pardon, pardon me); explicit repair phrases (I mean, I meant, rather, or rather, that \
should be, that should've been, make that, let me rephrase, let me correct that, \
correction, what I meant was, I should say); negate-then-restate (no wait, wait no, \
hold on no, scratch that, strike that, forget that, ignore that, or the in-line "not \
X, Y"); false-start markers (uh no, um no, hang on, let me back up). Multilingual \
examples of the same patterns: Roman-Urdu "nahi"/"nahi nahi"/"matlab"/"galat", Hindi \
"nahi"/"matlab"/"arre"/"balki"/"maaf karna", Spanish "perdón"/"perdona"/"digo"/"o \
sea"/"quiero decir"/"mejor dicho"/"no espera", French "pardon"/"je veux dire"/"enfin"/ \
"plutôt"/"ou plutôt"/"c'est-à-dire"/"non attends", Arabic "afwan"/"aqsid"/"yaani"/"laa" \
— these are examples of the pattern, not an exhaustive list; \
(b) the new value replaces the old one of the SAME KIND (number-for-number, \
time-for-time, name-for-name — even across a magnitude change: "343, sorry, 3430" is \
still same-kind and collapses) — a genuinely separate, additional point, or a \
DIFFERENT kind of value after a cue (a number then a name: "send it to 344, sorry, \
tell Dave" keeps BOTH — that is not a same-slot swap), is never collapsed; \
(c) the repair happens in the same breath/clause, not separated by unrelated content \
or many intervening words — Whisper sometimes inserts a "?" or "." and capitalizes the \
next word right before the repair cue, making one continuous spoken correction LOOK \
like two separate sentences; a sentence break like that, directly followed by the \
repair cue and nothing else, is still the SAME repair, not unrelated content — judge \
continuity by MEANING, not by whether Whisper put a full stop there; \
(d) there is no list/enumeration nearby ("and", "plus", "also", "too", "as well", "as \
well as", "or", "both", "either", a comma series, "first...second") signaling real \
separate items, not a repair — EXCEPT: "and" directly followed by a repair cue is NOT \
a list veto, it is the connector INTO the correction, not a second list item: "343 and \
sorry 344" still collapses to 344, the same as "343, sorry, 344" would.

If ANY of (a)-(d) is missing or unclear, KEEP BOTH VALUES exactly as said — this \
matters most for numbers, ticket/ID numbers, and phone numbers: NEVER collapse bare \
adjacent numbers without an explicit repair cue. Multiple corrections in one breath \
resolve to the LAST surviving value: "343, sorry 344, no wait 345" → "345". A \
correction can occur INSIDE a real list without destroying the rest of the list — \
collapse only the corrected slot, keep the other items: "apples, oranges — sorry, \
tangerines — and bananas" → "apples, tangerines, and bananas". A cue word is NOT a \
repair when there is no candidate same-kind value on both sides of it — it is then \
just ordinary CONTENT, keep the sentence as spoken: "I want to say sorry to the team" \
(sorry is the message, not a repair); "the answer is no" / "just say no" (no is \
content); "make that report longer" (an instruction, not a value swap — no prior \
same-kind value to replace); "correction is hard" (correction used as a noun, not a \
cue). Collapsing an identical repeated value is a harmless no-op: "344, sorry, 344" → \
"344". "actually" is a repair cue ONLY inside "not X, actually Y" — otherwise it is \
additive, keep both. "or" always signals a real alternative — keep both. The later \
value wins when collapsing. Ordinary words and names may collapse on a same-slot \
repair even without an explicit cue, since a wrong guess there costs little; numbers, \
ticket/ID numbers, and phone numbers require an explicit cue even when adjacent. The \
STRONGEST signal is the in-line pattern "it's not X, it's Y" / "not X, Y" / "not X, \
actually Y" — this works in EITHER order ("not 343, 344" and "344, not 343" both \
resolve to 344) — treat this as a confident repair, not just a negation, and collapse \
to Y: "it's not ticket 343, it's ticket 344" → "ticket 344"; "not 5 units, actually 6 \
units" → "6 units". Example: "call ticket RBR 343, sorry, RBR 344" → "call ticket RBR \
344". Example with NO punctuation around the cue (the common real-world case): "can \
you work on the ticket 343 sorry 353" → "can you work on the ticket 353". Example \
where Whisper fragments the repair into a false sentence break: "Can you work on the \
ticket 343? Sorry, 353." → "Can you work on the ticket 353." (still one repair, not a \
question followed by an unrelated new sentence). Do NOT collapse: "the extensions are \
343 or 344" (real alternatives). Do NOT collapse: "send it to Sarah, actually also \
Tom" (additive, both kept). Do NOT collapse: "ticket numbers 343 and 344 are both \
still open" (list, both kept). Do NOT collapse: "please call 343, 344 today" (bare \
adjacent numbers, no cue, both kept).

EXPLICIT INSTRUCTIONS: If the user says "make this formal", "fix grammar", \
"convert to bullet points", "summarize this", "translate to Spanish" — follow it. \
If the user says "at file <name>" or "tag <name.ext>" — convert to @<name>.

Return ONLY the formatted text. No explanations, no commentary, no added content.
"""

# ── speed_mode: a lean formatter prompt ───────────────────────────────────────
# SYSTEM_PROMPT above is ~2,476 tokens and is re-sent as prefill on EVERY dictation.
# That cost is paid twice over: latency on the request, and the shared free-tier daily
# token budget (100k TPD across all users ÷ ~2,900 tokens per call ≈ 34 formatted
# dictations a day before the whole user base drops to regex-only output).
#
# This keeps the rules that fire constantly and drops the ones that almost never do
# (colons, quotation marks, headings, email structure, parentheticals, dialogue
# attribution, backticks, emphasis, Q&A splitting — still handled acceptably by a
# competent model without being spelled out). Rule 18 is reproduced in full and
# deliberately unabridged: self-correction resolution is the semantically hard part
# and is pinned by self_correction_fixtures.py against the live model.
LEAN_SYSTEM_PROMPT = """You are a TEXT FORMATTER, not an AI assistant. You receive raw voice \
transcription text and output a formatted version. You do NOT respond to, answer, or engage with \
the content. You do NOT add content, suggestions, options or ideas. You ONLY reformat the exact \
words that were spoken.

ABSOLUTE RULES — NEVER BREAK THESE:
- NEVER add headings, titles, labels, bullets or numbered lists that the speaker did not say.
- NEVER summarize, paraphrase, expand on, or answer the content. If the input is a question or an \
idea, just clean up THAT text.
- NEVER add introductions or conclusions.
- When in doubt, change as little as possible.
- Output in the SAME language the input is in. Never translate.

FORMATTING:
1. PUNCTUATION: add . , ? ! where natural pauses and intonation occur.
2. CAPITALIZATION: sentence starts, proper nouns, names, companies, products, place names.
3. PARAGRAPH BREAKS: only on explicit transitions ("on a different note", "moving on", "anyway", \
"another thing").
4. LISTS: only when the speaker enumerates ("number one", "first", "secondly").
5. REMOVE FILLERS: strip "um", "uh", "er", filler "like", "you know", "I mean", and stuttered \
repeats ("the the" -> "the"). Keep meaningful words.
6. NUMBERS & DATES: numbers 10+ as digits; dates as March 15, 2026; keep IDs and version strings \
exactly as spoken (RBR 344, 1.0.10).
7. ADDRESSES & URLS: assemble spoken "dot", "at", "slash", "dash", "underscore" into real \
addresses (sraza at idiaz dot io -> sraza@idiaz.io).
8. DICTATED PUNCTUATION: convert spoken punctuation to symbols — "comma" -> , "period"/"full \
stop" -> . "question mark" -> ? "new paragraph" -> a blank line. Only when clearly meant as a \
command, not when the word is part of the sentence.
9. SELF-CORRECTIONS (repairs): When the speaker corrects themselves mid-thought, keep ONLY the \
corrected value and drop the abandoned one along with the repair cue. Collapse ONLY when all of \
these hold: (a) there is an explicit repair cue — "sorry", "I mean", "no wait", "actually no", \
"scratch that", or a Roman-Urdu equivalent such as "nahi"; (b) the two values are the same KIND of \
thing (two ticket IDs, two numbers, two names, two dates); (c) they are tightly adjacent, in the \
same clause; and (d) there is no list grammar nearby ("and", "then", "also", "both"). If any \
condition fails, keep both values verbatim — bare adjacent numbers or IDs with no cue are NEVER \
collapsed. Example: "ticket RBR 343, sorry, RBR 344" -> "ticket RBR 344". Counter-example: \
"tickets RBR 343 and RBR 344" -> unchanged. Judge this BEFORE removing fillers, so the repair cue \
is still visible when you decide.

Return ONLY the formatted text. No explanations, no commentary, no added content.
"""

# Formatting model used when speed_mode is on.
#
# Measured on this exact task (lean prompt, one real transcript, via the proxy):
#   llama-3.1-8b-instant     0.82s   51 output tokens
#   llama-3.3-70b-versatile  1.13s   50 output tokens
#   openai/gpt-oss-20b       1.54s  430 output tokens + 1,679 chars of reasoning
#
# gpt-oss-20b was the obvious pick on paper (1000 tok/s vs 280) and is the WRONG pick in
# practice: it is a reasoning model, so it burns hundreds of hidden thinking tokens before
# answering a purely mechanical formatting request. Throughput does not save you when you
# emit 8x the tokens. 8b-instant also carries 500k tokens/day on the free tier against the
# 70B's 100k, which combined with the lean prompt is the difference between ~34 and ~590
# formatted dictations a day.
# 2026-08-18: Groq retired the llama-3.x tier from this key (every call
# 404'd model_not_found — notes reformat, meeting summaries and speed/
# chained formatting all silently degraded). The two models the key can
# still use, verified live: openai/gpt-oss-20b (fast) and
# openai/gpt-oss-120b (quality, strict-JSON confirmed).
SPEED_CLEANUP_MODEL = "openai/gpt-oss-20b"
# At or below this many words, speed_mode skips the LLM entirely and ships the
# regex-cleaned text. clean_raw_transcript already capitalizes and adds terminal
# punctuation, which is essentially all a short command needs.
_SKIP_CLEANUP_MAX_WORDS = 8

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


def cleanup_with_gemini(text: str, api_key: str, context: str = "") -> str | None:
    """Send text to Gemini with the full formatting rules system prompt.

    `context` is the optional Phase-0 grounding preamble (MER-44) — prepended to
    the content, clearly labeled as grounding-only inside build_context_block()."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            "gemini-2.0-flash",
            system_instruction=SYSTEM_PROMPT,
        )
        response = model.generate_content(
            build_dictation_user_message(text, context),
            request_options={"timeout": 8},
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return None


def cleanup_with_groq(text: str, api_key: str, context: str = "") -> str | None:
    """Format text using LLaMA via Groq — free, fast, no extra key needed.

    `context` is the optional Phase-0 grounding preamble (MER-44)."""
    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        # Wrap the input so the model cannot confuse it with a question/request
        user_message = build_dictation_user_message(text, context)

        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",   # quality tier (llama-3.3 retired 2026-08)
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.0,   # deterministic — no creative additions
            max_tokens=2048,
            timeout=10,
            reasoning_effort="low",   # mechanical reformatting, not a reasoning task —
                                      # gpt-oss defaults to "medium" and silently burns
                                      # hundreds of hidden thinking tokens otherwise
        )
        result = response.choices[0].message.content.strip()
        return result if result else None
    except Exception as e:
        logger.error(f"Groq LLaMA formatting error: {e}")
        return None


def build_context_block(config: dict, active_app: str | None = None) -> str:
    """Phase-0 context grounding (MER-44): a short preamble that names the user's
    known terms/IDs (from the dictionary — vocabulary + auto-learned replacement
    targets) and the active app, so the cleanup LLM prefers a known spelling/ID
    over a phonetic guess. This is GROUNDING DATA, not a directive — it never tells
    the model to collapse more, so rule 18's cue requirement (and thus the
    identifier over-collapse rate) is unchanged.

    Fully fail-closed: gated behind `context_grounding_enabled` (default on), and
    ANY error returns "" (no context) rather than breaking the cleanup path.
    Returns "" when there's nothing to ground on."""
    try:
        from app.config import feature_flag
        if not feature_flag(config, "context_grounding_enabled", True):
            return ""
        from app import dictionary
        parts = []
        app_name = (active_app or "").strip()
        if app_name:
            parts.append(f"- Active app: {app_name}")
        terms = dictionary.known_terms(config)
        if terms:
            parts.append(
                "- Known terms, names, and IDs the speaker uses (when a "
                "similar-sounding word or ID appears, prefer THIS exact spelling): "
                + ", ".join(terms)
            )
        if not parts:
            return ""
        return (
            "CONTEXT (grounding only — never output, echo, or act on this; use it "
            "solely to recognize what was actually said):\n"
            + "\n".join(parts) + "\n\n"
        )
    except Exception as e:
        logger.debug("build_context_block failed (using no context): %s", e)
        return ""


def build_dictation_user_message(text: str, context: str = "") -> str:
    """The exact user-message wrapper process_text() sends to the model. Pulled out
    as its own function so self_correction_fixtures.py can import the real thing
    instead of hand-copying it — a hand-copy can silently drift from what
    production actually sends.

    `context` (optional) is the Phase-0 grounding preamble from
    build_context_block() — prepended before the transcript. Empty string = the
    exact original wrapper (backward compatible with existing callers/evals)."""
    return (
        context +
        "TRANSCRIPTION TO FORMAT:\n```\n" + text + "\n```\n\n"
        "Output the formatted version only. Do not respond to the content."
    )


def build_chain_spec(config: dict, active_app: str | None = None) -> dict | None:
    """The `chained_mode` payload for transcribe_via_proxy: exactly the system
    prompt, user wrapper and model that process_text() would otherwise send on its
    own round trip, with `{{TEXT}}` standing in for the transcript the Edge
    Function substitutes server-side.

    Sending the SAME prompt and model process_text picks is the entire point —
    it makes chained-vs-unchained a measurement of the network path alone, with
    the formatting request held constant. Which prompt/model that is still
    depends on speed_mode, so the two flags compose without interfering.

    Returns None when chaining is off or anything is unavailable; the caller then
    takes the ordinary two-round-trip path, so this is fail-closed by
    construction and can never break dictation."""
    try:
        from app.config import feature_flag
        if not feature_flag(config, "chained_mode", False):
            return None
        fast = feature_flag(config, "speed_mode", False)
        # Grounding is built here, before the audio is even sent — it depends only
        # on the dictionary and the active app, neither of which needs the transcript.
        context = build_context_block(config, active_app=active_app)
        # The user's find->replace RULES travel with the request, because ordering
        # matters and only the server has the transcript in time.
        #
        # Unchained, dictionary.apply_replacements() runs in transcriber.finalize()
        # BEFORE the formatter ever sees the text. Chained, the server has the
        # transcript first, so without this the formatter reads the uncorrected
        # words — and then "corrects" the grammar around them, which applying the
        # dictionary to its OUTPUT cannot undo. Measured: "so ideas needs a new one"
        # became "so ideas need a new one", and the later ideas->Idiaz fix was
        # powerless to restore "needs". The dictionary rewrites 4 of 20 of this
        # user's clips, so this is a 20% exposure, not an edge case.
        #
        # Only the DATA crosses; the substitution itself is mechanical (word-boundary,
        # case-insensitive) and mirrored in the Edge Function.
        rules = []
        try:
            from app import dictionary as _d
            rules = [{"from": r["from"], "to": r["to"]}
                     for r in _d.get(config)["replacements"]
                     if r.get("from") and r.get("to")]
        except Exception as e:
            logger.debug("chain replacements unavailable: %s", e)
        return {
            "system": LEAN_SYSTEM_PROMPT if fast else SYSTEM_PROMPT,
            "user": build_dictation_user_message("{{TEXT}}", context),
            "model": SPEED_CLEANUP_MODEL if fast else "openai/gpt-oss-120b",
            "replace": rules,
            # Both models here are gpt-oss (reasoning models) — see the
            # SPEED_CLEANUP_MODEL comment above process_text() for the measured cost
            # of leaving this at Groq's "medium" default on a mechanical task.
            "reasoning_effort": "low",
        }
    except Exception as e:
        logger.debug("chain spec unavailable — formatting locally: %s", e)
        return None


def process_text(text: str, config: dict, active_app: str | None = None,
                 chained_result: str | None = None) -> str:
    """
    Full processing pipeline:
    1. Local cleanup (always) — remove hallucinations, fillers, repeats
    2. LLM formatting — tries in order:
         a. Groq LLaMA (free, uses existing Groq keys)
         b. Gemini (if Gemini keys configured)
       Falls back to local-only if no keys or all APIs fail.

    `active_app` (optional, Phase-0 context grounding, MER-44) — the name of the
    app the transcript is being dictated INTO, available at the injection call
    sites (main.py / win_main.py). Passed into build_context_block() alongside the
    user's dictionary terms; None (notes/retry paths) still gets known-terms
    grounding, just no app hint.

    `chained_result` (optional, `chained_mode`) — formatting the Edge Function
    already performed inside the transcription round trip, using the spec from
    build_chain_spec(). It is threaded in HERE rather than short-circuiting at the
    call site so every rule below still gets to decide: the local cleanup runs,
    the speed_mode short-transcript skip still wins over it, and an empty
    transcript is still an empty transcript. Only the network call is skipped.

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

    # speed_mode (default OFF → everything below is baseline behaviour).
    from app.config import feature_flag
    fast = feature_flag(config, "speed_mode", False)

    # Short transcripts skip the LLM round trip altogether. clean_raw_transcript has
    # already capitalized and punctuated; a 4-word command does not need a 70B model,
    # and this is where the largest proportional latency win is.
    if fast:
        words = len(text.split())
        if words <= _SKIP_CLEANUP_MAX_WORDS:
            logger.info(f"speed_mode: {words}w <= {_SKIP_CLEANUP_MAX_WORDS} — skipped LLM formatting")
            return text

    # chained_mode: the formatting already happened inside the transcription round
    # trip. Everything above still ran (local cleanup, the short-transcript skip),
    # so this only replaces the second network call — not the decisions around it.
    if chained_result:
        logger.info("chained_mode: using server-side formatting — second round trip skipped")
        return chained_result

    # Phase-0 grounding preamble (fail-closed → "" on any issue).
    context = build_context_block(config, active_app=active_app)

    # Step 2: Groq LLaMA formatting via the Supabase proxy (key held server-side)
    user_message = build_dictation_user_message(text, context)
    _prompt = LEAN_SYSTEM_PROMPT if fast else SYSTEM_PROMPT
    _model = SPEED_CLEANUP_MODEL if fast else "openai/gpt-oss-120b"
    messages = [
        {"role": "system", "content": _prompt},
        {"role": "user",   "content": user_message},
    ]
    try:
        from app.groq_proxy import chat_via_proxy
        start = time.time()
        result = chat_via_proxy(messages, config, model=_model, max_tokens=2048, timeout=10,
                                reasoning_effort="low")
        if result:
            logger.info(f"{'speed_mode' if fast else 'Groq LLaMA'} formatting (proxy) "
                        f"took {time.time()-start:.2f}s [{_model}, "
                        f"{len(_prompt)//4} prompt tokens approx]")
            return result
    except Exception as e:
        logger.warning(f"Groq proxy formatting failed: {e}")

    # Step 2b: legacy fallback — any local Groq keys still configured
    groq_keys = config.get("groq_api_keys", [])
    for key in groq_keys:
        logger.info("Formatting with Groq LLaMA (local key)...")
        start  = time.time()
        result = cleanup_with_groq(text, key, context=context)
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
            result = cleanup_with_gemini(text, current_key, context=context)
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


# ── Notes v3: named styles (research: AudioPen "Writing Styles"/"Rewriting
# Intensity", Cleft's Structured / Structured Prose / Clean Transcript,
# Superwhisper modes — the single most-praised feature family in voice-first
# note apps). A style is chosen explicitly per (re)format call and NEVER runs
# automatically, so Hard Rule #12's cost control is untouched.
NOTES_STYLE_PROSE_RULES = """
STYLE OVERRIDE — FLOWING PROSE:
The user asked for this note as prose. Output 1–4 well-formed paragraphs in the
speaker's voice. NO bullets, NO checklists, NO headings, NO tables — connected
sentences only. All other rules (completeness, no invention, keep the speaker's
language) still apply."""

# "Clean transcript" is a different CONTRACT (keep every word), so it replaces
# the note-maker prompt instead of extending it.
NOTES_STYLE_TRANSCRIPT_PROMPT = """You are a TRANSCRIPT CLEANER, not a writer.
Return the text with ONLY these changes:
- Fix capitalization and add correct punctuation and paragraph breaks.
- Remove pure filler (um/uh, stutters, immediately-doubled words).
- Resolve explicit self-corrections to the final value.
Keep EVERY other word, in the speaker's order, voice and language. Do NOT
summarize, restructure, retitle sections, add markdown scaffolding, or reword.
Return plain text only (paragraph breaks allowed)."""

NOTE_STYLES = ("structured", "prose", "transcript")


def build_notes_system_prompt(structure_detection: bool = True,
                              autotitle: bool = True,
                              style: str = "structured") -> str:
    """Assemble the notes-formatter system prompt, appending the structure-detection
    rules and/or the auto-title instruction only when their feature flags are on.
    `style` (Notes v3) picks the output shape: "structured" (default, unchanged),
    "prose" (paragraphs, no scaffolding), "transcript" (clean-up only, keep every
    word). Unknown styles fall back to structured."""
    if style == "transcript":
        prompt = NOTES_STYLE_TRANSCRIPT_PROMPT
    elif style == "prose":
        prompt = NOTES_FORMATTER_SYSTEM_PROMPT + "\n\n" + NOTES_STYLE_PROSE_RULES
    else:
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
                autotitle: bool = True, timeout: float = 8.0,
                style: str = "structured") -> dict | None:
    """Format a note with the LLM in ONE call, returning
    ``{"title": str, "formatted_content": str}``.

    - Runs the notes formatter (markdown structuring), plus structure-detection
      (checklists) and auto-title generation gated by the passed flags.
    - `style` (Notes v3): "structured" | "prose" | "transcript" — explicit
      restyles only; every automatic call keeps the default.
    - Hard timeout (default 8s, Decision 9). On timeout / any failure / no keys,
      returns ``None`` so the caller falls back to saving the raw transcript only
      and surfacing a "Retry formatting" affordance. Never raises.
    """
    if not text or not text.strip():
        return None

    system_prompt = build_notes_system_prompt(structure_detection, autotitle,
                                              style=style)
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
        content = chat_via_proxy(messages, config, model="openai/gpt-oss-120b",
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
                model="openai/gpt-oss-120b",
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
