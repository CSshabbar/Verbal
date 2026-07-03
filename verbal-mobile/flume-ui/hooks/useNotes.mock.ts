/**
 * useNotes — notes list + CRUD with auto-save.
 * Wire to your persistent store.
 */
import { useState, useCallback } from 'react';

export type Note = {
  id: string;
  title: string;
  body: string;
  preview: string;          // first 140 chars stripped
  dateLabel: string;        // "Today · 9:24 AM" | "Yesterday" | "Mon · 2:08 PM"
  isVoice: boolean;
  createdAt: number;
  updatedAt: number;
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

  const updateNote = useCallback((id: string, patch: Partial<Note>) => {
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

  const removeNote = useCallback((id: string) => {
    setNotes(prev => prev.filter(n => n.id !== id));
  }, []);

  return { notes, getNote, createNote, updateNote, removeNote };
}
