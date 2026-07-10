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
import { getUserId } from './storage';

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

export async function saveDictionary(d: Dictionary): Promise<Dictionary> {
  const norm = normalize(d);
  await AsyncStorage.setItem(KEY, JSON.stringify(norm));
  pushRemote(norm).catch(() => {});
  // Refresh the native keyboard's config snapshot (dynamic import avoids a
  // circular dependency: keyboardBridge imports getDictionary from here).
  import('./keyboardBridge').then((m) => m.syncKeyboardConfig()).catch(() => {});
  return norm;
}

export async function addReplacement(from: string, to: string): Promise<Dictionary> {
  from = (from || '').trim(); to = (to || '').trim();
  const d = await getDictionary();
  if (!from || !to || from.toLowerCase() === to.toLowerCase()) return d;
  d.replacements = d.replacements.filter(r => r.from.toLowerCase() !== from.toLowerCase());
  d.replacements.push({ from, to });
  return saveDictionary(d);
}

export async function fetchRemote(): Promise<Dictionary> {
  try {
    const userId = await getUserId();
    const { data } = await supabase
      .from('dictionary').select('vocabulary,replacements,snippets')
      .eq('user_id', userId).maybeSingle();
    if (data) {
      const norm = normalize(data);
      await AsyncStorage.setItem(KEY, JSON.stringify(norm));
      return norm;
    }
  } catch { /* offline / not signed in */ }
  return getDictionary();
}

async function pushRemote(d: Dictionary) {
  try {
    const userId = await getUserId();
    await supabase.from('dictionary').upsert(
      { user_id: userId, vocabulary: d.vocabulary, replacements: d.replacements,
        snippets: d.snippets ?? [], updated_at: new Date().toISOString() },
      { onConflict: 'user_id' });
  } catch { /* best effort */ }
}

export function buildPrompt(d: Dictionary): string | undefined {
  if (!d.vocabulary.length) return undefined;
  return 'Glossary: ' + d.vocabulary.slice(0, 200).join(', ') + '.';
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
