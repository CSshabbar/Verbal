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
  NoteEntry,
} from '../../lib/notesStorage';
import { getUserId, getDeviceName } from '../../lib/storage';

export type Note = {
  id: string;
  title: string;
  body: string;
  preview: string;
  dateLabel: string;       // "Today · 9:24 AM" | "Yesterday" | "Mon · 2:08 PM"
  isVoice: boolean;
  createdAt: number;
  updatedAt: number;
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
    isVoice,
    createdAt,
    updatedAt,
  };
}

function toEntry(note: Note, deviceName: string): NoteEntry {
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

export function useNotes() {
  const [notes, setNotes] = useState<Note[]>([]);

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
          id: row.id,
          title: row.title || '',
          content: row.content || '',
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

  return { notes, getNote, createNote, updateNote, removeNote };
}
