/**
 * Meetings — Supabase adapter (mobile is READ-ONLY except the scratchpad).
 *
 * Mirrors the desktop data shapes (whisperflow/app/meetings.py::row()):
 * the `meetings` table row with jsonb transcript/speakers/decisions/
 * action_items/marked_moments/hybrid_notes. Scoped by getUserId() like every
 * other cloud read (lib/storage.ts — authoritative from the live session).
 */
import { supabase } from './supabase';
import { getUserId } from './storage';
import type {
  Meeting, MeetingUtterance, MeetingActionItem, MeetingMoment,
  MeetingHybridNote, MeetingStatus,
} from '../flume-ui/hooks/useMeetings.mock';

export type {
  Meeting, MeetingUtterance, MeetingActionItem, MeetingMoment,
  MeetingHybridNote, MeetingStatus,
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
    live: !!row.live,
    updatedAt: row.updated_at || row.started_at || new Date().toISOString(),
    dateLabel: dateLabel(row.started_at),
  };
}

export async function fetchMeetings(limit = 50): Promise<Meeting[]> {
  try {
    const userId = await getUserId();
    const { data, error } = await supabase
      .from('meetings')
      .select('*')
      .eq('user_id', userId)
      .order('started_at', { ascending: false })
      .limit(limit);
    if (error || !data) return [];
    return data.map(toMeeting);
  } catch {
    return [];
  }
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

/** The one mobile write: scratchpad edits (last-write-wins on updated_at). */
export async function updateScratchpadRemote(id: string, text: string): Promise<boolean> {
  try {
    const { error } = await supabase
      .from('meetings')
      .update({ scratchpad: text, updated_at: new Date().toISOString() })
      .eq('id', id);
    return !error;
  } catch {
    return false;
  }
}

/** A live meeting whose last update is older than this is treated as stale
 *  (desktop crashed mid-meeting and never cleared `live`). */
export const LIVE_STALE_MS = 90_000;

export function isLiveNow(m: Meeting): boolean {
  if (!m.live) return false;
  const age = Date.now() - new Date(m.updatedAt).getTime();
  return age >= 0 ? age < LIVE_STALE_MS : true;
}

/** Persist mobile-generated AI notes so desktop sees them too. */
export async function updateNotesRemote(id: string, notesMd: string): Promise<boolean> {
  try {
    const { error } = await supabase
      .from('meetings')
      .update({ notes_md: notesMd, updated_at: new Date().toISOString() })
      .eq('id', id);
    return !error;
  } catch {
    return false;
  }
}

/** Action-item checkboxes from mobile. Writes the FULL loaded list (never a
 *  partial reconstruction — the load-then-patch rule). */
export async function updateActionItemsRemote(
  id: string, items: MeetingActionItem[],
): Promise<boolean> {
  try {
    const { error } = await supabase
      .from('meetings')
      .update({ action_items: items, updated_at: new Date().toISOString() })
      .eq('id', id);
    return !error;
  } catch {
    return false;
  }
}

/** Realtime: desktop finishes a meeting → it appears here within seconds. */
export function subscribeMeetings(userId: string, onChange: () => void) {
  const channel = supabase
    .channel(`verbal_meetings_${userId}`)
    .on('postgres_changes',
      { event: 'INSERT', schema: 'public', table: 'meetings', filter: `user_id=eq.${userId}` },
      () => onChange())
    .on('postgres_changes',
      { event: 'UPDATE', schema: 'public', table: 'meetings', filter: `user_id=eq.${userId}` },
      () => onChange())
    .subscribe();
  return () => { supabase.removeChannel(channel).catch(() => {}); };
}
