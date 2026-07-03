/**
 * useAuth — sign-in, backed by Supabase auth + expo-secure-store.
 *
 * Contract (consumed by WelcomeScreen / HomeScreen / RootNavigator):
 *   { user, isLoading, signInWithGoogle, signInWithApple, signInWithEmail, signOut }
 *
 * NOTE: a mock user is returned on mount when there is no real Supabase
 * session, so the app lands on the main tabs during development. Replace the
 * mock fallback + wire the signInWith* methods (expo-auth-session) for prod.
 */
import { useState, useCallback, useEffect } from 'react';
import * as SecureStore from 'expo-secure-store';
import { supabase } from '../../lib/supabase';

export type User = {
  id: string;
  email: string;
  firstName?: string;
  avatarUrl?: string;
};

const SESSION_KEY = 'flume_user';

// Remove this for production and start signed-out (user: null).
const MOCK_USER: User = { id: 'mock_user', email: 'you@example.com', firstName: 'there' };

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

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession();
        if (session?.user) {
          setUser(fromSupabaseUser(session.user));
          return;
        }
        // No Supabase session — restore a previously signed-in mock user, else
        // start signed-out so the Onboarding → Welcome flow shows on first run.
        const stored = await SecureStore.getItemAsync(SESSION_KEY);
        setUser(stored ? (JSON.parse(stored) as User) : null);
      } catch (err) {
        console.error('Failed to restore session:', err);
        setUser(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const signInWithGoogle = useCallback(async () => {
    setLoading(true);
    try {
      // TODO: wire expo-auth-session Google provider, then exchange the
      // idToken with Supabase / your backend. For now, sign in the mock user.
      setUser(MOCK_USER);
      await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(MOCK_USER));
    } finally {
      setLoading(false);
    }
  }, []);

  const signInWithApple = useCallback(async () => {
    // TODO: expo-apple-authentication
    setUser(MOCK_USER);
    await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(MOCK_USER));
  }, []);

  const signInWithEmail = useCallback(async () => {
    // TODO: navigate to an email screen (not designed yet)
    setUser(MOCK_USER);
    await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(MOCK_USER));
  }, []);

  const signOut = useCallback(async () => {
    try {
      await supabase.auth.signOut();
    } catch {
      /* ignore — local sign-out below still runs */
    }
    await SecureStore.deleteItemAsync(SESSION_KEY);
    setUser(null);
  }, []);

  return { user, isLoading, signInWithGoogle, signInWithApple, signInWithEmail, signOut };
}
