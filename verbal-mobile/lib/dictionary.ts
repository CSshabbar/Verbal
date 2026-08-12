/**
 * Custom dictionary (mobile) — vocabulary biasing + replacement rules + snippets.
 * Mirrors whisperflow/app/dictionary.py. Stored in AsyncStorage + synced to the
 * Supabase `dictionary` table (one row per user).
 *
 * Snippets generalize replacement rules: a spoken `trigger` phrase expands into a
 * longer saved `expansion` block (LinkedIn URL, signature, disclaimer, …). They are
 * applied AFTER AI cleanup, immediately BEFORE injection/append, and are fully
 * fail-closed so they can never break the dictation pipeline.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { supabase } from './supabase';
import { getCloudUserId } from './storage';
import { getSyncEnabled } from './syncStore';

const KEY = 'flume_dictionary';

const TRIGGER_MAX = 40;    // matches the design mockups / desktop cap
const EXPANSION_MAX = 500; // matches the design mockups / desktop cap

export type Replacement = { from: string; to: string };
export type Snippet = {
  id: string;
  trigger: string;
  expansion: string;
  label: string;
  used: number;
  createdAt: string;
  updatedAt: string;
};
export type Dictionary = {
  vocabulary: string[];
  replacements: Replacement[];
  // Optional in the public type so existing consumers that build a bare
  // { vocabulary, replacements } literal keep type-checking; normalize() always
  // populates it, so any Dictionary returned by this module has snippets set.
  snippets?: Snippet[];
};

function genId(): string {
  return 'snip_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function normalizeSnippet(s: any): Snippet | null {
  const trigger = String(s?.trigger ?? '').trim().slice(0, TRIGGER_MAX);
  const expansion = String(s?.expansion ?? '').slice(0, EXPANSION_MAX);
  if (!trigger || !expansion.trim()) return null;
  const now = new Date().toISOString();
  const usedNum = Number(s?.used);
  return {
    id: String(s?.id ?? '').trim() || genId(),
    trigger,
    expansion,
    label: String(s?.label ?? '').trim(),
    used: Number.isFinite(usedNum) && usedNum > 0 ? Math.floor(usedNum) : 0,
    createdAt: String(s?.createdAt ?? '').trim() || now,
    updatedAt: String(s?.updatedAt ?? '').trim() || now,
  };
}

function normalize(d: any): Dictionary {
  const vocabulary = Array.isArray(d?.vocabulary)
    ? d.vocabulary.map((w: any) => String(w).trim()).filter(Boolean)
    : [];
  const replacements = Array.isArray(d?.replacements)
    ? d.replacements
        .filter((r: any) => r && String(r.from ?? '').trim() && String(r.to ?? '').trim())
        .map((r: any) => ({ from: String(r.from).trim(), to: String(r.to).trim() }))
    : [];
  const snippets = Array.isArray(d?.snippets)
    ? (d.snippets.map(normalizeSnippet).filter(Boolean) as Snippet[])
    : [];
  return { vocabulary, replacements, snippets };
}

export async function getDictionary(): Promise<Dictionary> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    return normalize(raw ? JSON.parse(raw) : {});
  } catch {
    return { vocabulary: [], replacements: [], snippets: [] };
  }
}

export type SaveResult = { dict: Dictionary; error?: string };

/**
 * Persist the dictionary locally, push it to the cloud, then refresh the
 * keyboard snapshot — IN THAT ORDER, and awaited (IDI-174).
 *
 * The order is the whole point. This used to fire `pushRemote()` and
 * `syncKeyboardConfig()` both un-awaited, and syncKeyboardConfig() internally
 * calls fetchRemote(), which overwrites the local cache with whatever is in the
 * cloud. The two raced, so roughly every other edit was silently reverted by
 * the app's own keyboard sync reading the PRE-push row. Awaiting the push first
 * means that fetch can only ever see the state we just wrote.
 *
 * Returns instead of throwing so the many fire-and-forget callers (snippet
 * usage counters, auto-learned replacements) can't be broken by a sync failure;
 * `saveDictionaryChecked` is the variant the editing screens use to surface it.
 */
export async function saveDictionaryChecked(d: Dictionary): Promise<SaveResult> {
  // "Always carry snippets": a caller that hands us an object with no snippets
  // key (the screens' initial `{vocabulary: [], replacements: []}` state) must
  // not be able to erase the stored ones — normalize() would turn the missing
  // key into [].
  const current = Array.isArray(d?.snippets) ? null : await getDictionary();
  const norm = normalize(current ? { ...d, snippets: current.snippets } : d);
  await AsyncStorage.setItem(KEY, JSON.stringify(norm));

  let error: string | undefined;
  try {
    await pushRemote(norm);
  } catch (e: any) {
    error = e?.message || 'Sync failed';
  }
  // Refresh the native keyboard's config snapshot (dynamic import avoids a
  // circular dependency: keyboardBridge imports getDictionary from here).
  // AFTER the push, so its internal fetchRemote() sees the pushed state — and
  // NOT AT ALL when the push failed, because that same fetchRemote() would
  // overwrite the local cache with the cloud row and throw the user's unsynced
  // edit away. Keeping it local is what makes "will retry" true: the next save
  // carries it up.
  if (!error) {
    try {
      await import('./keyboardBridge').then((m) => m.syncKeyboardConfig());
    } catch { /* best effort — the keyboard snapshot is peripheral */ }
  }

  // pushRemote may have MERGED with a concurrent remote edit and rewritten the
  // cache; return what's actually stored.
  return { dict: await getDictionary(), error };
}

/** Non-throwing convenience wrapper — the shape every existing caller expects. */
export async function saveDictionary(d: Dictionary): Promise<Dictionary> {
  return (await saveDictionaryChecked(d)).dict;
}

export async function addReplacement(from: string, to: string): Promise<Dictionary> {
  from = (from || '').trim(); to = (to || '').trim();
  const d = await getDictionary();
  if (!from || !to || from.toLowerCase() === to.toLowerCase()) return d;
  d.replacements = d.replacements.filter(r => r.from.toLowerCase() !== from.toLowerCase());
  d.replacements.push({ from, to });
  return saveDictionary(d);
}

/* ── cloud sync: compare-and-set on `updated_at` ─────────────────────────────
 *
 * One row per user holds vocabulary + replacements + snippets together, and
 * every writer sent the WHOLE row with a blind upsert. Two devices editing
 * different parts (phone adds a snippet, desktop adds a vocabulary word) meant
 * last-write-wins over the entire dictionary — the earlier edit vanished.
 *
 * So writes are conditional: `.eq('updated_at', <the value we last read>)`.
 * If it matches nobody else has written since our fetch, and the update
 * applies. If it matches nothing (0 rows returned), someone did — we refetch,
 * MERGE the two versions field by field, and retry ONCE. A second failure is
 * reported to the caller rather than swallowed.
 */

/** `updated_at` of the row as of our last successful read/write — the CAS
 *  witness. null = we have never seen a row (⇒ upsert instead of update). */
let lastUpdatedAt: string | null = null;

/** Set once the first fetch attempt has SETTLED (success, empty, or failure).
 *  Until then a push has no CAS witness and, worse, the editing screens may
 *  still be holding their empty initial state — pushing it would wipe the
 *  cloud row. See ensureFetched(). */
let firstFetchSettled = false;
let inFlightFetch: Promise<Dictionary> | null = null;

/** Reset on account change (clearAccountData wipes the local row too). */
export function resetSyncState(): void {
  lastUpdatedAt = null;
  firstFetchSettled = false;
  inFlightFetch = null;
}

type RemoteRow = { dict: Dictionary; updatedAt: string | null; found: boolean };

async function readRow(userId: string): Promise<RemoteRow | null> {
  const { data, error } = await supabase
    .from('dictionary').select('vocabulary,replacements,snippets,updated_at')
    .eq('user_id', userId).maybeSingle();
  if (error) return null;                                   // network/RLS — unknown state
  if (!data) return { dict: normalize({}), updatedAt: null, found: false };
  return { dict: normalize(data), updatedAt: (data as any).updated_at ?? null, found: true };
}

/**
 * Pull the cloud dictionary into the local cache. Gated on the Sync toggle and
 * on having a REAL account id (a locally-minted `user_<ts>` id would read and
 * write junk rows nobody can ever see — IDI-174). Always returns something
 * usable: the local cache when offline, signed out, or sync is off.
 */
export async function fetchRemote(): Promise<Dictionary> {
  if (inFlightFetch) return inFlightFetch;
  inFlightFetch = (async () => {
    try {
      if (!(await getSyncEnabled())) return await getDictionary();
      const userId = await getCloudUserId();
      if (!userId) return await getDictionary();
      const row = await readRow(userId);
      if (!row) return await getDictionary();               // fetch failed — keep local
      lastUpdatedAt = row.updatedAt;
      if (row.found) {
        await AsyncStorage.setItem(KEY, JSON.stringify(row.dict));
        return row.dict;
      }
      return await getDictionary();
    } catch {
      return await getDictionary();                         // offline / not signed in
    } finally {
      // Settled either way: a push must not queue forever just because the
      // device is offline.
      firstFetchSettled = true;
      inFlightFetch = null;
    }
  })();
  return inFlightFetch;
}

/** A push before the first fetch has no CAS witness, so make sure one has
 *  happened. Cheap: at most one network round-trip per app run. */
async function ensureFetched(): Promise<void> {
  if (firstFetchSettled) return;
  await fetchRemote();
}

/** Write the row conditionally. Returns false on a CAS miss (someone else wrote
 *  first) AND on a transport error — the caller's retry path handles both. */
async function casWrite(userId: string, d: Dictionary, witness: string | null): Promise<boolean> {
  const stamp = new Date().toISOString();
  // ALL THREE columns on every write. Sending a subset is what let a screen
  // that had only loaded vocabulary blank the snippets.
  const row = {
    user_id: userId,
    vocabulary: d.vocabulary,
    replacements: d.replacements,
    snippets: d.snippets ?? [],
    updated_at: stamp,
  };
  try {
    if (witness == null) {
      // No row known to exist yet → create it (or adopt an existing one).
      const { error } = await supabase.from('dictionary').upsert(row, { onConflict: 'user_id' });
      if (error) return false;
    } else {
      const { data, error } = await supabase
        .from('dictionary').update(row)
        .eq('user_id', userId).eq('updated_at', witness)
        .select('updated_at');
      // `.select()` is what makes the miss detectable: a conditional UPDATE that
      // matched nothing is not an error, it just returns zero rows.
      if (error || !data || data.length === 0) return false;
    }
  } catch {
    return false;
  }
  lastUpdatedAt = stamp;
  return true;
}

/**
 * Push the dictionary to the cloud with compare-and-set + one merge-and-retry.
 * THROWS when both attempts fail, so the caller can tell the user.
 */
export async function pushRemote(d: Dictionary): Promise<void> {
  await ensureFetched();
  if (!(await getSyncEnabled())) return;                    // toggle OFF ⇒ local-only
  const userId = await getCloudUserId();
  if (!userId) return;                                      // signed out ⇒ local-only

  if (await casWrite(userId, d, lastUpdatedAt)) return;

  // Conflict (or a failed write): refetch, merge, retry ONCE.
  const row = await readRow(userId);
  if (!row) throw new Error("Couldn't sync — will retry");
  lastUpdatedAt = row.updatedAt;
  const merged = row.found ? mergeDictionaries(row.dict, d) : d;
  if (row.found) await AsyncStorage.setItem(KEY, JSON.stringify(merged));
  if (await casWrite(userId, merged, row.updatedAt)) return;
  throw new Error("Couldn't sync — will retry");
}

/**
 * Merge two versions of the dictionary — PURE, and exported so it can be tested
 * without a network. `local` is the NEWER side (the edit being written);
 * `remote` is what another device put there in the meantime.
 *
 *   vocabulary   — union, case-insensitive (remote's spelling of a duplicate wins,
 *                  since it is already what the cloud shows)
 *   snippets     — union by trigger (case-insensitive); on a collision the newer
 *                  `updatedAt` wins, which is real data we have
 *   replacements — keyed by `from` (case-insensitive), newer wins. There is no
 *                  per-rule timestamp, so "newer" = the local edit in flight.
 *
 * Union semantics mean a deletion made on one device while the other was
 * editing can come back. That's deliberate: resurrecting a word is recoverable,
 * losing a device's whole edit is not.
 */
export function mergeDictionaries(remote: Dictionary, local: Dictionary): Dictionary {
  const r = normalize(remote);
  const l = normalize(local);

  const vocabulary: string[] = [];
  const seenWord = new Set<string>();
  for (const w of [...r.vocabulary, ...l.vocabulary]) {
    const k = w.toLowerCase();
    if (seenWord.has(k)) continue;
    seenWord.add(k);
    vocabulary.push(w);
  }

  const reps = new Map<string, Replacement>();
  for (const rep of r.replacements) reps.set(rep.from.toLowerCase(), rep);
  for (const rep of l.replacements) reps.set(rep.from.toLowerCase(), rep);   // local wins

  const snips = new Map<string, Snippet>();
  for (const s of [...(r.snippets ?? []), ...(l.snippets ?? [])]) {
    const k = s.trigger.toLowerCase();
    const prev = snips.get(k);
    if (!prev || Date.parse(s.updatedAt) >= Date.parse(prev.updatedAt)) snips.set(k, s);
  }

  return {
    vocabulary,
    replacements: [...reps.values()],
    snippets: [...snips.values()],
  };
}

/** Whisper conditions on the LAST ~224 tokens of the prompt, so the tail of the
 *  vocabulary (= what the user taught it most recently) is what actually biases
 *  the model. An over-long glossary is not merely ignored — every extra term is
 *  another word that can be dropped into an unrelated sentence, and another line
 *  that can be parroted back (see stripPromptEcho). Mirrors
 *  whisperflow/app/dictionary.py::build_prompt. */
const MAX_PROMPT_TERMS = 80;
const MAX_PROMPT_CHARS = 600;

export function buildPrompt(d: Dictionary): string | undefined {
  if (!d.vocabulary.length) return undefined;
  const words = d.vocabulary.slice(-MAX_PROMPT_TERMS);
  // Trim from the FRONT, never the back: clipping the assembled string would
  // throw away exactly the newest terms this ordering is meant to protect.
  while (words.length && `Glossary: ${words.join(', ')}.`.length > MAX_PROMPT_CHARS) {
    words.shift();
  }
  if (!words.length) return undefined;
  return `Glossary: ${words.join(', ')}.`;
}

// ── bias-prompt echo ("Glossary, M.T.:" showing up in a transcript) ───────────
// Whisper's `prompt` is a CONTINUATION prompt, not an instruction: the model is
// conditioned on it as though it were the transcript so far. Handed short, quiet
// or speech-free audio, the likeliest continuation of "Glossary: a, b, c." is
// MORE glossary — so the bias list comes back as the "transcription" and gets
// inserted into whatever field the user was dictating into. Mirrors
// whisperflow/app/dictionary.py::strip_prompt_echo — edit one, edit the other.

const BIAS_LABELS = ['glossary', 'vocabulary', 'files'];
const ANY_LABEL_RE = new RegExp(`\\b(${BIAS_LABELS.join('|')})\\b\\s*:`, 'gi');
// Chunk on commas/semicolons/newlines and on SENTENCE periods (a period followed
// by whitespace) so "M.T." and "main.py" survive as single chunks.
const CHUNK_RE = /(\s*[,;]\s*|\s*\.\s+|\s*\n+\s*)/;

/** Casefold and reduce every non-alphanumeric run to one space: 'M.T.:' and
 *  'm t' both become 'm t', so an echo matches the term we sent. */
function normTerm(s: string): string {
  return (s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

/** The section labels this prompt ACTUALLY carries ('Glossary:', 'Files:').
 *  Only these count as labels when scanning a transcript — which is what keeps a
 *  dictated "Files, I need to check them" intact on a run where no file list was
 *  ever sent. We can only be echoed text we spoke first. */
export function promptLabels(prompt: string | undefined): string[] {
  if (!prompt) return [];
  const found = new Set<string>();
  for (const m of prompt.matchAll(ANY_LABEL_RE)) found.add(m[1].toLowerCase());
  return [...found].sort();
}

/** Matcher for a leading label; group 1 marks the ':' that makes it OURS. */
function labelRe(labels: string[]): RegExp | null {
  return labels.length ? new RegExp(`^\\s*(?:${labels.join('|')})\\b\\s*(:)?\\s*`, 'i') : null;
}

/** The individual biasing terms of a bias prompt, normalized for comparison. */
export function promptTerms(prompt: string | undefined): Set<string> {
  const out = new Set<string>();
  if (!prompt) return out;
  const re = labelRe(promptLabels(prompt));
  for (const raw of prompt.split(CHUNK_RE)) {
    const t = normTerm(re ? (raw || '').replace(re, '') : raw || '');
    if (t) out.add(t);
  }
  return out;
}

/**
 * Remove regurgitated bias-prompt text from a transcription.
 *
 * Only words we actually SENT as labels count as labels (see promptLabels).
 * Deletes every run of chunks that is the glossary talking back to us: a run
 * introduced by a bias LABEL ('Glossary:', 'Files:') that is either followed by
 * terms we sent or STANDS ALONE as its own fragment (the model often drops the
 * list and echoes just the heading — 'Glossary. So, the thing is…'), and any
 * bare comma-list of TWO OR MORE consecutive chunks that are each exactly a term
 * we sent. A lone dictionary term is never dropped — that is just the user
 * saying a word they taught us — and a label that runs on inside its own clause
 * ('Files, I need to check them') is speech, not a heading.
 * Returns '' when the transcript was nothing but echo; never throws.
 */
export function stripPromptEcho(text: string, prompt: string | undefined): string {
  try {
    if (!text || !text.trim() || !prompt) return text;
    const terms = promptTerms(prompt);
    if (!terms.size) return text;
    const re = labelRe(promptLabels(prompt));

    const parts = text.split(CHUNK_RE);
    const chunks = parts.filter((_, i) => i % 2 === 0);
    const seps = parts.filter((_, i) => i % 2 === 1).concat(['']);
    const n = chunks.length;

    const info = chunks.map((c, k) => {
      const m = re ? re.exec(c) : null;
      const norm = normTerm(m ? c.slice(m[0].length) : c);
      // A heading standing on its own — 'Glossary:' or a 'Glossary.' ending the
      // fragment — is ours. One that runs on inside its clause is the user.
      const endsFragment = k === n - 1 || seps[k].includes('.') || seps[k].includes('\n');
      const alone = !!m && !norm && (!!m[1] || endsFragment);
      // A label punctuated like a label ('Glossary:') is ours, never speech —
      // peel the prefix off even if the chunk survives. Without the colon it may
      // well be a word the user said, so only the run rules below can remove it.
      if (m && m[1]) chunks[k] = c.slice(m[0].length);
      return { label: !!m, term: terms.has(norm), empty: !norm, alone };
    });

    const drop = new Array<boolean>(n).fill(false);
    let i = 0;
    while (i < n) {
      const it = info[i];
      const nxt = i + 1 < n ? info[i + 1] : null;
      const start =
        it.alone ||
        (it.label && it.term) ||
        (it.label && it.empty && !!nxt && nxt.term) ||
        (it.term && !!nxt && nxt.term);
      if (!start) {
        i += 1;
        continue;
      }
      let j = i;
      while (j < n && (info[j].term || info[j].empty)) {
        drop[j] = true;
        j += 1;
      }
      i = Math.max(j, i + 1);
    }

    // Rebuild unconditionally: even with no run to delete, a 'Glossary:' prefix
    // may have been peeled off an otherwise real sentence above.
    let out = chunks.map((c, k) => (drop[k] ? '' : c + seps[k])).join('');
    out = out.replace(/\s{2,}/g, ' ').trim();
    out = out.replace(/^[\s,;:.–—-]+/, '').trim();
    return normTerm(out) ? out : '';
  } catch {
    return text; // fail-closed: an echo scrub must never cost a dictation
  }
}

/**
 * Distinct user-specific terms for GROUNDING THE CLEANUP LLM (MER-44 Phase 0).
 * Mirrors whisperflow/app/dictionary.py::known_terms — vocabulary plus the
 * corrected ("to") side of every replacement rule (so auto-learned/manual fixes
 * ground the cleanup pass), deduped case-insensitively, capped. Distinct from
 * buildPrompt() (which feeds Whisper's transcription bias, vocabulary only).
 */
export function knownTerms(d: Dictionary, limit = 60): string[] {
  const terms: string[] = [];
  const seen = new Set<string>();
  for (const w of [...d.vocabulary, ...d.replacements.map((r) => r.to)]) {
    const t = (w || '').trim();
    const k = t.toLowerCase();
    if (t && !seen.has(k)) {
      seen.add(k);
      terms.push(t);
    }
  }
  return terms.slice(0, limit);
}

function escapeRe(s: string) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

export function applyReplacements(text: string, d: Dictionary): string {
  if (!text) return text;
  let out = text;
  for (const r of d.replacements) {
    try {
      out = out.replace(new RegExp('\\b' + escapeRe(r.from) + '\\b', 'gi'), r.to);
    } catch {
      out = out.split(r.from).join(r.to);
    }
  }
  return out;
}

// ── snippets ────────────────────────────────────────────────────────────────
export type SnippetPatch = Partial<Pick<Snippet, 'trigger' | 'expansion' | 'label' | 'used'>>;

export async function getSnippets(): Promise<Snippet[]> {
  return (await getDictionary()).snippets ?? [];
}

/** Append one snippet (dedupe by trigger, case-insensitive). Mirrors addReplacement. */
export async function addSnippet(trigger: string, expansion: string, label = ''): Promise<Dictionary> {
  trigger = (trigger || '').trim().slice(0, TRIGGER_MAX);
  expansion = (expansion ?? '').toString().slice(0, EXPANSION_MAX);
  const d = await getDictionary();
  if (!trigger || !expansion.trim()) return d;
  const now = new Date().toISOString();
  const snippets = (d.snippets ?? []).filter(
    s => s.trigger.toLowerCase() !== trigger.toLowerCase());
  snippets.push({
    id: genId(), trigger, expansion, label: (label || '').trim(),
    used: 0, createdAt: now, updatedAt: now,
  });
  d.snippets = snippets;
  return saveDictionary(d);
}

export async function updateSnippet(id: string, patch: SnippetPatch): Promise<Dictionary> {
  const d = await getDictionary();
  const now = new Date().toISOString();
  d.snippets = (d.snippets ?? []).map(s => {
    if (s.id !== id) return s;
    const trigger = patch.trigger !== undefined
      ? String(patch.trigger).trim().slice(0, TRIGGER_MAX) || s.trigger
      : s.trigger;
    const expansion = patch.expansion !== undefined
      ? String(patch.expansion).slice(0, EXPANSION_MAX)
      : s.expansion;
    const label = patch.label !== undefined ? String(patch.label).trim() : s.label;
    const usedNum = patch.used !== undefined ? Number(patch.used) : s.used;
    const used = Number.isFinite(usedNum) && usedNum > 0 ? Math.floor(usedNum) : 0;
    return { ...s, trigger, expansion, label, used, updatedAt: now };
  });
  return saveDictionary(d);
}

export async function removeSnippet(id: string): Promise<Dictionary> {
  const d = await getDictionary();
  d.snippets = (d.snippets ?? []).filter(s => s.id !== id);
  return saveDictionary(d);
}

/** Best-effort, fire-and-forget: bump `used` counters (by id) in stored snippets. */
function bumpUsed(counts: Record<string, number>): void {
  const ids = Object.keys(counts);
  if (!ids.length) return;
  (async () => {
    try {
      const d = await getDictionary();
      let changed = false;
      d.snippets = (d.snippets ?? []).map(s => {
        const n = counts[s.id];
        if (n && n > 0) { changed = true; return { ...s, used: (s.used || 0) + n }; }
        return s;
      });
      if (changed) await saveDictionary(d);
    } catch { /* best effort — never let usage-tracking break dictation */ }
  })();
}

/**
 * Expand snippet triggers found in `text`. ALGO (identical to desktop):
 *   - case-INSENSITIVE whole-phrase match on word boundaries (multi-word aware)
 *   - LONGEST trigger first (so "my email address" wins over "my email")
 *   - SINGLE pass only — an inserted expansion is never re-scanned (no cascade)
 *   - increments each matched snippet's `used` counter and persists (guarded)
 *   - fully fail-closed: any error returns `text` unchanged, never throws
 * Run AFTER AI cleanup, immediately BEFORE injection/append.
 */
export function applySnippets(text: string, snippets: Snippet[]): string {
  if (!text || !Array.isArray(snippets) || !snippets.length) return text;
  try {
    // Longest trigger first so alternation prefers the longer overlapping match.
    const valid = snippets
      .filter(s => s && String(s.trigger || '').trim() && String(s.expansion ?? '').length)
      .slice()
      .sort((a, b) => b.trigger.trim().length - a.trigger.trim().length);
    if (!valid.length) return text;

    const byTrigger = new Map<string, Snippet>();
    const parts: string[] = [];
    for (const s of valid) {
      const t = s.trigger.trim();
      const key = t.toLowerCase();
      if (byTrigger.has(key)) continue; // first (longest / earliest) wins
      byTrigger.set(key, s);
      parts.push('\\b' + escapeRe(t) + '\\b');
    }
    if (!parts.length) return text;

    // One global regex; String.replace is a single left-to-right pass and never
    // re-examines inserted text, giving the required no-recursion behavior.
    const re = new RegExp('(' + parts.join('|') + ')', 'gi');
    const counts: Record<string, number> = {};
    const out = text.replace(re, (m) => {
      const s = byTrigger.get(m.toLowerCase());
      if (!s) return m;
      counts[s.id] = (counts[s.id] || 0) + 1;
      s.used = (s.used || 0) + 1; // reflect on the passed object too
      return s.expansion;
    });
    bumpUsed(counts);
    return out;
  } catch {
    return text; // fail closed — never break the dictation pipeline
  }
}
