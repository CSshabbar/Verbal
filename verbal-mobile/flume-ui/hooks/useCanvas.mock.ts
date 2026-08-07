/**
 * useCanvas — MOCK (contract reference, never imported at runtime).
 * Same exported shape as ./useCanvas, backed by in-memory state.
 *
 * Model bridge the real hook implements: the design is a multi-item board, the
 * backend is ONE shared `canvas` row per user. `save` pushes an item onto that
 * row (+ system clipboard, + image upload); a realtime channel prepends what
 * OTHER devices wrote and raises the `toast` banner. Everything remote is gated
 * by the Sync toggle — the mock has no remote half, so `refresh` is a no-op and
 * `toast` only ever comes from a local action.
 */
import { useState, useCallback, useRef, useEffect } from 'react';

type BaseItem = {
  id: string;
  state: 'draft' | 'sent';
  sentAt?: string; // "9:24"
};

export type TextItem  = BaseItem & { kind: 'text';  text: string };
export type LinkItem  = BaseItem & { kind: 'link';  url: string };
export type ImageItem = BaseItem & {
  kind: 'image';
  uri: string;
  filename: string;
  sizeLabel?: string;
  dimensions?: string;
};

export type CanvasItem = TextItem | LinkItem | ImageItem;

const MOCK: CanvasItem[] = [
  {
    id: 'c1',
    kind: 'text',
    state: 'sent',
    sentAt: '9:24',
    text: "Let's meet at 3pm in Studio B — bring the latest mocks.",
  },
  {
    id: 'c2',
    kind: 'link',
    state: 'sent',
    sentAt: '9:18',
    url: 'github.com/flume/voice-app',
  },
  {
    id: 'c3',
    kind: 'image',
    state: 'sent',
    sentAt: '8:51',
    uri: 'https://placehold.co/120x120/0b0908/C85A3E/png',
    filename: 'screenshot-2026-06-30.png',
    sizeLabel: '1.2 MB',
    dimensions: '1920×1080',
  },
  {
    id: 'c4',
    kind: 'text',
    state: 'draft',
    text: 'Reschedule the design review to Thursday and pull marketing in.',
  },
];

const nowHHmm = () =>
  new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

export function useCanvas() {
  const [items, setItems] = useState<CanvasItem[]>(MOCK);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (toastTimer.current) clearTimeout(toastTimer.current); }, []);

  const flashToast = useCallback((msg: string) => {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2800);
  }, []);

  const dismissToast = useCallback(() => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(null);
  }, []);

  /** Push the item's payload to the shared row + the system clipboard. */
  const save = useCallback(async (id: string) => {
    const stamp = nowHHmm();
    setItems(prev => prev.map(i => (i.id === id ? { ...i, state: 'sent', sentAt: stamp } : i)));
    flashToast('Sent to your computer');
  }, [flashToast]);

  /** Remove a card. A 'sent' card also clears the shared row in the real hook. */
  const discard = useCallback(async (id: string) => {
    setItems(prev => prev.filter(i => i.id !== id));
  }, []);

  /** Start an empty, editable text draft (the card itself hosts the input). */
  const addText = useCallback(async () => {
    setItems(prev => [{ id: `c_${Date.now()}`, kind: 'text', state: 'draft', text: '' }, ...prev]);
  }, []);

  /** Live edit of a text draft's body. */
  const updateText = useCallback((id: string, text: string) => {
    setItems(prev => prev.map(i => (i.id === id && i.kind === 'text' ? { ...i, text } : i)));
  }, []);

  /** Real hook reads the system clipboard. */
  const addLink = useCallback(async () => {
    setItems(prev => [{ id: `c_${Date.now()}`, kind: 'link', state: 'draft', url: 'https://…' }, ...prev]);
  }, []);

  /** Real hook launches the image picker + uploads to canvas-images. */
  const addPhoto = useCallback(async () => {
    setItems(prev => [{
      id: `c_${Date.now()}`,
      kind: 'image',
      state: 'draft',
      uri: 'https://placehold.co/120x120/0b0908/C85A3E/png',
      filename: 'photo.jpg',
    }, ...prev]);
  }, []);

  /** Catch-up read of the shared row (pull-to-refresh / foreground). */
  const refresh = useCallback(async () => {}, []);

  return { items, save, discard, addText, addLink, addPhoto, updateText, refresh, toast, dismissToast };
}
