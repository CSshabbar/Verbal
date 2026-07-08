/**
 * Custom dictionary (mobile) — vocabulary biasing + replacement rules.
 * Mirrors whisperflow/app/dictionary.py. Stored in AsyncStorage + synced to the
 * Supabase `dictionary` table (one row per user).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { supabase } from './supabase';
import { getUserId } from './storage';

const KEY = 'flume_dictionary';

export type Replacement = { from: string; to: string };
export type Dictionary = { vocabulary: string[]; replacements: Replacement[] };

function normalize(d: any): Dictionary {
  const vocabulary = Array.isArray(d?.vocabulary)
    ? d.vocabulary.map((w: any) => String(w).trim()).filter(Boolean)
    : [];
  const replacements = Array.isArray(d?.replacements)
    ? d.replacements
        .filter((r: any) => r && String(r.from ?? '').trim() && String(r.to ?? '').trim())
        .map((r: any) => ({ from: String(r.from).trim(), to: String(r.to).trim() }))
    : [];
  return { vocabulary, replacements };
}

export async function getDictionary(): Promise<Dictionary> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    return normalize(raw ? JSON.parse(raw) : {});
  } catch {
    return { vocabulary: [], replacements: [] };
  }
}

export async function saveDictionary(d: Dictionary): Promise<Dictionary> {
  const norm = normalize(d);
  await AsyncStorage.setItem(KEY, JSON.stringify(norm));
  pushRemote(norm).catch(() => {});
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
      .from('dictionary').select('vocabulary,replacements')
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
        updated_at: new Date().toISOString() },
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
