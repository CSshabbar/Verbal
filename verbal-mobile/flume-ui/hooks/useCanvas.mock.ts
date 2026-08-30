/**
 * useCanvas.mock — the design contract for useCanvas (never imported at
 * runtime; kept mutually type-assignable with useCanvas.ts — IDI-179 rule).
 *
 * M1 redesign contract (2026-08-17): `live` slot + device-local `feed` +
 * sendText/sendPhoto composer verbs + copy/clear hero actions.
 */
import { useCallback, useState } from 'react';
import type { CanvasKind, FeedEntry, LiveSlot } from './useCanvas';

export type { CanvasKind, FeedEntry, LiveSlot } from './useCanvas';

const NOW = new Date().toISOString();

const MOCK_LIVE: LiveSlot = {
  kind: 'text',
  text: 'Meeting follow-ups for the latency pass: the baseline was 1.02s ASR plus roughly 1.2 seconds of formatting…',
  from: "Muhammad's Mac",
  own: false,
  at: NOW,
};

const MOCK_FEED: FeedEntry[] = [
  { id: 'f1', kind: 'text', text: 'Reminder: rotate the Groq key after the demo.', from: 'this phone', own: true, at: NOW },
  { id: 'f2', kind: 'link', text: 'https://linear.app/idiaz/issue/IDI-184/overlay-dpi', from: "Muhammad's Mac", own: false, at: NOW },
  { id: 'f3', kind: 'image', text: 'Image', imageUrl: 'https://example.com/x.jpg', from: 'this phone', own: true, at: NOW },
];

export function reset() {}
export async function catchUp() {}

export function useCanvas() {
  const [live, setLive] = useState<LiveSlot | null>(MOCK_LIVE);
  const [feed, setFeed] = useState<FeedEntry[]>(MOCK_FEED);
  const [toast, setToast] = useState<string | null>(null);

  const sendText = useCallback(async (text: string): Promise<boolean> => {
    const t = text.trim();
    if (!t) return false;
    const kind: CanvasKind = /^https?:\/\/\S+$/i.test(t) ? 'link' : 'text';
    const at = new Date().toISOString();
    setLive({ kind, text: t, from: 'this phone', own: true, at });
    setFeed(prev => [{ id: `f_${Date.now()}`, kind, text: t, from: 'this phone', own: true, at }, ...prev].slice(0, 20));
    return true;
  }, []);

  const sendPhoto = useCallback(async (): Promise<boolean> => {
    const at = new Date().toISOString();
    setLive({ kind: 'image', imageUrl: 'https://example.com/mock.jpg', from: 'this phone', own: true, at });
    return true;
  }, []);

  const copyLive = useCallback(async () => { setToast('Copied'); }, []);
  const clearLive = useCallback(async () => {
    setLive({ kind: 'empty', from: 'this phone', own: true, at: new Date().toISOString() });
  }, []);
  const copyFeedEntry = useCallback(async (_id: string) => { setToast('Copied'); }, []);
  const refresh = useCallback(async () => {}, []);
  const dismissToast = useCallback(() => setToast(null), []);

  return {
    live, feed,
    sendText, sendPhoto,
    copyLive, clearLive, copyFeedEntry,
    refresh, toast, dismissToast,
  };
}
