/**
 * syncLifecycle — foreground catch-up for the realtime stores (IDI-171).
 *
 * Supabase realtime channels don't survive a long background stint: iOS suspends
 * the socket, the server eventually drops the join, and on resume the app looked
 * connected while silently receiving nothing. Every store's own retry only
 * triggers on a status callback that a suspended socket never delivers, so
 * something has to poke them when the app comes back.
 *
 * On AppState 'active' we run one catch-up pass: refetch + rejoin history, pull
 * the shared canvas row. Each store gates itself on lib/syncStore, so this is a
 * no-op when sync is off or nobody is signed in.
 *
 * WHY NOT lib/supabase.ts: that file already has an AppState listener, but it
 * owns exactly one concern — driving `supabase.auth.startAutoRefresh()` per the
 * supabase-js React Native docs. It lives in `lib/` and must not know about
 * flume-ui stores. This is a second, independent listener registered from the
 * app root, which is where app-wide lifecycle wiring belongs.
 */
import { AppState, AppStateStatus } from 'react-native';
import * as historyStore from './historyStore';
import * as canvasStore from './useCanvas';
import * as syncStore from '../../lib/syncStore';

/** One catch-up pass. Never throws; each store is independently best-effort. */
export async function catchUpNow(): Promise<void> {
  if (!(await syncStore.getSyncEnabled())) return;
  await Promise.allSettled([
    historyStore.catchUp(),
    canvasStore.catchUp(),
  ]);
}

/**
 * Register the foreground listener. Returns an unsubscribe function, so it drops
 * straight into a `useEffect` at the app root.
 */
export function startSyncLifecycle(): () => void {
  const onChange = (state: AppStateStatus) => {
    if (state === 'active') catchUpNow().catch(() => { /* best effort */ });
  };
  const sub = AppState.addEventListener('change', onChange);
  return () => sub.remove();
}
