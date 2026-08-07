/**
 * useHistory — MOCK (contract reference, never imported at runtime).
 * Same exported shape as ./useHistory, backed by in-memory state.
 *
 * The real hook is a thin wrapper over the shared `historyStore` (one module
 * store, one realtime channel), so its returned functions are the store's — not
 * per-instance closures. Two mounted copies of this mock do NOT share state; the
 * shape is what the contract pins.
 */
import { useState } from 'react';

export type HistoryItem = {
  id: string;
  text: string;
  deviceTag: string;            // "MacBook", "Work PC", "Local"
  dayLabel: string;             // "Today" | "Yesterday" | "Monday" | "Jun 24"
  timeOfDay: string;            // "9:24 AM"
  relativeTime: string;         // "12 min ago"
  durationLabel: string;        // "14s"
  wordCount: number;
  /** Local file path of the saved audio (playback + retry cache). */
  audioUri?: string;
  /** Cloud object path/URL of the same audio, when sync uploaded it. */
  audioUrl?: string;
  /** True when either of the above exists — drives the play/retry affordances. */
  hasAudio?: boolean;
  /** 'failed' = transcription errored but the audio was kept: History shows Retry. */
  status?: 'done' | 'failed';
};

const MOCK: HistoryItem[] = [
  {
    id: 'h1',
    text: "Let's reschedule the design review to Thursday afternoon and pull in marketing for the second half.",
    deviceTag: 'MacBook',
    dayLabel: 'Today',
    timeOfDay: '9:24 AM',
    relativeTime: '12 min ago',
    durationLabel: '14s',
    wordCount: 38,
    hasAudio: true,
    audioUri: 'file:///mock/rec_1.m4a',
    status: 'done',
  },
  {
    id: 'h2',
    text: 'Reply to Sarah — yes I can join the call at noon and bring the proposal draft.',
    deviceTag: 'Work PC',
    dayLabel: 'Today',
    timeOfDay: '8:51 AM',
    relativeTime: '1 hour ago',
    durationLabel: '9s',
    wordCount: 22,
    hasAudio: false,
    status: 'done',
  },
  {
    id: 'h3',
    text: '',
    deviceTag: 'Local',
    dayLabel: 'Yesterday',
    timeOfDay: '6:12 PM',
    relativeTime: 'yesterday',
    durationLabel: '6s',
    wordCount: 0,
    hasAudio: true,
    audioUri: 'file:///mock/rec_3.m4a',
    audioUrl: 'user/rec_3.m4a',
    status: 'failed',        // the Retry state
  },
  {
    id: 'h4',
    text: 'Long note on the new onboarding flow — three things I want to validate this sprint.',
    deviceTag: 'MacBook',
    dayLabel: 'Yesterday',
    timeOfDay: '2:08 PM',
    relativeTime: 'yesterday',
    durationLabel: '52s',
    wordCount: 120,
    hasAudio: false,
    status: 'done',
  },
];

const wordsIn = (s: string) => (s.trim() ? s.trim().split(/\s+/).length : 0);

export function useHistory() {
  const [items, setItems] = useState<HistoryItem[]>(MOCK);

  const add = async (item: HistoryItem) => { setItems(prev => [item, ...prev]); };

  const remove = async (id: string) => { setItems(prev => prev.filter(i => i.id !== id)); };

  /** Persist a transcription (real hook: Supabase insert + local cache). */
  const addTranscription = async (
    text: string,
    deviceTag: string,
    durationMs = 0,
    _targetDeviceId?: string | null,
    audioUri?: string,
    status: 'done' | 'failed' = 'done',
  ): Promise<HistoryItem> => {
    const item: HistoryItem = {
      id: `h_${Date.now()}`,
      text,
      deviceTag,
      dayLabel: 'Today',
      timeOfDay: new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
      relativeTime: 'just now',
      durationLabel: `${Math.max(1, Math.round(durationMs / 1000))}s`,
      wordCount: wordsIn(text),
      audioUri,
      hasAudio: !!audioUri,
      status,
    };
    setItems(prev => [item, ...prev]);
    return item;
  };

  /** Re-run the shared dictation pipeline over a failed entry's saved audio. */
  const retryEntry = async (id: string): Promise<{ ok: boolean; error?: string }> => {
    const entry = items.find(i => i.id === id);
    if (!entry) return { ok: false, error: 'not found' };
    if (!entry.hasAudio) return { ok: false, error: 'no audio to retry' };
    setItems(prev => prev.map(i =>
      i.id === id
        ? { ...i, text: 'Retried transcript.', wordCount: 2, status: 'done' as const }
        : i));
    return { ok: true };
  };

  /** Play a saved recording. False when there is nothing playable. */
  const playEntry = async (id: string): Promise<boolean> =>
    !!items.find(i => i.id === id)?.hasAudio;

  const refresh = async (): Promise<void> => {};

  return { items, add, remove, addTranscription, retryEntry, playEntry, refresh };
}
