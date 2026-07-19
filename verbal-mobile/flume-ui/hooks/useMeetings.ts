/**
 * useMeetings — real hook; exact same exported shape as useMeetings.mock.ts
 * (the design contract). Read-only except updateScratchpad, which syncs the
 * edit back to the desktop (last-write-wins).
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import {
  fetchMeetings, updateScratchpadRemote, subscribeMeetings,
} from '../../lib/meetings';
import { getUserId, getSyncEnabled } from '../../lib/storage';
import type { Meeting } from './useMeetings.mock';

export type {
  Meeting, MeetingUtterance, MeetingActionItem, MeetingMoment,
  MeetingHybridNote, MeetingStatus,
} from './useMeetings.mock';

export function useMeetings() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [loading, setLoading] = useState(true);
  const scratchTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const refresh = useCallback(async () => {
    try {
      setMeetings(await fetchMeetings());
    } catch {
      /* keep previous list */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let dispose: (() => void) | null = null;
    let mounted = true;
    (async () => {
      await refresh();
      try {
        if (await getSyncEnabled()) {
          const uid = await getUserId();
          if (mounted) dispose = subscribeMeetings(uid, refresh);
        }
      } catch { /* realtime is best-effort */ }
    })();
    return () => { mounted = false; if (dispose) dispose(); };
  }, [refresh]);

  const getMeeting = useCallback(
    (id: string) => meetings.find(m => m.id === id) ?? null,
    [meetings],
  );

  /** Optimistic local update + debounced remote write (600 ms). */
  const updateScratchpad = useCallback((id: string, text: string) => {
    setMeetings(prev => prev.map(m => (m.id === id ? { ...m, scratchpad: text } : m)));
    const timers = scratchTimers.current;
    if (timers[id]) clearTimeout(timers[id]);
    timers[id] = setTimeout(() => { updateScratchpadRemote(id, text); }, 600);
  }, []);

  return { meetings, loading, getMeeting, refresh, updateScratchpad };
}
