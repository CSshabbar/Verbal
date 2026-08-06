/**
 * useAuth — Google sign-in via Supabase Auth (OAuth + `verbal://auth-callback`
 * deep link). Google is the only real method; Apple/email are kept as stubs to
 * preserve the hook contract but aren't offered in the UI.
 *
 * On sign-in we adopt the Supabase user id as the app's data key (setUserId) so
 * dictation / notes / canvas / recordings all sync under the real account, then
 * register this device and offer to sync if the account is already on others.
 */
import { useState, useCallback, useEffect } from 'react';
import { Linking } from 'react-native';
import * as WebBrowser from 'expo-web-browser';
import * as QueryParams from 'expo-auth-session/build/QueryParams';
import { supabase, SUPABASE_URL, SUPABASE_ANON_KEY } from '../../lib/supabase';
import { setUserId, setPairedUserId, getDeviceName, getDeviceId, getStoredUserId, clearAccountData } from '../../lib/storage';
import { setSyncEnabled } from '../../lib/syncStore';
import { clearKeyboardConfig } from '../../lib/keyboardBridge';
import * as recordings from '../../lib/recordings';
import * as historyStore from './historyStore';
import * as canvasStore from './useCanvas';
import { notify } from '../components/ConfirmDialog';
import { showDevicesSheet } from '../components/DevicesSyncSheet';

WebBrowser.maybeCompleteAuthSession();

export type User = {
  id: string;
  email: string;
  firstName?: string;
  avatarUrl?: string;
};

// Hardcoded to the exact value whitelisted in Supabase (Redirect URLs).
// Using makeRedirectUri() is nondeterministic (returns exp:// in Expo Go), which
// makes Supabase fall back to its Site URL (localhost:3000). This deep link only
// resolves in a DEV BUILD — Expo Go cannot handle the `verbal://` scheme.
const redirectTo = 'verbal://auth-callback';

function fromSupabaseUser(u: { id: string; email?: string | null; user_metadata?: any }): User {
  const name =
    u.user_metadata?.name ||
    u.user_metadata?.full_name ||
    (u.email ? u.email.split('@')[0] : undefined);
  return {
    id: u.id,
    email: u.email ?? '',
    firstName: name,
    avatarUrl: u.user_metadata?.avatar_url,
  };
}

function _parseFragment(url: string): Record<string, string> {
  const out: Record<string, string> = {};
  const hash = url.indexOf('#') !== -1 ? url.substring(url.indexOf('#') + 1) : '';
  if (!hash) return out;
  for (const kv of hash.split('&')) {
    const i = kv.indexOf('=');
    if (i > 0) out[kv.slice(0, i)] = decodeURIComponent(kv.slice(i + 1));
  }
  return out;
}

// A given auth code can only be exchanged once — both the browser result and the
// deep-link listener may fire for the same URL, so remember what we've handled.
const _handledCodes = new Set<string>();

// Involuntary sign-out detection (IDI-166): when the session dies WITHOUT the
// user tapping Sign out (revoked/expired refresh token), RootNavigator teleports
// to Welcome with zero explanation. Track intent module-level so every hook
// instance agrees; WelcomeScreen renders the notice.
let _explicitSignOut = false;
let _hadUser = false;
let _sessionExpired = false;
// Sibling flag for MER-32 / IDI-170: after a SUCCESSFUL account deletion the app
// teleports to Welcome exactly like a sign-out, with no confirmation that the
// irreversible thing actually happened. Set on success, cleared on the next
// sign-in; WelcomeScreen renders it and it outranks the expired notice.
let _accountDeleted = false;

/**
 * Local teardown shared by signOut and deleteAccount (IDI-170).
 *
 * Every step is best-effort and must never throw — a failure here cannot be
 * allowed to strand the user in a half-signed-out state.
 *
 * `wipeRecordings` is only true for deletion / an account switch: a plain
 * sign-out keeps the local audio so the same user can still retry a failed
 * dictation after signing back in.
 */
async function teardownLocalAccountState(wipeRecordings: boolean) {
  try { await setSyncEnabled(false); } catch { /* ignore */ }
  try { await clearAccountData(); } catch { /* ignore */ }
  try { await historyStore.reset(); } catch { /* ignore */ }
  try { canvasStore.reset(); } catch { /* ignore */ }
  // clearAccountData() is AsyncStorage-only, so the native keyboard's snapshot
  // (last 15 dictations + vocabulary + snippets) outlived it. Wiped here rather
  // than inside clearAccountData because keyboardBridge imports lib/storage —
  // calling it from there would be an import cycle.
  try { await clearKeyboardConfig(); } catch { /* ignore */ }
  if (wipeRecordings) {
    try { await recordings.removeAll(); } catch { /* ignore */ }
  }
}

/** Turn a returned OAuth deep link into a Supabase session.
 *  Handles PKCE (`?code=`) and, as a fallback, implicit (`#access_token=`). */
async function createSessionFromUrl(url: string) {
  const { params, errorCode } = QueryParams.getQueryParams(url);
  if (errorCode) throw new Error(errorCode);
  if (params.code) {
    if (_handledCodes.has(params.code)) return null;  // already exchanged
    _handledCodes.add(params.code);
    const { data, error } = await supabase.auth.exchangeCodeForSession(params.code);
    if (error) throw error;
    return data.session ?? null;
  }
  const frag = _parseFragment(url);
  if (frag.error_description) throw new Error(frag.error_description);
  if (frag.access_token && frag.refresh_token) {
    const { data, error } = await supabase.auth.setSession({
      access_token: frag.access_token, refresh_token: frag.refresh_token });
    if (error) throw error;
    return data.session ?? null;
  }
  return null;
}

async function afterSignIn(session: any) {
  const uid = session?.user?.id;
  if (!uid) return;
  // Account switch: if this device was last used by a DIFFERENT account, wipe the
  // previous account's cached data before adopting the new id — otherwise the new
  // account inherits the old one's history/notes/devices (the cross-account leak).
  const prev = await getStoredUserId();
  if (prev && prev !== uid) {
    try { await clearAccountData(); } catch { /* ignore */ }
    try { await historyStore.reset(); } catch { /* ignore */ }
    // Canvas kept the previous account's board + a channel keyed to the old uid.
    try { canvasStore.reset(); } catch { /* ignore */ }
    // …and the previous account's audio files sat in documentDirectory, where
    // the new account's History could still play them (IDI-170).
    try { await recordings.removeAll(); } catch { /* ignore */ }
    try { await clearKeyboardConfig(); } catch { /* ignore */ }
  }
  // A real sign-in supersedes any paired-account override (IDI-156) — the
  // session is now the identity. (An override to a DIFFERENT account was
  // already removed by clearAccountData above.)
  try { await setPairedUserId(null); } catch { /* ignore */ }
  await setUserId(uid);
  // Register this device, reconcile THIS device's sync flag from its cloud row,
  // then show the per-device sync sheet when there are other devices to manage.
  try {
    const deviceName = await getDeviceName();
    const deviceId = await getDeviceId();
    await supabase.from('devices').upsert(
      { user_id: uid, device_id: deviceId, device_name: deviceName,
        device_type: 'ios', last_seen: new Date().toISOString() },
      { onConflict: 'user_id,device_id' });
    // This device's own sync_enabled (default true) drives lib/useSync.
    const { data: mine } = await supabase
      .from('devices').select('sync_enabled')
      .eq('user_id', uid).eq('device_id', deviceId).maybeSingle();
    await setSyncEnabled((mine as any)?.sync_enabled ?? true);
    // Other devices on the account → open the sync sheet so the user can pick
    // which devices sync (per-device, cloud-backed).
    const { data } = await supabase
      .from('devices').select('device_id')
      .eq('user_id', uid).neq('device_id', deviceId);
    if ((data || []).length) {
      await showDevicesSheet();
    }
  } catch (e) {
    console.warn('device detect failed:', e);
    await setSyncEnabled(true);
  }
  // Now that the account id + sync flag are set, (re)pull history from the cloud and
  // open the realtime channel. RootNavigator's useHistory already ran load() once at
  // app start — BEFORE sign-in, with sync off — which trips the `started` guard, so
  // without this explicit refresh the post-login fetch never fires and history stays
  // empty on a fresh install. refresh() re-runs load() unconditionally.
  try { await historyStore.refresh(); } catch { /* ignore */ }
}

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(_sessionExpired);
  const [accountDeleted, setAccountDeleted] = useState(_accountDeleted);

  useEffect(() => {
    let mounted = true;
    supabase.auth.getSession()
      .then(({ data: { session } }) => {
        if (session?.user) { _hadUser = true; }
        if (mounted) { setUser(session?.user ? fromSupabaseUser(session.user) : null); setLoading(false); }
      })
      .catch(() => { if (mounted) { setUser(null); setLoading(false); } });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, session) => {
      if (session?.user) {
        _hadUser = true; _explicitSignOut = false; _sessionExpired = false;
        _accountDeleted = false;   // shown once — a new sign-in retires the notice
      } else if (_hadUser && !_explicitSignOut) {
        // Session died out from under a signed-in user — surface it on Welcome
        // instead of a silent teleport.
        _sessionExpired = true;
      }
      if (mounted) {
        setUser(session?.user ? fromSupabaseUser(session.user) : null);
        setSessionExpired(_sessionExpired);
        setAccountDeleted(_accountDeleted);
      }
    });

    // Catch the OAuth deep link when it reopens the app (Android often returns
    // via the link rather than resolving openAuthSessionAsync).
    const handleUrl = (url: string | null) => {
      if (!url) return;
      const isAuth = url.indexOf('auth-callback') !== -1
        || url.indexOf('code=') !== -1 || url.indexOf('access_token=') !== -1;
      if (!isAuth) return;
      createSessionFromUrl(url)
        .then((s) => { if (s && mounted) { afterSignIn(s); setUser(fromSupabaseUser(s.user)); } })
        .catch((e) => notify('Sign-in error', e?.message || String(e)));
    };
    const linkSub = Linking.addEventListener('url', ({ url }) => handleUrl(url));
    Linking.getInitialURL().then(handleUrl).catch(() => {});

    return () => { mounted = false; subscription.unsubscribe(); linkSub.remove(); };
  }, []);

  const signInWithGoogle = useCallback(async () => {
    setLoading(true);
    try {
      const { data, error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: { redirectTo, skipBrowserRedirect: true },
      });
      if (error) throw error;
      if (!data?.url) throw new Error('Could not start Google sign-in');

      const res = await WebBrowser.openAuthSessionAsync(data.url, redirectTo);
      // Happy path: the browser returns the redirect URL directly.
      // Otherwise (Android reopening via the deep link) the Linking listener
      // in the effect above completes the exchange.
      if (res.type === 'success' && res.url) {
        const session = await createSessionFromUrl(res.url);
        if (session) {
          await afterSignIn(session);
          setUser(fromSupabaseUser(session.user));
        }
      }
    } catch (e: any) {
      notify('Sign-in failed', e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Contract stubs — the UI only offers Google.
  const notAvailable = useCallback(async () => {
    notify('Sign in with Google', 'Google is the only sign-in method right now.');
  }, []);

  const signOut = useCallback(async () => {
    // `scope: 'local'` removes the on-device session immediately (no network
    // round-trip that can hang on a flaky connection) and fires onAuthStateChange
    // in every useAuth instance → RootNavigator flips to Welcome.
    _explicitSignOut = true;   // intentional — don't show "session expired"
    try { await supabase.auth.signOut({ scope: 'local' }); } catch { /* ignore */ }
    // Clear all account-scoped caches, tear down the history + canvas singletons
    // and empty the native keyboard's snapshot so the next account that signs in
    // on this device starts clean (no data leak). Local audio survives a plain
    // sign-out — see teardownLocalAccountState.
    await teardownLocalAccountState(false);
    setUser(null);
  }, []);

  // MER-32: permanently delete the account — server-side (DB rows, storage
  // objects, the auth user itself) via the `delete-account` Edge Function,
  // then the same local teardown as signOut(). Unlike signOut, this can't be
  // undone, so it returns {ok,error} instead of firing-and-forgetting — the
  // caller (Settings) needs the real result before telling the user it's done.
  const deleteAccount = useCallback(async (): Promise<{ ok: boolean; error?: string }> => {
    try {
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token;
      if (!token) return { ok: false, error: 'Not signed in' };
      const res = await fetch(`${SUPABASE_URL}/functions/v1/delete-account`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, apikey: SUPABASE_ANON_KEY },
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !body.ok) return { ok: false, error: body.error || `Server error (${res.status})` };
    } catch (e: any) {
      return { ok: false, error: e?.message || String(e) };
    }
    _explicitSignOut = true;   // intentional — don't show "session expired"
    _accountDeleted = true;    // …show "Your account has been deleted." instead
    try { await supabase.auth.signOut({ scope: 'local' }); } catch { /* ignore */ }
    // Same teardown as signOut PLUS the local recordings directory: the Edge
    // Function erased the cloud copies, but the on-device audio would otherwise
    // outlive the deleted account indefinitely (IDI-170).
    await teardownLocalAccountState(true);
    setAccountDeleted(true);
    setUser(null);
    return { ok: true };
  }, []);

  return {
    user,
    isLoading,
    /** True when the session died involuntarily (expired/revoked) — shown on Welcome. */
    sessionExpired,
    /** True right after a successful account deletion — shown on Welcome, and it
     *  takes precedence over sessionExpired. Cleared by the next sign-in. */
    accountDeleted,
    signInWithGoogle,
    signInWithApple: notAvailable,
    signInWithEmail: notAvailable,
    signOut,
    deleteAccount,
  };
}
