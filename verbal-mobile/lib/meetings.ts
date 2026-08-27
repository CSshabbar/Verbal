/**
 * Meetings — Supabase adapter (mobile is READ-ONLY except the scratchpad,
 * notes_md and action-item checkboxes).
 *
 * Mirrors the desktop data shapes (whisperflow/app/meetings.py::row()):
 * the `meetings` table row with jsonb transcript/speakers/decisions/
 * action_items/marked_moments/hybrid_notes. Scoped by getUserId() like every
 * other cloud read (lib/storage.ts — authoritative from the live session).
 *
 * Layering (IDI-175 §6): the UI `Meeting` types are DEFINED here, in lib/.
 * They used to live in `flume-ui/hooks/useMeetings.mock` and be imported back
 * down into lib/ — a lib → flume-ui edge that the project forbids. The mock now
 * re-exports these instead, so it is still the design contract and the arrow
 * points the legal way.
 *
 * Writes (IDI-175 §4) are compare-and-set, not blind:
 *   .eq('id')  .eq('user_id')  [.eq('updated_at', <witness>)]  .select()
 * A conditional UPDATE that matches nothing is not an error — it returns zero
 * rows — which is exactly how a "someone else wrote first" conflict is detected
 * (same scheme as lib/dictionary.ts).
 */
import { supabase } from './supabase';
import { getUserId } from './storage';

/* ── types (the design contract; useMeetings.mock re-exports these) ───────── */

export type MeetingUtterance = { speaker: string; t0: number; t1: number; text: string };
export type MeetingActionItem = {
  owner: string | null; task: string; done: boolean; due?: string | null; edited?: boolean;
};
export type MeetingMoment = { t: number; label: string; note?: string };
export type MeetingHybridNote = { user_line: string; ai_addition: string };
export type MeetingStatus = 'processing' | 'ready' | 'failed';

export type Meeting = {
  id: string;
  title: string;
  startedAt: string;              // ISO
  durationSeconds: number;
  audioUrl: string | null;
  audioExpired: boolean;          // MER-31: reaped by retention — notes/transcript survive
  transcript: MeetingUtterance[];
  speakers: Record<string, string>;   // speaker id → display name ('self' = You)
  scratchpad: string;
  summary: string;
  decisions: string[];
  actionItems: MeetingActionItem[];
  markedMoments: MeetingMoment[];
  hybridNotes: MeetingHybridNote[];
  deviceName: string | null;
  status: MeetingStatus;
  notesMd: string | null;             // full AI meeting notes (markdown; lazy on desktop)
  pinned: boolean;
  recognized: Record<string, { name: string; meetings: number }>;  // voiceprint hits
  // Provenance of the speaker split: 'diarized' = real who-spoke-when from the
  // audio; 'estimated' = 90 s silence-gap guess (diarization didn't run). null on
  // meetings older than the column (2026-08-27) — render as estimated.
  speakersSource: 'diarized' | 'estimated' | null;
  live: boolean;                  // currently being captured on another device
  updatedAt: string;
  dateLabel: string;              // "Today · 9:24 AM" | "Yesterday" | "Mon · 2:08 PM"
};

function dateLabel(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const diff = Math.round((day(now) - day(d)) / 86_400_000);
    const hm = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    if (diff <= 0) return `Today · ${hm}`;
    if (diff === 1) return 'Yesterday';
    return `${d.toLocaleDateString([], { weekday: 'short' })} · ${hm}`;
  } catch {
    return '';
  }
}

/** Map a `meetings` row (snake_case, jsonb) → the UI Meeting shape. */
export function toMeeting(row: any): Meeting {
  const status: MeetingStatus =
    row.status === 'ready' || row.status === 'failed' ? row.status : 'processing';
  return {
    id: String(row.id),
    title: row.title || 'Meeting',
    startedAt: row.started_at || new Date().toISOString(),
    durationSeconds: Number(row.duration_seconds) || 0,
    audioUrl: row.audio_url || null,
    audioExpired: !!row.audio_expired,
    transcript: Array.isArray(row.transcript) ? row.transcript : [],
    speakers: row.speakers && typeof row.speakers === 'object' ? row.speakers : {},
    scratchpad: row.scratchpad || '',
    summary: row.summary || '',
    decisions: Array.isArray(row.decisions) ? row.decisions : [],
    actionItems: Array.isArray(row.action_items) ? row.action_items : [],
    markedMoments: Array.isArray(row.marked_moments) ? row.marked_moments : [],
    hybridNotes: Array.isArray(row.hybrid_notes) ? row.hybrid_notes : [],
    deviceName: row.device_name || null,
    status,
    notesMd: row.notes_md || null,
    pinned: !!row.pinned,
    recognized: row.recognized && typeof row.recognized === 'object' ? row.recognized : {},
    speakersSource: row.speakers_source === 'diarized' || row.speakers_source === 'estimated'
      ? row.speakers_source : null,
    live: !!row.live,
    updatedAt: row.updated_at || row.started_at || new Date().toISOString(),
    dateLabel: dateLabel(row.started_at),
  };
}

/**
 * Fetch the meeting list.
 *
 * THROWS on failure (IDI-175 §2). It used to swallow every error and return
 * `[]`, which made a network blip indistinguishable from "you have no
 * meetings": the caller's keep-the-previous-list guard could never fire and the
 * list blanked itself. The store turns a throw into a banner over the
 * still-visible list.
 */
export async function fetchMeetings(limit = 50): Promise<Meeting[]> {
  const userId = await getUserId();
  const { data, error } = await supabase
    .from('meetings')
    .select('*')
    .eq('user_id', userId)
    .order('started_at', { ascending: false })
    .limit(limit);
  if (error) throw new Error(error.message || 'Failed to load meetings');
  if (!data) throw new Error('Failed to load meetings');
  return data.map(toMeeting);
}

export async function fetchMeeting(id: string): Promise<Meeting | null> {
  try {
    const { data, error } = await supabase
      .from('meetings').select('*').eq('id', id).maybeSingle();
    if (error || !data) return null;
    return toMeeting(data);
  } catch {
    return null;
  }
}

/* ── writes: compare-and-set ─────────────────────────────────────────────── */

export type WriteResult = {
  ok: boolean;
  /** true = the CAS witness didn't match: another device wrote first. */
  conflict?: boolean;
  /** the `updated_at` we stamped (the caller's next CAS witness). */
  updatedAt?: string;
  error?: string;
};

export type WriteOpts = {
  /** Authenticated user id; fetched when omitted. */
  userId?: string;
  /** `updated_at` as of our last read/write. Omitted/null ⇒ unconditional
   *  (but still user-scoped) write — used by callers with no witness. */
  witness?: string | null;
};

async function casUpdate(
  id: string, fields: Record<string, any>, opts: WriteOpts = {},
): Promise<WriteResult> {
  try {
    const uid = opts.userId ?? (await getUserId());
    const stamp = new Date().toISOString();
    let q = supabase
      .from('meetings')
      .update({ ...fields, updated_at: stamp })
      .eq('id', id)
      .eq('user_id', uid);          // never a blind row-id write (IDI-175 §4)
    if (opts.witness) q = q.eq('updated_at', opts.witness);
    const { data, error } = await q.select('updated_at');
    if (error) return { ok: false, error: error.message };
    // A conditional UPDATE that matched nothing isn't an error — zero rows IS
    // the conflict signal.
    if (!data || data.length === 0) {
      return opts.witness ? { ok: false, conflict: true } : { ok: false, error: 'no matching row' };
    }
    return { ok: true, updatedAt: stamp };
  } catch (e: any) {
    return { ok: false, error: e?.message ? String(e.message) : String(e) };
  }
}

/** Scratchpad edits (the original mobile write). */
export function updateScratchpadRemote(
  id: string, text: string, opts: WriteOpts = {},
): Promise<WriteResult> {
  return casUpdate(id, { scratchpad: text }, opts);
}

/** Persist mobile-generated / hand-edited AI notes so desktop sees them too. */
export function updateNotesRemote(
  id: string, notesMd: string, opts: WriteOpts = {},
): Promise<WriteResult> {
  return casUpdate(id, { notes_md: notesMd }, opts);
}

/** Action-item checkboxes from mobile. Writes the FULL loaded list (never a
 *  partial reconstruction — the load-then-patch rule). */
export function updateActionItemsRemote(
  id: string, items: MeetingActionItem[], opts: WriteOpts = {},
): Promise<WriteResult> {
  return casUpdate(id, { action_items: items }, opts);
}

/** A live meeting whose last update is older than this is treated as stale
 *  (desktop crashed mid-meeting and never cleared `live`). */
export const LIVE_STALE_MS = 90_000;

export function isLiveNow(m: Meeting): boolean {
  if (!m.live) return false;
  const age = Date.now() - new Date(m.updatedAt).getTime();
  return age >= 0 ? age < LIVE_STALE_MS : true;
}

/* ── realtime: ONE multiplexed channel ───────────────────────────────────── */
/**
 * Every consumer used to call this and get its OWN `supabase.channel(...)` on
 * the SAME topic (`verbal_meetings_${userId}`). supabase-js keys channels by
 * topic, so the four `useMeetings()` instances plus MeetingLiveScreen were
 * fighting over one socket subscription and any one unmount's removeChannel()
 * killed everybody's updates (IDI-175 §1).
 *
 * Now this module owns exactly one channel and fans events out to N listeners.
 * The channel is created on the first listener and torn down after the last.
 * A dropped connection rejoins itself with backoff (historyStore's scheme).
 */
export type MeetingsEvent = { eventType: 'INSERT' | 'UPDATE'; row: any };
type Listener = (ev?: MeetingsEvent) => void;

const listeners = new Set<Listener>();
let channel: ReturnType<typeof supabase.channel> | null = null;
let channelUserId: string | null = null;
let rejoinTimer: ReturnType<typeof setTimeout> | null = null;
let rejoinAttempts = 0;

function emit(ev: MeetingsEvent) {
  listeners.forEach((l) => { try { l(ev); } catch { /* one bad listener can't break the rest */ } });
}

function cancelRejoin() {
  if (rejoinTimer) { clearTimeout(rejoinTimer); rejoinTimer = null; }
}

/** Close the channel WITHOUT dropping listeners (they survive a rejoin). */
export async function closeMeetingsChannel(): Promise<void> {
  const ch = channel;
  channel = null;
  channelUserId = null;
  cancelRejoin();
  if (!ch) return;
  try { await supabase.removeChannel(ch); } catch { /* ignore */ }
}

function scheduleRejoin(userId: string) {
  if (rejoinTimer) return;
  const delay = Math.min(30_000, 1_000 * 2 ** rejoinAttempts);
  rejoinAttempts += 1;
  rejoinTimer = setTimeout(() => {
    rejoinTimer = null;
    if (listeners.size === 0) return;          // nobody left to serve
    joinChannel(userId).catch(() => { /* the next status error retries */ });
  }, delay);
}

async function joinChannel(userId: string): Promise<void> {
  if (channel && channelUserId === userId) return;
  await closeMeetingsChannel();
  channelUserId = userId;

  // THE one and only `verbal_meetings_` channel creation site in the app.
  const ch = supabase
    .channel(`verbal_meetings_${userId}`)
    .on('postgres_changes',
      { event: 'INSERT', schema: 'public', table: 'meetings', filter: `user_id=eq.${userId}` },
      (payload: any) => emit({ eventType: 'INSERT', row: payload.new }))
    .on('postgres_changes',
      { event: 'UPDATE', schema: 'public', table: 'meetings', filter: `user_id=eq.${userId}` },
      (payload: any) => emit({ eventType: 'UPDATE', row: payload.new }));
  channel = ch;
  ch.subscribe((status: string) => {
    if (status === 'SUBSCRIBED') { rejoinAttempts = 0; return; }
    if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT' || status === 'CLOSED') {
      if (channel !== ch) return;              // superseded, or an intentional teardown
      scheduleRejoin(userId);
    }
  });
}

/**
 * Realtime: desktop finishes a meeting → it appears here within seconds.
 * Returns an unsubscribe. Safe to call from many places — they share a channel.
 */
export function subscribeMeetings(userId: string, onChange: Listener): () => void {
  listeners.add(onChange);
  joinChannel(userId).catch(() => { /* best effort; rejoin covers it */ });
  return () => {
    listeners.delete(onChange);
    if (listeners.size === 0) closeMeetingsChannel().catch(() => {});
  };
}

/** Foreground catch-up: make sure the (possibly silently dead) channel is joined. */
export async function rejoinMeetingsChannel(userId: string): Promise<void> {
  if (listeners.size === 0) return;
  cancelRejoin();
  rejoinAttempts = 0;
  await closeMeetingsChannel();
  await joinChannel(userId);
}
