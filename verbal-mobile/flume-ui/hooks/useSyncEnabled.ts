/**
 * useSyncEnabled — the React face of lib/syncStore (IDI-171).
 *
 * The store itself is React-free so `lib/` can own it (lib must never import
 * flume-ui, and lib/deviceSync + lib/storage both need it). This thin hooks-layer
 * wrapper is the ONLY place that bridges it into React, via useSyncExternalStore
 * — the same subscribe/getSnapshot split historyStore already uses.
 *
 * Every sync toggle in the UI (MenuScreen, SettingsScreen, the DevicesScreen
 * self-row) reads through this hook and writes through setSyncEnabled, so they
 * always show the same value and a flip anywhere is reflected everywhere
 * immediately — no per-screen useState copy hydrated once on mount.
 */
import { useSyncExternalStore } from 'react';
import * as syncStore from '../../lib/syncStore';

/** Live cross-device Sync toggle value. Re-renders on any change. */
export function useSyncEnabled(): boolean {
  return useSyncExternalStore(syncStore.subscribe, syncStore.getSnapshot);
}

/** Persist a new value (and notify every reader + the realtime stores). */
export const setSyncEnabled = syncStore.setSyncEnabled;
