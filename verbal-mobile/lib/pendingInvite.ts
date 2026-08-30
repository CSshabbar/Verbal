/**
 * Deep-linked team invites (IDI-216 Phase 2, claim flow).
 *
 * An invite link can arrive at any point in the app's lifecycle — including on a
 * device that isn't signed in yet, which is the COMMON case: the recipient taps
 * the link in their email, the app opens on Welcome, and only then do they sign
 * in with Google. So the token is parked here rather than claimed on the spot,
 * and `claimPendingInvite()` runs again after every sign-in.
 *
 * Single-use by construction: the token is REMOVED before the claim is attempted.
 * A failed claim (expired, wrong address, no seats) must not leave a token that
 * silently retries on every future launch — the user is shown the reason once and
 * can paste the link again on the Team screen.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'flume_pending_invite';

/** True if this URL is a Flume team-invite deep link. */
export function isInviteUrl(url: string): boolean {
  return typeof url === 'string' && url.indexOf('team-invite') !== -1;
}

/** Pull the token out of `verbal://team-invite?t=<token>` (or an https claim URL).
 *  NB the app's registered scheme is `verbal`, not `flume` — `flume://` appears
 *  only inside the pairing QR payload, which the app PARSES rather than receiving
 *  from the OS, so it never needed to be a registered scheme. */
export function tokenFromUrl(url: string): string {
  const m = String(url ?? '').match(/[?&]t=([^&\s]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

export async function setPendingInvite(token: string): Promise<void> {
  try {
    if (token) await AsyncStorage.setItem(KEY, token);
  } catch {
    // best effort — the user can still paste the link on the Team screen
  }
}

/** Read and CLEAR the parked token. */
export async function takePendingInvite(): Promise<string> {
  try {
    const t = await AsyncStorage.getItem(KEY);
    if (t) await AsyncStorage.removeItem(KEY);
    return t ?? '';
  } catch {
    return '';
  }
}

export type PendingClaim = { claimed: boolean; error?: string };

/**
 * Claim a parked invite, if there is one. Safe to call unconditionally — with no
 * parked token it resolves to `{ claimed: false }` and touches nothing.
 *
 * Fails closed: never throws, so it can be awaited from the sign-in path without
 * any risk of wedging it.
 */
export async function claimPendingInvite(): Promise<PendingClaim> {
  const token = await takePendingInvite();
  if (!token) return { claimed: false };
  try {
    const { claimInvite } = await import('./organizations');
    const res = await claimInvite(token);
    return res.ok ? { claimed: true } : { claimed: false, error: res.error };
  } catch {
    return { claimed: false, error: "Couldn't reach the team service" };
  }
}
