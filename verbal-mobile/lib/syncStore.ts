/**
 * syncStore — the ONE source of truth for the cross-device Sync toggle (IDI-171).
 *
 * Before this module the flag lived as a bare AsyncStorage read/write in
 * lib/storage, and each of the three toggle UIs (Menu, Settings, the Devices
 * self-row) kept its own `useState` copy hydrated once on mount. They drifted,
 * and flipping the switch changed nothing until the next app launch, because the
 * realtime stores only ever read the flag inside their startup path.
 *
 * So: a tiny module-level store.
 *   - `getSyncEnabled()`  — async, reads AsyncStorage once then serves the cache
 *   - `setSyncEnabled(v)` — persists, updates the cache, notifies everyone
 *   - `subscribe`/`getSnapshot` — the `useSyncExternalStore` pair (React reads it
 *     through flume-ui/hooks/useSyncEnabled, so this file stays React-free and
 *     importable from `lib/`)
 *   - `onChange(l)` — for the non-React stores (historyStore) that must run a
 *     catch-up on ON and tear their channels down on OFF. Distinct from
 *     `subscribe` on purpose: it fires ONLY on a real value change, never on the
 *     initial hydration, so hydrating "true" at launch doesn't trigger a
 *     duplicate catch-up on top of the one the store's own load() already does.
 *
 * Layering: lib/ only. Imports AsyncStorage and nothing else — in particular not
 * lib/storage (which re-exports from here for backwards compatibility), so there
 * is no cycle.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

/** The ONLY definition of the sync flag's persistence key in the app. */
const KEY = 'verbal_sync_enabled';

/** Absent key reads as OFF (unchanged from the original storage.ts semantics —
 *  sign-in explicitly writes the device's cloud `sync_enabled`, default true). */
const DEFAULT = false;

let cached: boolean = DEFAULT;
let hydrated = false;
let hydrating: Promise<boolean> | null = null;

/** useSyncExternalStore subscribers — notified on hydration AND on change. */
const snapshotListeners = new Set<() => void>();
/** Behavioural subscribers (historyStore) — notified only on a real change. */
const changeListeners = new Set<(enabled: boolean) => void>();

function emitSnapshot() {
  snapshotListeners.forEach((l) => { try { l(); } catch { /* ignore */ } });
}
function emitChange(v: boolean) {
  changeListeners.forEach((l) => { try { l(v); } catch { /* ignore */ } });
}

async function hydrate(): Promise<boolean> {
  if (hydrated) return cached;
  if (hydrating) return hydrating;
  hydrating = (async () => {
    let value = DEFAULT;
    try {
      value = (await AsyncStorage.getItem(KEY)) === 'true';
    } catch { /* keep the default */ }
    const changed = value !== cached;
    cached = value;
    hydrated = true;
    hydrating = null;
    // Snapshot subscribers need this (their first render saw the default);
    // change subscribers deliberately do NOT — see the header note.
    if (changed) emitSnapshot();
    return cached;
  })();
  return hydrating;
}

/** Current value, hydrating from AsyncStorage on the first call. */
export async function getSyncEnabled(): Promise<boolean> {
  return hydrate();
}

/** Persist + broadcast. Idempotent: setting the same value notifies nobody. */
export async function setSyncEnabled(val: boolean): Promise<void> {
  const changed = !hydrated || val !== cached;
  cached = val;
  hydrated = true;
  try {
    await AsyncStorage.setItem(KEY, val ? 'true' : 'false');
  } catch { /* the in-memory value still wins for this session */ }
  if (changed) { emitSnapshot(); emitChange(val); }
}

/** useSyncExternalStore's subscribe. Kicks off hydration so the first mounted
 *  consumer is what pulls the persisted value in. */
export function subscribe(listener: () => void): () => void {
  snapshotListeners.add(listener);
  if (!hydrated) hydrate();
  return () => { snapshotListeners.delete(listener); };
}

/** useSyncExternalStore's getSnapshot — synchronous, cache-only. */
export function getSnapshot(): boolean {
  return cached;
}

/** Behavioural listener: fires only when the value actually changes. */
export function onChange(listener: (enabled: boolean) => void): () => void {
  changeListeners.add(listener);
  return () => { changeListeners.delete(listener); };
}
