/**
 * useNotes — thin wrapper over the shared `notesStore` (IDI-176 §8).
 *
 * All the notes state, persistence and realtime lives in ./notesStore; this is
 * the React face of it, so the list screen and the editor are guaranteed to be
 * looking at the same notes.
 *
 * Contract (consumed by NotesListScreen / NoteEditorScreen):
 *   { notes, flags, reloadFlags, reload, getNote, createNote, updateNote,
 *     removeNote, removeNotes, saveDictation, reformatNote, setPinned,
 *     updateRawContent, addAudioSegment, resolveConflict }
 *
 * NOTE: `isVoice` is DERIVED, not stored — a note counts as voice when it has a
 * raw transcript or at least one audio segment (both of which do persist), so it
 * survives a reload. `Note.isVoice` passed to createNote is the only in-memory
 * part, and it is only ever set for a note that is about to receive dictation.
 */
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import * as store from './notesStore';
import {
  getNotesFeatureFlags, DEFAULT_NOTES_FLAGS, NotesFeatureFlags,
} from '../../lib/storage';

export type { Note } from './notesStore';

export function useNotes() {
  const notes = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const [flags, setFlags] = useState<NotesFeatureFlags>(DEFAULT_NOTES_FLAGS);

  useEffect(() => {
    store.ensureLoaded();
    getNotesFeatureFlags().then(setFlags).catch(() => setFlags(DEFAULT_NOTES_FLAGS));
  }, []);

  /** Re-read the Settings toggles (call on screen focus — see NotesListScreen). */
  const reloadFlags = useCallback(async () => {
    const f = await getNotesFeatureFlags().catch(() => DEFAULT_NOTES_FLAGS);
    setFlags(f);
    return f;
  }, []);

  const getNote = useCallback(
    (id: string) => notes.find((n) => n.id === id) ?? null,
    [notes],
  );

  return {
    notes,
    flags,
    reloadFlags,
    reload: store.reload,
    getNote,
    createNote: store.createNote,
    updateNote: store.updateNote,
    removeNote: store.removeNote,
    removeNotes: store.removeNotes,
    saveDictation: store.saveDictation,
    reformatNote: store.reformatNote,
    setPinned: store.setPinned,
    updateRawContent: store.updateRawContent,
    addAudioSegment: store.addAudioSegment,
    resolveConflict: store.resolveConflict,
  };
}
