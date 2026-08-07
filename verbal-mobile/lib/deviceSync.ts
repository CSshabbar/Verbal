/**
 * Account devices — the single cloud-facing device layer (IDI-177).
 *
 * Owns three things, and is the ONLY place any of them is written:
 *   1. registerThisDevice() — the one upsert/heartbeat for this device's row.
 *      Every registration site in the app (the useDevices store, useAuth's
 *      post-sign-in block) funnels through here, so `device_type` can never
 *      drift again: it is `Platform.OS` ('ios' | 'android'), not a hardcoded
 *      'ios'/'iphone' literal that lied on the other platform.
 *   2. fetchAccountDevices() — every device on the account, self marked.
 *   3. removeDevice() — drop a row from the account list, scoped by user_id.
 *
 * Per-device sync is SELF-ONLY (IDI-177). The old setDeviceSync(deviceId, …)
 * let this phone write `sync_enabled` on a DESKTOP's row — but no desktop ever
 * reads that column, so the switch was remote control wired to nothing. The
 * replacement, setThisDeviceSync(value), can't address another device at all:
 * it writes the local sync store (lib/syncStore — what actually gates realtime
 * here) and mirrors the value onto THIS device's cloud row for display.
 */
import { Platform } from 'react-native';
import { supabase } from './supabase';
import { getCloudUserId, getDeviceId, getDeviceName } from './storage';
import { setSyncEnabled } from './syncStore';

export type AccountDevice = {
  deviceId: string;
  name: string;
  type: string | null;
  lastSeen: string | null;
  syncEnabled: boolean;
  isSelf: boolean;
};

const PRESENCE_MS = 5 * 60 * 1000;
export const isDeviceOnline = (d: AccountDevice) =>
  !!d.lastSeen && Date.now() - new Date(d.lastSeen).getTime() < PRESENCE_MS;

/** This device's honest `devices.device_type`: 'ios' | 'android'. */
export function thisDeviceType(): string {
  return Platform.OS;
}

/**
 * Register / heartbeat this device's row. The ONLY registration site.
 *
 * `onConflict: 'user_id,device_id'` matches the table's unique constraint, so
 * this is a true upsert — repeated calls (start-up, the 60s heartbeat, a
 * sign-in) update one row instead of accumulating duplicates.
 *
 * Gated on getCloudUserId(): signed out there is no account to attach the row
 * to, and writing under a locally-minted `user_…` id just litters the table.
 */
export async function registerThisDevice(userId?: string | null): Promise<void> {
  try {
    const uid = userId ?? (await getCloudUserId());
    if (!uid) return;
    const deviceId = await getDeviceId();
    const deviceName = await getDeviceName();
    await supabase.from('devices').upsert(
      {
        user_id: uid,
        device_id: deviceId,
        device_name: deviceName,
        device_type: thisDeviceType(),
        last_seen: new Date().toISOString(),
      },
      { onConflict: 'user_id,device_id' },
    );
  } catch (err) {
    console.warn('Failed to register device:', err);
  }
}

/** Every device on the current account, self marked, most-recent first. */
export async function fetchAccountDevices(): Promise<AccountDevice[]> {
  try {
    const uid = await getCloudUserId();
    const myId = await getDeviceId();
    if (!uid) return [];
    const { data } = await supabase
      .from('devices')
      .select('device_id,device_name,device_type,last_seen,sync_enabled')
      .eq('user_id', uid)
      .order('last_seen', { ascending: false });
    return ((data as any[]) || []).map((r) => ({
      deviceId: r.device_id,
      name: r.device_name || 'Device',
      type: r.device_type ?? null,
      lastSeen: r.last_seen ?? null,
      syncEnabled: r.sync_enabled !== false,
      isSelf: r.device_id === myId,
    }));
  } catch {
    return [];
  }
}

/**
 * Sync switch for THIS device. There is deliberately no deviceId parameter —
 * see the header: writing another device's flag controlled nothing.
 *
 * setSyncEnabled() first (it fires the live catch-up / teardown listeners), then
 * mirror to the cloud column so other devices' lists can display it.
 */
export async function setThisDeviceSync(value: boolean): Promise<void> {
  try {
    await setSyncEnabled(value);
  } catch { /* local store is best-effort too; never strand the UI */ }
  try {
    const uid = await getCloudUserId();
    const myId = await getDeviceId();
    if (!uid) return;
    await supabase
      .from('devices')
      .update({ sync_enabled: value })
      .eq('user_id', uid)
      .eq('device_id', myId);
  } catch {
    /* fail-closed; the local store already has the real value */
  }
}

/**
 * Remove a device from the account list.
 *
 * `.eq('user_id', uid)` is load-bearing: the old delete matched on device_id
 * ALONE, so under permissive RLS a guessed/collided device_id could delete
 * another tenant's row. Scoping by user_id makes the statement unable to reach
 * outside the caller's account regardless of what RLS does or doesn't enforce.
 *
 * Removal is list-level only — the device keeps working until it signs out, and
 * re-registers itself on its next heartbeat if it's still signed in.
 */
export async function removeDevice(deviceId: string): Promise<boolean> {
  try {
    const uid = await getCloudUserId();
    if (!uid || !deviceId) return false;
    const { error } = await supabase
      .from('devices')
      .delete()
      .eq('user_id', uid)
      .eq('device_id', deviceId);
    if (error) { console.warn('Failed to remove device:', error); return false; }
    return true;
  } catch (err) {
    console.warn('Failed to remove device:', err);
    return false;
  }
}
