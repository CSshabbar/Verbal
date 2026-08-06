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

  // 1+2) atomic single-use claim via the `claim_pairing` RPC (IDI-157): the
  // server validates expiry on ITS clock and stamps claimed_by in one guarded
  // UPDATE — the table itself is no longer readable/writable over REST, so
  // there is no select-then-patch race and no user_id enumeration surface.
  const deviceName = await getDeviceName();
  const { data, error } = await supabase.rpc('claim_pairing', {
    p_token: token,
    p_device_name: deviceName,
  });
  if (error) throw new Error(error.message);
  const rows = (Array.isArray(data) ? data : data ? [data] : []) as
    { user_id: string; host_device: string | null }[];
  if (rows.length === 0 || !rows[0]?.user_id) {
    throw new Error('This code is invalid, already used, or expired.');
  }
  const row = rows[0];

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
