/**
 * useHistory — transcription history.
 * Thin wrapper over the shared `historyStore` so every consumer (Home, History
 * tab, RootNavigator) stays in sync. A transcription saved from the recording
 * flow appears live in the History tab without a manual refresh.
 *
 * Contract (consumed by HistoryListScreen / HistoryDetailScreen / HomeScreen):
 *   { items, add, remove }   (+ addTranscription / refresh for the record flow)
 */
import { useEffect, useSyncExternalStore } from 'react';
import {
  subscribe,
  getSnapshot,
  ensureLoaded,
  add,
  remove,
  addTranscription,
  retryEntry,
  playEntry,
  refresh,
} from './historyStore';

export type { HistoryItem } from './historyStore';

export function useHistory() {
  const items = useSyncExternalStore(subscribe, getSnapshot);

  useEffect(() => { ensureLoaded(); }, []);

  return { items, add, remove, addTranscription, retryEntry, playEntry, refresh };
}
