/**
 * useCanvas — Flume staging board backed by the working realtime "canvas" sync.
 *
 * Model bridge: the design is a multi-item board; the backend is ONE shared
 * `canvas` row per user (the shared clipboard). So:
 *   - save(item)  → upsert the item's payload to the shared row (+ copy to the
 *     system clipboard, + upload images to the canvas-images bucket)
 *   - a realtime channel receives changes from OTHER devices → prepend them as
 *     "sent" items and copy their text to the clipboard (matches old behavior)
 * All remote activity is gated by the Sync toggle (getSyncEnabled).
 *
 * Contract (consumed by CanvasScreen): { items, save, discard, addText, addLink, addPhoto }
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import * as Clipboard from 'expo-clipboard';
import * as ImagePicker from 'expo-image-picker';
import * as Haptics from 'expo-haptics';
import { supabase, SUPABASE_URL, SUPABASE_ANON_KEY } from '../../lib/supabase';
import { getUserId, getDeviceName, getSyncEnabled } from '../../lib/storage';

type BaseItem = { id: string; state: 'draft' | 'sent'; sentAt?: string };
export type TextItem = BaseItem & { kind: 'text'; text: string };
export type LinkItem = BaseItem & { kind: 'link'; url: string };
export type ImageItem = BaseItem & {
  kind: 'image'; uri: string; filename: string; sizeLabel?: string; dimensions?: string;
};
export type CanvasItem = TextItem | LinkItem | ImageItem;

function nowHHmm() {
  return new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}
function humanFileSize(bytes?: number): string | undefined {
  if (!bytes) return undefined;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function uploadImage(localUri: string): Promise<string | null> {
  try {
    const ext = localUri.split('.').pop()?.split('?')[0]?.toLowerCase() ?? 'jpg';
    const mime = ext === 'png' ? 'image/png' : 'image/jpeg';
    const userId = await getUserId();
    const filename = `${userId}_${Date.now()}.${ext}`;
    const path = `canvas/${filename}`;
    const form = new FormData();
    form.append('file', { uri: localUri, name: filename, type: mime } as any);
    const resp = await fetch(`${SUPABASE_URL}/storage/v1/object/canvas-images/${path}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${SUPABASE_ANON_KEY}`, 'x-upsert': 'true' },
      body: form,
    });
    if (!resp.ok) return null;
    return supabase.storage.from('canvas-images').getPublicUrl(path).data.publicUrl;
  } catch (err) {
    console.error('Canvas image upload failed:', err);
    return null;
  }
}

export function useCanvas() {
  const [items, setItems] = useState<CanvasItem[]>([]);
  const channelRef = useRef<ReturnType<typeof supabase.channel> | null>(null);
  const myNameRef = useRef<string>('');

  // Subscribe to the shared canvas row for cross-device receive.
  useEffect(() => {
    let active = true;
    (async () => {
      if (!(await getSyncEnabled())) return;
      const userId = await getUserId();
      myNameRef.current = await getDeviceName();
      if (!active) return;

      channelRef.current = supabase
        .channel(`canvas_${userId}`)
        .on(
          'postgres_changes',
          { event: '*', schema: 'public', table: 'canvas', filter: `user_id=eq.${userId}` },
          async (payload: any) => {
            const content = (payload.new?.content ?? '') as string;
            const imageUrl = (payload.new?.image_url ?? null) as string | null;
            const from = (payload.new?.device_name ?? '') as string;
            if (from === myNameRef.current) return; // skip our own writes

            const id = `c_${Date.now()}`;
            if (imageUrl) {
              setItems(prev => [{ id, kind: 'image', state: 'sent', sentAt: nowHHmm(), uri: imageUrl, filename: 'shared.jpg' }, ...prev]);
              await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
            } else if (content) {
              const isLink = /^https?:\/\//i.test(content);
              setItems(prev => [
                isLink
                  ? { id, kind: 'link', state: 'sent', sentAt: nowHHmm(), url: content }
                  : { id, kind: 'text', state: 'sent', sentAt: nowHHmm(), text: content },
                ...prev,
              ]);
              await Clipboard.setStringAsync(content);
              await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
            }
          },
        )
        .subscribe();
    })();

    return () => {
      active = false;
      if (channelRef.current) { supabase.removeChannel(channelRef.current); channelRef.current = null; }
    };
  }, []);

  const pushToShared = useCallback(async (payload: { content: string | null; image_url: string | null }) => {
    if (!(await getSyncEnabled())) return;
    const userId = await getUserId();
    const deviceName = await getDeviceName();
    await supabase.from('canvas').upsert(
      { user_id: userId, content: payload.content, image_url: payload.image_url, device_name: deviceName, updated_at: new Date().toISOString() },
      { onConflict: 'user_id' },
    );
  }, []);

  const save = useCallback(async (id: string) => {
    const item = items.find(i => i.id === id);
    if (!item) return;
    try {
      if (item.kind === 'text') {
        await Clipboard.setStringAsync(item.text);
        await pushToShared({ content: item.text, image_url: null });
      } else if (item.kind === 'link') {
        await Clipboard.setStringAsync(item.url);
        await pushToShared({ content: item.url, image_url: null });
      } else if (item.kind === 'image') {
        const url = /^https?:\/\//i.test(item.uri) ? item.uri : await uploadImage(item.uri);
        if (url) {
          await Clipboard.setStringAsync(url);
          await pushToShared({ content: null, image_url: url });
        }
      }
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch (err) {
      console.error('Failed to save canvas item:', err);
    }
    setItems(prev => prev.map(i => (i.id === id ? { ...i, state: 'sent', sentAt: nowHHmm() } : i)));
  }, [items, pushToShared]);

  const discard = useCallback((id: string) => {
    setItems(prev => prev.filter(i => i.id !== id));
  }, []);

  const addText = useCallback(async () => {
    let text = '';
    try {
      const clip = await Clipboard.getStringAsync();
      if (clip && !/^https?:\/\//i.test(clip)) text = clip;
    } catch { /* ignore */ }
    setItems(prev => [{ id: `c_${Date.now()}`, kind: 'text', state: 'draft', text }, ...prev]);
  }, []);

  const addLink = useCallback(async () => {
    let url = '';
    try {
      const clip = await Clipboard.getStringAsync();
      if (/^https?:\/\//i.test(clip)) url = clip;
    } catch { /* ignore */ }
    setItems(prev => [{ id: `c_${Date.now()}`, kind: 'link', state: 'draft', url }, ...prev]);
  }, []);

  const addPhoto = useCallback(async () => {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) return;
      const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.8 });
      if (res.canceled || !res.assets?.length) return;
      const a = res.assets[0];
      setItems(prev => [{
        id: `c_${Date.now()}`, kind: 'image', state: 'draft',
        uri: a.uri, filename: a.fileName ?? 'photo.jpg',
        sizeLabel: humanFileSize(a.fileSize),
        dimensions: a.width && a.height ? `${a.width}×${a.height}` : undefined,
      }, ...prev]);
    } catch (err) {
      console.error('Failed to add photo:', err);
    }
  }, []);

  return { items, save, discard, addText, addLink, addPhoto };
}
