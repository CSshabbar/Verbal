import AsyncStorage from '@react-native-async-storage/async-storage';

const KEYS = {
  USER_ID:     'verbal_user_id',
  DEVICE_NAME: 'verbal_device_name',
  GROQ_KEY:    'verbal_groq_key',
  SYNC_ON:     'verbal_sync_enabled',
  HISTORY:     'verbal_history',
  PINNED:      'verbal_pinned',
};

export interface HistoryEntry {
  id:          string;   // uuid or local timestamp
  text:        string;
  device_name: string;
  device_id:   string;
  is_pinned:   boolean;
  created_at:  string;
  source:      'local' | 'remote';
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
}

// ── Sync ──────────────────────────────────────────────────────────────────────
export async function getSyncEnabled(): Promise<boolean> {
  return (await AsyncStorage.getItem(KEYS.SYNC_ON)) === 'true';
}
export async function setSyncEnabled(val: boolean) {
  await AsyncStorage.setItem(KEYS.SYNC_ON, val ? 'true' : 'false');
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
