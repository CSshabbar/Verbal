/**
 * notesSearch — full-text search over notes (Notes v2, Feature 1).
 *
 * Ranking mirrors the desktop DashboardApi.search_notes:
 *   • case-insensitive substring across title + content
 *   • title matches rank ABOVE content-only matches
 *   • recency (updatedAt, newest first) is the tiebreak
 *
 * Perf (Design Decision 9): a plain linear scan handles the 1,000-note target
 * well under the ~100 ms budget — for 1k notes this is a few string ops per note
 * (single-digit ms), so no prebuilt index is needed. If a library ever grows far
 * past that, build a lowercased index once and pass it in; the ranking here is
 * pure and does not depend on how the fields were produced.
 */

/** Minimum shape searchNotes needs. The UI `Note` type satisfies this. */
export interface SearchableNote {
  id: string;
  title: string;
  body: string;
  updatedAt: number;
}

// Title hit outranks a content-only hit regardless of recency.
const RANK_TITLE = 2;
const RANK_BODY = 1;

/**
 * Filter + rank notes for `query`. An empty/whitespace query returns the notes
 * sorted by recency (no filtering) so the caller can use it as the default list.
 */
export function searchNotes<T extends SearchableNote>(notes: T[], query: string): T[] {
  const q = (query ?? '').trim().toLowerCase();
  if (!q) {
    return [...notes].sort((a, b) => b.updatedAt - a.updatedAt);
  }
  const scored: { note: T; rank: number }[] = [];
  for (const note of notes) {
    const inTitle = (note.title || '').toLowerCase().includes(q);
    const inBody = !inTitle && (note.body || '').toLowerCase().includes(q);
    if (inTitle) scored.push({ note, rank: RANK_TITLE });
    else if (inBody) scored.push({ note, rank: RANK_BODY });
  }
  scored.sort((a, b) => (b.rank - a.rank) || (b.note.updatedAt - a.note.updatedAt));
  return scored.map(s => s.note);
}
