/**
 * useCanvas — the shared clipboard, presented honestly (M1 redesign, 2026-08-17).
 *
 * The backend is ONE shared `canvas` row per account ({content, image_url}).
 * The old hook dressed that up as a multi-card board; this contract says what
 * is true instead:
 *   - `live`  — the current shared slot: payload + who put it there + when +
 *     whether it was this device. The single source the hero card renders.
 *   - `feed`  — a DEVICE-LOCAL log of what this device sent/received (bounded,
 *     persisted in AsyncStorage `verbal_canvas_log`, account-wiped on sign-out).
 *     The backend keeps no history; this never pretends to be synced.
 *   - `sendText(text)` / `sendPhoto()` — the composer's two verbs. A text that
 *     looks like a URL becomes kind 'link' automatically.
 *   - `copyLive()` / `clearLive()` — the hero card's actions.
 *
 * All the battle-tested sync machinery is unchanged: selective-column writes
 * (IDI-173 — text never blanks the image), explicit clears receivers APPLY,
 * device_id own-echo filtering, live sync-toggle gating, channel rejoin with
 * backoff, reset()/catchUp() lifecycle (Hard Rule #28).
 *
 * Contract mirror: useCanvas.mock.ts — keep in sync in the same change.
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import * as Clipboard from 'expo-clipboard';
import * as ImagePicker from 'expo-image-picker';
import * as Haptics from 'expo-haptics';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { supabase, SUPABASE_URL, SUPABASE_ANON_KEY } from '../../lib/supabase';
import { getUserId, getDeviceName, getDeviceId } from '../../lib/storage';
import * as syncStore from '../../lib/syncStore';
import { useSyncEnabled } from './useSyncEnabled';

export type CanvasKind = 'text' | 'link' | 'image';

/** What is on the shared row right now. `null` until the first fetch. */
export type LiveSlot = {
  kind: CanvasKind | 'empty';
  text?: string;
  imageUrl?: string | null;
  /** Display name of the writing device ("Muhammad's Mac"), '' when unknown. */
  from: string;
  /** True when this device wrote it. */
  own: boolean;
  /** ISO timestamp of the write (row.updated_at), '' when unknown. */
  at: string;
};

export type FeedEntry = {
  id: string;
  kind: CanvasKind;
  /** The full text/url for text-likes; a label for images. */
  text: string;
  imageUrl?: string;
  from: string;
  own: boolean;
  at: string;          // ISO
};

const FEED_KEY = 'verbal_canvas_log';
const FEED_CAP = 20;

type CanvasRow = {
  content?: string | null;
  image_url?: string | null;
  device_name?: string | null;
  device_id?: string | null;
  updated_at?: string | null;
};

function rowSignature(row: CanvasRow): string {
  return `${row.updated_at ?? ''}|${row.image_url ?? ''}|${row.content ?? ''}`;
}
const isUrl = (s: string) => /^https?:\/\/\S+$/i.test(s.trim());

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

/* ── module-level lifecycle surface (Hard Rule #28) ─────────────────────── */

let accountEpoch = 0;
const epochListeners = new Set<() => void>();
let activeRefresh: (() => Promise<void>) | null = null;

/** Account switch / sign-out: drop state + re-key the channel. The persisted
 *  feed is wiped by storage.clearAccountData (it owns the AsyncStorage key). */
export function reset() {
  accountEpoch += 1;
  epochListeners.forEach((l) => { try { l(); } catch { /* ignore */ } });
}

/** Foreground catch-up — pull the shared row we may have missed. */
export async function catchUp() {
  if (!(await syncStore.getSyncEnabled())) return;
  try { await activeRefresh?.(); } catch { /* best effort */ }
}

export function useCanvas() {
  const [live, setLive] = useState<LiveSlot | null>(null);
  const [feed, setFeed] = useState<FeedEntry[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const channelRef = useRef<ReturnType<typeof supabase.channel> | null>(null);
  const myNameRef = useRef<string>('');
  const myDeviceIdRef = useRef<string>('');
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const syncEnabled = useSyncEnabled();
  const [epoch, setEpoch] = useState(accountEpoch);
  const lastAppliedRef = useRef<string | null>(null);
  const feedRef = useRef<FeedEntry[]>([]);

  useEffect(() => {
    const listener = () => {
      setEpoch(accountEpoch);
      setLive(null);
      setFeed([]);
      feedRef.current = [];
      lastAppliedRef.current = null;
    };
    epochListeners.add(listener);
    return () => { epochListeners.delete(listener); };
  }, []);

  // Load the persisted local log once (and after account switches).
  useEffect(() => {
    AsyncStorage.getItem(FEED_KEY)
      .then(raw => {
        if (!raw) return;
        const arr = JSON.parse(raw);
        if (Array.isArray(arr)) { feedRef.current = arr; setFeed(arr); }
      })
      .catch(() => {});
  }, [epoch]);

  const persistFeed = useCallback((entries: FeedEntry[]) => {
    feedRef.current = entries;
    setFeed(entries);
    AsyncStorage.setItem(FEED_KEY, JSON.stringify(entries)).catch(() => {});
  }, []);

  const logFeed = useCallback((e: Omit<FeedEntry, 'id'>) => {
    const id = `f_${Date.now()}_${Math.floor(Math.random() * 1e6)}`;
    // Collapse an immediate duplicate (same payload re-applied).
    const top = feedRef.current[0];
    if (top && top.kind === e.kind && top.text === e.text && top.imageUrl === e.imageUrl) return;
    persistFeed([{ id, ...e }, ...feedRef.current].slice(0, FEED_CAP));
  }, [persistFeed]);

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

  /** The single place a shared-row version becomes UI — realtime + fetch share it. */
  const applyRow = useCallback(async (row: CanvasRow, opts: { announce?: boolean; own?: boolean } = {}) => {
    const signature = rowSignature(row);
    if (signature === lastAppliedRef.current) return;
    lastAppliedRef.current = signature;

    const imageUrl = (row.image_url ?? null) as string | null;
    const content = (row.content ?? '') as string;
    const own = !!opts.own;
    const who = own ? 'this phone' : (row.device_name || 'another device');
    const at = row.updated_at ?? '';

    if (!imageUrl && !content) {
      setLive({ kind: 'empty', from: who, own, at });
      if (opts.announce) flashToast(`Canvas cleared from ${who}`);
      return;
    }

    if (imageUrl) {
      setLive({ kind: 'image', imageUrl, text: content || undefined, from: who, own, at });
      logFeed({ kind: 'image', text: 'Image', imageUrl, from: who, own, at: at || new Date().toISOString() });
      if (!own) {
        await Clipboard.setStringAsync(imageUrl);
        if (opts.announce) {
          flashToast(`Received image from ${who} — link copied`);
          await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        }
      }
      return;
    }

    const kind: CanvasKind = isUrl(content) ? 'link' : 'text';
    setLive({ kind, text: content, from: who, own, at });
    logFeed({ kind, text: content, from: who, own, at: at || new Date().toISOString() });
    if (!own) {
      await Clipboard.setStringAsync(content);
      if (opts.announce) {
        flashToast(`Received from ${who} — copied to clipboard`);
        await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
    }
  }, [flashToast, logFeed]);

  const isOwnWrite = useCallback((row: CanvasRow) => {
    if (row.device_id) return row.device_id === myDeviceIdRef.current;
    return !!myNameRef.current && (row.device_name ?? '') === myNameRef.current;
  }, []);

  // Realtime channel — unchanged lifecycle (live toggle + epoch + rejoin).
  useEffect(() => {
    if (!syncEnabled) return;
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
            if (!row || Object.keys(row).length === 0) {
              lastAppliedRef.current = null;
              setLive({ kind: 'empty', from: '', own: false, at: '' });
              return;
            }
            if (isOwnWrite(row)) {
              // Our own echo: the send path already updated `live` — just
              // record the version so a refresh doesn't re-apply it.
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
          if (channelRef.current !== ch) return;
          if (rejoinTimer) return;
          const delay = Math.min(30_000, 1_000 * 2 ** rejoinAttempts);
          rejoinAttempts += 1;
          rejoinTimer = setTimeout(() => {
            rejoinTimer = null;
            if (!active) return;
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

  /** Selective-column shared-row write (IDI-173) — the single writer. */
  const pushToShared = useCallback(async (payload: { content?: string | null; image_url?: string | null }) => {
    if (!(await syncStore.getSyncEnabled())) {
      flashToast('Sync is off — nothing was sent');
      throw new Error('sync off');
    }
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
    if (error) throw error;
    return row.updated_at as string;
  }, [flashToast]);

  /** Composer verb 1: send text (a URL-looking text becomes kind 'link'). */
  const sendText = useCallback(async (text: string): Promise<boolean> => {
    const t = text.trim();
    if (!t) return false;
    try {
      const at = await pushToShared({ content: t });
      lastAppliedRef.current = `${at}|${''}|${t}`;   // matches the echo's signature shape
      setLive({ kind: isUrl(t) ? 'link' : 'text', text: t, from: 'this phone', own: true, at });
      logFeed({ kind: isUrl(t) ? 'link' : 'text', text: t, from: 'this phone', own: true, at });
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      return true;
    } catch (err) {
      console.error('Canvas send failed:', err);
      if (String(err).indexOf('sync off') === -1) flashToast('Send failed — try again');
      return false;
    }
  }, [pushToShared, logFeed, flashToast]);

  /** Composer verb 2: pick a photo → upload → send. */
  const sendPhoto = useCallback(async (): Promise<boolean> => {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) return false;
      const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.8 });
      if (res.canceled || !res.assets?.length) return false;
      const a = res.assets[0];
      flashToast('Uploading image…');
      const url = await uploadImage(a.uri);
      if (!url) {
        flashToast('Image upload failed — check your connection');
        await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
        return false;
      }
      const at = await pushToShared({ image_url: url });
      lastAppliedRef.current = `${at}|${url}|${''}`;
      setLive({ kind: 'image', imageUrl: url, from: 'this phone', own: true, at });
      logFeed({ kind: 'image', text: 'Image', imageUrl: url, from: 'this phone', own: true, at });
      dismissToast();
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      return true;
    } catch (err) {
      console.error('Canvas photo send failed:', err);
      if (String(err).indexOf('sync off') === -1) flashToast('Send failed — try again');
      return false;
    }
  }, [pushToShared, logFeed, flashToast, dismissToast]);

  /** Hero action: copy whatever is live. */
  const copyLive = useCallback(async () => {
    if (!live || live.kind === 'empty') return;
    await Clipboard.setStringAsync(live.kind === 'image' ? (live.imageUrl ?? '') : (live.text ?? ''));
    flashToast('Copied');
    await Haptics.selectionAsync();
  }, [live, flashToast]);

  /** Hero action: explicit clear — every device applies it (IDI-173). */
  const clearLive = useCallback(async () => {
    try {
      const at = await pushToShared({ content: '', image_url: null });
      lastAppliedRef.current = `${at}||`;
      setLive({ kind: 'empty', from: 'this phone', own: true, at });
    } catch (err) {
      console.error('Canvas clear failed:', err);
      if (String(err).indexOf('sync off') === -1) flashToast('Clear failed — try again');
    }
  }, [pushToShared, flashToast]);

  /** Copy any feed entry back to the clipboard. */
  const copyFeedEntry = useCallback(async (id: string) => {
    const e = feedRef.current.find(x => x.id === id);
    if (!e) return;
    await Clipboard.setStringAsync(e.kind === 'image' ? (e.imageUrl ?? '') : e.text);
    flashToast('Copied');
  }, [flashToast]);

  /** Fetch-and-apply the current shared row (mount / toggle-ON / foreground). */
  const refresh = useCallback(async () => {
    try {
      if (!(await syncStore.getSyncEnabled())) return;
      const userId = await getUserId();
      myDeviceIdRef.current = await getDeviceId();
      if (!myNameRef.current) myNameRef.current = await getDeviceName();
      const { data } = await supabase
        .from('canvas').select('content,image_url,device_name,device_id,updated_at')
        .eq('user_id', userId).maybeSingle();
      if (!data) { setLive({ kind: 'empty', from: '', own: false, at: '' }); return; }
      const row = data as CanvasRow;
      // Own rows are APPLIED too now — the hero card shows this device's last
      // send with own:true (the old board hid them, which read as data loss).
      await applyRow(row, { own: isOwnWrite(row) });
    } catch (err) {
      console.error('Canvas refresh failed:', err);
    }
  }, [applyRow, isOwnWrite]);

  useEffect(() => {
    activeRefresh = refresh;
    return () => { if (activeRefresh === refresh) activeRefresh = null; };
  }, [refresh]);

  useEffect(() => {
    if (!syncEnabled) return;
    refresh().catch(() => { /* best effort */ });
  }, [syncEnabled, epoch, refresh]);

  return {
    live, feed,
    sendText, sendPhoto,
    copyLive, clearLive, copyFeedEntry,
    refresh, toast, dismissToast,
  };
}
