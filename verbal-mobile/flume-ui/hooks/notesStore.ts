/**
 * notesStore — the ONE notes store (IDI-176 §8).
 *
 * `useNotes()` used to hold the whole thing in per-instance React state: every
 * mounted copy ran its own `load()` exactly once, nothing was exported to
 * re-run it, and there was no realtime subscription at all — so a note written
 * on the desktop (or on this account's other phone) only appeared after an app
 * relaunch, and the list and the editor could disagree about what exists.
 *
 * Now it is module state + subscribe/getSnapshot (historyStore's shape) with the
 * wave-1 lifecycle: one channel (`verbal_notes_${userId}`) that rejoins itself
 * with backoff, gated by lib/syncStore, `catchUp()` for the foreground pass and
 * `reset()` for sign-out.
 *
 * Remote rows always land through `mergeRemoteNote`, which owns the v2 contract
 * (tombstones win, audio_segments union, conflict pairs) — this file never
 * reimplements any of it.
 *
 * Self-write suppression: our own write comes back as a realtime UPDATE. If the
 * user has typed again since, that echo is an OLDER version with DIFFERENT
 * content inside the 60 s window — i.e. mergeRemoteNote would have split our own
 * note into a bogus conflict pair. So every `updated_at` we stamp is remembered
 * and its echo dropped.
 */
import { supabase } from '../../lib/supabase';
import {
  getCachedNotes, addCachedNote, updateCachedNote, removeCachedNote,
  mergeRemoteNote, unionAudioSegments, NoteEntry, AudioSegment,
} from '../../lib/notesStorage';
import {
  getUserId, getDeviceName, getNotesFeatureFlags, DEFAULT_NOTES_FLAGS,
} from '../../lib/storage';
import * as syncStore from '../../lib/syncStore';
import { formatNoteWithTitle } from '../../lib/groq';
import * as recordings from '../../lib/recordings';

export type Note = {
  id: string;
  title: string;
  body: string;
  preview: string;
  dateLabel: string;       // "Today · 9:24 AM" | "Yesterday" | "Mon · 2:08 PM"
  isVoice: boolean;
  isPinned: boolean;       // Notes v3 — synced `is_pinned` column
  createdAt: number;
  updatedAt: number;
  // Notes v2 (see NOTES_ENHANCEMENT_SWARM.md). Absent/null on pre-existing notes.
  rawContent?: string | null;      // raw transcript behind an AI-formatted note
  audioSegments?: AudioSegment[];  // append-only source recordings
  conflict?: boolean;              // member of an unresolved conflict pair
  conflictOf?: string | null;      // set on the conflict copy -> canonical note id
  formatFailed?: boolean;          // cleanup timed out/errored -> show "Retry formatting"
  formatting?: boolean;            // transient: an AI cleanup call is in flight
};

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}
function timeOfDay(d: Date) {
  let h = d.getHours();
  const m = d.getMinutes();
  const ampm = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  return `${h}:${String(m).padStart(2, '0')} ${ampm}`;
}
export function dateLabelFor(ms: number): string {
  const d = new Date(ms);
  const now = new Date();
  const diff = Math.round((startOfDay(now) - startOfDay(d)) / 86_400_000);
  if (diff <= 0) return `Today · ${timeOfDay(d)}`;
  if (diff === 1) return 'Yesterday';
  if (diff < 7) return `${DAYS[d.getDay()]} · ${timeOfDay(d)}`;
  return `${DAYS[d.getDay()]}`;
}

function toNote(entry: NoteEntry, isVoice = false): Note {
  const createdAt = Date.parse(entry.created_at) || Date.now();
  const updatedAt = Date.parse(entry.updated_at) || createdAt;
  return {
    id: entry.id,
    title: entry.title,
    body: entry.content,
    preview: (entry.content || '').slice(0, 140),
    dateLabel: dateLabelFor(updatedAt),
    isVoice: isVoice || !!entry.raw_content || (entry.audio_segments?.length ?? 0) > 0,
    isPinned: !!entry.is_pinned,
    createdAt,
    updatedAt,
    rawContent: entry.raw_content ?? null,
    audioSegments: entry.audio_segments ?? [],
    conflict: entry.conflict ?? false,
    conflictOf: entry.conflict_of ?? null,
    formatFailed: !!entry.format_failed,
    formatting: false,
  };
}

function toEntry(note: Note, deviceName: string): NoteEntry {
  // Only known/UI-owned fields. raw_content & audio_segments are intentionally
  // omitted so updateCachedNote's spread preserves whatever the cache already
  // holds (append-only union) rather than clobbering it.
  return {
    id: note.id,
    title: note.title,
    content: note.body,
    folder: '',
    // Carry the REAL pin — a hard-coded false here used to clobber a pin set on
    // another device the moment this device saved a typed edit (Notes v3).
    is_pinned: !!note.isPinned,
    device_name: deviceName,
    created_at: new Date(note.createdAt).toISOString(),
    updated_at: new Date(note.updatedAt).toISOString(),
    source: 'local',
  };
}

/** One cloud-row → NoteEntry mapping shared by the fetch and the realtime
 *  handler, so neither can drop a column the other keeps. */
function rowToEntry(row: any): NoteEntry {
  return {
    // Spread the whole row first so raw_content, audio_segments, and any
    // newer-client columns are preserved verbatim (forward-compat).
    ...row,
    id: row.id,
    title: row.title || '',
    content: row.content || '',
    raw_content: row.raw_content ?? null,
    audio_segments: Array.isArray(row.audio_segments) ? row.audio_segments : [],
    folder: row.folder || '',
    is_pinned: row.is_pinned || false,
    device_name: row.device_name || '',
    created_at: row.created_at,
    updated_at: row.updated_at,
    source: 'remote' as const,
  };
}

/** Persist + upload one recording and return its audio_segments entry. */
async function persistAudioSegment(recordingUri: string): Promise<AudioSegment | null> {
  try {
    const segId = `seg_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    const userId = await getUserId();
    // Local backup (survives temp-cache eviction) + cloud copy for cross-device
    // playback. Fall back to whatever we have so a failed upload never drops the
    // linkage entirely.
    const local = (await recordings.persist(recordingUri, segId)) ?? recordingUri;
    const url = await recordings.uploadCloud(local, userId, segId);
    return { id: segId, url: url ?? local, created_at: new Date().toISOString() };
  } catch (err) {
    console.warn('persistAudioSegment failed:', err);
    return null;
  }
}

/* ── module state ────────────────────────────────────────────────────────── */

let notes: Note[] = [];
const listeners = new Set<() => void>();
/** `${id}|${updated_at}` values WE stamped — their realtime echo is dropped. */
const selfWrites = new Set<string>();

function emit() { listeners.forEach((l) => { try { l(); } catch { /* ignore */ } }); }
function publish(entries: NoteEntry[]) {
  notes = entries.filter((e) => !e.deleted_at).map((e) => toNote(e));
  emit();
}

export function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function getSnapshot(): Note[] { return notes; }

function patchNoteState(id: string, partial: Partial<Note>) {
  notes = notes.map((n) => (n.id === id ? { ...n, ...partial } : n));
  emit();
}

/** Remember a stamp we wrote so its own echo can be ignored. */
function markSelfWrite(id: string, updatedAtIso: string) {
  selfWrites.add(`${id}|${updatedAtIso}`);
  // Bounded: this only ever holds the recent tail of our own writes.
  if (selfWrites.size > 200) {
    const first = selfWrites.values().next().value;
    if (first) selfWrites.delete(first);
  }
}

/* ── load / back-fill ────────────────────────────────────────────────────── */

async function load(): Promise<void> {
  try {
    const userId = await getUserId();
    const { data, error } = await supabase
      .from('notes')
      .select('*')
      .eq('user_id', userId)
      .order('updated_at', { ascending: false })
      .limit(200);

    const remoteIds = new Set<string>();
    if (!error && data && data.length > 0) {
      const entries: NoteEntry[] = data.map(rowToEntry);
      for (const e of entries) { remoteIds.add(e.id); await mergeRemoteNote(e); }
    }
    const cached = await getCachedNotes();

    // Back-fill: push locally-cached notes that NEVER reached the cloud (created
    // before the `notes` table existed, or while signed out). Upsert on the
    // note's OWN id so local id === cloud id (no duplicates).
    //
    // Scoped hard (IDI-158): only `source === 'local'` entries qualify — an
    // entry that ever merged from (or pushed to) the cloud is 'remote', and
    // re-uploading one whose cloud row is gone RESURRECTS a deleted note on
    // every other device. Conflict copies (local-only artifacts) and anything
    // tombstoned never uploads either.
    if (!error && (await syncStore.getSyncEnabled())) {
      const deviceName = await getDeviceName();
      for (const e of cached) {
        if (remoteIds.has(e.id)) continue;
        if (e.source !== 'local') continue;               // was cloud-backed once — don't resurrect
        if (e.id.includes('::conflict::') || e.conflict_of) continue;
        if (e.deleted_at) continue;
        try {
          await supabase.from('notes').upsert({
            id: e.id,
            user_id: userId,
            title: e.title || '',
            content: e.content || '',
            raw_content: e.raw_content ?? null,
            audio_segments: e.audio_segments ?? [],
            folder: e.folder || '',
            is_pinned: e.is_pinned || false,
            device_name: deviceName,
            created_at: e.created_at,
            updated_at: e.updated_at,
          }, { onConflict: 'id' });
          if (e.updated_at) markSelfWrite(e.id, e.updated_at);
          // Now cloud-backed: flip the marker so a later cloud delete of this
          // note is honored instead of back-filled again.
          await updateCachedNote(e.id, { source: 'remote' });
        } catch (pushErr) {
          console.warn('Note back-fill push failed:', pushErr);
        }
      }
    }
    publish(await getCachedNotes());
  } catch (err) {
    console.error('Failed to load notes:', err);
    publish(await getCachedNotes());
  }
  try {
    if (await syncStore.getSyncEnabled()) await subscribeRealtime();
    else await closeChannel();
  } catch { /* realtime is best-effort */ }
}

let inFlight: Promise<void> | null = null;
let loadPromise: Promise<void> | null = null;
let started = false;

/** Coalesce concurrent loads — two screens mounting in the same tick, the sync
 *  toggle and a foreground catch-up can all land together. */
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
/** Exported refresh — pull-to-refresh, catch-up, post-resolve re-read. */
export function reload(): Promise<void> { return runLoad(); }

/* ── channel lifecycle ───────────────────────────────────────────────────── */

let channel: ReturnType<typeof supabase.channel> | null = null;
let rejoinTimer: ReturnType<typeof setTimeout> | null = null;
let rejoinAttempts = 0;

function cancelRejoin() {
  if (rejoinTimer) { clearTimeout(rejoinTimer); rejoinTimer = null; }
}

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

async function onRemoteRow(row: any) {
  if (!row?.id) return;
  const key = `${row.id}|${row.updated_at}`;
  if (selfWrites.has(key)) { selfWrites.delete(key); return; }   // our own echo
  publish(await mergeRemoteNote(rowToEntry(row)));
}

async function subscribeRealtime() {
  const userId = await getUserId();
  if (!userId) return;
  await closeChannel();

  const ch = supabase
    .channel(`verbal_notes_${userId}`)
    .on('postgres_changes',
      { event: 'INSERT', schema: 'public', table: 'notes', filter: `user_id=eq.${userId}` },
      (payload: any) => { onRemoteRow(payload.new).catch(() => {}); })
    .on('postgres_changes',
      // Covers deletes: a note delete is a tombstoning UPDATE (IDI-158), and
      // mergeRemoteNote prunes the local copy (and its ::conflict:: copies).
      { event: 'UPDATE', schema: 'public', table: 'notes', filter: `user_id=eq.${userId}` },
      (payload: any) => { onRemoteRow(payload.new).catch(() => {}); });
  channel = ch;
  ch.subscribe((status: string) => {
    if (status === 'SUBSCRIBED') { rejoinAttempts = 0; return; }
    if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT' || status === 'CLOSED') {
      if (channel !== ch) return;   // superseded, or an intentional teardown
      scheduleRejoin();
    }
  });
}

/** Sync toggled OFF: stop remote IO, keep the local notes on screen. */
export async function disconnect(): Promise<void> {
  await closeChannel();
}

/** Foreground catch-up (AppState 'active'): re-pull + make sure we're joined. */
export async function catchUp(): Promise<void> {
  if (!(await syncStore.getSyncEnabled())) return;
  await reload();
}

/**
 * Sign-out / account switch: drop the cached notes and the channel (keyed by the
 * OLD user id) so the next account starts clean.
 * NOTE for the useAuth owner — this needs calling next to historyStore.reset().
 */
export async function reset(): Promise<void> {
  notes = [];
  started = false;
  loadPromise = null;
  inFlight = null;
  rejoinAttempts = 0;
  selfWrites.clear();
  await closeChannel();
  emit();
}

// The toggle is live (IDI-171): ON re-pulls + joins, OFF closes the channel.
syncStore.onChange((enabled) => {
  if (enabled) reload().catch(() => {});
  else disconnect().catch(() => {});
});

/* ── CRUD ────────────────────────────────────────────────────────────────── */

export function createNote(data: Partial<Note>): Note {
  const now = Date.now();
  const note: Note = {
    id: `note_${now}`,
    title: data.title ?? '',
    body: data.body ?? '',
    preview: (data.body ?? '').slice(0, 140),
    dateLabel: dateLabelFor(now),
    isVoice: data.isVoice ?? false,
    isPinned: false,
    createdAt: now,
    updatedAt: now,
  };
  notes = [note, ...notes];
  emit();
  (async () => {
    try {
      const userId = await getUserId();
      const deviceName = await getDeviceName();
      await addCachedNote(toEntry(note, deviceName));
      // Upsert WITH the note's own id so the cloud row shares the local id —
      // otherwise the server mints a UUID we never learn, and every later
      // .update().eq('id', localId) matches zero rows (edits silently lost) and
      // the pulled-back UUID row shows up as a duplicate. Gated on sync so the
      // row always carries the authenticated user_id, never the local fallback.
      if (await syncStore.getSyncEnabled()) {
        const iso = new Date(note.updatedAt).toISOString();
        await supabase.from('notes').upsert({
          id: note.id,
          user_id: userId,
          title: note.title,
          content: note.body,
          folder: '',
          device_name: deviceName,
          created_at: new Date(note.createdAt).toISOString(),
          updated_at: iso,
        }, { onConflict: 'id' });
        markSelfWrite(note.id, iso);
      }
    } catch (err) {
      console.error('Failed to persist new note:', err);
    }
  })();
  return note;
}

/**
 * Apply a patch to one note.
 *
 * The old version did `if (!updated) return;` — so if `load()` had replaced
 * state between the optimistic `createNote` insert and this call (the editor
 * autosaves immediately), EVERY edit to that note was silently dropped and the
 * user was typing into a note nobody would ever persist. Now a miss falls back
 * to the AsyncStorage cache, and failing that to the caller's patch, and the
 * note is re-inserted into the store (IDI-176 §7).
 */
export function updateNote(id: string, patch: Partial<Note>): void {
  const now = Date.now();
  let updated: Note | undefined;
  notes = notes.map((n) => {
    if (n.id !== id) return n;
    updated = {
      ...n, ...patch,
      preview: (patch.body ?? n.body).slice(0, 140),
      updatedAt: now,
      dateLabel: dateLabelFor(now),
    };
    return updated;
  });
  if (updated) emit();

  (async () => {
    try {
      const cached = await getCachedNotes();
      const existing = cached.find((n) => n.id === id);
      let target = updated;
      if (!target) {
        const base: Note = existing
          ? toNote(existing)
          : {
              id, title: '', body: '', preview: '', dateLabel: dateLabelFor(now),
              isVoice: false, isPinned: false, createdAt: now, updatedAt: now,
            };
        target = {
          ...base, ...patch,
          preview: (patch.body ?? base.body).slice(0, 140),
          updatedAt: now,
          dateLabel: dateLabelFor(now),
        };
        notes = [target, ...notes.filter((n) => n.id !== id)];
        emit();
      }

      const deviceName = await getDeviceName();
      const entry = toEntry(target, deviceName);
      if (existing) await updateCachedNote(id, entry);
      else await addCachedNote(entry);

      // Gated like createNote (wave-1 decision: the Sync toggle gates notes).
      if (!(await syncStore.getSyncEnabled())) return;
      const iso = new Date(target.updatedAt).toISOString();
      const userId = await getUserId();
      const { data } = await supabase
        .from('notes')
        .update({ title: target.title, content: target.body, updated_at: iso })
        .eq('id', id)
        .eq('user_id', userId)
        .select('id');
      if (!data || data.length === 0) {
        // No cloud row yet (created while signed out / before the table existed).
        await supabase.from('notes').upsert({
          id, user_id: userId, title: target.title, content: target.body,
          folder: '', device_name: deviceName,
          created_at: new Date(target.createdAt).toISOString(), updated_at: iso,
        }, { onConflict: 'id' });
      }
      markSelfWrite(id, iso);
    } catch (err) {
      console.error('Failed to update note:', err);
    }
  })();
}

// Deletion = TOMBSTONE, not a hard DELETE (IDI-158). The row stays with
// deleted_at set and content cleared, so every other device's merge removes
// its copy and nothing (incl. our own back-fill) can resurrect it.
async function tombstoneRemote(ids: string[]) {
  const cloudIds = ids.filter((id) => !id.includes('::conflict::')); // conflict copies are local-only
  if (cloudIds.length === 0) return;
  if (!(await syncStore.getSyncEnabled())) return;
  const nowIso = new Date().toISOString();
  await supabase
    .from('notes')
    .update({
      deleted_at: nowIso, updated_at: nowIso,
      title: '', content: '', raw_content: null, audio_segments: [],
    })
    .in('id', cloudIds);
  for (const id of cloudIds) markSelfWrite(id, nowIso);
}

export function removeNote(id: string): void {
  notes = notes.filter((n) => n.id !== id && n.conflictOf !== id);
  emit();
  (async () => {
    try {
      await removeCachedNote(id);
      await tombstoneRemote([id]);
    } catch (err) {
      console.error('Failed to remove note:', err);
    }
  })();
}

/** Batch delete (multi-select). One cloud round-trip via .in(), local cache
 *  cleared per id. Best-effort — local removal always applies. */
export function removeNotes(ids: string[]): void {
  if (ids.length === 0) return;
  const idSet = new Set(ids);
  notes = notes.filter((n) => !idSet.has(n.id) && !idSet.has(n.conflictOf ?? ''));
  emit();
  (async () => {
    try {
      for (const id of ids) await removeCachedNote(id);
      await tombstoneRemote(ids);
    } catch (err) {
      console.error('Failed to remove notes:', err);
    }
  })();
}

/** Persist changes to cache + Supabase, refresh store state, return the Note. */
async function commitEntryChanges(
  id: string, existing: NoteEntry, changes: Partial<NoteEntry>, remoteFields: Record<string, any>,
): Promise<Note> {
  await updateCachedNote(id, changes);
  try {
    if (await syncStore.getSyncEnabled()) {
      await supabase.from('notes').update(remoteFields).eq('id', id);
      if (typeof remoteFields.updated_at === 'string') markSelfWrite(id, remoteFields.updated_at);
    }
  } catch (err) {
    console.error('commitEntryChanges: supabase update failed:', err);
  }
  const mergedNote = toNote({ ...existing, ...changes }, true);
  notes = notes.map((n) => (n.id === id ? mergedNote : n));
  emit();
  return mergedNote;
}

/**
 * saveDictation — the voice save path (prerequisite + Features 2/3/4).
 * Runs AI cleanup ONCE per dictated segment (Design Decision 2), storing BOTH
 * raw transcript and formatted content (Decision 1):
 *   • first dictation on the note  → clean the full raw text, auto-title if the
 *     title is still empty (never overwrites a manual title).
 *   • appended dictation           → clean ONLY the new segment and append it.
 * Audio is persisted + uploaded and unioned into audio_segments (Feature 4).
 * On cleanup timeout/error the raw text is saved and `formatFailed` is set so
 * the UI can offer "Retry formatting". Typed edits go through updateNote and
 * never trigger cleanup.
 */
export async function saveDictation(
  id: string, opts: { rawText: string; recordingUri?: string },
): Promise<Note | null> {
  const rawText = (opts.rawText || '').trim();
  const cached = await getCachedNotes();
  const existing = cached.find((n) => n.id === id);
  if (!existing) return null;

  const f = await getNotesFeatureFlags().catch(() => DEFAULT_NOTES_FLAGS);
  const isFirst = !existing.raw_content;

  // Audio linkage (gated).
  let newSegment: AudioSegment | null = null;
  if (f.audio && opts.recordingUri) newSegment = await persistAudioSegment(opts.recordingUri);

  // AI cleanup (gated behaviors within one call). Auth is the proxy's job —
  // formatNoteWithTitle fails closed (ok:false → raw text) on any error.
  patchNoteState(id, { formatting: true });
  const titleIsEmpty = !(existing.title || '').trim();
  const wantTitle = f.autotitle && isFirst && titleIsEmpty;
  const result = rawText
    ? await formatNoteWithTitle(rawText, undefined, {
        timeoutMs: 8000,
        detectStructure: f.structure,
        withTitle: wantTitle,
      })
    : { ok: false, title: null, content: rawText };

  const formattedSeg = result.content || rawText;
  const content = isFirst
    ? formattedSeg
    : (existing.content || '') + (existing.content ? '\n\n' : '') + formattedSeg;
  const raw_content = isFirst
    ? rawText
    : (existing.raw_content || '') + (existing.raw_content ? '\n\n' : '') + rawText;
  const title = wantTitle && result.ok && result.title ? result.title : (existing.title || '');
  const audio_segments = newSegment
    ? unionAudioSegments(existing.audio_segments, [newSegment])
    : (existing.audio_segments ?? []);
  const nowIso = new Date().toISOString();

  const changes: Partial<NoteEntry> = {
    title, content, raw_content, audio_segments,
    format_failed: !result.ok, updated_at: nowIso,
  };
  return commitEntryChanges(id, existing, changes, {
    title, content, raw_content, audio_segments, updated_at: nowIso,
  });
}

/**
 * reformatNote — explicit "Reformat" / "Retry formatting" (Design Decision 2 +
 * Decision 6). Re-runs cleanup on the raw transcript (or the body if the note
 * never had one). Only fills the title when it is still empty — never
 * overwrites a manually-set title.
 */
export async function reformatNote(
  id: string, style: 'structured' | 'prose' | 'transcript' = 'structured',
): Promise<Note | null> {
  const cached = await getCachedNotes();
  const existing = cached.find((n) => n.id === id);
  if (!existing) return null;
  const source = (existing.raw_content && existing.raw_content.trim())
    ? existing.raw_content
    : existing.content;
  if (!source || !source.trim()) return null;

  const f = await getNotesFeatureFlags().catch(() => DEFAULT_NOTES_FLAGS);
  const titleIsEmpty = !(existing.title || '').trim();
  patchNoteState(id, { formatting: true });
  const result = await formatNoteWithTitle(source, undefined, {
    timeoutMs: 8000,
    detectStructure: f.structure,
    withTitle: f.autotitle && titleIsEmpty,
    style,
  });

  const content = result.content || source;
  const title = f.autotitle && titleIsEmpty && result.ok && result.title
    ? result.title
    : (existing.title || '');
  const raw_content = existing.raw_content ?? source; // preserve "show original"
  const nowIso = new Date().toISOString();

  const changes: Partial<NoteEntry> = {
    title, content, raw_content, format_failed: !result.ok, updated_at: nowIso,
  };
  return commitEntryChanges(id, existing, changes, {
    title, content, raw_content, updated_at: nowIso,
  });
}

/**
 * setPinned — pin/unpin a note (Notes v3). Deliberately does NOT bump
 * updated_at: pinning is a preference, not an edit, so it must not reorder the
 * recency-sorted list or mint a conflict pair (desktop set_note_pinned agrees).
 * Cloud write is best-effort; local state applies immediately.
 */
export async function setPinned(id: string, pinned: boolean): Promise<void> {
  patchNoteState(id, { isPinned: pinned });
  try {
    await updateCachedNote(id, { is_pinned: pinned });
    if (await syncStore.getSyncEnabled()) {
      const userId = await getUserId();
      await supabase.from('notes').update({ is_pinned: pinned })
        .eq('id', id).eq('user_id', userId);
    }
  } catch (err) {
    console.error('setPinned failed:', err);
  }
}

/**
 * updateRawContent — persist an edited ORIGINAL transcript (Notes v3, the
 * Cleft edit-then-regenerate pattern). Never triggers cleanup — pair it with
 * reformatNote when the user explicitly asks.
 */
export async function updateRawContent(id: string, raw: string): Promise<Note | null> {
  const cached = await getCachedNotes();
  const existing = cached.find((n) => n.id === id);
  if (!existing) return null;
  const nowIso = new Date().toISOString();
  const changes: Partial<NoteEntry> = { raw_content: raw, updated_at: nowIso };
  return commitEntryChanges(id, existing, changes, { raw_content: raw, updated_at: nowIso });
}

/**
 * addAudioSegment — attach a recording to a note without re-running cleanup
 * (Feature 4). No-op (returns the note unchanged) when audio linkage is off.
 */
export async function addAudioSegment(id: string, recordingUri: string): Promise<Note | null> {
  const f = await getNotesFeatureFlags().catch(() => DEFAULT_NOTES_FLAGS);
  const cached = await getCachedNotes();
  const existing = cached.find((n) => n.id === id);
  if (!existing) return null;
  if (!f.audio) return toNote(existing);
  const seg = await persistAudioSegment(recordingUri);
  if (!seg) return toNote(existing);
  const audio_segments = unionAudioSegments(existing.audio_segments, [seg]);
  const nowIso = new Date().toISOString();
  const changes: Partial<NoteEntry> = { audio_segments, updated_at: nowIso };
  return commitEntryChanges(id, existing, changes, { audio_segments, updated_at: nowIso });
}

/* ── conflict pairs (IDI-176 §9) ─────────────────────────────────────────── */

/**
 * Resolve a conflict pair created by `mergeRemoteNote`.
 *
 * `canonicalId` is ALWAYS the surviving note's id (the copy lives at
 * `<canonicalId>::conflict::<updated_at>` and carries `conflict_of`), so the
 * caller can pass either member's identity through it:
 *   keep 'canonical' → discard the copy, clear the flags, push the canonical
 *   keep 'copy'      → the copy's content is written ONTO the canonical id, then
 *                      the copy is deleted. The canonical id is what the cloud
 *                      and every other device know, so promoting means copying
 *                      content across, never renaming a row.
 *
 * `conflict` / `conflict_of` are LOCAL-only markers (the copy is never uploaded
 * — see the back-fill guard), so resolution clears them in the cache and pushes
 * only real content.
 */
export async function resolveConflict(
  canonicalId: string, keep: 'canonical' | 'copy',
): Promise<Note | null> {
  const cached = await getCachedNotes();
  const canonical = cached.find((n) => n.id === canonicalId);
  if (!canonical) return null;
  const copy = cached.find(
    (n) => n.conflict_of === canonicalId || n.id.startsWith(`${canonicalId}::conflict::`),
  );
  const winner = keep === 'copy' && copy ? copy : canonical;
  const nowIso = new Date().toISOString();

  const changes: Partial<NoteEntry> = {
    title: winner.title,
    content: winner.content,
    raw_content: winner.raw_content ?? null,
    audio_segments: unionAudioSegments(canonical.audio_segments, copy?.audio_segments),
    conflict: false,
    conflict_of: null,
    updated_at: nowIso,
  };
  await updateCachedNote(canonicalId, changes);
  if (copy) await removeCachedNote(copy.id);

  try {
    if (await syncStore.getSyncEnabled()) {
      const userId = await getUserId();
      await supabase.from('notes').update({
        title: changes.title, content: changes.content,
        raw_content: changes.raw_content, updated_at: nowIso,
      }).eq('id', canonicalId).eq('user_id', userId);
      markSelfWrite(canonicalId, nowIso);
    }
  } catch (err) {
    console.warn('resolveConflict push failed:', err);
  }

  publish(await getCachedNotes());
  return notes.find((n) => n.id === canonicalId) ?? null;
}
