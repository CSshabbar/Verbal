/**
 * useSnippets — MOCK (contract reference, never imported at runtime).
 * Same exported shape as ./useSnippets, backed by in-memory state.
 */
import { useState, useCallback } from 'react';

export type Snippet = {
  id: string;
  trigger: string;
  expansion: string;
  label: string;
  used: number;
  createdAt: string;
  updatedAt: string;
};

export type SnippetPatch = Partial<Pick<Snippet, 'trigger' | 'expansion' | 'label' | 'used'>>;

const now = () => new Date().toISOString();

const MOCK: Snippet[] = [
  {
    id: 's1',
    trigger: 'my linkedin',
    expansion: 'https://www.linkedin.com/in/your-handle',
    label: 'LinkedIn',
    used: 12,
    createdAt: now(),
    updatedAt: now(),
  },
  {
    id: 's2',
    trigger: 'my email signature',
    expansion: 'Best,\nAlex Rivera · Founder, Flume\nalex@flume.app',
    label: 'Email signature',
    used: 5,
    createdAt: now(),
    updatedAt: now(),
  },
  {
    id: 's3',
    trigger: 'my calendar',
    expansion: 'https://cal.com/your-handle/30min',
    label: 'Calendar link',
    used: 3,
    createdAt: now(),
    updatedAt: now(),
  },
];

export function useSnippets() {
  const [snippets, setSnippets] = useState<Snippet[]>(MOCK);

  const createSnippet = useCallback(
    async (trigger: string, expansion: string, label = '') => {
      const t = (trigger || '').trim();
      const e = (expansion || '').trim();
      if (!t || !e) return;
      setSnippets(prev => [
        {
          id: `s_${Date.now()}`,
          trigger: t,
          expansion,
          label: (label || '').trim(),
          used: 0,
          createdAt: now(),
          updatedAt: now(),
        },
        ...prev.filter(s => s.trigger.toLowerCase() !== t.toLowerCase()),
      ]);
    },
    [],
  );

  const updateSnippet = useCallback(async (id: string, patch: SnippetPatch) => {
    setSnippets(prev => prev.map(s => (s.id === id ? { ...s, ...patch, updatedAt: now() } : s)));
  }, []);

  const removeSnippet = useCallback(async (id: string) => {
    setSnippets(prev => prev.filter(s => s.id !== id));
  }, []);

  const reload = useCallback(async () => {}, []);

  return { snippets, createSnippet, updateSnippet, removeSnippet, reload };
}
