/**
 * historyStore — shared transcription-history store with real cross-device sync.
 *
 * Ports the working scheme from the original app (the retired lib/useSync + lib/storage):
 *   - local cache is the source of truth; remote rows merge in via mergeRemoteEntries
 *   - a realtime channel (`verbal_history_${userId}`) receives inserts from OTHER
 *     devices (own inserts skipped; respects target_device_id) and refetches on update
 *   - all remote activity is gated by the Sync toggle (lib/syncStore)
 *
 * Lifecycle (IDI-171): the toggle is LIVE. Flipping it ON runs an immediate
 * catch-up and joins the channel; flipping it OFF calls disconnect() — channels
 * closed, remote IO stopped, local cache and on-screen items untouched (OFF is
 * not sign-out; only reset() throws the data away). A dropped channel rejoins
 * itself from the subscribe() status callback, and catchUp() is what the
 * foreground AppState listener calls.
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
  mergeRemoteEntries,
  HistoryEntry, getDeviceName } from '../../lib/storage';
import * as syncStore from '../../lib/syncStore';
import { runDictation } from '../../lib/dictationPipeline';
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
  // Prefer the caller's just-measured duration, then the one persisted with the
  // entry (IDI-172 — this is what survives a refresh/restart), and only fall
  // back to the wordCount/2.5 estimate for rows that predate it or arrived from
  // another device (there is no cloud column for it).
  const ms = durationMs && durationMs > 0 ? durationMs : entry.duration_ms;
  const seconds = ms && ms > 0
    ? Math.max(1, Math.round(ms / 1000))
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
  // Every mergeRemoteEntries-driven fetch consults the store, not just the ones
  // on the startup path — a fetch queued before the toggle went OFF must not
  // land after it (IDI-171 uniform gating).
  if (!(await syncStore.getSyncEnabled())) return getHistory();
  const userId = await getUserId();
  const { data, error } = await supabase
    .from('transcriptions')
    .select('*')
    .eq('user_id', userId)
    .order('created_at', { ascending: false })
    .limit(100);
  if (error || !data) return getHistory();
  // NOTE: tombstoned rows are deliberately NOT filtered out server-side — they
  // are what tells this device to prune its local copy (IDI-172). rowToEntry
  // carries `deleted_at` through and mergeRemoteEntries does the drop + prune.
  return mergeRemoteEntries(data.map(rowToEntry));
}

/** One shared cloud-row → HistoryEntry mapping for the fetch and the realtime
 *  INSERT handler, so the tombstone marker can never be dropped by one of them. */
function rowToEntry(r: any): HistoryEntry {
  return {
    id: r.id,
    text: r.edited_text ?? r.text ?? '',
    device_name: r.device_name,
    device_id: r.device_id,
    is_pinned: r.is_pinned ?? false,
    created_at: r.created_at,
    source: 'remote' as const,
    audio_url: r.audio_url ?? undefined,
    status: r.status ?? 'done',
    deleted_at: r.deleted_at ?? null,
  };
}

/* ── channel lifecycle ───────────────────────────────────────────────────── */

let rejoinTimer: ReturnType<typeof setTimeout> | null = null;
let rejoinAttempts = 0;

function cancelRejoin() {
  if (rejoinTimer) { clearTimeout(rejoinTimer); rejoinTimer = null; }
}

/** Close the channel WITHOUT touching cached items or the load guard.
 *  `channel` is nulled first so the resulting 'CLOSED' status callback can tell
 *  an intentional teardown from a dropped connection and not fight us. */
async function closeChannel() {
  const ch = channel;
  channel = null;
  cancelRejoin();
  if (!ch) return;
  try { await supabase.removeChannel(ch); } catch { /* ignore */ }
}

function scheduleRejoin() {
  if (rejoinTimer) return;
  const delay = Math.min(30_000, 1_000 * 2 ** rejoinAttempts);
  rejoinAttempts += 1;
  rejoinTimer = setTimeout(async () => {
    rejoinTimer = null;
    if (!(await syncStore.getSyncEnabled())) return;   // toggled off while waiting
    try { await subscribeRealtime(); } catch { /* the next status error retries */ }
  }, delay);
}

async function subscribeRealtime() {
  const userId = await getUserId();
  const myDeviceId = await getDeviceId();
  await closeChannel();

  const ch = supabase
    .channel(`verbal_history_${userId}`)
    .on(
      'postgres_changes',
      { event: 'INSERT', schema: 'public', table: 'transcriptions', filter: `user_id=eq.${userId}` },
      async (payload: any) => {
        const r = payload.new;
        // A tombstoned row still has to reach mergeRemoteEntries (it prunes the
        // local copy) — the own-device / target filters below would otherwise
        // swallow a delete made on this account's other device.
        if (!r.deleted_at) {
          if (r.device_id === myDeviceId) return;                       // skip own
          if (r.target_device_id && r.target_device_id !== myDeviceId) return; // not for us
        }
        publish(await mergeRemoteEntries([rowToEntry(r)]));
      },
    )
    .on(
      'postgres_changes',
      { event: 'UPDATE', schema: 'public', table: 'transcriptions', filter: `user_id=eq.${userId}` },
      // Covers deletes too: a delete is a tombstoning UPDATE (IDI-172), and the
      // refetch feeds the tombstone into mergeRemoteEntries, which prunes the
      // local row so it disappears from this device's list.
      async () => { publish(await fetchRemoteAndMerge()); },
    );
  channel = ch;
  ch.subscribe((status) => {
    // Without this the channel died silently on a network blip and history just
    // stopped updating until the app was killed (IDI-171).
    if (status === 'SUBSCRIBED') { rejoinAttempts = 0; return; }
    if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT' || status === 'CLOSED') {
      if (channel !== ch) return;   // superseded, or an intentional teardown
      scheduleRejoin();
    }
  });
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
    if (await syncStore.getSyncEnabled()) {
      publish(await fetchRemoteAndMerge());
      await subscribeRealtime();
    } else {
      // Sync off — make sure no channel is left over from a previous ON period.
      await closeChannel();
    }
  } catch (err) {
    console.error('History sync failed:', err);
  }
}

let loadPromise: Promise<void> | null = null;
let inFlight: Promise<void> | null = null;

/** Coalesce concurrent loads — sign-in, the sync-toggle listener and a
 *  foreground catch-up can all land within the same tick. */
function runLoad(): Promise<void> {
  if (inFlight) return inFlight;
  inFlight = load().finally(() => { inFlight = null; });
  loadPromise = inFlight;
  return inFlight;
}

export function ensureLoaded() {
  if (!started) { started = true; return runLoad(); }
  return loadPromise;
}
export function refresh() { return runLoad(); }

/**
 * Foreground catch-up (AppState 'active', IDI-171): re-pull anything that
 * arrived while the app was backgrounded and make sure the channel is joined.
 * refresh() re-runs load(), which resubscribes — so it covers both.
 */
export async function catchUp() {
  if (!(await syncStore.getSyncEnabled())) return;
  await refresh();
}

/**
 * Sync toggled OFF: stop all remote IO, keep everything local.
 *
 * Distinct from reset() on purpose — OFF is not sign-out. The user still wants
 * to see and search the dictations already on this device, so cached items, the
 * AsyncStorage history and the `started` guard all survive; only the channel and
 * any pending rejoin go away.
 */
export async function disconnect() {
  await closeChannel();
}

/**
 * Tear down the singleton on sign-out / account switch: drop the cached items,
 * unsubscribe the realtime channel (keyed by the OLD user id), and reset the
 * load guard so the next signed-in account reloads from scratch. Without this the
 * previous account's transcriptions stay on screen after switching accounts.
 */
export async function reset() {
  items = [];
  started = false;
  loadPromise = null;
  inFlight = null;
  rejoinAttempts = 0;
  await closeChannel();
  emit();
}

// The toggle is live (IDI-171): ON runs an immediate catch-up + rejoins the
// channel, OFF tears the channel down. Registered at module load — historyStore
// is a singleton imported by useHistory/useAuth, so this runs exactly once.
syncStore.onChange((enabled) => {
  if (enabled) { refresh().catch(() => {}); }
  else { disconnect().catch(() => {}); }
});

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
  // false = "This phone only" (send-mode 'none'): the entry stays in THIS
  // device's local history — no cloud row, so no other device ever sees it.
  pushToCloud = true,
): Promise<HistoryItem> {
  let remoteId: string | undefined;
  let audioUrl: string | undefined;
  try {
    if (pushToCloud && await syncStore.getSyncEnabled()) {
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
          // The row's device_name is the SOURCE device (what the receiving
          // desktop shows as "from …"). `deviceTag` is the LOCAL history label
          // and, for "send to <device>" mode, callers pass the TARGET's name —
          // which used to land here, so the Mac saw its own name on phone
          // dictations (2026-08-30). Always send this phone's name.
          device_name: await getDeviceName(),
          text,
          target_device_id: targetDeviceId ?? null,
          audio_url: audioUrl ?? null,
          status,
          // 2026-08-16: durations sync now (nullable column) — they feed the
          // account-wide WPM on every device's Insights page.
          duration_ms: durationMs > 0 ? Math.round(durationMs) : null,
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
    // duration_ms is persisted locally AND on the cloud row (2026-08-16) so
    // the real duration survives a refresh and feeds account-wide WPM.
    { audio_uri: audioUri, audio_url: audioUrl, status,
      duration_ms: durationMs > 0 ? durationMs : undefined });
  const created = entries[0];
  // Override the just-added entry's duration label with the real duration.
  items = [toItem(created, durationMs), ...items.filter(i => i.id !== created.id)];
  emit();
  return items[0];
}

/**
 * Retry a failed transcription from its saved audio (local or cloud).
 *
 * Goes through the SAME `lib/dictationPipeline.runDictation` as the first pass
 * in useRecorder.stop() (IDI-179) — transcribe → AI cleanup → snippet
 * expansion, all with `cleanup: true`. Before that, retry ran formatText and
 * the first pass didn't, so the same audio produced different text depending on
 * which door it came through.
 */
export async function retryEntry(id: string): Promise<{ ok: boolean; error?: string }> {
  const entry = (await getHistory()).find(e => e.id === id);
  if (!entry) return { ok: false, error: 'not found' };
  const path = await recordings.ensureLocal(id, entry.audio_uri, entry.audio_url);
  if (!path) return { ok: false, error: 'no audio to retry' };
  try {
    const { text: formatted, raw } = await runDictation(path, { cleanup: true });
    if (!raw.trim()) return { ok: false, error: 'Still failing — check your connection' };
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

/**
 * Delete a dictation everywhere (IDI-172 cross-platform contract).
 *
 * The cloud row is TOMBSTONED, never hard-deleted: `.delete()` produced no
 * realtime payload the other devices could act on (Supabase DELETE events carry
 * no `new`, and the row simply vanished from the next fetch — which the old
 * add-only merge ignored), so a delete on one device never propagated. An
 * UPDATE that stamps `deleted_at` and blanks the payload is a normal UPDATE
 * event every device already listens to, and it survives a device being offline
 * because it is still there on the next fetch.
 *
 * Order matters: capture the entry (for its audio_url) BEFORE the row's
 * audio_url is nulled, then clean up the cloud object and the local file.
 * Storage cleanup is best-effort — never let it hold up the delete.
 */
export async function remove(id: string) {
  const entry = (await getHistory()).find(e => e.id === id);
  items = items.filter(i => i.id !== id);
  emit();
  try {
    await deleteEntry(id);
    if (!id.startsWith('local_')) {
      const { error } = await supabase
        .from('transcriptions')
        .update({
          deleted_at: new Date().toISOString(),
          text: '',
          edited_text: null,
          audio_url: null,
        })
        .eq('id', id);
      if (error) console.error('Failed to tombstone transcription:', error);
    }
    // Cloud object + local file. Deliberately NOT gated on the sync toggle:
    // removing data the user asked to delete is always safe, and leaving an
    // orphan recording behind because sync happens to be off is not.
    if (entry?.audio_url) await recordings.removeCloud(entry.audio_url);
    await recordings.remove(entry?.audio_uri);
  } catch (err) {
    console.error('Failed to remove transcription:', err);
  }
}
