/**
 * Device pairing (QR claim) — the scanning device's half.
 *
 * The host (e.g. the Mac) shows a QR encoding `flume://pair?t=<token>`. We
 * extract the token, look up the short-lived single-use pairing row, stamp it
 * claimed, then adopt the host's account (user_id) and turn on sync.
 *
 * Mirrors whisperflow/app/pairing.py + the `pairings` table.
 */
import { supabase } from './supabase';
import {
  setUserId, setPairedUserId, setSyncEnabled,
  getDeviceName, getDeviceId, getStoredUserId, clearAccountData,
} from './storage';

export type PairResult = { userId: string; hostDevice: string };

/** Pull the token out of a `flume://pair?t=…` payload, or accept a raw code. */
export function extractToken(payload: string): string | null {
  if (!payload) return null;
  const p = payload.trim();
  const m = p.match(/[?&]t=([^&\s]+)/);
  if (m) return decodeURIComponent(m[1]);
  if (/^[A-Za-z0-9_-]{4,64}$/.test(p)) return p; // raw token / manual entry
  return null;
}

export async function claimPairing(payload: string): Promise<PairResult> {
  const token = extractToken(payload);
  if (!token) throw new Error('That’s not a Flume pairing code.');

  const nowIso = new Date().toISOString();

  // 1) find a valid, unclaimed, unexpired row
  const { data: rows, error } = await supabase
    .from('pairings')
    .select('id,user_id,host_device')
    .eq('token', token)
    .is('claimed_by', null)
    .gt('expires_at', nowIso)
    .limit(1);
  if (error) throw new Error(error.message);
  if (!rows || rows.length === 0) {
    throw new Error('This code is invalid, already used, or expired.');
  }
  const row = rows[0] as { id: string; user_id: string; host_device: string | null };

  // 2) claim it (single-use: only rows still unclaimed match)
  const deviceName = await getDeviceName();
  const { data: upd, error: uErr } = await supabase
    .from('pairings')
    .update({ claimed_by: deviceName, claimed_at: nowIso })
    .eq('id', row.id)
    .is('claimed_by', null)
    .select('id');
  if (uErr) throw new Error(uErr.message);
  if (!upd || upd.length === 0) {
    throw new Error('This code was just used by another device.');
  }

  // 3) adopt the host account (IDI-156).
  // Account-switch teardown FIRST — same rule as useAuth.afterSignIn: the
  // previous account's cached history/notes/dictionary must never back-fill
  // into the host's account. (The caller resets UI-layer stores — see the
  // PairDevice onScan handler; lib/ must not import from flume-ui/.)
  const prev = await getStoredUserId();
  if (prev && prev !== row.user_id) {
    try { await clearAccountData(); } catch { /* best effort */ }
  }
  // The paired override OUTRANKS the local Supabase session id in getUserId() —
  // plain setUserId() alone is reverted by the session write-back within ms.
  await setPairedUserId(row.user_id);
  await setUserId(row.user_id);
  await setSyncEnabled(true);

  // Register this device under the host account so it shows up in Devices
  // lists on the host's other devices. Best-effort — pairing already succeeded.
  try {
    const deviceId = await getDeviceId();
    await supabase.from('devices').upsert(
      { user_id: row.user_id, device_id: deviceId, device_name: deviceName,
        device_type: 'ios', last_seen: new Date().toISOString() },
      { onConflict: 'user_id,device_id' });
  } catch { /* best effort */ }

  return { userId: row.user_id, hostDevice: row.host_device || '' };
}
