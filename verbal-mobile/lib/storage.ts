import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { supabase } from './supabase';   // no cycle: supabase.ts imports only createClient + AsyncStorage

const KEYS = {
  USER_ID:     'verbal_user_id',
  // RETIRED by IDI-29. Was the paired-account override: a user_id this device
  // adopted via QR pairing or the Settings "Account ID" field, which outranked
  // the local Supabase session id. `auth.uid()` RLS made that unrepresentable —
  // the JWT decides, so an adopted id can only ever read zero rows. Nothing
  // reads or writes this key any more; it stays in the clearAccountData() sweep
  // below purely to purge the value from installs that set it pre-cutover.
  PAIRED_UID:  'verbal_paired_user_id',
  DEVICE_NAME: 'verbal_device_name',
  // Stable per-INSTALL device identity (IDI-177). Minted once and never derived
  // from anything mutable — see getDeviceId(). Deliberately NOT wiped by
  // clearAccountData(): the install is the same device whoever signs into it.
  DEVICE_UUID: 'verbal_device_uuid',
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
  // The signed-in Supabase user id is authoritative — it scopes ALL cloud data
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
 * (IDI-174). The Supabase session id, and nothing else — WITHOUT the
 * `user_<timestamp>` minting fallback: a locally-minted id is a device-scoped
 * placeholder, and writing cloud rows under it just litters shared tables with
 * orphan data no account can ever read back.
 *
 * Since IDI-29 this is necessarily the session id: `auth.uid()` RLS evaluates
 * the JWT, so any id that isn't the session's own subject reads zero rows and
 * fails every write. Returning anything else would produce silent no-ops.
 *
 * Callers use it as a gate: null ⇒ stay local-only, skip the read/write.
 * getUserId() keeps the minting fallback because other callers still depend on
 * it (removed in IDI-179).
 */
export async function getCloudUserId(): Promise<string | null> {
  try {
    const { data } = await supabase.auth.getSession();
    return data.session?.user?.id ?? null;
  } catch {
    return null;
  }
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
    KEYS.PAIRED_UID,        // verbal_paired_user_id — retired (IDI-29); purge any pre-cutover value
    KEYS.HISTORY,           // verbal_history
    KEYS.PINNED,            // verbal_pinned
    'verbal_notes_cache',   // lib/notesStorage
    'flume_dictionary',     // lib/dictionary (vocabulary + snippets)
    'flume_target_device',  // flume-ui/hooks/useDevices target selection
    'verbal_insights_cache', // lib/insights cloud aggregate (account-scoped)
    'verbal_canvas_log',     // useCanvas local activity feed (account-scoped)
    'flume_org',             // lib/organizations — another team's shared vocabulary,
                             // snippets and member roster must never survive an
                             // account switch on this device (IDI-216)
  ]);
  // The dictionary's CAS witness (`updated_at` of the row we last read) belongs
  // to the OLD account — keeping it would make the next push compare against a
  // foreign row. Dynamic import: lib/dictionary imports this module.
  import('./dictionary').then((m) => m.resetSyncState()).catch(() => {});
  // The org module also keeps an in-memory mirror of that cache for the dictation
  // path, so removing the AsyncStorage key alone would leave it live for the rest
  // of the app run. Dynamic import for the same cycle reason as above.
  import('./organizations').then((m) => m.clearOrgCache()).catch(() => {});
}

export async function getDeviceName(): Promise<string> {
  const stored = await AsyncStorage.getItem(KEYS.DEVICE_NAME);
  if (stored) return stored;
  // No rename yet: use the hardware name/model instead of a hard-coded
  // 'iPhone' — Android phones showed up as "iPhone" on the Mac's device list
  // and in claim_pairing's claimed_by (review 2026-08-30). expo-device is
  // optional at runtime (same guarded require as lib/notifications.ts).
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const Device = require('expo-device');
    const hw = (Device?.deviceName || Device?.modelName || '').toString().trim();
    if (hw) return hw;
  } catch { /* fall through */ }
  const { Platform } = require('react-native');
  return Platform.OS === 'android' ? 'Android phone' : 'iPhone';
}
export async function setDeviceName(name: string) {
  await AsyncStorage.setItem(KEYS.DEVICE_NAME, name);
}

export async function getDeviceId(): Promise<string> {
  // Stable per-install UUID (IDI-177). The old id derived from
  // deviceName + userId.slice(-6), so RENAMING the device or switching
  // accounts orphaned its `devices` row and (post-IDI-173) changed the canvas
  // origin id. Minted once; account- and name-independent.
  //
  // Stored in the KEYCHAIN first, AsyncStorage second. AsyncStorage is wiped by
  // an app reinstall (and by a simulator reset), so a reinstall minted a fresh
  // identity and orphaned the old `devices` row EVERY time — that is how one
  // test account reached 14 dead "iPhone" rows, all named the same, none seen in
  // three weeks. The iOS Keychain / Android keystore survives reinstall, so the
  // install now keeps its identity across one.
  try {
    const secure = await SecureStore.getItemAsync(KEYS.DEVICE_UUID);
    if (secure) {
      // Mirror back so the AsyncStorage path stays warm (and readable by any
      // sync code that reads it directly). Fire-and-forget: never block on it.
      AsyncStorage.setItem(KEYS.DEVICE_UUID, secure).catch(() => {});
      return secure;
    }
  } catch {
    // SecureStore unavailable (web, or keychain locked) — fall through to
    // AsyncStorage rather than minting a duplicate identity.
  }
  try {
    const existing = await AsyncStorage.getItem(KEYS.DEVICE_UUID);
    if (existing) {
      // Promote a pre-Keychain id so it survives the NEXT reinstall. Existing
      // installs therefore keep the row they already have — no id churn.
      SecureStore.setItemAsync(KEYS.DEVICE_UUID, existing).catch(() => {});
      return existing;
    }
    const minted = `dev_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
    await AsyncStorage.setItem(KEYS.DEVICE_UUID, minted);
    SecureStore.setItemAsync(KEYS.DEVICE_UUID, minted).catch(() => {});
    return minted;
  } catch {
    // Storage unavailable — fall back to the legacy derived id (stable enough
    // within a session; never throws into a caller).
    const uid = await getUserId();
    const dn  = await getDeviceName();
    return `${dn.toLowerCase().replace(/\s+/g, '_')}_${uid.slice(-6)}`;
  }
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
