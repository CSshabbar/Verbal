/**
 * useMeetings — READ-ONLY view of meetings captured on the desktop app
 * (MEETINGS_DESIGN_HANDOFF.md; mobile cannot start/pause/regenerate).
 * The ONE mobile write: editing the user scratchpad, which syncs back.
 *
 * This mock is the design contract — useMeetings.ts must export the exact
 * same shape.
 */
import { useState, useCallback } from 'react';

export type MeetingUtterance = { speaker: string; t0: number; t1: number; text: string };
export type MeetingActionItem = { owner: string | null; task: string; done: boolean; due?: string | null; edited?: boolean };
export type MeetingMoment = { t: number; label: string; note?: string };
export type MeetingHybridNote = { user_line: string; ai_addition: string };
export type MeetingStatus = 'processing' | 'ready' | 'failed';

export type Meeting = {
  id: string;
  title: string;
  startedAt: string;              // ISO
  durationSeconds: number;
  audioUrl: string | null;
  transcript: MeetingUtterance[];
  speakers: Record<string, string>;   // speaker id → display name ('self' = You)
  scratchpad: string;
  summary: string;
  decisions: string[];
  actionItems: MeetingActionItem[];
  markedMoments: MeetingMoment[];
  hybridNotes: MeetingHybridNote[];
  deviceName: string | null;
  status: MeetingStatus;
  notesMd: string | null;             // full AI meeting notes (markdown; lazy on desktop)
  pinned: boolean;
  recognized: Record<string, { name: string; meetings: number }>;  // voiceprint hits
  live: boolean;                  // currently being captured on another device
  updatedAt: string;
  dateLabel: string;              // "Today · 9:24 AM" | "Yesterday" | "Mon · 2:08 PM"
};

const MOCK: Meeting[] = [
  {
    id: 'm1',
    title: 'Design review — Meetings feature',
    startedAt: new Date(Date.now() - 3 * 3600_000).toISOString(),
    durationSeconds: 42 * 60 + 18,
    audioUrl: null,
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

  return { meetings, loading, getMeeting, refresh, updateScratchpad };
}
