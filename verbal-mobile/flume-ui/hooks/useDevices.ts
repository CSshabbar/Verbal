/**
 * useDevices — the account's other online devices + the "target" a new dictation
 * is sent to.
 *
 * SINGLETON STORE (IDI-177). This used to be a plain hook, and five screens call
 * it (RootNavigator ×2, HomeScreen, RecordingScreen, CanvasScreen) — so there
 * were five independent copies of the state: five registerSelf upserts, five 60s
 * poll loops, and five `targetIdRef`s each seeded once from AsyncStorage. Picking
 * a target on Home mutated Home's copy only; RootNavigator's copy — the one that
 * actually stamps `target_device_id` on the outgoing transcription — never heard
 * about it and kept routing to whatever it had picked at mount. The routing bug
 * was structural, not a race.
 *
 * Now there is ONE module-level store (same shape as historyStore): one poll
 * loop, one registration site, one `target`, published to React through
 * useSyncExternalStore. `useDevices()` keeps its previous return shape, so every
 * caller works unchanged — but they now share a single snapshot, and a
 * setTarget() on Home is visible to RootNavigator on the same tick.
 *
 * Lifecycle: start() is idempotent and runs on the first mount; restart() is for
 * an account change (useAuth.afterSignIn); reset() is sign-out teardown — it
 * stops the poll so a signed-out app makes no device queries at all.
 */
import { useEffect, useSyncExternalStore } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { supabase } from '../../lib/supabase';
import { getCloudUserId, getDeviceId } from '../../lib/storage';
import { registerThisDevice, removeDevice as removeDeviceRow } from '../../lib/deviceSync';

export type DevicePlatform = 'macos' | 'windows' | 'linux';
export type DeviceStatus = 'online' | 'offline';

export type Device = {
  id: string;            // = device_id
  name: string;
  platform: DevicePlatform;
  status: DeviceStatus;
  isDefault: boolean;
  lastSeen?: string;
};

const TARGET_KEY = 'flume_target_device';
// Sentinel values stored in TARGET_KEY beside real device ids — the SAME
// sentinels the desktop dashboard uses for its target ('__all__'/'__none__').
const ALL_SENTINEL = '__all__';
const NONE_SENTINEL = '__none__';
const PRESENCE_MS = 5 * 60 * 1000;
const POLL_MS = 60_000;

/** Where a finished dictation goes (v2, 2026-08-16):
 *  'device' → the picked target only · 'all' → broadcast (null target row) ·
 *  'none' → THIS PHONE ONLY, no cloud push at all. */
export type SendMode = 'device' | 'all' | 'none';

function toPlatform(deviceType?: string): DevicePlatform {
  const v = String(deviceType ?? '').toLowerCase();
  if (v.includes('win')) return 'windows';
  if (v.includes('linux')) return 'linux';
  return 'macos'; // mac / ios / android / unknown → mac glyph
}

/* ── store internals ─────────────────────────────────────────────────────── */

type Snapshot = { devices: Device[]; target: Device | null; mode: SendMode; ready: boolean };

let snapshot: Snapshot = { devices: [], target: null, mode: 'device', ready: false };
let targetId: string | null = null;
/** The explicit send mode. 'device' with targetId=null means "no explicit
 *  choice yet" → the poll adopts the most-recently-active device (the
 *  long-standing default). 'all' and 'none' are explicit user choices the
 *  poll must never override. */
let sendMode: SendMode = 'device';
/** First register+load has completed — before this the UI must say
 *  "Finding devices…" instead of claiming there is no device (the exact lie
 *  behind "it said No device but sent to my laptop"). */
let ready = false;
let targetHydrated = false;
let started = false;
let poll: ReturnType<typeof setInterval> | null = null;
let bootstrap: Promise<void> | null = null;
const listeners = new Set<() => void>();

function emit() { listeners.forEach(l => l()); }

function sameDevices(a: Device[], b: Device[]) {
  return a.length === b.length && a.every((d, i) =>
    d.id === b[i].id && d.name === b[i].name &&
    d.isDefault === b[i].isDefault && d.status === b[i].status && d.platform === b[i].platform);
}

/** Publish a new snapshot, skipping the no-op case. With one shared store the
 *  60s poll would otherwise re-render every subscriber every minute even when
 *  nothing about the device list changed. */
function publish(devices: Device[], target: Device | null) {
  if (sameDevices(snapshot.devices, devices)
      && (snapshot.target?.id ?? null) === (target?.id ?? null)
      && snapshot.mode === sendMode && snapshot.ready === ready) return;
  snapshot = { devices, target, mode: sendMode, ready };
  emit();
}

export function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function getSnapshot(): Snapshot { return snapshot; }

async function hydrateTarget() {
  if (targetHydrated) return;
  targetHydrated = true;
  let stored: string | null = null;
  try { stored = await AsyncStorage.getItem(TARGET_KEY); } catch { stored = null; }
  if (stored === ALL_SENTINEL) { sendMode = 'all'; targetId = null; }
  else if (stored === NONE_SENTINEL) { sendMode = 'none'; targetId = null; }
  else { sendMode = 'device'; targetId = stored; }
}

function persistChoice() {
  const v = sendMode === 'all' ? ALL_SENTINEL
    : sendMode === 'none' ? NONE_SENTINEL
    : targetId;
  if (v) AsyncStorage.setItem(TARGET_KEY, v).catch(() => {});
  else AsyncStorage.removeItem(TARGET_KEY).catch(() => {});
}

/** Other devices seen in the last 5 minutes. Self is excluded — you never send
 *  a dictation to the phone you're dictating on. */
async function loadDevices() {
  try {
    const userId = await getCloudUserId();
    const myId = await getDeviceId();
    if (!userId) { publish([], null); return; }   // signed out: nothing to list
    const cutoff = new Date(Date.now() - PRESENCE_MS).toISOString();
    const { data } = await supabase
      .from('devices')
      .select('device_id, device_name, device_type, last_seen')
      .eq('user_id', userId)
      .neq('device_id', myId)
      .gte('last_seen', cutoff)
      // Stable order: keeps the snapshot comparison meaningful and makes the
      // "no target chosen yet" fallback the most-recently-active device.
      .order('last_seen', { ascending: false });

    const list: Device[] = (data ?? []).map((r: any) => ({
      id: r.device_id,
      name: r.device_name || 'Device',
      platform: toPlatform(r.device_type),
      status: 'online',
      isDefault: r.device_id === targetId,
      lastSeen: r.last_seen ?? undefined,
    }));

    // Keep the target valid; the most-recent-device fallback applies ONLY in
    // 'device' mode (an explicit All / This-phone-only choice is never undone).
    let next: Device | null = null;
    if (sendMode === 'device') {
      const stillThere = list.find(d => d.id === targetId) ?? null;
      next = stillThere ?? list[0] ?? null;
      targetId = next?.id ?? null;
    }
    publish(list.map(d => ({ ...d, isDefault: d.id === targetId })), next);
  } catch (err) {
    console.error('Failed to load devices:', err);
  } finally {
    // Even a failed load ends "Finding devices…" — the UI then tells the truth
    // about what it knows instead of hanging on a spinner state.
    if (!ready) { ready = true; publish(snapshot.devices, snapshot.target); }
  }
}

/** One heartbeat tick: refresh this device's row, then re-read the others. */
async function tick() {
  await registerThisDevice();
  await loadDevices();
}

/** Start the singleton. Idempotent — the 2nd…5th mount is a no-op, so there is
 *  exactly one registration and one poll interval for the whole app. Resolves
 *  when the first register+load has landed. */
export function start(): Promise<void> {
  if (started) return bootstrap ?? Promise.resolve();
  started = true;
  poll = setInterval(() => { tick().catch(() => {}); }, POLL_MS);
  bootstrap = (async () => { await hydrateTarget(); await tick(); })().catch(() => {});
  return bootstrap;
}

/** Stop the poll and drop the list, keeping the target selection. Internal. */
function stop() {
  if (poll) { clearInterval(poll); poll = null; }
  started = false;
  bootstrap = null;
}

/** Account change (sign-in / pairing): re-register under the new account and
 *  reload from scratch. Awaited by useAuth so the row exists before it reads
 *  this device's `sync_enabled` back. */
export async function restart(): Promise<void> {
  stop();
  publish([], null);
  await start();
}

/**
 * Sign-out / account-deletion teardown (called from useAuth). Stops the poll —
 * a signed-out app must not keep querying `devices` every 60s — and throws away
 * the list and the target so the next account can't inherit them.
 * (`flume_target_device` itself is removed by storage.clearAccountData.)
 */
export function reset(): void {
  stop();
  targetId = null;
  sendMode = 'device';
  targetHydrated = false;
  ready = false;
  publish([], null);
}

export function refresh(): Promise<void> {
  return tick().catch(() => {});
}

/* ── mutations ───────────────────────────────────────────────────────────── */

export function setTarget(d: Device | null): void {
  // Kept API: setTarget(null) is the Home pills' "All" (broadcast) — the
  // this-phone-only state is set via setSendMode('none').
  targetId = d?.id ?? null;
  sendMode = d ? 'device' : 'all';
  persistChoice();
  publish(snapshot.devices.map(x => ({ ...x, isDefault: x.id === targetId })), d);
}

export function setSendMode(m: SendMode): void {
  if (m === 'device') return;   // pick a device via setTarget instead
  sendMode = m;
  targetId = null;
  persistChoice();
  publish(snapshot.devices.map(x => ({ ...x, isDefault: false })), null);
}

export function makeDefault(id: string): void {
  const chosen = snapshot.devices.find(d => d.id === id) ?? null;
  if (chosen) setTarget(chosen);
}

/** Devices self-register via their own app; kept for the local/manual add path. */
export function pair(d: Device): void {
  if (snapshot.devices.some(x => x.id === d.id)) return;
  publish([...snapshot.devices, d], snapshot.target);
}

/**
 * Remove another device from the account list (IDI-177).
 *
 * Optimistic locally, then the user_id-scoped delete in lib/deviceSync. The
 * device itself keeps working — it re-appears on its next heartbeat if it is
 * still signed in, which is why the confirm copy says so.
 */
export async function removeDevice(id: string): Promise<boolean> {
  const remaining = snapshot.devices.filter(d => d.id !== id);
  const nextTarget = snapshot.target?.id === id ? null : snapshot.target;
  if (snapshot.target?.id === id) { targetId = null; persistChoice(); }
  publish(remaining, nextTarget);
  return removeDeviceRow(id);
}

/* ── React face ──────────────────────────────────────────────────────────── */

export function useDevices() {
  const snap = useSyncExternalStore(subscribe, getSnapshot);
  useEffect(() => { start(); }, []);
  return {
    devices: snap.devices,
    target: snap.target,
    mode: snap.mode,
    ready: snap.ready,
    setTarget,
    setSendMode,
    pair,
    /** Deprecated alias kept for the useDevices.mock.ts contract. */
    unpair: removeDevice,
    removeDevice,
    makeDefault,
    refresh,
  };
}
