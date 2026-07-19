/**
 * remoteConfig — app-wide settings hosted centrally in the Supabase `app_config`
 * table (read-only to clients). Currently just the shared Groq API key, so users
 * never have to paste one. The fetched value is cached in AsyncStorage so
 * getGroqKey() stays synchronous-fast after the first successful fetch and keeps
 * working offline.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { supabase } from './supabase';

const CACHE_KEY = 'bundled_groq_key_cache';

/** The last-fetched shared Groq key (cached). '' if never fetched. */
export async function getCachedBundledGroqKey(): Promise<string> {
  try { return (await AsyncStorage.getItem(CACHE_KEY)) ?? ''; } catch { return ''; }
}

/** Pull the shared Groq key from the DB and refresh the cache. Best-effort:
 *  returns '' (and leaves any existing cache intact) on any failure. */
export async function refreshBundledGroqKey(): Promise<string> {
  try {
    const { data, error } = await supabase
      .from('app_config')
      .select('value')
      .eq('name', 'groq_api_key')
      .maybeSingle();
    if (error) return getCachedBundledGroqKey();
    const v = (data?.value ?? '').trim();
    if (v) await AsyncStorage.setItem(CACHE_KEY, v);
    return v || getCachedBundledGroqKey();
  } catch {
    return getCachedBundledGroqKey();
  }
}
