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
    2. File tag conversion (always)
    3. LLM formatting — tries in order:
         a. Groq LLaMA (free, uses existing Groq keys)
         b. Gemini (if Gemini keys configured)
       Falls back to local-only if no keys or all APIs fail.
    """
    from app.config import get_active_gemini_key, rotate_gemini_key

    # Step 1: local cleanup
    text = clean_raw_transcript(text)
    if not text:
        return text

    # Step 2: file tags
    text = apply_file_tags(text)

    # Step 3a: Groq LLaMA formatting (uses same keys as transcription — already set up)
    groq_keys = config.get("groq_api_keys", [])
    for key in groq_keys:
        logger.info("Formatting with Groq LLaMA...")
        start  = time.time()
        result = cleanup_with_groq(text, key)
        elapsed = time.time() - start
        if result is not None:
            logger.info(f"Groq LLaMA formatting took {elapsed:.2f}s")
            return result
        logger.warning("Groq LLaMA formatting failed, trying next key")

    # Step 3b: Gemini fallback
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
