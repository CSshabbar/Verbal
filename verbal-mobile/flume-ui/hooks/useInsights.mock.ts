/**
 * useInsights.mock — the design contract for useInsights (never imported at
 * runtime; kept mutually type-assignable with useInsights.ts — IDI-179 rule).
 */
import { useCallback, useState } from 'react';
import type { Insights } from '../../lib/insights';

export type { Insights } from '../../lib/insights';

function mockSeries(): Array<[string, number]> {
  const out: Array<[string, number]> = [];
  const today = new Date();
  for (let i = 369; i >= 0; i--) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
    const p = (x: number) => String(x).padStart(2, '0');
    const key = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    const seed = (d.getDate() * 37 + d.getMonth() * 11) % 97;
    out.push([key, i > 200 ? 0 : seed < 25 ? 0 : seed * 23]);
  }
  return out;
}

const MOCK: Insights = {
  empty: false,
  totalWords: 148213,
  totalDictations: 2741,
  todayWords: 1284,
  weekWords: 9412,
  monthWords: 31240,
  monthDeltaPct: 18,
  wpm: 142,
  wpmPercentile: 1,
  typingWpm: 40,
  savedMonthMin: 246,
  currentStreak: 11,
  bestStreak: 23,
  busiestDay: { day: '2026-07-12', words: 4213 },
  series: mockSeries(),
  devices: [
    { name: 'Shabbar’s Mac', words: 98400, pct: 66 },
    { name: 'iPhone', words: 31200, pct: 21 },
    { name: 'Shabbar-Windows', words: 18613, pct: 13 },
  ],
  hours: [0, 0, 0, 0, 0, 120, 340, 900, 1600, 2600, 3400, 2800, 1900, 1500, 1700, 2000, 1700, 1300, 900, 500, 300, 120, 0, 0],
  peakHour: 10,
  morningShare: 46,
  fetchedAt: '2026-08-15T12:00:00.000Z',
};

export function useInsights() {
  const [data] = useState<Insights | null>(MOCK);
  const [loading] = useState(false);
  const refresh = useCallback(async () => {}, []);
  return { data, loading, refresh };
}
