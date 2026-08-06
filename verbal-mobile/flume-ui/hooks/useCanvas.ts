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
import { getUserId, getDeviceName, getDeviceId } from '../../lib/storage';
import * as syncStore from '../../lib/syncStore';
import { useSyncEnabled } from './useSyncEnabled';

type BaseItem = { id: string; state: 'draft' | 'sent'; sentAt?: string };
export type TextItem = BaseItem & { kind: 'text'; text: string };
export type LinkItem = BaseItem & { kind: 'link'; url: string };
export type ImageItem = BaseItem & {
  kind: 'image'; uri: string; filename: string; sizeLabel?: string; dimensions?: string;
};
export type CanvasItem = TextItem | LinkItem | ImageItem;

/** The shared `canvas` row, as far as this hook cares. `device_id` is the
 *  authoritative write origin (IDI-173); `device_name` is the legacy fallback
 *  for rows written by a client that predates the column. */
type CanvasRow = {
  content?: string | null;
  image_url?: string | null;
  device_name?: string | null;
  device_id?: string | null;
  updated_at?: string | null;
};

function nowHHmm() {
  return new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

/* Card identity. The board renders one card per *version* of the shared row, so
 * the id must be a function of the row's content — `c_${Date.now()}` gave the
 * same payload a different id on every realtime event and every refresh, which
 * is what made catch-up duplicate cards and forced the old "just don't apply it
 * twice" guard. With a content-derived id, re-applying is idempotent. */
function hashish(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}
function rowSignature(row: CanvasRow): string {
  return `${row.updated_at ?? ''}|${row.image_url ?? ''}|${row.content ?? ''}`;
}
function cardIdFor(signature: string): string {
  return `c_${hashish(signature)}`;
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
  const myDeviceIdRef = useRef<string>('');
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const syncEnabled = useSyncEnabled();
  const [epoch, setEpoch] = useState(accountEpoch);
  // Signature (updated_at + payload) of the last shared-row version we applied,
  // including the ones we skipped because WE wrote them. Same shape as before,
  // now also the dedupe key for realtime-then-refresh of the same version.
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

  /**
   * Apply one version of the shared row to the board — the SINGLE place a
   * remote canvas state becomes UI, shared by the realtime handler and the
   * fetch/catch-up path (they used to duplicate the logic and disagree).
   *
   * An empty row is not "nothing to do": per the IDI-173 contract a clear is an
   * explicit `{content: '', image_url: null}` write and receivers must APPLY
   * it. Local drafts survive — they were never on the shared row.
   */
  const applyRow = useCallback(async (row: CanvasRow, opts: { announce?: boolean } = {}) => {
    const signature = rowSignature(row);
    if (signature === lastAppliedRef.current) return;   // same version, already on screen
    lastAppliedRef.current = signature;

    const imageUrl = (row.image_url ?? null) as string | null;
    const content = (row.content ?? '') as string;
    const who = row.device_name || 'another device';
    const id = cardIdFor(signature);

    if (!imageUrl && !content) {
      setItems(prev => prev.filter(i => i.state === 'draft'));
      if (opts.announce) flashToast(`Canvas cleared from ${who}`);
      return;
    }

    if (imageUrl) {
      setItems(prev => [
        { id, kind: 'image', state: 'sent', sentAt: nowHHmm(), uri: imageUrl, filename: 'shared.jpg' },
        ...prev.filter(i => i.id !== id),
      ]);
      // Copy the image's URL so it's pasteable even before the thumbnail loads.
      await Clipboard.setStringAsync(imageUrl);
      if (opts.announce) {
        flashToast(`Received image from ${who} — link copied`);
        await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
      return;
    }

    const isLink = /^https?:\/\//i.test(content);
    setItems(prev => [
      isLink
        ? { id, kind: 'link', state: 'sent', sentAt: nowHHmm(), url: content }
        : { id, kind: 'text', state: 'sent', sentAt: nowHHmm(), text: content },
      ...prev.filter(i => i.id !== id),
    ]);
    await Clipboard.setStringAsync(content);
    if (opts.announce) {
      flashToast(`Received from ${who} — copied to clipboard`);
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    }
  }, [flashToast]);

  /** True when this device wrote the row. `device_id` is authoritative; the
   *  device-NAME compare is used ONLY when the event carries no device_id (a
   *  row written by an older client), because two devices can share a name. */
  const isOwnWrite = useCallback((row: CanvasRow) => {
    if (row.device_id) return row.device_id === myDeviceIdRef.current;
    return !!myNameRef.current && (row.device_name ?? '') === myNameRef.current;
  }, []);

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
      myDeviceIdRef.current = await getDeviceId();
      if (!active) return;

      const ch = supabase
        .channel(`canvas_${userId}`)
        .on(
          'postgres_changes',
          { event: '*', schema: 'public', table: 'canvas', filter: `user_id=eq.${userId}` },
          async (payload: any) => {
            const row = (payload.new ?? null) as CanvasRow | null;
            // A DELETE carries no `new` — the shared row is gone, which is the
            // same thing as a cleared board.
            if (!row || Object.keys(row).length === 0) {
              lastAppliedRef.current = null;
              setItems(prev => prev.filter(i => i.state === 'draft'));
              return;
            }
            if (isOwnWrite(row)) {
              // Still record the version, so the next refresh() doesn't hand our
              // own write back to us as a "received" card.
              lastAppliedRef.current = rowSignature(row);
              return;
            }
            await applyRow(row, { announce: true });
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
  }, [syncEnabled, epoch, applyRow, isOwnWrite]);

  /**
   * Write the shared row. Every write stamps BOTH `device_id` (the origin the
   * receivers filter on) and `device_name` (what they display).
   *
   * The columns are applied SELECTIVELY: a key absent from `payload` is left
   * out of the upsert entirely, so a text send can't blank someone's image and
   * an image send can't blank the text (the old unconditional
   * `{content, image_url}` pair did both). A CLEAR is therefore explicit —
   * `{content: '', image_url: null}` — and never a side effect.
   */
  const pushToShared = useCallback(async (payload: { content?: string | null; image_url?: string | null }) => {
    if (!(await syncStore.getSyncEnabled())) return;   // OFF ⇒ no remote writes
    const userId = await getUserId();
    const deviceName = await getDeviceName();
    const deviceId = await getDeviceId();
    myNameRef.current = deviceName;
    myDeviceIdRef.current = deviceId;
    const row: Record<string, any> = {
      user_id: userId,
      device_id: deviceId,
      device_name: deviceName,
      updated_at: new Date().toISOString(),
    };
    if ('content' in payload) row.content = payload.content ?? '';
    if ('image_url' in payload) row.image_url = payload.image_url ?? null;
    const { error } = await supabase.from('canvas').upsert(row, { onConflict: 'user_id' });
    if (error) throw error;   // surfaced by save()/discard() — used to fail silently
  }, []);

  const save = useCallback(async (id: string) => {
    const item = items.find(i => i.id === id);
    if (!item) return;
    try {
      if (item.kind === 'text') {
        await Clipboard.setStringAsync(item.text);
        await pushToShared({ content: item.text });          // text-only: image_url untouched
      } else if (item.kind === 'link') {
        await Clipboard.setStringAsync(item.url);
        await pushToShared({ content: item.url });           // text-only: image_url untouched
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
        await pushToShared({ image_url: url });              // image-only: content untouched
      }
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch (err) {
      console.error('Failed to save canvas item:', err);
      flashToast('Send failed — try again');
      return;
    }
    setItems(prev => prev.map(i => (i.id === id ? { ...i, state: 'sent', sentAt: nowHHmm() } : i)));
  }, [items, pushToShared, flashToast]);

  /**
   * Dismiss a card. For a card that is on the SHARED row (state 'sent' — one we
   * sent or one we received), dismissing it is a real CLEAR: an explicit
   * `{content: '', image_url: null}` write, so the other devices drop it too
   * instead of re-serving it on their next fetch. Drafts were never shared, so
   * they're removed locally only — as is everything when sync is OFF.
   */
  const discard = useCallback(async (id: string) => {
    const item = items.find(i => i.id === id);
    setItems(prev => prev.filter(i => i.id !== id));
    if (!item || item.state !== 'sent') return;
    try {
      await pushToShared({ content: '', image_url: null });   // no-op when sync is OFF
    } catch (err) {
      console.error('Canvas clear failed:', err);
      flashToast('Clear failed — try again');
    }
  }, [items, pushToShared, flashToast]);

  const addText = useCallback(async () => {
    // Start with an empty, editable draft so the user can type.
    setItems(prev => [{ id: `c_${Date.now()}`, kind: 'text', state: 'draft', text: '' }, ...prev]);
  }, []);

  // Local-only: this edits a DRAFT card's text in place, and a draft has not
  // been shared yet (save() is what writes the row, through pushToShared, which
  // is the single writer and always stamps device_id/device_name). Pushing per
  // keystroke would mean one shared-row write per character.
  const updateText = useCallback((id: string, text: string) => {
    setItems(prev => prev.map(i => (i.id === id && i.kind === 'text' ? { ...i, text } : i)));
  }, []);

  /**
   * Fetch-and-apply the current shared row — on mount, on a sync-ON flip, on an
   * account change, on the manual refresh button and on every foreground
   * catch-up.
   *
   * This APPLIES the row (that's the IDI-173 fix): it used to only guard against
   * duplicating a payload, so a board another device had CLEARED still showed
   * the stale card, and a card that arrived while the app was backgrounded
   * needed a second realtime event to appear. Idempotence now comes from the
   * content-derived card id plus the version signature, not from refusing to
   * apply.
   */
  const refresh = useCallback(async () => {
    try {
      if (!(await syncStore.getSyncEnabled())) return;
      const userId = await getUserId();
      myDeviceIdRef.current = await getDeviceId();
      if (!myNameRef.current) myNameRef.current = await getDeviceName();
      const { data } = await supabase
        .from('canvas').select('content,image_url,device_name,device_id,updated_at')
        .eq('user_id', userId).maybeSingle();
      if (!data) return;                       // no row at all ⇒ nothing shared yet
      const row = data as CanvasRow;
      if (isOwnWrite(row)) {
        // Our own last send — don't echo it back onto the board as "received",
        // but remember the version so a later event for it is a no-op too.
        lastAppliedRef.current = rowSignature(row);
        return;
      }
      await applyRow(row);
    } catch (err) {
      console.error('Canvas refresh failed:', err);
    }
  }, [applyRow, isOwnWrite]);

  // Hand this instance's refresh() to the module-level catchUp() the AppState
  // foreground listener calls. Last mount wins; unregisters on unmount.
  useEffect(() => {
    activeRefresh = refresh;
    return () => { if (activeRefresh === refresh) activeRefresh = null; };
  }, [refresh]);

  // Mount, sync turned ON, or the account changed → immediate fetch + apply, so
  // the board shows whatever another device left on the shared row (including a
  // cleared board) instead of waiting for the next realtime event. Re-running is
  // harmless: applyRow is idempotent per row version.
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
