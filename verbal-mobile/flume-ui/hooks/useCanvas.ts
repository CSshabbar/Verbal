/**
 * useCanvas — Flume staging board backed by the working realtime "canvas" sync.
 *
 * Model bridge: the design is a multi-item board; the backend is ONE shared
 * `canvas` row per user (the shared clipboard). So:
 *   - save(item)  → upsert the item's payload to the shared row (+ copy to the
 *     system clipboard, + upload images to the canvas-images bucket)
 *   - a realtime channel receives changes from OTHER devices → prepend them as
 *     "sent" items and copy their text to the clipboard (matches old behavior)
 * All remote activity is gated by the Sync toggle (lib/syncStore).
 *
 * Lifecycle (IDI-171 / the subscribe half of IDI-173). The subscribe effect used
 * to have an empty dep array that read the sync flag ONCE and bailed with
 * `if (!syncEnabled) return` — so enabling sync after mount was permanently
 * dead, the channel never followed an account change, and sign-out never tore it
 * down. Now the effect is driven by the live store value plus an account epoch:
 *   - toggle ON  → effect re-runs → channel joins
 *   - toggle OFF → effect re-runs → channel closes, no remote reads/writes
 *   - sign-out / account switch → reset() bumps the epoch → items dropped, the
 *     old user's channel closed, a new one opened under the new id
 *   - dropped connection → the subscribe() status callback rejoins
 *
 * Contract (consumed by CanvasScreen): { items, save, discard, addText, addLink, addPhoto }
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import * as Clipboard from 'expo-clipboard';
import * as ImagePicker from 'expo-image-picker';
import * as Haptics from 'expo-haptics';
import { supabase, SUPABASE_URL, SUPABASE_ANON_KEY } from '../../lib/supabase';
import { getUserId, getDeviceName } from '../../lib/storage';
import * as syncStore from '../../lib/syncStore';
import { useSyncEnabled } from './useSyncEnabled';

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

/* ── module-level lifecycle surface ──────────────────────────────────────────
 * Canvas state lives in the hook (unlike historyStore), but sign-out and the
 * AppState foreground listener are module-level events. These two tiny
 * registries are the bridge — parallel to historyStore.reset()/catchUp(). */

let accountEpoch = 0;
const epochListeners = new Set<() => void>();
/** The mounted hook instance's refresh(), if the Canvas screen is alive. */
let activeRefresh: (() => Promise<void>) | null = null;

/**
 * Drop canvas state and re-key its channel to the current account (IDI-170/171).
 * Called from useAuth's signOut / deleteAccount / account-switch branch — the
 * canvas equivalent of historyStore.reset(). Safe when nothing is mounted: the
 * epoch bump is picked up by whatever mounts next.
 */
export function reset() {
  accountEpoch += 1;
  epochListeners.forEach((l) => { try { l(); } catch { /* ignore */ } });
}

/** Foreground catch-up (AppState 'active') — pull the shared row we may have
 *  missed while backgrounded. No-op when the Canvas screen isn't mounted. */
export async function catchUp() {
  if (!(await syncStore.getSyncEnabled())) return;
  try { await activeRefresh?.(); } catch { /* best effort */ }
}

export function useCanvas() {
  const [items, setItems] = useState<CanvasItem[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const channelRef = useRef<ReturnType<typeof supabase.channel> | null>(null);
  const myNameRef = useRef<string>('');
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const syncEnabled = useSyncEnabled();
  const [epoch, setEpoch] = useState(accountEpoch);
  // Signature of the last shared-row payload we turned into an item. Guards the
  // now-repeatable refresh() (foreground catch-up) against prepending the same
  // clipboard row again and again. Real fetch/merge semantics are IDI-173's
  // later wave; this is only the minimum that makes catch-up non-destructive.
  const lastAppliedRef = useRef<string | null>(null);

  // Account change / sign-out → forget the board, then let the subscribe effect
  // below re-run against the new identity.
  useEffect(() => {
    const listener = () => {
      setEpoch(accountEpoch);
      setItems([]);
      lastAppliedRef.current = null;
    };
    epochListeners.add(listener);
    return () => { epochListeners.delete(listener); };
  }, []);

  // Transient in-app banner ("Received from X — copied to clipboard"), auto-hides.
  const flashToast = useCallback((msg: string) => {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2800);
  }, []);
  const dismissToast = useCallback(() => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(null);
  }, []);
  useEffect(() => () => { if (toastTimer.current) clearTimeout(toastTimer.current); }, []);

  // Subscribe to the shared canvas row for cross-device receive.
  // Deps: the LIVE sync flag + the account epoch, so the channel follows both
  // (the old empty dep array is what made enabling sync after mount dead).
  useEffect(() => {
    if (!syncEnabled) return;   // OFF → nothing joined; the cleanup below already ran
    let active = true;
    let rejoinTimer: ReturnType<typeof setTimeout> | null = null;
    let rejoinAttempts = 0;

    const join = async () => {
      const userId = await getUserId();
      myNameRef.current = await getDeviceName();
      if (!active) return;

      const ch = supabase
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
            const who = from || 'another device';
            // Remember what we just showed so a foreground catch-up refresh()
            // doesn't prepend the same shared row a second time.
            lastAppliedRef.current = imageUrl || content || null;
            if (imageUrl) {
              setItems(prev => [{ id, kind: 'image', state: 'sent', sentAt: nowHHmm(), uri: imageUrl, filename: 'shared.jpg' }, ...prev]);
              // Copy the image's URL so it's pasteable even before the thumbnail loads.
              await Clipboard.setStringAsync(imageUrl);
              flashToast(`Received image from ${who} — link copied`);
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
              flashToast(`Received from ${who} — copied to clipboard`);
              await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
            }
          },
        );
      channelRef.current = ch;
      ch.subscribe((status) => {
        if (!active) return;
        if (status === 'SUBSCRIBED') { rejoinAttempts = 0; return; }
        if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT' || status === 'CLOSED') {
          if (channelRef.current !== ch) return;   // superseded / intentional teardown
          if (rejoinTimer) return;
          const delay = Math.min(30_000, 1_000 * 2 ** rejoinAttempts);
          rejoinAttempts += 1;
          rejoinTimer = setTimeout(() => {
            rejoinTimer = null;
            if (!active) return;
            // Null the ref first so this channel's own CLOSED can't re-enter.
            const old = channelRef.current;
            channelRef.current = null;
            if (old) { try { supabase.removeChannel(old); } catch { /* ignore */ } }
            join().catch(() => { /* the next status error retries */ });
          }, delay);
        }
      });
    };

    join().catch((err) => console.error('Canvas subscribe failed:', err));

    return () => {
      active = false;
      if (rejoinTimer) { clearTimeout(rejoinTimer); rejoinTimer = null; }
      if (channelRef.current) { supabase.removeChannel(channelRef.current); channelRef.current = null; }
    };
  }, [syncEnabled, epoch, flashToast]);

  const pushToShared = useCallback(async (payload: { content: string | null; image_url: string | null }) => {
    if (!(await syncStore.getSyncEnabled())) return;   // OFF ⇒ no remote writes
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
        if (!url) {
          // Surface the silent upload failure instead of no-op'ing (was the
          // "I send a picture and nothing happens" bug).
          flashToast('Image upload failed — check your connection');
          await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
          return;
        }
        await Clipboard.setStringAsync(url);
        await pushToShared({ content: null, image_url: url });
      }
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch (err) {
      console.error('Failed to save canvas item:', err);
      flashToast('Send failed — try again');
      return;
    }
    setItems(prev => prev.map(i => (i.id === id ? { ...i, state: 'sent', sentAt: nowHHmm() } : i)));
  }, [items, pushToShared, flashToast]);

  const discard = useCallback((id: string) => {
    setItems(prev => prev.filter(i => i.id !== id));
  }, []);

  const addText = useCallback(async () => {
    // Start with an empty, editable draft so the user can type.
    setItems(prev => [{ id: `c_${Date.now()}`, kind: 'text', state: 'draft', text: '' }, ...prev]);
  }, []);

  const updateText = useCallback((id: string, text: string) => {
    setItems(prev => prev.map(i => (i.id === id && i.kind === 'text' ? { ...i, text } : i)));
  }, []);

  /** Manually pull the current shared canvas row (in case realtime missed it,
   *  and on every foreground catch-up). */
  const refresh = useCallback(async () => {
    try {
      if (!(await syncStore.getSyncEnabled())) return;
      const userId = await getUserId();
      const { data } = await supabase
        .from('canvas').select('content,image_url,device_name')
        .eq('user_id', userId).maybeSingle();
      if (!data) return;
      // Now that refresh() runs on every foreground (IDI-171), the same shared
      // row would be prepended again each time. Skip the payload we've already
      // shown. (Minimum viable guard — proper fetch/merge is IDI-173.)
      const signature = (data.image_url || data.content || null) as string | null;
      if (!signature || signature === lastAppliedRef.current) return;
      lastAppliedRef.current = signature;
      const id = `c_${Date.now()}`;
      if (data.image_url) {
        setItems(prev => [{ id, kind: 'image', state: 'sent', sentAt: nowHHmm(), uri: data.image_url, filename: 'shared.jpg' }, ...prev]);
      } else if (data.content) {
        const isLink = /^https?:\/\//i.test(data.content);
        setItems(prev => [
          isLink
            ? { id, kind: 'link', state: 'sent', sentAt: nowHHmm(), url: data.content }
            : { id, kind: 'text', state: 'sent', sentAt: nowHHmm(), text: data.content },
          ...prev,
        ]);
        await Clipboard.setStringAsync(data.content);
      }
    } catch (err) {
      console.error('Canvas refresh failed:', err);
    }
  }, []);

  // Hand this instance's refresh() to the module-level catchUp() the AppState
  // foreground listener calls. Last mount wins; unregisters on unmount.
  useEffect(() => {
    activeRefresh = refresh;
    return () => { if (activeRefresh === refresh) activeRefresh = null; };
  }, [refresh]);

  // Sync turned ON (or the account changed) → immediate catch-up pull, so the
  // board shows whatever another device left on the shared row instead of
  // waiting for the next realtime event. The lastAppliedRef guard inside
  // refresh() stops this duplicating a row we already have.
  useEffect(() => {
    if (!syncEnabled) return;
    refresh().catch(() => { /* best effort */ });
  }, [syncEnabled, epoch, refresh]);

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

  return { items, save, discard, addText, addLink, addPhoto, updateText, refresh, toast, dismissToast };
}
