import {
  getEffectiveDictionary,
  buildPrompt,
  applyReplacements,
  knownTerms,
  stripPromptEcho,
} from './dictionary';
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

const SPOKEN_LANGUAGE_KEY = 'flume_spoken_language';

/** Spoken language for transcription — ISO-639-1 or 'auto'. Defaults to 'en'
 *  (the historical behavior). Written ONLY by setSpokenLanguage() below. */
export async function getSpokenLanguage(): Promise<string> {
  try {
    return (await AsyncStorage.getItem(SPOKEN_LANGUAGE_KEY)) || 'en';
  } catch {
    return 'en';
  }
}

// ── Pipeline + transcription model (mirrors desktop config) ──────────────────
// Desktop stores three booleans (speed_mode / chained_mode / hybrid_mode) and derives
// the pipeline from them. Mobile stores the derived id directly because it has no
// dictation path reading the flags — but the ids, order and meaning are identical, so
// the two platforms describe the same thing.
//
// `hybrid` is deliberately ABSENT here: it streams audio while you speak, and mobile
// records to a file and uploads afterwards. Offering it would be a switch that does
// nothing.
const PIPELINE_KEY = 'flume_pipeline';
const ASR_MODEL_KEY = 'flume_asr_model';

export type PipelineId = 'one' | 'two' | 'old';
export const PIPELINES: { id: PipelineId; label: string; desc: string; wait: string }[] = [
  { id: 'one', label: 'One round trip',  desc: 'Best all-round. Same words, sooner.', wait: '1.3s' },
  { id: 'two', label: 'Two round trips', desc: 'The older, slower route.',            wait: '1.9s' },
  { id: 'old', label: 'Original',        desc: 'How Flume used to sound.',            wait: '' },
];

/** Same table desktop keeps in transcriber.ASR_CHOICES. `bias` = accepts a Whisper
 *  glossary; only Whisper does, so on the others the dictionary is applied AFTER
 *  transcription instead of biasing it. */
export const ASR_MODELS: {
  id: string; name: string; vendor: string; desc: string; wait: string;
  provider?: 'eleven' | 'assembly'; altModel?: string; bias: boolean;
}[] = [
  { id: 'auto', name: 'Automatic', vendor: 'Groq', bias: true,
    desc: 'Fast and good at everything.', wait: '1.0s' },
  { id: 'whisper-large-v3-turbo', name: 'Whisper turbo', vendor: 'Groq', bias: true,
    desc: 'Always the fast one, any language.', wait: '1.0s' },
  { id: 'whisper-large-v3', name: 'Whisper large', vendor: 'Groq', bias: true,
    desc: 'Better for languages other than English.', wait: '1.1s' },
  { id: 'eleven-scribe-v1', name: 'Scribe', vendor: 'ElevenLabs', bias: false,
    provider: 'eleven', altModel: 'scribe_v1',
    desc: 'Most accurate on your voice.', wait: '1.8s' },
  { id: 'aai-universal-2', name: 'Universal-2', vendor: 'AssemblyAI', bias: false,
    provider: 'assembly', altModel: 'universal-2',
    desc: 'Best with Urdu mixed into English.', wait: '5s' },
  { id: 'aai-universal-3-5-pro', name: 'Universal-3.5', vendor: 'AssemblyAI', bias: false,
    provider: 'assembly', altModel: 'universal-3-5-pro',
    desc: 'Strong English. Struggles with Urdu.', wait: '5s' },
];

export async function getPipeline(): Promise<PipelineId> {
  try {
    const v = await AsyncStorage.getItem(PIPELINE_KEY);
    return (PIPELINES.some(p => p.id === v) ? v : 'one') as PipelineId;
  } catch {
    return 'one';
  }
}
export async function setPipeline(id: PipelineId): Promise<void> {
  try { await AsyncStorage.setItem(PIPELINE_KEY, id); } catch { /* local pref only */ }
}
export async function getAsrModel(): Promise<string> {
  try {
    const v = await AsyncStorage.getItem(ASR_MODEL_KEY);
    return ASR_MODELS.some(m => m.id === v) ? (v as string) : 'auto';
  } catch {
    return 'auto';
  }
}
export async function setAsrModel(id: string): Promise<void> {
  try { await AsyncStorage.setItem(ASR_MODEL_KEY, id); } catch { /* local pref only */ }
}

/** The picker's options (IDI-180). 'auto' = let Whisper detect — transcribeAudio
 *  omits the `language` param, and both natives omit it too (keyboardBridge ships
 *  the value as `spokenLanguage`). Mirrors desktop's `spoken_language` config. */
export const SPOKEN_LANGUAGES: { code: string; label: string }[] = [
  { code: 'auto', label: 'Auto-detect' },
  { code: 'en', label: 'English' },
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
  { code: 'de', label: 'German' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'hi', label: 'Hindi' },
  { code: 'ur', label: 'Urdu' },
  { code: 'ar', label: 'Arabic' },
  { code: 'zh', label: 'Chinese' },
];

/**
 * Persist the spoken language and push it to the native keyboards.
 *
 * The keyboard snapshot carries `spokenLanguage`, so the picker would only
 * affect in-app dictation until the snapshot is rewritten — hence the
 * fire-and-forget resync. The import is DYNAMIC on purpose: keyboardBridge
 * imports getSpokenLanguage from this module, so a static import here would
 * close a cycle. Fail-closed — a failed resync never breaks the setting.
 */
export async function setSpokenLanguage(code: string): Promise<void> {
  const lang = (code || 'en').trim() || 'en';
  await AsyncStorage.setItem(SPOKEN_LANGUAGE_KEY, lang);
  import('./keyboardBridge').then((m) => m.syncKeyboardConfig()).catch(() => { /* best effort */ });
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

// Notes v3 named styles — mirrors desktop ai_cleanup.NOTES_STYLE_PROSE_RULES /
// NOTES_STYLE_TRANSCRIPT_PROMPT (edit one, edit both). A style only ever
// arrives from an explicit user pick, so Hard Rule #12's cost control holds.
export const NOTES_STYLE_PROSE_RULES = `

STYLE OVERRIDE — FLOWING PROSE:
The user asked for this note as prose. Output 1–4 well-formed paragraphs in the
speaker's voice. NO bullets, NO checklists, NO headings, NO tables — connected
sentences only. All other rules (completeness, no invention, keep the speaker's
language) still apply.`;

export const NOTES_STYLE_TRANSCRIPT_PROMPT = `You are a TRANSCRIPT CLEANER, not a writer.
Return the text with ONLY these changes:
- Fix capitalization and add correct punctuation and paragraph breaks.
- Remove pure filler (um/uh, stutters, immediately-doubled words).
- Resolve explicit self-corrections to the final value.
Keep EVERY other word, in the speaker's order, voice and language. Do NOT
summarize, restructure, retitle sections, add markdown scaffolding, or reword.
Return plain text only (paragraph breaks allowed).`;

export type NoteStyle = 'structured' | 'prose' | 'transcript';

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
  _apiKey?: string,
  opts: { timeoutMs?: number; detectStructure?: boolean; withTitle?: boolean; style?: NoteStyle } = {},
): Promise<NoteFormatResult> {
  const { timeoutMs = 8000, detectStructure = true, withTitle = true, style = 'structured' } = opts;
  const raw = (text ?? '').trim();
  if (!raw) return { ok: false, title: null, content: text };

  // Style selection mirrors desktop build_notes_system_prompt: "transcript" is
  // a different contract (keep every word) so it REPLACES the note-maker prompt;
  // "prose" extends it and suppresses checklists.
  const system = style === 'transcript'
    ? NOTES_STYLE_TRANSCRIPT_PROMPT
    : style === 'prose'
      ? NOTES_FORMATTER_PROMPT + NOTES_STYLE_PROSE_RULES
      : NOTES_FORMATTER_PROMPT + (detectStructure ? NOTES_STRUCTURE_RULES : NOTES_NO_STRUCTURE_RULES);
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
        model: 'openai/gpt-oss-120b',
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

/**
 * askNotes — Ask-your-notes (Notes v3, mirrors desktop DashboardApi.ask_notes).
 * The caller ranks + trims the context notes (token overlap, top ~6); this
 * makes ONE proxy chat call and fails closed to ok:false. Explicit user action
 * only — never fired automatically.
 */
export async function askNotes(
  question: string,
  contextNotes: Array<{ title: string; content: string; updatedAt?: string }>,
  opts: { timeoutMs?: number } = {},
): Promise<{ ok: boolean; answer: string }> {
  const q = (question || '').trim();
  if (!q || contextNotes.length === 0) return { ok: false, answer: '' };
  const ctx = contextNotes
    .map((n) => `NOTE: ${n.title || 'Untitled'}${n.updatedAt ? ` (${n.updatedAt.slice(0, 10)})` : ''}\n${(n.content || '').slice(0, 2000)}`)
    .join('\n\n---\n\n');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? 30_000);
  try {
    const res = await fetch(PROXY_URL, {
      method: 'POST',
      headers: await proxyHeaders(true),
      body: JSON.stringify({
        model: 'openai/gpt-oss-120b',
        messages: [
          {
            role: 'system',
            content: 'You answer questions from the user\'s personal notes. '
              + 'Use ONLY the notes provided below. Be concise and direct — a short '
              + 'paragraph or a few bullets. If the notes don\'t contain the answer, '
              + 'say so plainly. Never invent facts. Answer in the language of the question.',
          },
          { role: 'user', content: `NOTES:\n\n${ctx}\n\nQUESTION: ${q}` },
        ],
        temperature: 0,
        max_tokens: 768,
      }),
      signal: controller.signal,
    });
    if (!res.ok) return { ok: false, answer: '' };
    const data = await res.json();
    const out = (data.choices?.[0]?.message?.content ?? '').trim();
    return out ? { ok: true, answer: out } : { ok: false, answer: '' };
  } catch {
    return { ok: false, answer: '' };
  } finally {
    clearTimeout(timer);
  }
}

export async function transcribeAudio(
  audioUri: string,
  _apiKey?: string,
): Promise<string> {
  const formData = new FormData();
  formData.append('file', {
    uri: audioUri,
    type: 'audio/m4a',
    name: 'recording.m4a',
  } as any);
  // Transcription model (Settings → Models). Mirrors desktop transcriber.asr_choice:
  // 'auto' keeps the historical turbo default; a non-Groq pick sends asr_provider so
  // the proxy routes it and normalizes the reply back to Groq's `{text}` shape.
  const chosenId = await getAsrModel();
  const choice = ASR_MODELS.find(m => m.id === chosenId) ?? ASR_MODELS[0];
  const alt = !!choice.provider;
  formData.append('model', (!alt && choice.id !== 'auto')
    ? choice.id : 'whisper-large-v3-turbo');
  if (alt) {
    formData.append('asr_provider', choice.provider as string);
    if (choice.altModel) formData.append('asr_alt_model', choice.altModel);
  }
  // Spoken language: 'auto' → omit (Whisper detects); else pin the ISO code.
  // Mirrors desktop config['spoken_language']; stored via flume_spoken_language.
  const lang = await getSpokenLanguage();
  if (lang && lang !== 'auto') formData.append('language', lang);
  formData.append('temperature', '0');

  // Custom dictionary: bias Whisper toward the user's vocabulary. Only Whisper takes
  // a glossary, so non-Groq providers are sent none — and the echo scrub below is
  // skipped for them too, since it would be hunting an echo that cannot exist.
  // Personal ∪ team (IDI-216 Phase 4). Pure cache read on the team side, so this
  // stays a local lookup — the dictation path makes no extra network call.
  const dict = await getEffectiveDictionary();
  const prompt = choice.bias ? buildPrompt(dict) : '';
  if (prompt) formData.append('prompt', prompt);

  // multipart → proxy routes to /audio/transcriptions. Do NOT set Content-Type
  // (fetch adds the multipart boundary itself).
  const headers = await proxyHeaders(false);
  const post = (body: FormData) => fetch(PROXY_URL, { method: 'POST', headers, body });
  let res = await post(formData);

  // FAIL CLOSED: an alternate provider that is unconfigured, down or out of credit
  // must never cost a dictation, so retry once on Groq. The provider is a
  // preference, not a dependency — same rule the desktop path follows.
  if (!res.ok && alt) {
    const retry = new FormData();
    retry.append('file', { uri: audioUri, type: 'audio/m4a', name: 'recording.m4a' } as any);
    retry.append('model', 'whisper-large-v3-turbo');
    if (lang && lang !== 'auto') retry.append('language', lang);
    retry.append('temperature', '0');
    const groqPrompt = buildPrompt(dict);
    if (groqPrompt) retry.append('prompt', groqPrompt);
    res = await post(retry);
    if (res.ok) {
      const d = await res.json();
      const s = stripPromptEcho(d.text?.trim() ?? '', groqPrompt);
      return s ? applyReplacements(s, dict) : '';
    }
  }

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Transcription failed: ${err}`);
  }

  const data = await res.json();
  // Drop any bias-prompt echo FIRST. Whisper continues the glossary we sent when
  // it hears no real speech, so "Glossary, M.T.:" arrives as the transcript and
  // would be inserted verbatim into the user's field. '' here means the clip was
  // nothing but echo — i.e. silence, which callers already handle.
  const scrubbed = stripPromptEcho(data.text?.trim() ?? '', prompt);
  if (!scrubbed) return '';
  // Apply the user's replacement rules to fix persistent mishearings.
  return applyReplacements(scrubbed, dict);
}

/** Ollama Cloud fallback model, served through the SAME groq-proxy with
 *  `provider: 'ollama'` — a separate quota with a server-held key, so it survives
 *  Groq's shared daily-token cap. Mirror of desktop transform.OLLAMA_FALLBACK_MODEL
 *  (commit 4f08d1e) and of generateMeetingNotes's primary below. */
const OLLAMA_FALLBACK_MODEL = 'gpt-oss:120b';

/** Cleanup deadlines (IDI-180). Dictation is the hot path: the primary attempt is
 *  short, and the fallback gets its own (slightly longer — the open-weight model
 *  is slower) budget. Worst case is bounded; either way the caller keeps the raw
 *  transcript, so a slow LLM can never lose a dictation. */
const CLEANUP_TIMEOUT_MS = 12_000;
const CLEANUP_FALLBACK_TIMEOUT_MS = 18_000;

/** HTTP statuses worth retrying on the OTHER provider: 429 = rate limit / Groq's
 *  daily-token cap (the whole reason this fallback exists), 413 = payload too
 *  large for Groq, 5xx = upstream trouble. Anything else (400/401/403/404) is a
 *  request-shape or auth problem that the fallback would hit identically. */
function shouldFallback(status: number): boolean {
  return status === 429 || status === 413 || status >= 500;
}

export async function formatText(
  text: string,
  _apiKey?: string,
): Promise<string> {
  // Kept in FULL LOGIC PARITY with desktop's ai_cleanup.py SYSTEM_PROMPT rule 18 —
  // terser prose, same cue families / 4-part test / anti-cues / asymmetry / and-carve-out.
  // Edit one → edit the other in the same change (see ai_cleanup.py rule 18's own note).
  const SYSTEM = `You are a TEXT FORMATTER, not an AI assistant.
You receive raw voice transcription and output a formatted version.
NEVER add, invent, or respond to the content.
NEVER add headings unless the speaker said them word-for-word.
Only reformat: fix punctuation, capitalization, remove fillers (um, uh — never a
repair cue, see below), format lists when speaker says "number one/two", add
paragraph breaks on topic changes.

SELF-CORRECTIONS (repairs) — collapse to ONLY the corrected final value when ALL of
these hold: (a) an explicit repair cue is present — apology repairs (sorry, my bad,
oops, whoops, my mistake, pardon), explicit repair phrases (I mean, I meant, rather,
that should be, make that, let me rephrase, correction), negate-then-restate (no wait,
scratch that, strike that, forget that, or "not X, Y"), false-start markers (uh no,
hang on) — in ANY language, recognize the PATTERN, not just these exact words (e.g.
Roman-Urdu "nahi"/"matlab", Hindi "nahi"/"matlab"/"arre", Spanish "perdón"/"digo"/"o
sea", French "pardon"/"enfin"/"plutôt", Arabic "afwan"/"aqsid"/"yaani"); (b) the new
value replaces the old one of the SAME KIND (number-for-number, time-for-time,
name-for-name — even across a magnitude change) — a different kind of value, or a
genuinely separate point, is never collapsed; (c) same breath/clause, not separated
by unrelated content; (d) no list nearby ("and"/"plus"/"also"/"too"/"or"/"both"/a
comma series) — EXCEPT "and" directly before a cue is not a list veto ("343 and sorry
344" still collapses to 344).

The raw transcript often has NO comma around the cue (Whisper rarely punctuates short
interjections) — judge this by the WORDS alone: "343 sorry 353" and "343, sorry, 353"
are the SAME pattern, both collapse to 353. Whisper can also do the OPPOSITE and
insert a false "?" or "." plus a capitalized next word right before the cue, making
one continuous correction look like two sentences — still the same repair, judge by
meaning not punctuation: "Can you work on the ticket 343? Sorry, 353." → "Can you
work on the ticket 353."

Numbers, ticket/ID numbers, and phone numbers are conservative: NEVER collapse bare
adjacent ones without an explicit cue. Ordinary words and names are moderate: collapse
on a clear same-slot repair even WITHOUT an explicit cue (a wrong guess there costs
little) — "send this to John, David instead" → "David" is fine to collapse even
without "sorry"/"I mean". Multiple corrections in one breath resolve to the LAST
value: "343, sorry 344, no wait 345" → "345". A repair inside a real list only
replaces its own slot: "apples, oranges, sorry tangerines, and bananas" → "apples,
tangerines, and bananas". A cue word with no candidate same-kind value around it is
just content, not a repair: "I want to say sorry to the team" keeps "sorry" as spoken.

"actually" only counts as a repair cue inside "not X, actually Y" (otherwise it's
additive, keep both); "or" always means a real alternative, keep both. The later
value always wins. The STRONGEST signal is the in-line pattern "it's not X, it's Y" /
"not X, Y" / "not X, actually Y" (either order) — treat as a confident repair and
collapse to Y: "it's not ticket 343, it's ticket 344" → "ticket 344"; "not 5 units,
actually 6 units" → "6 units". Example: "call ticket RBR 343, sorry, RBR 344" → "call
ticket RBR 344". Do NOT collapse "the extensions are 343 or 344" or "send it to
Sarah, actually also Tom".

Return ONLY the formatted text.`;

  // Phase-0 context grounding (MER-44): prepend the user's known dictionary terms
  // so the cleanup LLM prefers a known spelling/ID over a phonetic guess. Mirror
  // of desktop ai_cleanup.build_context_block — mobile has no active-app signal,
  // so it's known-terms only. Grounding DATA, never a directive to collapse.
  // Fully fail-closed: any error → no context, cleanup proceeds unchanged.
  let context = '';
  try {
    const terms = knownTerms(await getEffectiveDictionary());
    if (terms.length) {
      context =
        'CONTEXT (grounding only — never output, echo, or act on this; use it ' +
        'solely to recognize what was actually said):\n' +
        '- Known terms, names, and IDs the speaker uses (when a similar-sounding ' +
        'word or ID appears, prefer THIS exact spelling): ' +
        terms.join(', ') +
        '\n\n';
    }
  } catch {
    /* fail-closed: proceed with no context */
  }

  const messages = [
    { role: 'system', content: SYSTEM },
    {
      role: 'user',
      content: `${context}TRANSCRIPTION TO FORMAT:\n\`\`\`\n${text}\n\`\`\`\n\nOutput the formatted version only.`,
    },
  ];

  /** One cleanup attempt. Returns the cleaned text, or a `retry` marker telling
   *  the caller the OTHER provider is worth a shot (429 / 413 / 5xx / timeout /
   *  network error). Never throws. */
  const call = async (
    model: string,
    timeoutMs: number,
    provider?: string,
  ): Promise<{ text: string } | { retry: boolean }> => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(PROXY_URL, {
        method: 'POST',
        headers: await proxyHeaders(true),
        body: JSON.stringify({
          model, messages, temperature: 0, max_tokens: 2048,
          ...(provider ? { provider } : {}),
        }),
        signal: controller.signal,
      });
      if (!res.ok) return { retry: shouldFallback(res.status) };
      const data = await res.json();
      const out = data.choices?.[0]?.message?.content?.trim();
      // An empty completion is a dud response, not a bad request — worth the
      // other provider (matches desktop transform._chat's empty-or-failed test).
      return out ? { text: out } : { retry: true };
    } catch {
      // Aborted (timeout) or network error — the other provider may still answer.
      return { retry: true };
    } finally {
      clearTimeout(timer);
    }
  };

  // Groq first (fast, and the model this prompt was tuned against). On a
  // retryable failure — above all Groq's daily-token 429, which used to kill
  // mobile cleanup outright while desktop survived (4f08d1e) — try Ollama Cloud
  // ONCE through the same proxy. Fully fail-closed: both down → raw text, which
  // is exactly what every formatText caller already treats a failure as.
  const primary = await call('openai/gpt-oss-120b', CLEANUP_TIMEOUT_MS);
  if ('text' in primary) return primary.text;
  if (!primary.retry) return text;

  const fallback = await call(OLLAMA_FALLBACK_MODEL, CLEANUP_FALLBACK_TIMEOUT_MS, 'ollama');
  return 'text' in fallback ? fallback.text : text;
}

// Notes model on Ollama Cloud (OpenAI-compatible). Mirror of desktop meetings.NOTES_MODEL.
const NOTES_MODEL = 'gpt-oss:120b';

const MEETING_NOTES_SYSTEM = `You are a world-class MEETING ANALYST. You turn a raw, messy call
transcript (plus the user's own quick notes and marked moments) into the notes the
participant WISHED they had taken: complete, beautifully organized, instantly
scannable. Match the depth and polish of a top human analyst's write-up.

THE CONTRACT
- Lose nothing that matters: every decision, commitment, number, amount, date, name,
  option, reason and open question in the transcript appears in the notes.
- Reorganize by MEANING, not the order things were said. Group related points; lead
  with the most consequential.
- Attach reasons to their point ("chose X because Y"). Resolve self-corrections to the
  FINAL value ("Aug 4th, no wait the 5th" → the 5th). Keep stated uncertainty uncertain
  ("~", "roughly", "needs confirming") — never harden a maybe into a fact.
- The user's own notes + marked moments flag what mattered to THEM — fold each in where
  it belongs.
- If part of the audio is garbled or one-sided, reconstruct the missing side ONLY where
  context makes it unambiguous, and say briefly that you did. Never invent facts.
- Write EVERYTHING in the OUTPUT LANGUAGE stated in the user message. Never translate.

STRUCTURE (GitHub markdown). Use the sections that FIT this meeting — a rich advisory
call earns all of them; a 30-second sync earns two lines. In this order:

1. ## TL;DR — 3–6 tight bullets: the answer, the key numbers, the decision, the next
   move. Skip entirely for a trivial note.
2. ## <Topic> sections — one per real topic, logically ordered. One idea per bullet;
   nest sub-bullets for supporting detail; **bold** the load-bearing facts (names, dates,
   amounts, the operative word of a decision).
3. TABLES — this is mandatory, not optional. The MOMENT the meeting covers three or more
   items that share the same fields, render a real Markdown table, never a bullet list.
   Costs/prices, option comparisons, pros/cons, schedules, criteria rankings, before/after,
   anything with amounts or a shared shape becomes a table. Example — a cost discussion
   MUST come out like this, not as bullets:

   | Item | Cost | Notes |
   |---|---|---|
   | Tuition (non-EU) | €10,000–25,000/yr | Public unis €14k–18k |
   | Living funds to show | ~€13,500/yr | Your own money, not a fee |

   Compute derived values the speakers implied (totals, the unit conversions they used) —
   but NEVER invent numbers that weren't given or derivable.
4. ## Decisions — each agreement with its why.
5. ## Action items — "- [ ] task — **owner**, due **date**" (owner = a speaker NAME,
   never an id; omit owner/due when unstated). If the meeting laid out a multi-step plan,
   present it as a PHASED ROADMAP: "### Phase 1 — <name>" then its checkbox items.
6. ## Open questions — unresolved items, disagreements, things to confirm.

QUALITY BAR
- Rich when the meeting is rich, terse when it's thin — never padded, never a wall of text.
- Every heading must carry real content; drop empty ones.
- Sentence-case, clean punctuation, complete phrasing — you are a writer, not a transcript.
- NEVER invent facts, names, numbers or tasks. No preamble, no "Here are the notes", no
  closing remarks. Output the notes only.`;

const LANG_NAMES: Record<string, string> = {
  en: 'English', ur: 'Urdu', hi: 'Hindi', ar: 'Arabic', es: 'Spanish', fr: 'French',
  de: 'German', pt: 'Portuguese', tr: 'Turkish', id: 'Indonesian', ru: 'Russian',
  zh: 'Chinese', ja: 'Japanese',
};

/** Hard cap for one notes generation, shared across the Ollama→Groq fallback
 *  (IDI-175 §5). Without it a hung proxy left the "Writing the notes…" spinner
 *  up forever, with no way back except killing the app. */
const MEETING_NOTES_TIMEOUT_MS = 30_000;

/** Generate full AI meeting notes on-device (same prompt as desktop).
 *  Returns null on timeout/failure so the caller can show an error state. */
export async function generateMeetingNotes(meeting: {
  transcript: { speaker: string; t0: number; text: string }[];
  speakers: Record<string, string>;
  scratchpad: string;
  markedMoments: { t: number; label: string; note?: string }[];
}): Promise<string | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), MEETING_NOTES_TIMEOUT_MS);
  try {
    if (!meeting.transcript.length) return null;
    const langCode = await getSpokenLanguage();
    // 'auto' became reachable when the picker landed (IDI-180) — mapping it to
    // English would force English notes on a non-English meeting, so it defers
    // to the transcript instead. A named language still pins the output.
    const outLang = LANG_NAMES[langCode]
      || (langCode === 'auto' ? "the SAME language the transcript is in" : 'English');
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
    const messages = [
      { role: 'system', content: MEETING_NOTES_SYSTEM },
      { role: 'user', content:
        `OUTPUT LANGUAGE: ${outLang}. Everything must be written in ${outLang}.\n\n` +
        `SPEAKERS: ${spk}\n\nUSER'S OWN NOTES:\n${notes}\n\nMARKED MOMENTS:\n${marks}\n\n` +
        `TRANSCRIPT:\n${tx}` },
    ];
    // One notes call. Try Ollama Cloud (gpt-oss:120b — strong at structured markdown +
    // tables); fall back to Groq llama-3.3 so notes never fail to generate.
    // BOTH attempts share the one 30 s deadline above — the fallback gets
    // whatever budget the first attempt didn't spend, and the total is bounded.
    const call = async (model: string, provider?: string): Promise<string | null> => {
      const res = await fetch(PROXY_URL, {
        method: 'POST',
        headers: await proxyHeaders(true),
        body: JSON.stringify({
          model, messages, temperature: 0, max_tokens: 4000,
          ...(provider ? { provider } : {}),
        }),
        signal: controller.signal,
      });
      if (!res.ok) return null;
      const data = await res.json();
      let text = (data.choices?.[0]?.message?.content ?? '').trim();
      if (text.startsWith('```')) text = text.replace(/^```(markdown)?/i, '').replace(/```$/, '').trim();
      return text || null;
    };
    return (await call(NOTES_MODEL, 'ollama')) || (await call('openai/gpt-oss-120b'));
  } catch {
    // Aborted (30 s timeout) or network error — the caller shows the failure.
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export async function formatNotes(
  text: string,
  _apiKey?: string,
): Promise<string> {
  const res = await fetch(PROXY_URL, {
    method: 'POST',
    headers: await proxyHeaders(true),
    body: JSON.stringify({
      model: 'openai/gpt-oss-120b',
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
