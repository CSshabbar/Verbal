import AsyncStorage from '@react-native-async-storage/async-storage';
import { supabase } from './supabase';   // no cycle: supabase.ts imports only createClient + AsyncStorage

const KEYS = {
  USER_ID:     'verbal_user_id',
  // Paired-account override (IDI-156): set when this device joins ANOTHER
  // account via QR pairing (or the Settings "Account ID" field). Outranks the
  // local Supabase session id in getUserId() — without it, the session
  // write-back reverts the adoption milliseconds after the claim.
  PAIRED_UID:  'verbal_paired_user_id',
  DEVICE_NAME: 'verbal_device_name',
  // NOTE: the sync flag's key lives in lib/syncStore — the single source of
  // truth (IDI-171). getSyncEnabled/setSyncEnabled are re-exported below.
  HISTORY:     'verbal_history',
  PINNED:      'verbal_pinned',
  // Notes v2 per-user feature flags (Design Decision 4). Default ON.
  NOTES_SEARCH:    'notes_search_enabled',
  NOTES_AUTOTITLE: 'notes_autotitle_enabled',
  NOTES_STRUCTURE: 'notes_structure_detection_enabled',
  NOTES_AUDIO:     'notes_audio_linkage_enabled',
  // Keyboard clipboard history (quick-paste chip + clipboard overlay). Default ON —
  // the clipboard content itself never reaches this key/AsyncStorage; it's captured
  // and persisted entirely native-side (see FlumeInputMethodService.kt / KeyboardViewController.swift).
  KBD_CLIPBOARD_ENABLED: 'keyboard_clipboard_history_enabled',
  // Keyboard Transform (select text elsewhere → instruction → LLM rewrite → replace).
  // Default OFF, matching desktop's opt-in posture for this heavier/LLM-driven feature
  // (whisperflow/app/config.py transform_enabled).
  KBD_TRANSFORM_ENABLED: 'keyboard_transform_enabled',
};

export interface HistoryEntry {
  id:          string;   // uuid or local timestamp
  text:        string;
  device_name: string;
  device_id:   string;
  is_pinned:   boolean;
  created_at:  string;
  source:      'local' | 'remote';
  audio_uri?:  string;              // local file (backup + retry cache)
  audio_url?:  string;              // cloud URL (primary, cross-device)
  status?:     'done' | 'failed';   // 'failed' = retryable
  // Real recording length, LOCAL CACHE ONLY (IDI-172). There is no
  // `duration_ms` column on `transcriptions`, so this never round-trips through
  // the cloud — but it survives an app restart, which is what stops the History
  // row's duration label from degrading to the wordCount/2.5 estimate after the
  // first refresh.
  duration_ms?: number;
  // Tombstone marker (IDI-172 cross-platform contract). Only ever set on rows
  // coming FROM the cloud: a delete is an UPDATE that stamps `deleted_at` and
  // blanks the payload, never a hard DELETE. Entries carrying it are dropped by
  // mergeRemoteEntries (and their ids pruned from the local cache), so it is
  // never persisted.
  deleted_at?: string | null;
}

// ── Identity ──────────────────────────────────────────────────────────────────
export async function getUserId(): Promise<string> {
  // 1) Paired-account override wins (IDI-156). When this device explicitly
  //    joined a host account (QR pair / manual Account ID), that id scopes all
  //    cloud data even though the local Supabase session belongs to a different
  //    Google account. Cleared on sign-in, sign-out, and account deletion.
  //    INTERIM mechanism: replaced by real session minting once auth.uid() RLS
  //    (IDI-29) lands — a user_id override cannot survive JWT-scoped policies.
  try {
    const paired = await AsyncStorage.getItem(KEYS.PAIRED_UID);
    if (paired) return paired;
  } catch { /* fall through */ }
  // 2) The signed-in Supabase user id is authoritative — it scopes ALL cloud data
  // (notes, dictionary, snippets, history). Prefer it (and cache it) so a RESTORED
  // session — where afterSignIn never ran — still reads the right account instead of
  // a stray minted id, which showed everything as 0. Falls back to the stored/local
  // id only when signed out.
  try {
    const { data } = await supabase.auth.getSession();
    const uid = data.session?.user?.id;
    if (uid) {
      const stored = await AsyncStorage.getItem(KEYS.USER_ID);
      if (stored !== uid) await AsyncStorage.setItem(KEYS.USER_ID, uid);
      return uid;
    }
  } catch { /* offline / not ready — fall through to the stored id */ }
  let id = await AsyncStorage.getItem(KEYS.USER_ID);
  if (!id) {
    id = `user_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    await AsyncStorage.setItem(KEYS.USER_ID, id);
  }
  return id;
}
export async function setUserId(id: string) {
  await AsyncStorage.setItem(KEYS.USER_ID, id);
}

/**
 * The id that may legitimately scope CLOUD data, or null when there isn't one
 * (IDI-174). Same first two steps as getUserId() — paired-account override,
 * then the Supabase session id — but WITHOUT the `user_<timestamp>` minting
 * fallback: a locally-minted id is a device-scoped placeholder, and writing
 * cloud rows under it just litters shared tables with orphan data no account
 * can ever read back.
 *
 * Callers use it as a gate: null ⇒ stay local-only, skip the read/write.
 * getUserId() keeps the minting fallback because other callers still depend on
 * it (removed in IDI-179).
 */
export async function getCloudUserId(): Promise<string | null> {
  try {
    const paired = await AsyncStorage.getItem(KEYS.PAIRED_UID);
    if (paired) return paired;
  } catch { /* fall through */ }
  try {
    const { data } = await supabase.auth.getSession();
    return data.session?.user?.id ?? null;
  } catch {
    return null;
  }
}

/** The paired-account override, or null when this device isn't paired into
 *  another account. See KEYS.PAIRED_UID / getUserId() step 1. */
export async function getPairedUserId(): Promise<string | null> {
  try { return await AsyncStorage.getItem(KEYS.PAIRED_UID); } catch { return null; }
}
export async function setPairedUserId(id: string | null): Promise<void> {
  if (id) await AsyncStorage.setItem(KEYS.PAIRED_UID, id);
  else await AsyncStorage.removeItem(KEYS.PAIRED_UID);
}

// The stored id WITHOUT minting a new one (unlike getUserId, which generates a
// local fallback when absent). Null if unset — used to detect an account switch.
export async function getStoredUserId(): Promise<string | null> {
  return AsyncStorage.getItem(KEYS.USER_ID);
}

// Wipe every account-scoped local cache so a different signed-in account never
// inherits the previous account's data (history, notes, vocabulary/snippets,
// device selection) — the cross-account leak. Removing USER_ID means the next
// getUserId() mints a fresh local id. Device-level config (Groq key, device name,
// Notes feature-flag prefs) is intentionally preserved. Call on sign-out and on
// an account change.
//
// NOT wiped here (IDI-170): the native keyboard's `flume_kbd_config.json`
// snapshot (last 15 dictations + vocabulary + snippets). keyboardBridge imports
// THIS module, so calling keyboardBridge.clearKeyboardConfig() from here would
// be an import cycle — useAuth's signOut/deleteAccount call it right after
// clearAccountData() instead. Likewise the local recordings directory, which
// only account DELETION removes (recordings.removeAll(), also from useAuth).
export async function clearAccountData(): Promise<void> {
  await AsyncStorage.multiRemove([
    KEYS.USER_ID,           // verbal_user_id
    KEYS.PAIRED_UID,        // verbal_paired_user_id — pairing doesn't survive account changes
    KEYS.HISTORY,           // verbal_history
    KEYS.PINNED,            // verbal_pinned
    'verbal_notes_cache',   // lib/notesStorage
    'flume_dictionary',     // lib/dictionary (vocabulary + snippets)
    'flume_target_device',  // flume-ui/hooks/useDevices target selection
  ]);
  // The dictionary's CAS witness (`updated_at` of the row we last read) belongs
  // to the OLD account — keeping it would make the next push compare against a
  // foreign row. Dynamic import: lib/dictionary imports this module.
  import('./dictionary').then((m) => m.resetSyncState()).catch(() => {});
}

export async function getDeviceName(): Promise<string> {
  return (await AsyncStorage.getItem(KEYS.DEVICE_NAME)) ?? 'iPhone';
}
export async function setDeviceName(name: string) {
  await AsyncStorage.setItem(KEYS.DEVICE_NAME, name);
}

export async function getDeviceId(): Promise<string> {
  const uid = await getUserId();
  const dn  = await getDeviceName();
  return `${dn.toLowerCase().replace(/\s+/g, '_')}_${uid.slice(-6)}`;
}

// ── API keys ──────────────────────────────────────────────────────────────────
// There are none client-side. All Groq access goes through the `groq-proxy`
// Edge Function (session JWT or anon key) — the provider key lives only in the
// function's server-side secrets. The old getGroqKey()/setGroqKey()/app_config
// resolution chain was removed (IDI-160): the `app_config` table never existed
// in the live schema, so the empty-key gate falsely failed every dictation.

// ── Sync ──────────────────────────────────────────────────────────────────────
// Delegated to lib/syncStore (IDI-171) so the toggle has ONE owner: one
// persistence key, one cache, one set of listeners. Re-exported here purely for
// backwards compatibility with the existing `from '../../lib/storage'` imports —
// new code should import from './syncStore' (or the useSyncEnabled hook) directly.
export { getSyncEnabled, setSyncEnabled } from './syncStore';

// Absent key reads as ON, same convention as the Notes feature flags below.
export async function getClipboardHistoryEnabled(): Promise<boolean> {
  return (await AsyncStorage.getItem(KEYS.KBD_CLIPBOARD_ENABLED)) !== 'false';
}
export async function setClipboardHistoryEnabled(val: boolean) {
  await AsyncStorage.setItem(KEYS.KBD_CLIPBOARD_ENABLED, val ? 'true' : 'false');
  import('./keyboardBridge').then((m) => m.syncKeyboardConfig()).catch(() => {});
}

// Absent key reads as OFF — opt-in, matching desktop's transform_enabled default.
export async function getTransformEnabled(): Promise<boolean> {
  return (await AsyncStorage.getItem(KEYS.KBD_TRANSFORM_ENABLED)) === 'true';
}
export async function setTransformEnabled(val: boolean) {
  await AsyncStorage.setItem(KEYS.KBD_TRANSFORM_ENABLED, val ? 'true' : 'false');
  import('./keyboardBridge').then((m) => m.syncKeyboardConfig()).catch(() => {});
}

// ── Notes v2 feature flags ──────────────────────────────────────────────────────
// Four per-user toggles, default true, individually disable-able in Settings
// (Design Decision 4). Stored as 'false' only when explicitly turned off, so an
// absent key reads as ON.
export interface NotesFeatureFlags {
  search:    boolean;   // notes_search_enabled          — full-text search UI
  autotitle: boolean;   // notes_autotitle_enabled       — auto-title dictated notes
  structure: boolean;   // notes_structure_detection_enabled — checklist detection
  audio:     boolean;   // notes_audio_linkage_enabled   — note ↔ recording linkage
}

export const DEFAULT_NOTES_FLAGS: NotesFeatureFlags = {
  search: true, autotitle: true, structure: true, audio: true,
};

const NOTES_FLAG_KEY: Record<keyof NotesFeatureFlags, string> = {
  search:    KEYS.NOTES_SEARCH,
  autotitle: KEYS.NOTES_AUTOTITLE,
  structure: KEYS.NOTES_STRUCTURE,
  audio:     KEYS.NOTES_AUDIO,
};

export async function getNotesFeatureFlags(): Promise<NotesFeatureFlags> {
  try {
    const pairs = await AsyncStorage.multiGet(Object.values(NOTES_FLAG_KEY));
    const map = new Map(pairs);
    const read = (k: keyof NotesFeatureFlags) => map.get(NOTES_FLAG_KEY[k]) !== 'false';
    return { search: read('search'), autotitle: read('autotitle'), structure: read('structure'), audio: read('audio') };
  } catch {
    return { ...DEFAULT_NOTES_FLAGS };
  }
}

export async function setNotesFeatureFlag(key: keyof NotesFeatureFlags, val: boolean): Promise<void> {
  await AsyncStorage.setItem(NOTES_FLAG_KEY[key], val ? 'true' : 'false');
}

// ── History (local cache) ─────────────────────────────────────────────────────
export async function getHistory(): Promise<HistoryEntry[]> {
  const raw = await AsyncStorage.getItem(KEYS.HISTORY);
  return raw ? JSON.parse(raw) : [];
}

export async function addToHistory(
  text: string,
  deviceName: string,
  deviceId: string,
  id?: string,
  extra?: Partial<Pick<HistoryEntry, 'audio_uri' | 'audio_url' | 'status' | 'duration_ms'>>,
): Promise<HistoryEntry[]> {
  const h = await getHistory();
  const entry: HistoryEntry = {
    id:          id ?? `local_${Date.now()}`,
    text,
    device_name: deviceName,
    device_id:   deviceId,
    is_pinned:   false,
    created_at:  new Date().toISOString(),
    source:      'local',
    status:      'done',
    ...(extra || {}),
  };
  const updated = [entry, ...h].slice(0, 100);
  await AsyncStorage.setItem(KEYS.HISTORY, JSON.stringify(updated));
  // Push the new dictation to the native keyboard's History panel.
  import('./keyboardBridge').then((m) => m.syncKeyboardConfig()).catch(() => {});
  return updated;
}

/**
 * Merge cloud rows into the local cache. Tombstone-aware (IDI-172): rows with
 * `deleted_at` set are never adopted, AND any local copy of them is PRUNED — a
 * delete performed on the desktop arrives as a tombstoned UPDATE, and without
 * the prune the row would live on in this device's cache forever (the old code
 * only ever added rows, so a delete could not propagate at all).
 */
export async function mergeRemoteEntries(remote: HistoryEntry[]): Promise<HistoryEntry[]> {
  const local = await getHistory();
  const tombstoned = new Set(remote.filter(e => e.deleted_at).map(e => e.id));
  const kept = tombstoned.size ? local.filter(e => !tombstoned.has(e.id)) : local;
  const pruned = kept.length !== local.length;

  const keptIds = new Set(kept.map(e => e.id));
  const newEntries = remote
    .filter(e => !e.deleted_at && !keptIds.has(e.id))
    .map(({ deleted_at, ...e }) => ({ ...e, source: 'remote' as const }));

  if (newEntries.length === 0 && !pruned) return local;
  const merged = [...newEntries, ...kept]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 100);
  await AsyncStorage.setItem(KEYS.HISTORY, JSON.stringify(merged));
  // New cloud dictations synced in → refresh the keyboard's History panel.
  import('./keyboardBridge').then((m) => m.syncKeyboardConfig()).catch(() => {});
  return merged;
}

export async function updateEntry(id: string, changes: Partial<HistoryEntry>): Promise<HistoryEntry[]> {
  const h = await getHistory();
  const updated = h.map(e => e.id === id ? { ...e, ...changes } : e);
  await AsyncStorage.setItem(KEYS.HISTORY, JSON.stringify(updated));
  return updated;
}

export async function deleteEntry(id: string): Promise<HistoryEntry[]> {
  const h = await getHistory();
  const updated = h.filter(e => e.id !== id);
  await AsyncStorage.setItem(KEYS.HISTORY, JSON.stringify(updated));
  return updated;
}

export async function clearHistory() {
  await AsyncStorage.setItem(KEYS.HISTORY, JSON.stringify([]));
}
