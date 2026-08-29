/**
 * Device pairing (QR claim) — the scanning device's half.
 *
 * The host (e.g. the Mac) shows a QR encoding `flume://pair?t=<token>`. We
 * extract the token, look up the short-lived single-use pairing row, stamp it
 * claimed, verify this device is signed in as the same account, then enable
 * sync and register the device.
 *
 * Since IDI-29 pairing CONFIRMS an account rather than granting one: `auth.uid()`
 * RLS means only a real session can read the host's data.
 *
 * Mirrors whisperflow/app/pairing.py + the `pairings` table.
 */
import { supabase } from './supabase';
import {
  setUserId, setSyncEnabled,
  getDeviceName, getStoredUserId, clearAccountData,
} from './storage';
import { registerThisDevice } from './deviceSync';

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

  // 3) Confirm this device is ALREADY signed in as the host account (IDI-29).
  // Pairing used to ADOPT the host's user_id, granting cloud access to a device
  // holding no session for that account. Under `auth.uid()` RLS that is no
  // longer expressible: policies read the JWT, so an adopted id reads zero rows
  // and fails every write. Rather than let pairing appear to succeed and then
  // sync nothing, refuse the claim with an actionable message. The pairing row
  // is already stamped claimed at this point — single-use is preserved, and the
  // host can simply show a new code.
  const { data: sess } = await supabase.auth.getSession();
  const sessionUid = sess.session?.user?.id ?? null;
  if (!sessionUid) {
    throw new Error('Sign in to Flume on this device first, then scan the code again.');
  }
  if (sessionUid !== row.user_id) {
    throw new Error(
      'This code belongs to a different Flume account. Sign in with the same account as the host device, then scan again.',
    );
  }

  // Same account, so there is no cross-account cache to tear down in the normal
  // case — but a stale local id from a previous account must still not survive.
  const prev = await getStoredUserId();
  if (prev && prev !== row.user_id) {
    try { await clearAccountData(); } catch { /* best effort */ }
  }
  await setUserId(row.user_id);
  await setSyncEnabled(true);

  // Register this device under the host account so it shows up in Devices
  // lists on the host's other devices. Best-effort — pairing already succeeded.
  // Goes through the one registration site (IDI-177) so device_type is
  // Platform.OS, not the 'ios' literal this used to write on Android too.
  await registerThisDevice(row.user_id);

  return { userId: row.user_id, hostDevice: row.host_device || '' };
}
