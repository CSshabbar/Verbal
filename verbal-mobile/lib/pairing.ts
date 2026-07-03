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
import { setUserId, setSyncEnabled, getDeviceName } from './storage';

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

  // 3) adopt the host account + enable sync
  await setUserId(row.user_id);
  await setSyncEnabled(true);

  return { userId: row.user_id, hostDevice: row.host_device || '' };
}
