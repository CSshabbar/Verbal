/**
 * meetingsStore — the ONE meetings store (IDI-175 §1).
 *
 * Before this, `useMeetings()` was a plain hook and four screens mounted four
 * independent copies of it. Each ran its own `select *` (transcripts included)
 * and each opened its own realtime channel on the SAME topic
 * (`verbal_meetings_${userId}`) — so one screen's unmount `removeChannel` killed
 * another's subscription, and every notes-edit echo fanned out into N full
 * refetches that could land on top of text the user was still typing.
 *
 * Now: module state + subscribe/getSnapshot (historyStore's shape), one fetch,
 * one channel (owned by lib/meetings), and `useMeetings()` is a thin
 * useSyncExternalStore wrapper that keeps its old return shape.
 *
 * What the store adds on top of "share one fetch":
 *
 *  • error ≠ empty (§2) — fetchMeetings THROWS now; a failure keeps the
 *    previous list and exposes `error` for the list screen's banner.
 *  • a pending-writes queue (§3) — per meeting+field, latest wins. A failed
 *    write is retried on catchUp()/reconnect instead of being dropped on the
 *    floor, and the meeting is flagged `unsaved` so the Notes screen can say so.
 *  • compare-and-set writes (§4) — every update carries `.eq('user_id')` and an
 *    `updated_at` witness. On a CAS miss we refetch and DON'T write; the meeting
 *    is flagged `conflict` so the UI can offer a Reload.
 *  • self-write suppression (§1) — a realtime echo whose `updated_at` is one we
 *    just stamped is ignored, and a field with a pending local edit is never
 *    overwritten by a refetch (the `localEdits` overlay).
 */
import { AppState } from 'react-native';
import {
  fetchMeetings, fetchMeeting, subscribeMeetings, rejoinMeetingsChannel,
  closeMeetingsChannel, updateScratchpadRemote, updateNotesRemote,
  updateActionItemsRemote, Meeting, MeetingActionItem, MeetingsEvent,
} from '../../lib/meetings';
import { getUserId } from '../../lib/storage';
import * as syncStore from '../../lib/syncStore';

export type { Meeting } from '../../lib/meetings';

/** Fields mobile can write. Each is queued/retried independently. */
type Field = 'scratchpad' | 'notesMd' | 'actionItems';

export type MeetingsSnapshot = {
  meetings: Meeting[];
  loading: boolean;
  /** Non-null when the last refresh failed. The list below is the last good one. */
  error: string | null;
  /** meetingId → a write is queued/failed and will be retried. */
  unsaved: Record<string, boolean>;
  /** meetingId → another device wrote first; the UI should offer a Reload. */
  conflicts: Record<string, boolean>;
};

const DEBOUNCE_MS = 600;

/* ── module state ────────────────────────────────────────────────────────── */

/** Rows exactly as fetched. `snapshot.meetings` is this + the localEdits overlay. */
let rows: Meeting[] = [];
let loading = true;
let error: string | null = null;

/** meetingId → `updated_at` as of our last read/write: the CAS witness. */
const witnesses = new Map<string, string>();
/** meetingId → fields the user has changed locally but we haven't confirmed
 *  written. A refetch must never overwrite one of these. */
const localEdits = new Map<string, Partial<Record<Field, any>>>();
/** `${id}|${updated_at}` values WE stamped — their realtime echo is skipped. */
const selfWrites = new Set<string>();
/** meetingId → field → value still to be written (latest wins). */
const pending = new Map<string, Map<Field, any>>();
/** `${id}|${field}` → debounce timer. */
const timers = new Map<string, ReturnType<typeof setTimeout>>();
const conflicts = new Set<string>();

let snapshot: MeetingsSnapshot = {
  meetings: [], loading: true, error: null, unsaved: {}, conflicts: {},
};
const listeners = new Set<() => void>();

const MEETING_FIELD: Record<Field, keyof Meeting> = {
  scratchpad: 'scratchpad', notesMd: 'notesMd', actionItems: 'actionItems',
};

function overlay(list: Meeting[]): Meeting[] {
  if (localEdits.size === 0) return list;
  return list.map((m) => {
    const e = localEdits.get(m.id);
    if (!e) return m;
    const next: any = { ...m };
    for (const k of Object.keys(e) as Field[]) next[MEETING_FIELD[k]] = e[k];
    return next as Meeting;
  });
}

function toRecord(keys: Iterable<string>): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const k of keys) out[k] = true;
  return out;
}

function emit() {
  snapshot = {
    meetings: overlay(rows),
    loading,
    error,
    unsaved: toRecord(pending.keys()),
    conflicts: toRecord(conflicts),
  };
  listeners.forEach((l) => { try { l(); } catch { /* ignore */ } });
}

export function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function getSnapshot(): MeetingsSnapshot { return snapshot; }

/* ── fetching ────────────────────────────────────────────────────────────── */

function adoptRows(list: Meeting[]) {
  rows = list;
  for (const m of list) {
    // Don't move the witness for a meeting whose write is still in flight —
    // that write's CAS is against the value it read.
    if (!pending.has(m.id)) witnesses.set(m.id, m.updatedAt);
  }
}

async function load(): Promise<void> {
  try {
    adoptRows(await fetchMeetings());
    error = null;
  } catch (e: any) {
    // Keep the previous list — a network blip is NOT "you have no meetings".
    error = e?.message
      ? "Couldn't refresh meetings — showing the last loaded list."
      : "Couldn't refresh meetings.";
  } finally {
    loading = false;
    emit();
  }
  try {
    if (await syncStore.getSyncEnabled()) await ensureSubscribed();
    else await disconnect();
  } catch { /* realtime is best-effort */ }
}

let inFlight: Promise<void> | null = null;
let loadPromise: Promise<void> | null = null;
let started = false;

function runLoad(): Promise<void> {
  if (inFlight) return inFlight;
  inFlight = load().finally(() => { inFlight = null; });
  loadPromise = inFlight;
  return inFlight;
}

export function ensureLoaded(): Promise<void> {
  if (!started) { started = true; return runLoad(); }
  return loadPromise ?? Promise.resolve();
}

export async function refresh(): Promise<void> {
  await runLoad();
  await flushPending();
}

/** Refetch ONE meeting (after a CAS miss, or the Reload affordance). */
async function refetchOne(id: string): Promise<Meeting | null> {
  const m = await fetchMeeting(id);
  if (!m) return null;
  witnesses.set(id, m.updatedAt);
  rows = rows.some((r) => r.id === id)
    ? rows.map((r) => (r.id === id ? m : r))
    : [m, ...rows];
  emit();
  return m;
}

/* ── realtime ────────────────────────────────────────────────────────────── */

let unsubscribeChannel: (() => void) | null = null;
let coalesce: ReturnType<typeof setTimeout> | null = null;

function onRealtime(ev?: MeetingsEvent) {
  const r = ev?.row;
  if (r?.id && r?.updated_at) {
    const key = `${r.id}|${r.updated_at}`;
    // Our own write coming back. Refetching here is what used to clobber
    // in-flight local text with a stale round-trip.
    if (selfWrites.has(key)) { selfWrites.delete(key); return; }
  }
  // Coalesce bursts (desktop writes transcript chunks rapidly while live).
  if (coalesce) return;
  coalesce = setTimeout(() => { coalesce = null; runLoad().catch(() => {}); }, 250);
}

async function ensureSubscribed(): Promise<void> {
  if (unsubscribeChannel) return;
  const uid = await getUserId();
  if (!uid) return;
  unsubscribeChannel = subscribeMeetings(uid, onRealtime);
}

/** Sync toggled OFF: stop remote IO, keep the loaded meetings on screen. */
export async function disconnect(): Promise<void> {
  if (unsubscribeChannel) { unsubscribeChannel(); unsubscribeChannel = null; }
  await closeMeetingsChannel();
}

/**
 * Foreground catch-up (AppState 'active'): rejoin a channel iOS may have
 * silently dropped, re-pull, and retry any write that failed while we were away.
 */
export async function catchUp(): Promise<void> {
  if (!(await syncStore.getSyncEnabled())) return;
  await ensureSubscribed();
  try {
    const uid = await getUserId();
    if (uid) await rejoinMeetingsChannel(uid);
  } catch { /* best effort */ }
  await refresh();
}

/**
 * Sign-out / account switch. Drops everything: the previous account's meetings
 * must not stay on screen, and the channel is keyed by the OLD user id.
 * NOTE for the useAuth owner — this needs calling next to historyStore.reset().
 */
export async function reset(): Promise<void> {
  for (const t of timers.values()) clearTimeout(t);
  timers.clear();
  pending.clear();
  localEdits.clear();
  witnesses.clear();
  selfWrites.clear();
  conflicts.clear();
  rows = [];
  loading = true;
  error = null;
  started = false;
  loadPromise = null;
  inFlight = null;
  if (coalesce) { clearTimeout(coalesce); coalesce = null; }
  await disconnect();
  emit();
}

// The Sync toggle is live (IDI-171): ON re-pulls + joins, OFF closes the channel
// but keeps the list. Registered once, at module load.
syncStore.onChange((enabled) => {
  if (enabled) refresh().catch(() => {});
  else disconnect().catch(() => {});
});

// Backgrounding must not eat the last 600 ms of typing — flush the debounce
// before iOS suspends us. (The screens also flush on unmount; this covers the
// case where the app goes away with a meeting screen still mounted.)
AppState.addEventListener('change', (s) => {
  if (s !== 'active') flushNow().catch(() => {});
});

/* ── writes: debounce → pending queue → CAS ──────────────────────────────── */

function setLocalEdit(id: string, field: Field, value: any) {
  const e = localEdits.get(id) ?? {};
  e[field] = value;
  localEdits.set(id, e);
}

function clearLocalEdit(id: string, field: Field, writtenValue: any) {
  const e = localEdits.get(id);
  if (!e) return;
  // Only drop the overlay if the user hasn't typed since — otherwise the newer
  // text would flash back to the value we just wrote.
  if (e[field] !== writtenValue) return;
  delete e[field];
  if (Object.keys(e).length === 0) localEdits.delete(id);
}

function queue(id: string, field: Field, value: any) {
  const p = pending.get(id) ?? new Map<Field, any>();
  p.set(field, value);                       // latest wins
  pending.set(id, p);
}

function dequeue(id: string, field: Field) {
  const p = pending.get(id);
  if (!p) return;
  p.delete(field);
  if (p.size === 0) pending.delete(id);
}

/** Optimistic local change + a debounced remote write. */
function edit(id: string, field: Field, value: any) {
  setLocalEdit(id, field, value);
  emit();
  const key = `${id}|${field}`;
  const t = timers.get(key);
  if (t) clearTimeout(t);
  timers.set(key, setTimeout(() => {
    timers.delete(key);
    queue(id, field, value);
    emit();
    flushOne(id, field).catch(() => {});
  }, DEBOUNCE_MS));
}

export function updateScratchpad(id: string, text: string) { edit(id, 'scratchpad', text); }
export function updateNotes(id: string, text: string) { edit(id, 'notesMd', text); }
export function updateActionItems(id: string, items: MeetingActionItem[]) {
  // Checkboxes aren't typing — write straight through, no debounce.
  setLocalEdit(id, 'actionItems', items);
  queue(id, 'actionItems', items);
  emit();
  flushOne(id, 'actionItems').catch(() => {});
}

async function writeField(
  id: string, field: Field, value: any, userId: string, witness: string | null,
) {
  const opts = { userId, witness };
  if (field === 'scratchpad') return updateScratchpadRemote(id, value, opts);
  if (field === 'notesMd') return updateNotesRemote(id, value, opts);
  return updateActionItemsRemote(id, value, opts);
}

let flushing = false;

async function flushOne(id: string, field: Field): Promise<void> {
  const value = pending.get(id)?.get(field);
  if (value === undefined) return;
  // A conflicted meeting is frozen until the user resolves it — writing anyway
  // is exactly the silent clobber this ticket is about.
  if (conflicts.has(id)) return;

  let uid = '';
  try { uid = await getUserId(); } catch { /* handled below */ }
  if (!uid) return;

  const res = await writeField(id, field, value, uid, witnesses.get(id) ?? null);
  const latest = pending.get(id)?.get(field);

  if (res.ok && res.updatedAt) {
    witnesses.set(id, res.updatedAt);
    selfWrites.add(`${id}|${res.updatedAt}`);
    // Bounded: an echo that never arrives (sync off, socket down) must not leak.
    if (selfWrites.size > 200) {
      const oldest = selfWrites.values().next().value;
      if (oldest) selfWrites.delete(oldest);
    }
    rows = rows.map((m) => (m.id === id
      ? ({ ...m, [MEETING_FIELD[field]]: value, updatedAt: res.updatedAt! } as Meeting)
      : m));
    if (latest === value) {                   // nothing newer arrived mid-write
      dequeue(id, field);
      clearLocalEdit(id, field, value);
    }
  } else if (res.conflict) {
    // Another device wrote first. Do NOT write. Adopt the remote row and let the
    // user decide (MeetingNotesScreen shows "changed on another device" + Reload).
    dequeue(id, field);
    conflicts.add(id);
    await refetchOne(id);
  }
  // else: transport failure — the entry stays queued, `unsaved` stays true, and
  // the next catchUp() retries it exactly once.
  emit();
}

/** Retry every queued write ONCE. Called from catchUp()/refresh(). */
export async function flushPending(): Promise<void> {
  if (flushing) return;
  flushing = true;
  try {
    const work: Array<[string, Field]> = [];
    for (const [id, fields] of pending) for (const f of fields.keys()) work.push([id, f]);
    for (const [id, f] of work) await flushOne(id, f);
  } finally {
    flushing = false;
  }
}

/**
 * Flush the debounce timers immediately (screen blur / unmount / background).
 * The 600 ms window used to swallow the last keystrokes when the user hit back.
 */
export async function flushNow(): Promise<void> {
  for (const [key, t] of timers) {
    clearTimeout(t);
    const sep = key.lastIndexOf('|');
    const id = key.slice(0, sep);
    const field = key.slice(sep + 1) as Field;
    const value = localEdits.get(id)?.[field];
    if (value !== undefined) queue(id, field, value);
  }
  timers.clear();
  emit();
  await flushPending();
}

/* ── conflict affordances ────────────────────────────────────────────────── */

/** "Reload" — throw away the local edit and adopt what the other device wrote. */
export async function reloadMeeting(id: string): Promise<Meeting | null> {
  const t: string[] = [];
  for (const key of timers.keys()) if (key.startsWith(`${id}|`)) t.push(key);
  for (const key of t) { clearTimeout(timers.get(key)!); timers.delete(key); }
  pending.delete(id);
  localEdits.delete(id);
  conflicts.delete(id);
  const m = await refetchOne(id);
  emit();
  return m;
}

/** Dismiss the conflict banner without discarding the local text. The next edit
 *  writes against the refreshed witness, so it will land. */
export function clearConflict(id: string) {
  conflicts.delete(id);
  emit();
}

/** True when `field` on `id` is holding an unconfirmed local edit. */
export function hasLocalEdit(id: string, field: Field): boolean {
  return localEdits.get(id)?.[field] !== undefined;
}

/** Adopt a freshly generated notes_md (the Generate/Regenerate path). */
export async function setNotesNow(id: string, md: string): Promise<boolean> {
  setLocalEdit(id, 'notesMd', md);
  queue(id, 'notesMd', md);
  emit();
  await flushOne(id, 'notesMd');
  return !pending.get(id)?.has('notesMd');
}
