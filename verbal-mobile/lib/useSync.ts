import { useEffect, useRef, useCallback } from 'react';
import { supabase } from './supabase';
import { getSyncEnabled, getUserId, getDeviceId, mergeRemoteEntries, HistoryEntry } from './storage';

/**
 * Fetches remote history from Supabase and subscribes to new inserts.
 * Calls onUpdate(entries) whenever new data arrives.
 */
export function useSync(onUpdate: (entries: HistoryEntry[]) => void) {
  const channelRef = useRef<ReturnType<typeof supabase.channel> | null>(null);

  const fetchRemote = useCallback(async () => {
    const syncOn = await getSyncEnabled();
    if (!syncOn) return;

    const userId = await getUserId();
    const { data, error } = await supabase
      .from('transcriptions')
      .select('*')
      .eq('user_id', userId)
      .order('created_at', { ascending: false })
      .limit(100);

    if (error || !data) return;

    const remote: HistoryEntry[] = data.map((r: any) => ({
      id:          r.id,
      text:        r.edited_text ?? r.text,
      device_name: r.device_name,
      device_id:   r.device_id,
      is_pinned:   r.is_pinned ?? false,
      created_at:  r.created_at,
      source:      'remote' as const,
    }));

    const merged = await mergeRemoteEntries(remote);
    onUpdate(merged);
  }, [onUpdate]);

  const subscribe = useCallback(async () => {
    const syncOn = await getSyncEnabled();
    if (!syncOn) return;

    const userId   = await getUserId();
    const deviceId = await getDeviceId();

    // Unsubscribe previous
    if (channelRef.current) {
      await supabase.removeChannel(channelRef.current);
    }

    const channel = supabase
      .channel(`verbal_history_${userId}`)
      .on(
        'postgres_changes',
        {
          event:  'INSERT',
          schema: 'public',
          table:  'transcriptions',
          filter: `user_id=eq.${userId}`,
        },
        async (payload: any) => {
          const r = payload.new;
          // Skip own inserts
          if (r.device_id === deviceId) return;
          // Respect target_device_id — only receive if targeted at us or broadcast
          if (r.target_device_id && r.target_device_id !== deviceId) return;
          const entry: HistoryEntry = {
            id:          r.id,
            text:        r.edited_text ?? r.text,
            device_name: r.device_name,
            device_id:   r.device_id,
            is_pinned:   r.is_pinned ?? false,
            created_at:  r.created_at,
            source:      'remote',
          };
          const merged = await mergeRemoteEntries([entry]);
          onUpdate(merged);
        }
      )
      .on(
        'postgres_changes',
        {
          event:  'UPDATE',
          schema: 'public',
          table:  'transcriptions',
          filter: `user_id=eq.${userId}`,
        },
        async () => {
          // Re-fetch on any update (pin/edit)
          await fetchRemote();
        }
      )
      .subscribe();

    channelRef.current = channel;
  }, [onUpdate, fetchRemote]);

  useEffect(() => {
    fetchRemote();
    subscribe();
    return () => {
      if (channelRef.current) {
        supabase.removeChannel(channelRef.current);
      }
    };
  }, []);

  return { fetchRemote };
}
