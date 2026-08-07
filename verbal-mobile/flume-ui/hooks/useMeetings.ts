/**
 * useMeetings — thin wrapper over the shared `meetingsStore` (IDI-175 §1).
 *
 * Same exported shape as useMeetings.mock.ts (the design contract), plus the
 * three things the screens now need to be honest about sync:
 *   error      — the last refresh failed; the list below is stale, not empty
 *   unsaved    — per meeting: a write is queued/failed and will be retried
 *   conflicts  — per meeting: another device wrote first, offer a Reload
 *
 * Every instance reads the SAME store, so four mounted screens share one fetch
 * and one realtime channel.
 */
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import * as store from './meetingsStore';
import type { Meeting } from '../../lib/meetings';

export type {
  Meeting, MeetingUtterance, MeetingActionItem, MeetingMoment,
  MeetingHybridNote, MeetingStatus,
} from '../../lib/meetings';

export function useMeetings() {
  const snap = useSyncExternalStore(store.subscribe, store.getSnapshot);

  useEffect(() => { store.ensureLoaded(); }, []);

  const getMeeting = useCallback(
    (id: string): Meeting | null => snap.meetings.find((m) => m.id === id) ?? null,
    [snap.meetings],
  );

  return {
    meetings: snap.meetings,
    loading: snap.loading,
    error: snap.error,
    unsaved: snap.unsaved,
    conflicts: snap.conflicts,
    getMeeting,
    refresh: store.refresh,
    updateScratchpad: store.updateScratchpad,
    updateNotes: store.updateNotes,
    updateActionItems: store.updateActionItems,
    /** Flush debounced edits right now (call on blur/back/unmount). */
    flushNow: store.flushNow,
    /** Discard the local edit and adopt the other device's version. */
    reloadMeeting: store.reloadMeeting,
    clearConflict: store.clearConflict,
    setNotesNow: store.setNotesNow,
  };
}
