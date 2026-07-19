import { getDictionary, buildPrompt, applyReplacements } from './dictionary';
import { supabase, SUPABASE_URL, SUPABASE_ANON_KEY } from './supabase';
import { getDeviceId } from './storage';

// All Groq access now goes through the Supabase `groq-proxy` Edge Function — the
// Groq key lives ONLY on the server. We authenticate with the signed-in user's
// session token when available (so the proxy can meter/limit per user), otherwise
// the anon key; a device id rides along as the fallback identity. The old `apiKey`
// parameters are kept for call-site compatibility but are IGNORED (no client key).
const PROXY_URL = `${SUPABASE_URL}/functions/v1/groq-proxy`;

async function proxyHeaders(json: boolean): Promise<Record<string, string>> {
  let token = SUPABASE_ANON_KEY;
  try {
    const { data } = await supabase.auth.getSession();
    if (data.session?.access_token) token = data.session.access_token;
  } catch { /* fall back to anon */ }
  let device = '';
  try { device = await getDeviceId(); } catch { /* optional */ }
  const h: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    apikey: SUPABASE_ANON_KEY,
  };
  if (device) h['x-flume-device'] = device;
  if (json) h['Content-Type'] = 'application/json';
  return h;
}

import AsyncStorage from '@react-native-async-storage/async-storage';

/** Spoken language for transcription — ISO-639-1 or 'auto'. Defaults to 'en'
 *  (the historical behavior). Set via the key below when mobile grows a picker. */
export async function getSpokenLanguage(): Promise<string> {
  try {
    return (await AsyncStorage.getItem('flume_spoken_language')) || 'en';
  } catch {
    return 'en';
  }
}

export const NOTES_FORMATTER_PROMPT = `You are a world-class NOTE-MAKER, not an AI assistant.
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
- Technical → numbered steps; \`backticks\` for commands/files/identifiers.
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
   ## headings, **bold**).`;

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
 * ({title, formatted_content}) contract. Routes through the groq-proxy.
 *
 * @param _apiKey             ignored (the proxy holds the key) — kept for compat
 * @param opts.timeoutMs      hard cap (default 8000 — Design Decision 9)
 * @param opts.detectStructure gate for Feature 3 (default true)
 * @param opts.withTitle      request a title too (default true)
 */
export async function formatNoteWithTitle(
  text: string,
  _apiKey: string,
  opts: { timeoutMs?: number; detectStructure?: boolean; withTitle?: boolean } = {},
): Promise<NoteFormatResult> {
  const { timeoutMs = 8000, detectStructure = true, withTitle = true } = opts;
  const raw = (text ?? '').trim();
  if (!raw) return { ok: false, title: null, content: text };

  const system = NOTES_FORMATTER_PROMPT + (detectStructure ? NOTES_STRUCTURE_RULES : NOTES_NO_STRUCTURE_RULES);
  const user = withTitle
    ? `NOTES TO FORMAT:\n\`\`\`\n${raw}\n\`\`\`\n\nRespond with ONLY a JSON object of the form {"title": "<a concise title, 6 words max>", "content": "<the formatted markdown>"}. Do not wrap it in code fences.`
    : `NOTES TO FORMAT:\n\`\`\`\n${raw}\n\`\`\`\n\nOutput the formatted markdown only.`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(PROXY_URL, {
      method: 'POST',
      headers: await proxyHeaders(true),
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
  _apiKey: string,
): Promise<string> {
  const formData = new FormData();
  formData.append('file', {
    uri: audioUri,
    type: 'audio/m4a',
    name: 'recording.m4a',
  } as any);
  formData.append('model', 'whisper-large-v3-turbo');
  // Spoken language: 'auto' → omit (Whisper detects); else pin the ISO code.
  // Mirrors desktop config['spoken_language']; stored via flume_spoken_language.
  const lang = await getSpokenLanguage();
  if (lang && lang !== 'auto') formData.append('language', lang);
  formData.append('temperature', '0');

  // Custom dictionary: bias Whisper toward the user's vocabulary.
  const dict = await getDictionary();
  const prompt = buildPrompt(dict);
  if (prompt) formData.append('prompt', prompt);

  // multipart → proxy routes to /audio/transcriptions. Do NOT set Content-Type
  // (fetch adds the multipart boundary itself).
  const res = await fetch(PROXY_URL, {
    method: 'POST',
    headers: await proxyHeaders(false),
    body: formData,
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Transcription failed: ${err}`);
  }

  const data = await res.json();
  // Apply the user's replacement rules to fix persistent mishearings.
  return applyReplacements((data.text?.trim() ?? ''), dict);
}

export async function formatText(
  text: string,
  _apiKey: string,
): Promise<string> {
  const SYSTEM = `You are a TEXT FORMATTER, not an AI assistant.
You receive raw voice transcription and output a formatted version.
NEVER add, invent, or respond to the content.
NEVER add headings unless the speaker said them word-for-word.
Only reformat: fix punctuation, capitalization, remove fillers (um, uh),
format lists when speaker says "number one/two", add paragraph breaks on topic changes.
Return ONLY the formatted text.`;

  const res = await fetch(PROXY_URL, {
    method: 'POST',
    headers: await proxyHeaders(true),
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

const MEETING_NOTES_SYSTEM = `You are a world-class MEETING NOTE-TAKER. From a raw meeting
transcript (plus the user's own quick notes and marked moments) you write the
DEFINITIVE notes for the meeting — the document a diligent chief of staff would
produce: complete, organized, effortless to scan.

THE CONTRACT:
- A reader who MISSED the meeting must lose nothing that matters: every decision,
  commitment, number, date, amount, name, reason and open question appears.
- Organize by TOPIC in the order that makes sense — not strictly the order spoken.
- Reasons stay attached to their point ("decided X because Y") on the same bullet.
- Resolve self-corrections to the final version; keep stated uncertainty uncertain.
- The user's own notes mark what mattered to THEM — weave each one in where it
  belongs. Marked moments deserve their point in the notes.
- Write EVERYTHING in the OUTPUT LANGUAGE stated in the user message.

SHAPE (GitHub markdown; include only sections with real content):
- Start with a 1–2 sentence context line (what this meeting was, who, purpose) —
  plain text, no heading.
- ## <Topic> — one short section per discussion topic; one point per bullet;
  **bold** the key facts (dates, amounts, names, the operative word of a decision).
- ## Decisions — every agreement, each with its why.
- ## Action items — "- [ ] task — **owner**, due **date**" (only real commitments;
  use the speaker NAMES given, never ids; omit owner/due when not said).
- ## Open questions — unresolved items, disagreements left standing.

NEVER invent content. No meta commentary, no "Here are the notes". Notes only.`;

const LANG_NAMES: Record<string, string> = {
  en: 'English', ur: 'Urdu', hi: 'Hindi', ar: 'Arabic', es: 'Spanish', fr: 'French',
  de: 'German', pt: 'Portuguese', tr: 'Turkish', id: 'Indonesian', ru: 'Russian',
  zh: 'Chinese', ja: 'Japanese',
};

/** Generate full AI meeting notes on-device (same prompt as desktop). */
export async function generateMeetingNotes(meeting: {
  transcript: { speaker: string; t0: number; text: string }[];
  speakers: Record<string, string>;
  scratchpad: string;
  markedMoments: { t: number; label: string; note?: string }[];
}): Promise<string | null> {
  try {
    if (!meeting.transcript.length) return null;
    const langCode = await getSpokenLanguage();
    const outLang = LANG_NAMES[langCode] || 'English';
    const lines = meeting.transcript.map((u) => {
      const name = meeting.speakers[u.speaker] || u.speaker;
      const t = Math.floor(u.t0 || 0);
      return `[${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}] ${name}: ${u.text}`;
    });
    let tx = lines.join('\n');
    if (tx.length > 24000) tx = tx.slice(0, 12000) + '\n[… middle elided …]\n' + tx.slice(-12000);
    const notes = (meeting.scratchpad || '').split('\n').filter((l) => l.trim()).join('\n') || '(none)';
    const marks = meeting.markedMoments.map((m) => {
      const t = Math.floor(m.t || 0);
      return `- at ${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')} ${m.label || '(unlabeled)'}` +
        (m.note ? ` — user note: ${m.note}` : '');
    }).join('\n') || '(none)';
    const spk = Object.entries(meeting.speakers).map(([k, v]) => `${k} = ${v}`).join(', ') || '(unknown)';
    const res = await fetch(PROXY_URL, {
      method: 'POST',
      headers: await proxyHeaders(true),
      body: JSON.stringify({
        model: 'llama-3.3-70b-versatile',
        messages: [
          { role: 'system', content: MEETING_NOTES_SYSTEM },
          { role: 'user', content:
            `OUTPUT LANGUAGE: ${outLang}. Everything must be written in ${outLang}.\n\n` +
            `SPEAKERS: ${spk}\n\nUSER'S OWN NOTES:\n${notes}\n\nMARKED MOMENTS:\n${marks}\n\n` +
            `TRANSCRIPT:\n${tx}` },
        ],
        temperature: 0,
        max_tokens: 2500,
      }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    let text = (data.choices?.[0]?.message?.content ?? '').trim();
    if (text.startsWith('```')) text = text.replace(/^```(markdown)?/i, '').replace(/```$/, '').trim();
    return text || null;
  } catch {
    return null;
  }
}

export async function formatNotes(
  text: string,
  _apiKey: string,
): Promise<string> {
  const res = await fetch(PROXY_URL, {
    method: 'POST',
    headers: await proxyHeaders(true),
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
