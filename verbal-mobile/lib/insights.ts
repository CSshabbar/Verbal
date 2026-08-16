/**
 * insights.ts — dictation statistics behind the mobile Insights screen.
 *
 * Mobile has no per-day local ledger (that's the desktop's `stats_daily`), so
 * the account-wide picture comes from the cloud `transcriptions` table:
 * an INCREMENTAL aggregate (words/dictations per local day, per hour, per
 * device) cached in AsyncStorage so reopening the screen is instant and each
 * refresh only fetches rows newer than the last one seen. Tombstoned rows
 * (text cleared) count zero words and are skipped.
 *
 * Speaking speed is the one metric the cloud can't provide (rows carry no
 * duration): it comes from THIS device's local history entries, which persist
 * `duration_ms` for recordings made here.
 *
 * Fail-closed (desktop Hard Rule #1 applies here too): every entry point
 * catches; a network/parse failure just leaves the cached aggregate as-is.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { supabase } from './supabase';
import { getCloudUserId, getDeviceId, getHistory } from './storage';

const CACHE_KEY = 'verbal_insights_cache';
const CACHE_V = 2;            // v2: rows re-read for duration_ms (2026-08-16)
const PAGE = 1000;
const MAX_PAGES = 40;
export const TYPING_WPM = 40; // the average-typist baseline for "time saved"

type DayAgg = { w: number; n: number };
export type InsightsCache = {
  v: number;
  uid: string;
  days: Record<string, DayAgg>;
  hh: number[];                                  // 24 buckets, words by local hour
  byDev: Record<string, { name: string; w: number }>;
  // Measured-speech accumulator for WPM, from OTHER devices' rows that carry
  // duration_ms (this device's own speech is measured from local history, so
  // its rows are excluded here to avoid double counting).
  wpmW: number;
  wpmMs: number;
  lastTs: string;
  fetchedAt: string;
};

export type Insights = {
  empty: boolean;
  totalWords: number;
  totalDictations: number;
  todayWords: number;
  weekWords: number;
  monthWords: number;
  monthDeltaPct: number | null;
  wpm: number | null;                            // this device's recordings
  wpmPercentile: number | null;                  // vs global typing speeds
  typingWpm: number;
  savedMonthMin: number | null;                  // estimated, needs wpm
  currentStreak: number;
  bestStreak: number;
  busiestDay: { day: string; words: number } | null;
  series: Array<[string, number]>;               // last 370 days [date, words]
  devices: Array<{ name: string; words: number; pct: number }>;
  hours: number[];
  peakHour: number | null;
  morningShare: number | null;
  fetchedAt: string;
};

const emptyCache = (uid: string): InsightsCache => ({
  v: CACHE_V, uid, days: {}, hh: new Array(24).fill(0), byDev: {},
  wpmW: 0, wpmMs: 0, lastTs: '', fetchedAt: '',
});

function localDayKey(d: Date): string {
  const p = (x: number) => String(x).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export async function loadCache(): Promise<InsightsCache | null> {
  try {
    const uid = await getCloudUserId();
    if (!uid) return null;
    const raw = await AsyncStorage.getItem(CACHE_KEY);
    if (!raw) return emptyCache(uid);
    const c = JSON.parse(raw) as InsightsCache;
    // A cache written under another account never leaks across sign-ins
    // (belt-and-suspenders on top of clearAccountData()). A version bump
    // also invalidates: v2 re-reads history for the duration_ms column.
    if (c.uid !== uid || c.v !== CACHE_V) return emptyCache(uid);
    if (!Array.isArray(c.hh) || c.hh.length !== 24) c.hh = new Array(24).fill(0);
    if (typeof c.wpmW !== 'number') c.wpmW = 0;
    if (typeof c.wpmMs !== 'number') c.wpmMs = 0;
    return c;
  } catch {
    return null;
  }
}

/** Fold rows newer than the cache's high-water mark into the aggregate.
 *  Returns the updated cache (=== input when nothing new). */
export async function refreshCache(cache: InsightsCache): Promise<InsightsCache> {
  try {
    let lastTs = cache.lastTs;
    let changed = false;
    const ownDeviceId = await getDeviceId().catch(() => '');
    for (let page = 0; page < MAX_PAGES; page++) {
      let q = supabase
        .from('transcriptions')
        .select('created_at,device_id,device_name,text,duration_ms')
        .eq('user_id', cache.uid)
        .order('created_at', { ascending: true })
        .limit(PAGE);
      if (lastTs) q = q.gt('created_at', lastTs);
      const { data, error } = await q;
      if (error || !data || data.length === 0) break;
      for (const row of data) {
        const ts = row.created_at as string;
        if (ts) lastTs = ts;
        const words = String(row.text ?? '').split(/\s+/).filter(Boolean).length;
        if (!words) continue; // tombstoned / empty rows
        const dt = new Date(ts);
        if (isNaN(dt.getTime())) continue;
        const day = localDayKey(dt);
        const d = cache.days[day] ?? { w: 0, n: 0 };
        d.w += words; d.n += 1;
        cache.days[day] = d;
        cache.hh[dt.getHours()] += words;
        const devKey = String(row.device_id || row.device_name || 'unknown');
        const dev = cache.byDev[devKey] ?? { name: String(row.device_name || 'Device'), w: 0 };
        dev.w += words;
        if (row.device_name) dev.name = String(row.device_name);
        cache.byDev[devKey] = dev;
        // Measured speech for WPM — other devices only (this device's own
        // rows are measured from local history, richer and never synced-late).
        const ms = Number(row.duration_ms) || 0;
        if (ms > 0 && devKey !== ownDeviceId) {
          cache.wpmW += words;
          cache.wpmMs += ms;
        }
        changed = true;
      }
      if (data.length < PAGE) break;
    }
    if (changed || !cache.fetchedAt) {
      cache.lastTs = lastTs;
      cache.fetchedAt = new Date().toISOString();
      await AsyncStorage.setItem(CACHE_KEY, JSON.stringify(cache));
    }
    return cache;
  } catch {
    return cache;
  }
}

/** 'Top X%' vs global TYPING speeds (avg typist ≈ 52 wpm; 100 ≈ top 4%,
 *  150 ≈ top 0.5%). Mirrors desktop app/insights.py::_percentile. */
export function percentile(wpm: number): number {
  const pts: Array<[number, number]> = [
    [40, 75], [52, 50], [65, 25], [80, 10], [100, 4], [120, 2], [150, 0.5], [180, 0.1],
  ];
  if (wpm <= pts[0][0]) return 99;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    if (wpm <= x1) return Math.round((y0 + ((wpm - x0) / (x1 - x0)) * (y1 - y0)) * 10) / 10;
  }
  return 0.1;
}

/** This device's measured speech (words + ms) from local history entries that
 *  kept their recording duration. Combined with the cloud accumulator in
 *  compute() — WPM is account-wide since 2026-08-16. */
export async function localSpeech(): Promise<{ w: number; ms: number }> {
  try {
    const entries = await getHistory();
    let w = 0, ms = 0;
    for (const e of entries) {
      if (e.duration_ms && e.duration_ms > 0 && e.text) {
        w += e.text.split(/\s+/).filter(Boolean).length;
        ms += e.duration_ms;
      }
    }
    return { w, ms };
  } catch {
    return { w: 0, ms: 0 };
  }
}

export function compute(
  cache: InsightsCache,
  local: { w: number; ms: number } = { w: 0, ms: 0 },
): Insights {
  // Account-wide speaking speed: this device's measured recordings plus every
  // synced row that carries duration_ms. Still gated on ≥60s of real speech.
  const wpmW = local.w + cache.wpmW;
  const wpmMs = local.ms + cache.wpmMs;
  const wpm = (wpmMs >= 60_000 && wpmW > 0) ? Math.round(wpmW / (wpmMs / 60_000)) : null;
  const days = cache.days;
  const today = new Date();
  const dayKey = (offset: number) =>
    localDayKey(new Date(today.getFullYear(), today.getMonth(), today.getDate() - offset));

  const span = (n: number, endOffset = 0) => {
    let w = 0;
    for (let i = 0; i < n; i++) w += days[dayKey(endOffset + i)]?.w ?? 0;
    return w;
  };

  let totalWords = 0, totalDictations = 0;
  let busiest: { day: string; words: number } | null = null;
  for (const [day, d] of Object.entries(days)) {
    totalWords += d.w; totalDictations += d.n;
    if (d.w > 0 && (!busiest || d.w > busiest.words)) busiest = { day, words: d.w };
  }

  const monthWords = span(30);
  const prevMonthWords = span(30, 30);
  const monthDeltaPct = prevMonthWords > 0
    ? Math.round(((monthWords - prevMonthWords) / prevMonthWords) * 100) : null;

  // Streaks over active days; the current run may end today or yesterday.
  const active = Object.keys(days).filter(d => (days[d]?.w ?? 0) > 0).sort();
  let best = 0, run = 0, prev: string | null = null;
  for (const d of active) {
    if (prev) {
      const gap = Math.round((new Date(d).getTime() - new Date(prev).getTime()) / 86_400_000);
      run = gap === 1 ? run + 1 : 1;
    } else run = 1;
    best = Math.max(best, run);
    prev = d;
  }
  let currentStreak = 0;
  if (active.length) {
    const last = active[active.length - 1];
    if (last === dayKey(0) || last === dayKey(1)) currentStreak = run;
  }

  const series: Array<[string, number]> = [];
  for (let i = 369; i >= 0; i--) {
    const k = dayKey(i);
    series.push([k, days[k]?.w ?? 0]);
  }

  const hours = cache.hh.slice();
  const hoursTotal = hours.reduce((a, b) => a + b, 0);
  let peakHour: number | null = null;
  if (hoursTotal) peakHour = hours.indexOf(Math.max(...hours));
  const morningShare = hoursTotal
    ? Math.round((hours.slice(5, 12).reduce((a, b) => a + b, 0) / hoursTotal) * 100)
    : null;

  const devList = Object.values(cache.byDev).sort((a, b) => b.w - a.w);
  const top = devList.slice(0, 5);
  const rest = devList.slice(5).reduce((a, d) => a + d.w, 0);
  if (rest > 0) top.push({ name: 'Other', w: rest });
  const devTotal = top.reduce((a, d) => a + d.w, 0) || 1;

  // "Time saved" is an estimate on mobile (the cloud rows carry no duration):
  // this month's words at your measured speaking speed vs typing at 40 wpm.
  const savedMonthMin = wpm && monthWords
    ? Math.max(0, Math.round(monthWords / TYPING_WPM - monthWords / wpm))
    : null;

  return {
    empty: totalWords === 0,
    totalWords,
    totalDictations,
    todayWords: span(1),
    weekWords: span(7),
    monthWords,
    monthDeltaPct,
    wpm,
    wpmPercentile: wpm ? percentile(wpm) : null,
    typingWpm: TYPING_WPM,
    savedMonthMin,
    currentStreak,
    bestStreak: best,
    busiestDay: busiest,
    series,
    devices: top.map(d => ({
      name: d.name, words: d.w, pct: Math.round((d.w / devTotal) * 100),
    })),
    hours,
    peakHour,
    morningShare,
    fetchedAt: cache.fetchedAt,
  };
}

/** clearAccountData() companion — the aggregate is account-scoped. */
export async function clearInsightsCache(): Promise<void> {
  try { await AsyncStorage.removeItem(CACHE_KEY); } catch { /* fail closed */ }
}
