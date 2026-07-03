/**
 * useCanvas — staging board for items to push to the paired computer.
 * Add* helpers integrate with image picker / system paste / your input modal.
 * `save` sends the item to the device clipboard via your sync backend.
 */
import { useState, useCallback } from 'react';

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
    uri: 'https://placehold.co/120x120/0b0908/E0552C/png',
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

export function useCanvas() {
  const [items, setItems] = useState<CanvasItem[]>(MOCK);

  const save = useCallback(async (id: string) => {
    // TODO: send the item's payload to the paired device clipboard.
    // const item = items.find(i => i.id === id);
    // await flumeSync.copyToClipboard(targetDeviceId, item);
    const stamp = new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    setItems(prev => prev.map(i => i.id === id ? { ...i, state: 'sent', sentAt: stamp } : i));
  }, []);

  const discard = useCallback((id: string) => {
    setItems(prev => prev.filter(i => i.id !== id));
  }, []);

  const addText = useCallback(() => {
    // TODO: open a text-input bottom sheet, then push the item as draft
    const id = `c_${Date.now()}`;
    setItems(prev => [{ id, kind: 'text', state: 'draft', text: 'New text…' }, ...prev]);
  }, []);

  const addLink = useCallback(async () => {
    // TODO: read from clipboard:
    //   import * as Clipboard from 'expo-clipboard';
    //   const url = await Clipboard.getStringAsync();
    const id = `c_${Date.now()}`;
    setItems(prev => [{ id, kind: 'link', state: 'draft', url: 'https://…' }, ...prev]);
  }, []);

  const addPhoto = useCallback(async () => {
    // TODO: launch image picker:
    //   import * as ImagePicker from 'expo-image-picker';
    //   const res = await ImagePicker.launchImageLibraryAsync({ ... });
    const id = `c_${Date.now()}`;
    setItems(prev => [{
      id,
      kind: 'image',
      state: 'draft',
      uri: 'https://placehold.co/120x120/0b0908/E0552C/png',
      filename: 'photo.jpg',
    }, ...prev]);
  }, []);

  return { items, save, discard, addText, addLink, addPhoto };
}
