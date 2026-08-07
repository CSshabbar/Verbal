/**
 * useMeetings — READ-ONLY view of meetings captured on the desktop app
 * (MEETINGS_DESIGN_HANDOFF.md; mobile cannot start/pause/regenerate).
 * The ONE mobile write: editing the user scratchpad, which syncs back.
 *
 * This mock is the design contract — useMeetings.ts must export the exact
 * same shape.
 *
 * The TYPES themselves now live in `lib/meetings.ts` (IDI-175 §6): lib/ needs
 * them and lib/ may never import flume-ui/, so the definition moved down and
 * this file re-exports it. The contract is unchanged — only its home is.
 */
import { useState, useCallback } from 'react';

export type {
  Meeting, MeetingUtterance, MeetingActionItem, MeetingMoment,
  MeetingHybridNote, MeetingStatus,
} from '../../lib/meetings';
import type { Meeting } from '../../lib/meetings';

const MOCK: Meeting[] = [
  {
    id: 'm1',
    title: 'Design review — Meetings feature',
    startedAt: new Date(Date.now() - 3 * 3600_000).toISOString(),
    durationSeconds: 42 * 60 + 18,
    audioUrl: null,
    audioExpired: false,
    transcript: [
      { speaker: 's1', t0: 4, t1: 12, text: 'Walking through the two-panel view first.' },
      { speaker: 'self', t0: 14, t1: 22, text: 'The scratchpad should feel like my own notes, not a transcript.' },
      { speaker: 's1', t0: 24, t1: 40, text: 'Agreed — and the hybrid summary merges both afterward.' },
    ],
    speakers: { self: 'You', s1: 'Sarah' },
    scratchpad: 'two-panel: transcript + my notes\nhybrid summary is the payoff',
    summary: 'Reviewed the Meetings two-panel design; agreed the hybrid post-meeting summary is the core payoff.',
    decisions: ['Ship the two-panel layout', 'Hybrid notes render user text first'],
    actionItems: [
      { owner: 's1', task: 'Send the updated wireframes', done: false },
      { owner: 'self', task: 'Prototype the hybrid renderer', done: false },
    ],
    markedMoments: [{ t: 25, label: 'Hybrid summary decision' }],
    hybridNotes: [
      { user_line: 'two-panel: transcript + my notes', ai_addition: 'Sarah confirmed the layout ships as designed.' },
      { user_line: 'hybrid summary is the payoff', ai_addition: '' },
    ],
    deviceName: 'MacBook Pro',
    status: 'ready',
    notesMd: null,
    pinned: false,
    recognized: {},
    live: false,
    updatedAt: new Date().toISOString(),
    dateLabel: 'Today · 9:24 AM',
  },
  {
    id: 'm2',
    title: 'Client kickoff',
    startedAt: new Date(Date.now() - 26 * 3600_000).toISOString(),
    durationSeconds: 31 * 60,
    audioUrl: null,
    audioExpired: false,
    transcript: [],
    speakers: { self: 'You', s1: 'Speaker 1' },
    scratchpad: '',
    summary: '',
    decisions: [],
    actionItems: [],
    markedMoments: [],
    hybridNotes: [],
    deviceName: 'MacBook Pro',
    status: 'processing',
    notesMd: null,
    pinned: false,
    recognized: {},
    live: false,
    updatedAt: new Date().toISOString(),
    dateLabel: 'Yesterday',
  },
];

export function useMeetings() {
  const [meetings, setMeetings] = useState<Meeting[]>(MOCK);
  const [loading] = useState(false);

  const getMeeting = useCallback(
    (id: string) => meetings.find(m => m.id === id) ?? null,
    [meetings],
  );

  const refresh = useCallback(async () => {}, []);

  /** The one mobile write — scratchpad edits sync back to the desktop. */
  const updateScratchpad = useCallback((id: string, text: string) => {
    setMeetings(prev => prev.map(m => (m.id === id ? { ...m, scratchpad: text } : m)));
  }, []);

  /** Manual notes_md edits — mock is local-only, same shape as the real hook. */
  const updateNotes = useCallback((id: string, text: string) => {
    setMeetings(prev => prev.map(m => (m.id === id ? { ...m, notesMd: text } : m)));
  }, []);

  /** Action-item checkboxes — mock is local-only. */
  const updateActionItems = useCallback((id: string, items: Meeting['actionItems']) => {
    setMeetings(prev => prev.map(m => (m.id === id ? { ...m, actionItems: items } : m)));
  }, []);

  const noop = useCallback(async () => {}, []);

  // Sync-state contract (IDI-175): the real store surfaces a failed refresh,
  // queued/failed writes and cross-device conflicts. The mock is always happy.
  return {
    meetings, loading, error: null as string | null,
    unsaved: {} as Record<string, boolean>,
    conflicts: {} as Record<string, boolean>,
    getMeeting, refresh, updateScratchpad, updateNotes, updateActionItems,
    flushNow: noop,
    reloadMeeting: useCallback(async (id: string) => meetings.find(m => m.id === id) ?? null, [meetings]),
    clearConflict: useCallback((_id: string) => {}, []),
    setNotesNow: useCallback(async (id: string, md: string) => {
      setMeetings(prev => prev.map(m => (m.id === id ? { ...m, notesMd: md } : m)));
      return true;
    }, []),
  };
}
