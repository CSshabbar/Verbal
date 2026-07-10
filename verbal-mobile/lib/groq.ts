import { getDictionary, buildPrompt, applyReplacements } from './dictionary';

const GROQ_API = 'https://api.groq.com/openai/v1';

export const NOTES_FORMATTER_PROMPT = `You are a NOTE FORMATTER, not an AI assistant.
You receive raw notes (often voice-transcribed) and output well-structured markdown.

DETECT the note's context and format accordingly:
- Brainstorming: Group related ideas under ## headings, use bullet points.
- Todo/Tasks: Format as - [ ] checklist items with clear action verbs.
- Meeting notes: Add ## Key Points, ## Action Items, ## Notes sections.
- Product ideas: Organize as ## Problem, ## Solution, ## Features.
- Code/Technical: Format with \`\`\` code blocks, separate ## Concepts.
- Journal/Personal: Gentle paragraph formatting, preserve voice.
- Study notes: ## Topics with sub-bullets, bold key terms.

RULES:
1. NEVER add, invent, or respond to the content. Only reformat.
2. Fix transcription artifacts (um, uh, repeated words).
3. Add markdown headers (##, ###) to organize sections.
4. Use **bold** for emphasis and key terms naturally.
5. Use bullet points (- ) for lists. Numbered lists (1. ) for steps.
6. Clean up punctuation and capitalization.
7. Keep the original meaning — DO NOT summarize or truncate.
8. Return ONLY the formatted markdown.`;

// Structure-detection rules (Notes v2). Extends the NOTE FORMATTER system prompt
// — this is the LLM prompt, NOT the Whisper bias prompt (the 896-char cap in
// 05-conventions Hard Rule #6 is Whisper-only). Mirrors the desktop
// NOTES_FORMATTER_SYSTEM_PROMPT extension so both platforms detect lists alike.
export const NOTES_STRUCTURE_RULES = `

STRUCTURE DETECTION (voice-dictated lists):
- When the speaker enumerates things to do / buy / get / remember, or lists items
  in sequence ("first… then… also…", "number one… number two…", "and then"),
  output them as a markdown task list — one "- [ ] item" per item — NOT as a
  prose paragraph.
- Use "- [ ] " for open items. Only use "- [x] " when the speaker explicitly says
  an item is already done or completed.
- Keep genuine narration/journaling as normal prose; do not force everything into
  a checklist.
- Preserve each item's wording, just tighten it into a short phrase.`;

// Appended when the structure-detection feature flag is OFF: still format, but
// never convert prose into interactive checklists.
export const NOTES_NO_STRUCTURE_RULES = `

Do NOT convert prose into task-list checkboxes ("- [ ]"); use plain bullets ("- ")
for any lists instead.`;

export interface NoteFormatResult {
  /** false = LLM timed out / errored and we fell back to raw text. */
  ok: boolean;
  /** Suggested title, or null when none was requested/produced. */
  title: string | null;
  /** Formatted markdown, or the raw input text on fallback. */
  content: string;
}

/** Pull the first {...} JSON object out of an LLM response (tolerates ``` fences). */
function extractJsonObject(s: string): any | null {
  if (!s) return null;
  const start = s.indexOf('{');
  const end = s.lastIndexOf('}');
  if (start < 0 || end <= start) return null;
  try { return JSON.parse(s.slice(start, end + 1)); } catch { return null; }
}

/**
 * Format a note AND (optionally) produce a title in a single LLM call, with a
 * hard timeout. On timeout/error the note is saved raw (`ok:false`) so the UI
 * can offer "Retry formatting". Mirrors the desktop format_note_with_ai
 * ({title, formatted_content}) contract.
 *
 * @param opts.timeoutMs      hard cap (default 8000 — Design Decision 9)
 * @param opts.detectStructure gate for Feature 3 (default true)
 * @param opts.withTitle      request a title too (default true)
 */
export async function formatNoteWithTitle(
  text: string,
  apiKey: string,
  opts: { timeoutMs?: number; detectStructure?: boolean; withTitle?: boolean } = {},
): Promise<NoteFormatResult> {
  const { timeoutMs = 8000, detectStructure = true, withTitle = true } = opts;
  const raw = (text ?? '').trim();
  if (!raw || !apiKey) return { ok: false, title: null, content: text };

  const system = NOTES_FORMATTER_PROMPT + (detectStructure ? NOTES_STRUCTURE_RULES : NOTES_NO_STRUCTURE_RULES);
  const user = withTitle
    ? `NOTES TO FORMAT:\n\`\`\`\n${raw}\n\`\`\`\n\nRespond with ONLY a JSON object of the form {"title": "<a concise title, 6 words max>", "content": "<the formatted markdown>"}. Do not wrap it in code fences.`
    : `NOTES TO FORMAT:\n\`\`\`\n${raw}\n\`\`\`\n\nOutput the formatted markdown only.`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${GROQ_API}/chat/completions`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'llama-3.3-70b-versatile',
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: user },
        ],
        temperature: 0,
        max_tokens: 4096,
      }),
      signal: controller.signal,
    });
    if (!res.ok) return { ok: false, title: null, content: text };
    const data = await res.json();
    const out = (data.choices?.[0]?.message?.content ?? '').trim();
    if (!out) return { ok: false, title: null, content: text };

    if (withTitle) {
      const obj = extractJsonObject(out);
      if (obj && typeof obj.content === 'string' && obj.content.trim()) {
        const title = typeof obj.title === 'string' && obj.title.trim() ? obj.title.trim() : null;
        return { ok: true, title, content: obj.content.trim() };
      }
      // Model ignored the JSON instruction — treat the whole reply as content.
      return { ok: true, title: null, content: out };
    }
    return { ok: true, title: null, content: out };
  } catch {
    // Aborted (timeout) or network error → fail closed to raw text.
    return { ok: false, title: null, content: text };
  } finally {
    clearTimeout(timer);
  }
}

export async function transcribeAudio(
  audioUri: string,
  apiKey: string
): Promise<string> {
  const formData = new FormData();
  formData.append('file', {
    uri: audioUri,
    type: 'audio/m4a',
    name: 'recording.m4a',
  } as any);
  formData.append('model', 'whisper-large-v3-turbo');
  formData.append('language', 'en');
  formData.append('temperature', '0');

  // Custom dictionary: bias Whisper toward the user's vocabulary.
  const dict = await getDictionary();
  const prompt = buildPrompt(dict);
  if (prompt) formData.append('prompt', prompt);

  const res = await fetch(`${GROQ_API}/audio/transcriptions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
    },
    body: formData,
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Groq transcription failed: ${err}`);
  }

  const data = await res.json();
  // Apply the user's replacement rules to fix persistent mishearings.
  return applyReplacements((data.text?.trim() ?? ''), dict);
}

export async function formatText(
  text: string,
  apiKey: string
): Promise<string> {
  const SYSTEM = `You are a TEXT FORMATTER, not an AI assistant.
You receive raw voice transcription and output a formatted version.
NEVER add, invent, or respond to the content.
NEVER add headings unless the speaker said them word-for-word.
Only reformat: fix punctuation, capitalization, remove fillers (um, uh),
format lists when speaker says "number one/two", add paragraph breaks on topic changes.
Return ONLY the formatted text.`;

  const res = await fetch(`${GROQ_API}/chat/completions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: 'llama-3.3-70b-versatile',
      messages: [
        { role: 'system', content: SYSTEM },
        {
          role: 'user',
          content: `TRANSCRIPTION TO FORMAT:\n\`\`\`\n${text}\n\`\`\`\n\nOutput the formatted version only.`,
        },
      ],
      temperature: 0,
      max_tokens: 2048,
    }),
  });

  if (!res.ok) return text; // fallback to raw
  const data = await res.json();
  return data.choices?.[0]?.message?.content?.trim() ?? text;
}

export async function formatNotes(
  text: string,
  apiKey: string
): Promise<string> {
  const res = await fetch(`${GROQ_API}/chat/completions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: 'llama-3.3-70b-versatile',
      messages: [
        { role: 'system', content: NOTES_FORMATTER_PROMPT },
        { role: 'user', content: `NOTES TO FORMAT:\n\`\`\`\n${text}\n\`\`\`\n\nOutput the formatted markdown only.` },
      ],
      temperature: 0,
      max_tokens: 4096,
    }),
  });
  if (!res.ok) return text;
  const data = await res.json();
  return data.choices?.[0]?.message?.content?.trim() ?? text;
}
