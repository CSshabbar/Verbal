/**
 * useNotes — MOCK (contract reference, never imported at runtime).
 * Same exported shape as ./useNotes, backed by in-memory state.
 *
 * The real hook is a thin wrapper over the shared `notesStore` (IDI-176 §8), so
 * the list screen and the editor look at the same notes. `NotesFeatureFlags`
 * comes from `lib/storage` in both — lib owns the Settings toggles and flume-ui
 * may not redefine them.
 *
 * NOTE: `isVoice` is DERIVED in the real store (raw transcript OR ≥1 audio
 * segment), not stored; the mock mirrors that rule in createNote/saveDictation.
 */
import { useState, useCallback } from 'react';
import { DEFAULT_NOTES_FLAGS, NotesFeatureFlags } from '../../lib/storage';
import type { AudioSegment } from '../../lib/notesStorage';

export type Note = {
  id: string;
  title: string;
  body: string;
  preview: string;          // first 140 chars stripped
  dateLabel: string;        // "Today · 9:24 AM" | "Yesterday" | "Mon · 2:08 PM"
  isVoice: boolean;
  createdAt: number;
  updatedAt: number;
  // Notes v2 (NOTES_ENHANCEMENT_SWARM.md). Absent/null on pre-existing notes.
  rawContent?: string | null;      // raw transcript behind an AI-formatted note
  audioSegments?: AudioSegment[];  // append-only source recordings
  conflict?: boolean;              // member of an unresolved conflict pair
  conflictOf?: string | null;      // set on the conflict copy -> canonical note id
  formatFailed?: boolean;          // cleanup timed out/errored -> show "Retry formatting"
  formatting?: boolean;            // transient: an AI cleanup call is in flight
};

const MOCK: Note[] = [
  {
    id: 'n1',
    title: 'Sprint review notes',
    body: 'Things to bring up: onboarding regression…',
    preview: 'Things to bring up: the onboarding regression, design review timing, and whether we ship behind a flag…',
    dateLabel: 'Today · 9:24 AM',
    isVoice: true,
    createdAt: Date.now() - 60_000,
    updatedAt: Date.now() - 60_000,
    rawContent: 'things to bring up the onboarding regression design review timing',
    audioSegments: [{ id: 'seg1', url: 'file:///mock/note_seg_1.m4a', created_at: new Date().toISOString() }],
  },
  {
    id: 'n2',
    title: 'Ideas — Lisbon trip',
    body: 'Belém pastries, Time Out market…',
    preview: 'Belém pastries, Time Out market, tram 28 early morning before crowds…',
    dateLabel: 'Yesterday',
    isVoice: false,
    createdAt: Date.now() - 86_400_000,
    updatedAt: Date.now() - 86_400_000,
  },
  {
    id: 'n3',
    title: 'Client call follow-up',
    body: 'They want a revised quote by Friday…',
    preview: 'They want a revised quote by Friday. Three deliverables: copy, hi-fi mocks, and a deck for the board…',
    dateLabel: 'Mon · 2:08 PM',
    isVoice: true,
    createdAt: Date.now() - 4 * 86_400_000,
    updatedAt: Date.now() - 4 * 86_400_000,
    rawContent: 'they want a revised quote by friday',
    formatFailed: true,      // the "Retry formatting" state
  },
  {
    id: 'n4',
    title: 'Grocery list',
    body: 'Eggs, oat milk, bread, garlic, lemons, parmesan…',
    preview: 'Eggs, oat milk, bread, garlic, lemons, parmesan…',
    dateLabel: 'Mon',
    isVoice: false,
    createdAt: Date.now() - 4 * 86_400_000,
    updatedAt: Date.now() - 4 * 86_400_000,
  },
];

export function useNotes() {
  const [notes, setNotes] = useState<Note[]>(MOCK);
  const [flags, setFlags] = useState<NotesFeatureFlags>(DEFAULT_NOTES_FLAGS);

  /** Re-read the Settings toggles (call on screen focus — see NotesListScreen). */
  const reloadFlags = useCallback(async (): Promise<NotesFeatureFlags> => {
    setFlags(DEFAULT_NOTES_FLAGS);
    return DEFAULT_NOTES_FLAGS;
  }, []);

  /** Re-run the cache/cloud load. No-op here. */
  const reload = useCallback(async (): Promise<void> => {}, []);

  const getNote = useCallback(
    (id: string) => notes.find(n => n.id === id) ?? null,
    [notes],
  );

  const createNote = useCallback((data: Partial<Note>): Note => {
    const now = Date.now();
    const note: Note = {
      id: `n_${now}`,
      title: data.title ?? '',
      body: data.body ?? '',
      preview: (data.body ?? '').slice(0, 140),
      dateLabel: 'Just now',
      isVoice: data.isVoice ?? false,
      createdAt: now,
      updatedAt: now,
    };
    setNotes(prev => [note, ...prev]);
    return note;
  }, []);

  const updateNote = useCallback((id: string, patch: Partial<Note>): void => {
    setNotes(prev => prev.map(n =>
      n.id === id
        ? {
            ...n,
            ...patch,
            preview: (patch.body ?? n.body).slice(0, 140),
            updatedAt: Date.now(),
          }
        : n
    ));
  }, []);

  const removeNote = useCallback((id: string): void => {
    setNotes(prev => prev.filter(n => n.id !== id));
  }, []);

  /** Multi-select delete from the list screen. */
  const removeNotes = useCallback((ids: string[]): void => {
    const kill = new Set(ids);
    setNotes(prev => prev.filter(n => !kill.has(n.id)));
  }, []);

  /**
   * The voice save path: first dictation cleans the whole raw text (+ auto-title
   * when the title is still empty), an appended one cleans only the new segment.
   * The mock skips the LLM and just appends.
   */
  const saveDictation = useCallback(
    async (id: string, opts: { rawText: string; recordingUri?: string }): Promise<Note | null> => {
      const raw = (opts.rawText || '').trim();
      let out: Note | null = null;
      setNotes(prev => prev.map(n => {
        if (n.id !== id) return n;
        const isFirst = !n.rawContent;
        const body = isFirst ? raw : `${n.body}${n.body ? '\n\n' : ''}${raw}`;
        const segments = opts.recordingUri
          ? [...(n.audioSegments ?? []),
             { id: `seg_${Date.now()}`, url: opts.recordingUri, created_at: new Date().toISOString() }]
          : n.audioSegments;
        out = {
          ...n,
          title: n.title || (isFirst ? raw.slice(0, 40) : ''),
          body,
          preview: body.slice(0, 140),
          rawContent: isFirst ? raw : `${n.rawContent}\n\n${raw}`,
          audioSegments: segments,
          isVoice: true,
          formatFailed: false,
          formatting: false,
          updatedAt: Date.now(),
        };
        return out;
      }));
      return out;
    },
    [],
  );

  /** Explicit "Reformat" / "Retry formatting" over the stored raw transcript. */
  const reformatNote = useCallback(async (id: string): Promise<Note | null> => {
    let out: Note | null = null;
    setNotes(prev => prev.map(n => {
      if (n.id !== id) return n;
      const source = (n.rawContent && n.rawContent.trim()) ? n.rawContent : n.body;
      if (!source.trim()) return n;
      out = { ...n, body: source, preview: source.slice(0, 140),
              formatFailed: false, formatting: false, updatedAt: Date.now() };
      return out;
    }));
    return out;
  }, []);

  /** Attach a recording without re-running cleanup (no-op when audio is off). */
  const addAudioSegment = useCallback(
    async (id: string, recordingUri: string): Promise<Note | null> => {
      let out: Note | null = null;
      setNotes(prev => prev.map(n => {
        if (n.id !== id) return n;
        if (!flags.audio) { out = n; return n; }
        out = {
          ...n,
          audioSegments: [...(n.audioSegments ?? []),
            { id: `seg_${Date.now()}`, url: recordingUri, created_at: new Date().toISOString() }],
          isVoice: true,
          updatedAt: Date.now(),
        };
        return out;
      }));
      return out;
    },
    [flags.audio],
  );

  /**
   * Resolve a conflict pair. `canonicalId` is ALWAYS the surviving note's id —
   * keeping the copy writes its content ONTO that id and drops the copy, because
   * the canonical id is what the cloud and every other device know.
   */
  const resolveConflict = useCallback(
    async (canonicalId: string, keep: 'canonical' | 'copy'): Promise<Note | null> => {
      let out: Note | null = null;
      setNotes(prev => {
        const canonical = prev.find(n => n.id === canonicalId);
        if (!canonical) return prev;
        const copy = prev.find(
          n => n.conflictOf === canonicalId || n.id.startsWith(`${canonicalId}::conflict::`));
        const winner = keep === 'copy' && copy ? copy : canonical;
        out = {
          ...canonical,
          title: winner.title,
          body: winner.body,
          preview: winner.body.slice(0, 140),
          rawContent: winner.rawContent ?? null,
          conflict: false,
          conflictOf: null,
          updatedAt: Date.now(),
        };
        return prev
          .filter(n => !copy || n.id !== copy.id)
          .map(n => (n.id === canonicalId ? out! : n));
      });
      return out;
    },
    [],
  );

  return {
    notes,
    flags,
    reloadFlags,
    reload,
    getNote,
    createNote,
    updateNote,
    removeNote,
    removeNotes,
    saveDictation,
    reformatNote,
    addAudioSegment,
    resolveConflict,
  };
}
