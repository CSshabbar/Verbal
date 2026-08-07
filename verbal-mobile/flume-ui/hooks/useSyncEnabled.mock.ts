/**
 * useSyncEnabled — MOCK (contract reference, never imported at runtime).
 * Same exported shape as ./useSyncEnabled, backed by in-memory state.
 *
 * The real hook is the ONLY React bridge over `lib/syncStore` (IDI-171), which
 * is deliberately React-free so `lib/` can own it. There is exactly ONE sync
 * flag (Hard Rule #28): MenuScreen, SettingsScreen, the DevicesScreen self-row
 * and DevicesSyncSheet all read through this hook and write through
 * setSyncEnabled, so a flip anywhere is reflected everywhere immediately.
 *
 * That module-level sharing is the point of the contract, so the mock keeps its
 * value in a module-level variable + listener set too — a per-component
 * useState copy would be a different hook.
 */
import { useSyncExternalStore } from 'react';

let enabled = true;
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function getSnapshot(): boolean { return enabled; }

/** Live cross-device Sync toggle value. Re-renders on any change. */
export function useSyncEnabled(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot);
}

/** Persist a new value (and notify every reader + the realtime stores). */
export async function setSyncEnabled(val: boolean): Promise<void> {
  if (val === enabled) return;
  enabled = val;
  listeners.forEach(l => l());
}
