import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'verbal_notes_cache';

// ── Notes v2 sync contract (mirrors whisperflow/app/shared_dashboard.py) ──────
// Two devices that edited the same note within this window are a conflict pair:
// BOTH versions are kept (never silently discarded) and both are flagged so the
// editor can show a one-time "resolve" prompt.
export const NOTES_CONFLICT_WINDOW_MS = 60_000;

export interface AudioSegment {
  id:         string;
  url:        string;
  created_at: string;
}

export interface NoteEntry {
  id:            string;
  title:         string;
  content:       string;
  raw_content?:  string | null;      // raw transcript; null/absent for typed/old notes
  audio_segments?: AudioSegment[];   // append-only, UNION-on-merge
  folder:        string;
  is_pinned:     boolean;
  device_name:   string;
  created_at:    string;
  updated_at:    string;
  source:        'local' | 'remote';
  conflict?:     boolean;            // true on BOTH members of a conflict pair
  conflict_of?:  string | null;      // set on the conflict copy -> canonical note id
  deleted_at?:   string | null;      // tombstone (IDI-158) — deletion is authoritative
  // Forward-compat: unknown fields from newer clients are preserved verbatim.
  [key: string]: any;
}

// Fields this client understands. Anything else is preserved untouched on merge.
const KNOWN_FIELDS = new Set([
  'id', 'title', 'content', 'raw_content', 'audio_segments', 'folder',
  'is_pinned', 'device_name', 'created_at', 'updated_at', 'source',
  'conflict', 'conflict_of', 'deleted_at',
]);

export async function getCachedNotes(): Promise<NoteEntry[]> {
  const raw = await AsyncStorage.getItem(KEY);
  if (!raw) return [];
  try { return JSON.parse(raw); } catch { return []; }
}

async function saveNotes(notes: NoteEntry[]): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify(notes.slice(0, 200)));
}

function ts(s?: string): number {
  const t = s ? Date.parse(s) : NaN;
  return Number.isNaN(t) ? 0 : t;
}

export function unionAudioSegments(
  a?: AudioSegment[] | null, b?: AudioSegment[] | null,
): AudioSegment[] {
  const out: AudioSegment[] = [];
  const seen = new Set<string>();
  for (const seg of [...(a ?? []), ...(b ?? [])]) {
    if (!seg || typeof seg !== 'object') continue;
    const sid = seg.id || seg.url;
    if (!sid || seen.has(sid)) continue;
    seen.add(sid);
    out.push(seg);
  }
  out.sort((x, y) => (x.created_at || '').localeCompare(y.created_at || ''));
  return out;
}

function isConflict(a: NoteEntry, b: NoteEntry): boolean {
  const ta = ts(a.updated_at), tb = ts(b.updated_at);
  if (!ta || !tb) return false;
  if (Math.abs(ta - tb) > NOTES_CONFLICT_WINDOW_MS) return false;
  return (
    (a.content || '') !== (b.content || '') ||
    (a.title || '') !== (b.title || '') ||
    (a.raw_content || '') !== (b.raw_content || '')
  );
}

/**
 * Merge one remote note into the local cache, applying the v2 contract:
 *   • audio_segments UNION on every merge (append-only, never lost)
 *   • unknown fields preserved verbatim from both sides (forward-compat)
 *   • conflict pair: local & remote edited within NOTES_CONFLICT_WINDOW_MS and
 *     diverge -> keep BOTH. Newer keeps the canonical id (conflict=true,
 *     conflict_of=null); older stored under a deterministic id
 *     `<id>::conflict::<updated_at>` (conflict=true, conflict_of=<id>).
 *   • otherwise last-write-wins on known fields, unknowns unioned.
 */
export async function mergeRemoteNote(note: NoteEntry): Promise<NoteEntry[]> {
  const notes = await getCachedNotes();
  const cand: NoteEntry = { ...note, source: 'remote' };

  // Tombstone wins unconditionally (IDI-158): a remote deleted_at removes the
  // local copy AND its local-only ::conflict:: derivatives — no LWW comparison,
  // so an offline edit can never resurrect a note deleted elsewhere.
  if (cand.deleted_at) {
    const kept = notes.filter(
      n => n.id !== cand.id && n.conflict_of !== cand.id
        && !n.id.startsWith(`${cand.id}::conflict::`),
    );
    if (kept.length !== notes.length) await saveNotes(kept);
    return kept;
  }

  const idx = notes.findIndex(n => n.id === cand.id);

  if (idx < 0) {
    notes.unshift(cand);
  } else {
    const ex = notes[idx];
    const mergedSegments = unionAudioSegments(ex.audio_segments, cand.audio_segments);

    if (isConflict(ex, cand)) {
      const candNewer = ts(cand.updated_at) >= ts(ex.updated_at);
      const newer = candNewer ? cand : ex;
      const older = candNewer ? ex : cand;

      const winner: NoteEntry = { ...older, ...newer };  // newer's fields win, older's unknowns kept
      winner.audio_segments = mergedSegments;
      winner.conflict = true;
      winner.conflict_of = null;
      notes[idx] = winner;

      const copyId = `${cand.id}::conflict::${older.updated_at || ''}`;
      if (!notes.some(n => n.id === copyId)) {
        notes.push({
          ...older,
          id: copyId,
          conflict: true,
          conflict_of: cand.id,
          audio_segments: unionAudioSegments(older.audio_segments, []),
        });
      }
    } else {
      const candNewer = ts(cand.updated_at) >= ts(ex.updated_at);
      let base: NoteEntry;
      if (candNewer) {
        base = { ...ex, ...cand };            // remote newer: its values + unknowns win
      } else {
        base = { ...ex };                     // local newer: keep local...
        for (const k of Object.keys(cand)) {  // ...add only keys local lacks
          if (!(k in base)) base[k] = cand[k];
        }
      }
      base.audio_segments = mergedSegments;
      notes[idx] = base;
    }
  }

  const sorted = notes.sort((a, b) => ts(b.updated_at) - ts(a.updated_at));
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
  id: string, changes: Partial<NoteEntry>,
): Promise<NoteEntry[]> {
  const notes = await getCachedNotes();
  const updated = notes.map(n => {
    if (n.id !== id) return n;
    const next: NoteEntry = { ...n, ...changes };  // spread preserves unknown fields
    // audio_segments is append-only: UNION rather than overwrite.
    if (changes.audio_segments !== undefined) {
      next.audio_segments = unionAudioSegments(n.audio_segments, changes.audio_segments);
    }
    return next;
  });
  await saveNotes(updated);
  return updated;
}

export async function removeCachedNote(id: string): Promise<NoteEntry[]> {
  const notes = await getCachedNotes();
  // Removing a canonical note also removes its local-only ::conflict:: copies —
  // orphaned conflict artifacts would otherwise linger (and confuse the UI) forever.
  const updated = notes.filter(
    n => n.id !== id && n.conflict_of !== id && !n.id.startsWith(`${id}::conflict::`),
  );
  await saveNotes(updated);
  return updated;
}

/** Fields a write-back must always carry so newer columns survive an old-client save. */
export function preserveUnknownFields(note: NoteEntry): Record<string, any> {
  const extra: Record<string, any> = {};
  for (const k of Object.keys(note)) {
    if (!KNOWN_FIELDS.has(k)) extra[k] = note[k];
  }
  return extra;
}
