/**
 * useNotes — notes list + CRUD with auto-save.
 * Backed by the local notes cache (`lib/notesStorage`) + Supabase `notes` sync.
 *
 * Contract (consumed by NotesListScreen / NoteEditorScreen):
 *   { notes, getNote, createNote, updateNote, removeNote }
 *
 * NOTE: `isVoice` is not persisted by the storage layer yet, so it survives in
 * memory for the session but resets to false on reload. Add an `is_voice`
 * column to persist it.
 */
import { useState, useCallback, useEffect } from 'react';
import { supabase } from '../../lib/supabase';
import {
  getCachedNotes,
  addCachedNote,
  updateCachedNote,
  removeCachedNote,
  mergeRemoteNote,
  unionAudioSegments,
  NoteEntry,
  AudioSegment,
} from '../../lib/notesStorage';
import {
  getUserId,
  getDeviceName,
  getGroqKey,
  getNotesFeatureFlags,
  DEFAULT_NOTES_FLAGS,
  NotesFeatureFlags,
} from '../../lib/storage';
import { formatNoteWithTitle } from '../../lib/groq';
import * as recordings from '../../lib/recordings';

export type Note = {
  id: string;
  title: string;
  body: string;
  preview: string;
  dateLabel: string;       // "Today · 9:24 AM" | "Yesterday" | "Mon · 2:08 PM"
  isVoice: boolean;
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

function dateLabelFor(ms: number): string {
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
    is_pinned: false,
    device_name: deviceName,
    created_at: new Date(note.createdAt).toISOString(),
    updated_at: new Date(note.updatedAt).toISOString(),
    source: 'local',
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

export function useNotes() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [flags, setFlags] = useState<NotesFeatureFlags>(DEFAULT_NOTES_FLAGS);

  useEffect(() => {
    getNotesFeatureFlags().then(setFlags).catch(() => setFlags(DEFAULT_NOTES_FLAGS));
  }, []);

  const reloadFlags = useCallback(async () => {
    const f = await getNotesFeatureFlags().catch(() => DEFAULT_NOTES_FLAGS);
    setFlags(f);
    return f;
  }, []);

  // Merge a partial into one note in local state (used for transient flags like
  // `formatting` and to reflect a completed dictation without a full reload).
  const patchNoteState = useCallback((id: string, partial: Partial<Note>) => {
    setNotes(prev => prev.map(n => (n.id === id ? { ...n, ...partial } : n)));
  }, []);

  const load = useCallback(async () => {
    try {
      const userId = await getUserId();
      const { data, error } = await supabase
        .from('notes')
        .select('*')
        .eq('user_id', userId)
        .order('updated_at', { ascending: false })
        .limit(200);

      if (!error && data && data.length > 0) {
        const entries: NoteEntry[] = data.map((row: any) => ({
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
        }));
        for (const e of entries) await mergeRemoteNote(e);
      }
      const cached = await getCachedNotes();
      setNotes(cached.map(e => toNote(e)));
    } catch (err) {
      console.error('Failed to load notes:', err);
      const cached = await getCachedNotes();
      setNotes(cached.map(e => toNote(e)));
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const getNote = useCallback(
    (id: string) => notes.find(n => n.id === id) ?? null,
    [notes],
  );

  const createNote = useCallback((data: Partial<Note>): Note => {
    const now = Date.now();
    const note: Note = {
      id: `note_${now}`,
      title: data.title ?? '',
      body: data.body ?? '',
      preview: (data.body ?? '').slice(0, 140),
      dateLabel: dateLabelFor(now),
      isVoice: data.isVoice ?? false,
      createdAt: now,
      updatedAt: now,
    };
    setNotes(prev => [note, ...prev]);
    (async () => {
      try {
        const userId = await getUserId();
        const deviceName = await getDeviceName();
        await addCachedNote(toEntry(note, deviceName));
        await supabase.from('notes').insert({
          user_id: userId,
          title: note.title,
          content: note.body,
          folder: '',
          device_name: deviceName,
        });
      } catch (err) {
        console.error('Failed to persist new note:', err);
      }
    })();
    return note;
  }, []);

  const updateNote = useCallback((id: string, patch: Partial<Note>) => {
    let updated: Note | undefined;
    setNotes(prev => {
      const next = prev.map(n => {
        if (n.id !== id) return n;
        updated = {
          ...n,
          ...patch,
          preview: (patch.body ?? n.body).slice(0, 140),
          updatedAt: Date.now(),
          dateLabel: dateLabelFor(Date.now()),
        };
        return updated;
      });
      return next;
    });
    if (!updated) return;
    (async () => {
      try {
        const deviceName = await getDeviceName();
        await updateCachedNote(updated!.id, toEntry(updated!, deviceName));
        await supabase
          .from('notes')
          .update({
            title: updated!.title,
            content: updated!.body,
            updated_at: new Date(updated!.updatedAt).toISOString(),
          })
          .eq('id', id);
      } catch (err) {
        console.error('Failed to update note:', err);
      }
    })();
  }, []);

  const removeNote = useCallback((id: string) => {
    setNotes(prev => prev.filter(n => n.id !== id));
    (async () => {
      try {
        await removeCachedNote(id);
        await supabase.from('notes').delete().eq('id', id);
      } catch (err) {
        console.error('Failed to remove note:', err);
      }
    })();
  }, []);

  // Persist changes to cache + Supabase, refresh local state, return the Note.
  const commitEntryChanges = useCallback(
    async (id: string, existing: NoteEntry, changes: Partial<NoteEntry>, remoteFields: Record<string, any>) => {
      await updateCachedNote(id, changes);
      try {
        await supabase.from('notes').update(remoteFields).eq('id', id);
      } catch (err) {
        console.error('commitEntryChanges: supabase update failed:', err);
      }
      const mergedNote = toNote({ ...existing, ...changes }, true);
      setNotes(prev => prev.map(n => (n.id === id ? mergedNote : n)));
      return mergedNote;
    },
    [],
  );

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
  const saveDictation = useCallback(
    async (id: string, opts: { rawText: string; recordingUri?: string }): Promise<Note | null> => {
      const rawText = (opts.rawText || '').trim();
      const cached = await getCachedNotes();
      const existing = cached.find(n => n.id === id);
      if (!existing) return null;

      const f = await getNotesFeatureFlags().catch(() => flags);
      const isFirst = !existing.raw_content;

      // Audio linkage (gated).
      let newSegment: AudioSegment | null = null;
      if (f.audio && opts.recordingUri) newSegment = await persistAudioSegment(opts.recordingUri);

      // AI cleanup (gated behaviors within one call).
      patchNoteState(id, { formatting: true });
      const apiKey = await getGroqKey();
      const titleIsEmpty = !(existing.title || '').trim();
      const wantTitle = f.autotitle && isFirst && titleIsEmpty;
      const result = rawText && apiKey
        ? await formatNoteWithTitle(rawText, apiKey, {
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
    },
    [flags, patchNoteState, commitEntryChanges],
  );

  /**
   * reformatNote — explicit "Reformat" / "Retry formatting" (Design Decision 2 +
   * Decision 6). Re-runs cleanup on the raw transcript (or the body if the note
   * never had one). Only fills the title when it is still empty — never
   * overwrites a manually-set title.
   */
  const reformatNote = useCallback(
    async (id: string): Promise<Note | null> => {
      const cached = await getCachedNotes();
      const existing = cached.find(n => n.id === id);
      if (!existing) return null;
      const source = (existing.raw_content && existing.raw_content.trim())
        ? existing.raw_content
        : existing.content;
      if (!source || !source.trim()) return null;

      const f = await getNotesFeatureFlags().catch(() => flags);
      const apiKey = await getGroqKey();
      const titleIsEmpty = !(existing.title || '').trim();
      patchNoteState(id, { formatting: true });
      const result = apiKey
        ? await formatNoteWithTitle(source, apiKey, {
            timeoutMs: 8000,
            detectStructure: f.structure,
            withTitle: f.autotitle && titleIsEmpty,
          })
        : { ok: false, title: null, content: source };

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
    },
    [flags, patchNoteState, commitEntryChanges],
  );

  /**
   * addAudioSegment — attach a recording to a note without re-running cleanup
   * (Feature 4). No-op (returns the note unchanged) when audio linkage is off.
   */
  const addAudioSegment = useCallback(
    async (id: string, recordingUri: string): Promise<Note | null> => {
      const f = await getNotesFeatureFlags().catch(() => flags);
      const cached = await getCachedNotes();
      const existing = cached.find(n => n.id === id);
      if (!existing) return null;
      if (!f.audio) return toNote(existing);
      const seg = await persistAudioSegment(recordingUri);
      if (!seg) return toNote(existing);
      const audio_segments = unionAudioSegments(existing.audio_segments, [seg]);
      const nowIso = new Date().toISOString();
      const changes: Partial<NoteEntry> = { audio_segments, updated_at: nowIso };
      return commitEntryChanges(id, existing, changes, { audio_segments, updated_at: nowIso });
    },
    [flags, commitEntryChanges],
  );

  return {
    notes,
    flags,
    reloadFlags,
    getNote,
    createNote,
    updateNote,
    removeNote,
    saveDictation,
    reformatNote,
    addAudioSegment,
  };
}
