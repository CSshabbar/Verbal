/**
 * useAuth — MOCK (contract reference, never imported at runtime).
 * Same exported shape as ./useAuth, backed by in-memory state, so it is a
 * drop-in replacement anywhere a screen imports the real hook.
 *
 * Real hook: Google sign-in via Supabase Auth. Apple/email are contract stubs
 * (the UI only offers Google) and `deleteAccount` hits the `delete-account`
 * Edge Function; here they are local no-ops.
 */
import { useState, useCallback } from 'react';

export type User = {
  id: string;
  email: string;
  firstName?: string;
  avatarUrl?: string;
};

export function useAuth() {
  const [user, setUser] = useState<User | null>({
    // MOCK — remove for prod and start with null.
    id: 'u_1',
    email: 'aman@example.com',
    firstName: 'Aman',
  });
  const [isLoading, setLoading] = useState(false);
  // Involuntary sign-out (IDI-166) and post-deletion (MER-32/IDI-170) notices.
  // WelcomeScreen renders them; accountDeleted outranks sessionExpired.
  const [sessionExpired, setSessionExpired] = useState(false);
  const [accountDeleted, setAccountDeleted] = useState(false);

  const signInWithGoogle = useCallback(async () => {
    setLoading(true);
    setSessionExpired(false);
    setAccountDeleted(false);   // shown once — a new sign-in retires the notice
    setUser({ id: 'u_1', email: 'aman@example.com', firstName: 'Aman' });
    setTimeout(() => setLoading(false), 600);
  }, []);

  // Contract stubs — the UI only offers Google.
  const signInWithApple = useCallback(async () => {}, []);
  const signInWithEmail = useCallback(async () => {}, []);

  const signOut = useCallback(async () => {
    setSessionExpired(false);   // intentional — don't show "session expired"
    setUser(null);
  }, []);

  const deleteAccount = useCallback(async (): Promise<{ ok: boolean; error?: string }> => {
    setSessionExpired(false);
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
    signInWithApple,
    signInWithEmail,
    signOut,
    deleteAccount,
  };
}
