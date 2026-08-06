/**
 * Account devices + per-device sync — shared by the sign-in DevicesSyncSheet and
 * the Devices screen. Backed by the cloud `devices.sync_enabled` column.
 * Toggling THIS device also writes the local sync store (lib/syncStore), which
 * is what actually drives realtime on this device — so the Devices self-row, the
 * Menu toggle and the Settings toggle can never disagree (IDI-171).
 */
import { supabase } from './supabase';
import { getUserId, getDeviceId } from './storage';
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

/** Every device on the current account, self marked, most-recent first. */
export async function fetchAccountDevices(): Promise<AccountDevice[]> {
  try {
    const uid = await getUserId();
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

/** Set a device's sync flag in the cloud; write the local store when it's this
 *  device (which also fires the live catch-up / teardown listeners). */
export async function setDeviceSync(deviceId: string, value: boolean): Promise<void> {
  try {
    const uid = await getUserId();
    const myId = await getDeviceId();
    if (deviceId === myId) await setSyncEnabled(value);
    await supabase
      .from('devices')
      .update({ sync_enabled: value })
      .eq('user_id', uid)
      .eq('device_id', deviceId);
  } catch {
    /* fail-closed; caller keeps optimistic UI */
  }
}
