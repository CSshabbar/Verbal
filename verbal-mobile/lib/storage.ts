import AsyncStorage from '@react-native-async-storage/async-storage';

const KEYS = {
  USER_ID:     'verbal_user_id',
  DEVICE_NAME: 'verbal_device_name',
  GROQ_KEY:    'verbal_groq_key',
  SYNC_ON:     'verbal_sync_enabled',
  HISTORY:     'verbal_history',
  PINNED:      'verbal_pinned',
  // Notes v2 per-user feature flags (Design Decision 4). Default ON.
  NOTES_SEARCH:    'notes_search_enabled',
  NOTES_AUTOTITLE: 'notes_autotitle_enabled',
  NOTES_STRUCTURE: 'notes_structure_detection_enabled',
  NOTES_AUDIO:     'notes_audio_linkage_enabled',
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
}

// ── Identity ──────────────────────────────────────────────────────────────────
export async function getUserId(): Promise<string> {
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
export async function getGroqKey(): Promise<string> {
  return (await AsyncStorage.getItem(KEYS.GROQ_KEY)) ?? '';
}
export async function setGroqKey(key: string) {
  await AsyncStorage.setItem(KEYS.GROQ_KEY, key);
  // Keep the native keyboard's config in sync with the current Groq key.
  import('./keyboardBridge').then((m) => m.syncKeyboardConfig()).catch(() => {});
}

// ── Sync ──────────────────────────────────────────────────────────────────────
export async function getSyncEnabled(): Promise<boolean> {
  return (await AsyncStorage.getItem(KEYS.SYNC_ON)) === 'true';
}
export async function setSyncEnabled(val: boolean) {
  await AsyncStorage.setItem(KEYS.SYNC_ON, val ? 'true' : 'false');
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
  extra?: Partial<Pick<HistoryEntry, 'audio_uri' | 'audio_url' | 'status'>>,
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
  return updated;
}

export async function mergeRemoteEntries(remote: HistoryEntry[]): Promise<HistoryEntry[]> {
  const local = await getHistory();
  const localIds = new Set(local.map(e => e.id));
  const newEntries = remote
    .filter(e => !localIds.has(e.id))
    .map(e => ({ ...e, source: 'remote' as const }));
  if (newEntries.length === 0) return local;
  const merged = [...newEntries, ...local]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 100);
  await AsyncStorage.setItem(KEYS.HISTORY, JSON.stringify(merged));
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
