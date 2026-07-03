/**
 * useAuth — stub for sign-in. Wire to your backend.
 *
 * Replace the bodies of signInWith* with your real auth calls
 * (Google: expo-auth-session, Apple: expo-apple-authentication, etc).
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

  const signInWithGoogle = useCallback(async () => {
    setLoading(true);
    // TODO: integrate expo-auth-session Google provider.
    // const result = await Google.logInAsync({ ... });
    // const u = await yourBackend.exchange(result.idToken);
    // setUser(u);
    setTimeout(() => setLoading(false), 600);
  }, []);

  const signInWithApple = useCallback(async () => {
    // TODO: expo-apple-authentication
  }, []);

  const signInWithEmail = useCallback(async () => {
    // TODO: navigate to email screen (not designed yet)
  }, []);

  const signOut = useCallback(() => setUser(null), []);

  return { user, isLoading, signInWithGoogle, signInWithApple, signInWithEmail, signOut };
}
