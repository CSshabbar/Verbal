/**
 * historyStore — shared transcription-history store with real cross-device sync.
 *
 * Ports the working scheme from the original app (lib/useSync + lib/storage):
 *   - local cache is the source of truth; remote rows merge in via mergeRemoteEntries
 *   - a realtime channel (`verbal_history_${userId}`) receives inserts from OTHER
 *     devices (own inserts skipped; respects target_device_id) and refetches on update
 *   - all remote activity is gated by the Sync toggle (getSyncEnabled)
 *
 * Presentation: entries are mapped to `HistoryItem` (computed labels) for the UI.
 */
import { supabase } from '../../lib/supabase';
import {
  getHistory,
  addToHistory,
  updateEntry,
  deleteEntry,
  getUserId,
  getDeviceId,
  getSyncEnabled,
  getGroqKey,
  mergeRemoteEntries,
  clearHistory as clearStoredHistory,
  HistoryEntry,
} from '../../lib/storage';
import { transcribeAudio, formatText } from '../../lib/groq';
import * as recordings from '../../lib/recordings';

export type HistoryItem = {
  id: string;
  text: string;
  deviceTag: string;
  dayLabel: string;
  timeOfDay: string;
  relativeTime: string;
  durationLabel: string;
  wordCount: number;
  audioUri?: string;
  audioUrl?: string;
  hasAudio?: boolean;
  status?: 'done' | 'failed';
};

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

function dayLabelFor(d: Date, now: Date): string {
  const diff = Math.round((startOfDay(now) - startOfDay(d)) / 86_400_000);
  if (diff <= 0) return 'Today';
  if (diff === 1) return 'Yesterday';
  if (diff < 7) return DAYS[d.getDay()];
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}
function timeOfDayFor(d: Date): string {
  let h = d.getHours();
  const ampm = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  return `${h}:${String(d.getMinutes()).padStart(2, '0')} ${ampm}`;
}
function relativeTimeFor(d: Date, now: Date): string {
  const sec = Math.max(0, Math.round((now.getTime() - d.getTime()) / 1000));
  if (sec < 60) return 'just now';
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} min ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr} hour${hr === 1 ? '' : 's'} ago`;
  const day = Math.round(hr / 24);
  return day === 1 ? 'yesterday' : `${day} days ago`;
}
const wordsIn = (t: string) => (t.trim() ? t.trim().split(/\s+/).length : 0);

function toItem(entry: HistoryEntry, durationMs?: number): HistoryItem {
  const created = new Date(entry.created_at);
  const now = new Date();
  const wordCount = wordsIn(entry.text);
  const seconds = durationMs && durationMs > 0
    ? Math.max(1, Math.round(durationMs / 1000))
    : Math.max(1, Math.round(wordCount / 2.5));
  return {
    id: entry.id,
    text: entry.text,
    deviceTag: entry.device_name || 'Local',
    dayLabel: dayLabelFor(created, now),
    timeOfDay: timeOfDayFor(created),
    relativeTime: relativeTimeFor(created, now),
    durationLabel: `${seconds}s`,
    wordCount,
    audioUri: entry.audio_uri,
    audioUrl: entry.audio_url,
    hasAudio: !!(entry.audio_uri || entry.audio_url),
    status: entry.status || 'done',
  };
}

/* ── store internals ─────────────────────────────────────────────────────── */

let items: HistoryItem[] = [];
let started = false;
let channel: ReturnType<typeof supabase.channel> | null = null;
const listeners = new Set<() => void>();

function emit() { listeners.forEach(l => l()); }
function publish(entries: HistoryEntry[]) {
  items = entries.map(e => toItem(e));
  emit();
}

async function fetchRemoteAndMerge(): Promise<HistoryEntry[]> {
  const userId = await getUserId();
  const { data, error } = await supabase
    .from('transcriptions')
    .select('*')
    .eq('user_id', userId)
    .order('created_at', { ascending: false })
    .limit(100);
  if (error || !data) return getHistory();
  const remote: HistoryEntry[] = data.map((r: any) => ({
    id: r.id,
    text: r.edited_text ?? r.text,
    device_name: r.device_name,
    device_id: r.device_id,
    is_pinned: r.is_pinned ?? false,
    created_at: r.created_at,
    source: 'remote' as const,
    audio_url: r.audio_url ?? undefined,
    status: r.status ?? 'done',
  }));
  return mergeRemoteEntries(remote);
}

async function subscribeRealtime() {
  const userId = await getUserId();
  const myDeviceId = await getDeviceId();
  if (channel) await supabase.removeChannel(channel);

  channel = supabase
    .channel(`verbal_history_${userId}`)
    .on(
      'postgres_changes',
      { event: 'INSERT', schema: 'public', table: 'transcriptions', filter: `user_id=eq.${userId}` },
      async (payload: any) => {
        const r = payload.new;
        if (r.device_id === myDeviceId) return;                       // skip own
        if (r.target_device_id && r.target_device_id !== myDeviceId) return; // not for us
        const entry: HistoryEntry = {
          id: r.id,
          text: r.edited_text ?? r.text,
          device_name: r.device_name,
          device_id: r.device_id,
          is_pinned: r.is_pinned ?? false,
          created_at: r.created_at,
          source: 'remote',
          audio_url: r.audio_url ?? undefined,
          status: r.status ?? 'done',
        };
        publish(await mergeRemoteEntries([entry]));
      },
    )
    .on(
      'postgres_changes',
      { event: 'UPDATE', schema: 'public', table: 'transcriptions', filter: `user_id=eq.${userId}` },
      async () => { publish(await fetchRemoteAndMerge()); },
    )
    .subscribe();
}

export function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function getSnapshot(): HistoryItem[] { return items; }

async function load() {
  // Always show the local cache first…
  publish(await getHistory());
  // …then, if sync is on, pull remote + open the realtime channel.
  try {
    if (await getSyncEnabled()) {
      publish(await fetchRemoteAndMerge());
      await subscribeRealtime();
    }
  } catch (err) {
    console.error('History sync failed:', err);
  }
}

let loadPromise: Promise<void> | null = null;
export function ensureLoaded() {
  if (!started) { started = true; loadPromise = load(); }
  return loadPromise;
}
export function refresh() { loadPromise = load(); return loadPromise; }

/** Tear down account-scoped singleton state on sign-out/account changes. */
export async function reset() {
  items = [];
  started = false;
  loadPromise = null;
  if (channel) {
    try { await supabase.removeChannel(channel); } catch { /* ignore */ }
    channel = null;
  }
  emit();
}

/** Clear device-local history and publish the empty snapshot immediately. */
export async function clear() {
  await clearStoredHistory();
  items = [];
  emit();
}

/** Legacy contract helper — prepend an already-built item. */
export async function add(item: HistoryItem) {
  items = [item, ...items];
  emit();
}

/**
 * Persist a transcription: insert to Supabase (when sync on) reusing the remote
 * row id so the local + remote copies dedupe, then update the local cache.
 */
export async function addTranscription(
  text: string,
  deviceTag: string,
  durationMs = 0,
  targetDeviceId?: string | null,
  audioUri?: string,
  status: 'done' | 'failed' = 'done',
): Promise<HistoryItem> {
  let remoteId: string | undefined;
  let audioUrl: string | undefined;
  try {
    if (await getSyncEnabled()) {
      const userId = await getUserId();
      const deviceId = await getDeviceId();
      // Upload the audio first so its URL rides along on the row.
      if (audioUri && userId) {
        audioUrl = (await recordings.uploadCloud(audioUri, userId, `rec_${Date.now()}`)) ?? undefined;
      }
      const { data } = await supabase
        .from('transcriptions')
        .insert({
          user_id: userId,
          device_id: deviceId,
          device_name: deviceTag,
          text,
          target_device_id: targetDeviceId ?? null,
          audio_url: audioUrl ?? null,
          status,
        })
        .select('id')
        .single();
      remoteId = data?.id;
    }
  } catch (err) {
    console.error('Supabase transcription insert failed:', err);
  }

  const deviceId = await getDeviceId();
  const entries = await addToHistory(text, deviceTag, deviceId, remoteId,
    { audio_uri: audioUri, audio_url: audioUrl, status });
  const created = entries[0];
  // Override the just-added entry's duration label with the real duration.
  items = [toItem(created, durationMs), ...items.filter(i => i.id !== created.id)];
  emit();
  return items[0];
}

/** Retry a failed transcription from its saved audio (local or cloud). */
export async function retryEntry(id: string): Promise<{ ok: boolean; error?: string }> {
  const entry = (await getHistory()).find(e => e.id === id);
  if (!entry) return { ok: false, error: 'not found' };
  const path = await recordings.ensureLocal(id, entry.audio_uri, entry.audio_url);
  if (!path) return { ok: false, error: 'no audio to retry' };
  const apiKey = await getGroqKey();
  if (!apiKey) return { ok: false, error: 'Add a Groq API key in Settings first' };
  try {
    const raw = await transcribeAudio(path, apiKey);
    if (!raw.trim()) return { ok: false, error: 'Still failing — check your connection' };
    let formatted = raw;
    try { formatted = await formatText(raw, apiKey); } catch { /* keep raw */ }
    await updateEntry(id, { text: formatted, status: 'done' });
    if (!id.startsWith('local_')) {
      try {
        await supabase.from('transcriptions').update({ text: formatted, status: 'done' }).eq('id', id);
      } catch { /* best effort */ }
    }
    publish(await getHistory());
    return { ok: true };
  } catch (e: any) {
    return { ok: false, error: e?.message || 'Retry failed' };
  }
}

/** Play a saved recording (local file, or download from the cloud URL). */
export async function playEntry(id: string): Promise<boolean> {
  const entry = (await getHistory()).find(e => e.id === id);
  if (!entry) return false;
  const path = await recordings.ensureLocal(id, entry.audio_uri, entry.audio_url);
  if (!path) return false;
  try {
    const { createAudioPlayer, setAudioModeAsync } = require('expo-audio');
    try { await setAudioModeAsync({ playsInSilentMode: true }); } catch { /* ignore */ }
    const player = createAudioPlayer(path);
    player.play();
    return true;
  } catch (e) {
    console.warn('playEntry failed:', e);
    return false;
  }
}

export async function remove(id: string) {
  items = items.filter(i => i.id !== id);
  emit();
  try {
    await deleteEntry(id);
    if (!id.startsWith('local_')) {
      await supabase.from('transcriptions').delete().eq('id', id);
    }
  } catch (err) {
    console.error('Failed to remove transcription:', err);
  }
}
