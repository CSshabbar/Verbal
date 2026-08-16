/**
 * useInsights — dictation statistics for the Insights screen.
 *
 * Contract (see useInsights.mock.ts, the design contract):
 *   { data, loading, refresh }
 *
 * Loads the cached cloud aggregate instantly, then folds in any new
 * `transcriptions` rows (incremental — only rows newer than the cache's
 * high-water mark) and recomputes. All failure paths leave `data` at the last
 * good value; a signed-out session yields the empty payload.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Insights, compute, loadCache, localSpeech, refreshCache,
} from '../../lib/insights';

export type { Insights } from '../../lib/insights';

export function useInsights() {
  const [data, setData] = useState<Insights | null>(null);
  const [loading, setLoading] = useState(true);
  const busy = useRef(false);

  const refresh = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      const cache = await loadCache();
      if (!cache) { setLoading(false); return; }
      const local = await localSpeech();
      // Instant paint from the cache, network fold-in after.
      setData(compute(cache, local));
      setLoading(false);
      const updated = await refreshCache(cache);
      setData(compute(updated, local));
    } finally {
      busy.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return { data, loading, refresh };
}
