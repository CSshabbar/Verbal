import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'verbal_notes_cache';

export interface NoteEntry {
  id:           string;
  title:        string;
  content:      string;
  folder:       string;
  is_pinned:    boolean;
  device_name:  string;
  created_at:   string;
  updated_at:   string;
  source:       'local' | 'remote';
}

export async function getCachedNotes(): Promise<NoteEntry[]> {
  const raw = await AsyncStorage.getItem(KEY);
  if (!raw) return [];
  try { return JSON.parse(raw); } catch { return []; }
}

async function saveNotes(notes: NoteEntry[]): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify(notes.slice(0, 200)));
}

export async function mergeRemoteNote(note: NoteEntry): Promise<NoteEntry[]> {
  const notes = await getCachedNotes();
  const idx = notes.findIndex(n => n.id === note.id);
  const entry = { ...note, source: 'remote' as const };
  if (idx >= 0) {
    notes[idx] = entry;
  } else {
    notes.unshift(entry);
  }
  const sorted = notes.sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  );
  await saveNotes(sorted);
  return sorted;
}

export async function addCachedNote(note: NoteEntry): Promise<NoteEntry[]> {
  const notes = await getCachedNotes();
  notes.unshift({ ...note, source: 'local' as const });
  await saveNotes(notes);
  return notes;
}

export async function updateCachedNote(
  id: string, changes: Partial<NoteEntry>
): Promise<NoteEntry[]> {
  const notes = await getCachedNotes();
  const updated = notes.map(n => n.id === id ? { ...n, ...changes } : n);
  await saveNotes(updated);
  return updated;
}

export async function removeCachedNote(id: string): Promise<NoteEntry[]> {
  const notes = await getCachedNotes();
  const updated = notes.filter(n => n.id !== id);
  await saveNotes(updated);
  return updated;
}
