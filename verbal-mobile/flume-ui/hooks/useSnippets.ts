/**
 * useSnippets — spoken-phrase → full-text expansions.
 * Backed by lib/dictionary snippet functions (AsyncStorage `flume_dictionary`
 * + Supabase `dictionary` sync). Snippets live in the same row as vocabulary +
 * replacements; this hook only surfaces the snippet slice.
 *
 * Contract (consumed by SnippetsScreen):
 *   { snippets, createSnippet, updateSnippet, removeSnippet, reload }
 *
 * Fail-closed: a load error yields an empty list, never a throw — snippet UI
 * must never be able to wedge the app.
 */
import { useState, useCallback, useEffect } from 'react';
import {
  fetchRemote,
  getSnippets,
  addSnippet as addSnippetLib,
  updateSnippet as updateSnippetLib,
  removeSnippet as removeSnippetLib,
  type Snippet,
  type SnippetPatch,
} from '../../lib/dictionary';

export type { Snippet, SnippetPatch } from '../../lib/dictionary';

export function useSnippets() {
  const [snippets, setSnippets] = useState<Snippet[]>([]);

  const load = useCallback(async () => {
    try {
      const d = await fetchRemote();      // sync from cloud, then read local
      setSnippets(d.snippets ?? []);
    } catch {
      try { setSnippets(await getSnippets()); } catch { setSnippets([]); }
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const createSnippet = useCallback(
    async (trigger: string, expansion: string, label = '') => {
      const d = await addSnippetLib(trigger, expansion, label);
      setSnippets(d.snippets ?? []);
    },
    [],
  );

  const updateSnippet = useCallback(async (id: string, patch: SnippetPatch) => {
    const d = await updateSnippetLib(id, patch);
    setSnippets(d.snippets ?? []);
  }, []);

  const removeSnippet = useCallback(async (id: string) => {
    const d = await removeSnippetLib(id);
    setSnippets(d.snippets ?? []);
  }, []);

  return { snippets, createSnippet, updateSnippet, removeSnippet, reload: load };
}
