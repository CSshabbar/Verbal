import React, { useEffect, useMemo, useState } from 'react';
import { View, StyleSheet, ScrollView, Pressable, Share, useWindowDimensions } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Path, Circle } from 'react-native-svg';
import { Text, MenuButton } from '../components';
import { colors, pressedStyle } from '../theme';
import { useInsights, Insights } from '../hooks/useInsights';
import { useSyncEnabled } from '../hooks/useSyncEnabled';
import { useOrganization } from '../hooks/useOrganization';
import { TeamInsights } from '../components/TeamInsights';

// onBack is optional since the V2 nav redesign (2026-08-16): as a bottom TAB
// the screen has no back destination — the slot keeps the title centered.
type Props = { onBack?: () => void };

// Pastel stat-card palette (matches the desktop Insights band + Home cards).
const CREAM = '#EADFCE'; const CREAM_INK = '#2a1f18';
const SAGE = '#DDE4D3'; const SAGE_INK = '#1e2418';
const PLUM = '#e6dae4'; const PLUM_INK = '#221820';
// Sequential terracotta ramp for magnitude (heatmap / bars) — mirrors desktop.
const RAMP = ['#1f2225', '#4a2d24', '#7a4030', '#a84b33', '#C85A3E', '#E88D6A'];

const fmtN = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('en-US');
const fmtMin = (min: number | null) => {
  if (min == null) return '—';
  const h = Math.floor(min / 60), m = Math.round(min % 60);
  return h > 0 ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m`;
};
const fmtHour = (h: number | null) => {
  if (h == null) return '—';
  const ap = h < 12 ? 'AM' : 'PM';
  return `${h % 12 === 0 ? 12 : h % 12} ${ap}`;
};
const fmtPct = (p: number | null) =>
  p == null ? '' : p >= 10 ? String(Math.round(p)) : String(p);

/**
 * Insights — words, speaking speed, streaks and rhythm, computed from the
 * account's cloud history plus this device's recorded durations. Same
 * hero-gauge + pastel-band design as the desktop dashboard's Insights page.
 */
export const InsightsScreen: React.FC<Props> = ({ onBack }) => {
  const insets = useSafeAreaInsets();
  const { data, loading } = useInsights();
  const sync = useSyncEnabled();
  // Team scope (user request, 2026-08-27): the same `Mine | <team>` segment the
  // Dictionary screen uses. Only drawn when the account is on a team, and it
  // snaps back to personal if the team goes away underneath it.
  const t = useOrganization();
  const [scope, setScope] = useState<'personal' | 'team'>('personal');
  const teamScope = scope === 'team' && t.hasTeam;
  useEffect(() => { if (scope === 'team' && !t.hasTeam) setScope('personal'); }, [scope, t.hasTeam]);

  const shareRecap = async () => {
    if (!data) return;
    const L = [
      'My Flume insights —',
      `${fmtN(data.totalWords)} words dictated (${fmtN(data.totalDictations)} dictations)`,
    ];
    if (data.wpm) L.push(`${data.wpm} words/min — top ${fmtPct(data.wpmPercentile)}% of typists`);
    if (data.savedMonthMin) L.push(`≈ ${fmtMin(data.savedMonthMin)} saved this month vs typing`);
    if (data.currentStreak) L.push(`${data.currentStreak}-day streak (best ${data.bestStreak})`);
    try { await Share.share({ message: L.join('\n') }); } catch { /* user cancelled */ }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 12 }]}>
      <View style={styles.topBar}>
        {onBack ? (
          <Pressable onPress={onBack} style={({ pressed }) => [styles.iconCircle, pressed && pressedStyle]} accessibilityRole="button" accessibilityLabel="Back" hitSlop={8}>
            <Ionicons name="chevron-back" size={18} color={colors.textSecondary} />
          </Pressable>
        ) : teamScope ? (
          // Invisible spacer (same footprint) — a styled-but-empty circle would
          // read as a blank button, the exact bug class of rule #44.
          <View style={{ width: 34, height: 34 }} />
        ) : (
          // Share sits left when there's no Back, so the ☰ can keep the
          // rightmost slot like every other tab root.
          <Pressable onPress={shareRecap} style={({ pressed }) => [styles.iconCircle, pressed && pressedStyle]} accessibilityRole="button" accessibilityLabel="Share recap" hitSlop={8}>
            <Ionicons name="share-outline" size={17} color={colors.textSecondary} />
          </Pressable>
        )}
        <Text variant="titleSm">Insights</Text>
        {/* Rightmost slot: the ☰ (opens the SidePanel). Renders nothing outside
            the MenuContext provider, so the sized wrapper keeps the title centred. */}
        <View style={{ width: 34, height: 34 }}><MenuButton /></View>
      </View>
      {t.hasTeam ? (
        <View style={styles.seg}>
          {([['personal', 'Mine'], ['team', t.org.name || 'Team']] as const).map(([k, label]) => (
            <Pressable
              key={k}
              onPress={() => setScope(k)}
              accessibilityRole="button"
              accessibilityState={{ selected: scope === k }}
              style={({ pressed }) => [styles.segBtn, scope === k && styles.segBtnOn, pressed && pressedStyle]}
            >
              <Text variant="caption" color={scope === k ? colors.textPrimary : colors.textMuted} numberOfLines={1}>
                {label}
              </Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      <ScrollView
        style={{ flex: 1 }}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingTop: 14, paddingBottom: insets.bottom + 28 }}
      >
        {teamScope ? (
          <TeamInsights t={t} />
        ) : !data || data.empty ? (
          <EmptyState loading={loading} />
        ) : (
          <>
            <Hero data={data} />
            {!sync && (
              <View style={styles.syncHint}>
                <Ionicons name="cloud-offline-outline" size={15} color={colors.textMuted} />
                <Text variant="caption" color={colors.textMuted} style={{ flex: 1 }}>
                  Sync is off — dictations from this phone aren’t being counted.
                </Text>
              </View>
            )}
            <Band data={data} />
            <Heatmap data={data} />
            <Devices data={data} />
            <Rhythm data={data} />
          </>
        )}
      </ScrollView>
    </View>
  );
};

const EmptyState: React.FC<{ loading: boolean }> = ({ loading }) => (
  <View style={styles.empty}>
    <View style={styles.emptyMic}>
      <Ionicons name="mic-outline" size={26} color={colors.primary} />
    </View>
    <Text variant="subtitle" style={{ fontSize: 19, marginBottom: 8 }}>
      {loading ? 'Crunching your numbers…' : 'Your story starts with a sentence'}
    </Text>
    <Text variant="bodyXs" color={colors.textMuted} style={{ textAlign: 'center', maxWidth: 300 }}>
      Dictate anything. Words, speed, streaks and your daily rhythm all start
      counting from your first take.
    </Text>
  </View>
);

const Hero: React.FC<{ data: Insights }> = ({ data }) => {
  const wpm = data.wpm;
  const speedX = wpm ? Math.round((wpm / data.typingWpm) * 10) / 10 : null;
  // Semicircular gauge, 0..200 wpm, typist marker at 52 (desktop parity).
  const W = 230, H = 122, cx = 115, cy = 112, r = 92, sw = 12;
  const pt = (a: number) => ({ x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r });
  const arc = (a0: number, a1: number) => {
    const p0 = pt(a0), p1 = pt(a1);
    return `M ${p0.x} ${p0.y} A ${r} ${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${p1.x} ${p1.y}`;
  };
  const frac = wpm ? Math.min(1, wpm / 200) : 0;
  const typist = pt(Math.PI + Math.PI * (52 / 200));
  return (
    <View style={styles.hero}>
      <Svg width={W} height={H}>
        <Path d={arc(Math.PI, 2 * Math.PI)} stroke="rgba(240,240,240,0.08)" strokeWidth={sw} strokeLinecap="round" fill="none" />
        {wpm ? (
          <>
            <Path d={arc(Math.PI, Math.PI + Math.PI * frac)} stroke={colors.primary} strokeWidth={sw} strokeLinecap="round" fill="none" />
            <Circle cx={typist.x} cy={typist.y} r={3.6} fill={colors.bgScreen} stroke="rgba(240,240,240,0.6)" strokeWidth={1.4} />
          </>
        ) : null}
      </Svg>
      <Text style={[styles.heroNum, !wpm && { fontSize: 34, color: colors.textMuted }]}>
        {wpm ?? '—'}
      </Text>
      <Text variant="metaSm" color={colors.textMuted} style={{ letterSpacing: 2, marginTop: 4 }}>
        WORDS PER MINUTE
      </Text>
      {wpm && data.wpmPercentile != null ? (
        <View style={styles.badge}>
          <Text style={styles.badgeTx}>Top {fmtPct(data.wpmPercentile)}% of typists</Text>
        </View>
      ) : null}
      <Text variant="caption" color={colors.textSecondary} style={{ marginTop: 10, textAlign: 'center' }}>
        {wpm
          ? <>You speak <Text variant="caption" style={{ fontFamily: 'Geist_600SemiBold' }}>{speedX}×</Text> faster than the average typist writes.</>
          : 'Dictate a little more (about a minute of speech) and we’ll clock your speed.'}
      </Text>
    </View>
  );
};

const Band: React.FC<{ data: Insights }> = ({ data }) => {
  const novels = data.totalWords >= 40000
    ? Math.round((data.totalWords / 80000) * 10) / 10 : null;
  const delta = data.monthDeltaPct;
  return (
    <View style={styles.band}>
      <Tile bg={CREAM} ink={CREAM_INK} label="WORDS DICTATED"
        value={fmtN(data.totalWords)}
        tag={delta != null && delta !== 0 ? `${delta > 0 ? '▲' : '▼'}${Math.abs(delta)}%` : undefined}
        sub={`${fmtN(data.todayWords)} today${novels ? ` · ≈ ${novels} novels` : ''}`} />
      <Tile bg={SAGE} ink={SAGE_INK} label="TIME SAVED"
        value={fmtMin(data.savedMonthMin)}
        sub={data.savedMonthMin != null
          ? `this month · vs ${data.typingWpm} wpm typing`
          : 'needs a speed reading first'} />
      <Tile bg={PLUM} ink={PLUM_INK} label="STREAK"
        value={`${data.currentStreak} day${data.currentStreak === 1 ? '' : 's'}`}
        sub={`best ever · ${data.bestStreak} days`} />
      <Tile label="THIS WEEK"
        value={fmtN(data.weekWords)}
        sub={`${fmtN(data.totalDictations)} dictations all time`} />
    </View>
  );
};

const Tile: React.FC<{
  bg?: string; ink?: string; label: string; value: string; sub: string; tag?: string;
}> = ({ bg, ink, label, value, sub, tag }) => {
  const dark = !bg;
  const inkC = ink ?? colors.textPrimary;
  return (
    <View style={[styles.tile, dark
      ? { backgroundColor: colors.surface1, borderWidth: 1, borderColor: colors.borderSubtle }
      : { backgroundColor: bg }]}>
      <Text variant="metaSm" style={{ color: dark ? colors.textMuted : `${ink}99`, fontSize: 10 }}>
        {label}
      </Text>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 6, marginTop: 14 }}>
        <Text style={{ fontFamily: 'Geist_600SemiBold', fontSize: 22, letterSpacing: -0.5, color: inkC }}>
          {value}
        </Text>
        {tag ? (
          <Text style={{ fontFamily: 'JetBrainsMono_600SemiBold', fontSize: 10, color: inkC, opacity: 0.7 }}>
            {tag}
          </Text>
        ) : null}
      </View>
      <Text style={{ fontFamily: 'Geist_400Regular', fontSize: 11, marginTop: 3, color: dark ? colors.textSubtle : inkC, opacity: dark ? 1 : 0.6 }} numberOfLines={1}>
        {sub}
      </Text>
    </View>
  );
};

const Heatmap: React.FC<{ data: Insights }> = ({ data }) => {
  const { width } = useWindowDimensions();
  const GAP = 3;
  const avail = width - 36 - 32; // screen padding + card padding
  const cell = 13;
  const weeks = Math.max(8, Math.floor((avail + GAP) / (cell + GAP)));

  const { cols, mx } = useMemo(() => {
    const series = data.series;
    // Pad so columns are real Sun..Sat weeks, then keep the newest `weeks`.
    const first = new Date(series[0][0] + 'T00:00:00');
    const cells: Array<[string, number] | null> = [];
    for (let i = 0; i < first.getDay(); i++) cells.push(null);
    for (const d of series) cells.push(d);
    const totalWeeks = Math.ceil(cells.length / 7);
    const drop = Math.max(0, totalWeeks - weeks) * 7;
    const kept = cells.slice(drop);
    const columns: Array<Array<[string, number] | null>> = [];
    for (let i = 0; i < kept.length; i += 7) columns.push(kept.slice(i, i + 7));
    const m = Math.max(1, ...kept.map(c => (c ? c[1] : 0)));
    return { cols: columns, mx: m };
  }, [data.series, weeks]);

  const flatLen = cols.reduce((a, c) => a + c.length, 0);
  let idx = -1;
  return (
    <Card label="ACTIVITY" trailing="day by day">
      <View style={{ flexDirection: 'row', gap: GAP }}>
        {cols.map((col, ci) => (
          <View key={ci} style={{ gap: GAP }}>
            {col.map((c, ri) => {
              idx += 1;
              if (!c) return <View key={ri} style={{ width: cell, height: cell }} />;
              const f = c[1] / mx;
              const step = c[1] === 0 ? 0 : f < 0.15 ? 1 : f < 0.35 ? 2 : f < 0.6 ? 3 : f < 0.85 ? 4 : 5;
              const inStreak = data.currentStreak > 1 && idx > flatLen - 1 - data.currentStreak;
              return (
                <View key={ri} style={{
                  width: cell, height: cell, borderRadius: 3.5,
                  backgroundColor: inStreak && step === 0 ? RAMP[1] : RAMP[step],
                  ...(inStreak ? { shadowColor: colors.primary, shadowOpacity: 0.55, shadowRadius: 4, shadowOffset: { width: 0, height: 0 }, elevation: 3 } : {}),
                }} />
              );
            })}
          </View>
        ))}
      </View>
      <View style={styles.hmFoot}>
        <Text variant="caption" color={colors.textSubtle} style={{ flex: 1, fontSize: 12 }}>
          {data.currentStreak > 1 ? `🔥 ${data.currentStreak}-day streak` : 'Every square is a day you dictated'}
          {data.busiestDay ? ` — busiest ${data.busiestDay.day} (${fmtN(data.busiestDay.words)})` : ''}
        </Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
          {RAMP.map((c, i) => (
            <View key={i} style={{ width: 8, height: 8, borderRadius: 2.5, backgroundColor: c }} />
          ))}
        </View>
      </View>
    </Card>
  );
};

const Devices: React.FC<{ data: Insights }> = ({ data }) => {
  if (!data.devices.length) return null;
  const rankCol = [RAMP[4], RAMP[3], RAMP[3], RAMP[2], RAMP[2], RAMP[2]];
  return (
    <Card label="WHERE YOUR WORDS LAND" trailing="all time">
      {data.devices.map((d, i) => (
        <View key={d.name + i} style={{ marginBottom: i === data.devices.length - 1 ? 0 : 11 }}>
          <View style={styles.barRow}>
            <Text variant="bodyXs" style={{ fontSize: 13, flex: 1 }} numberOfLines={1}>{d.name}</Text>
            <Text variant="metaSm" color={colors.textMuted} style={{ fontSize: 11, textTransform: 'none' }}>
              {fmtN(d.words)} · {d.pct}%
            </Text>
          </View>
          <View style={styles.track}>
            <View style={[styles.fill, { width: `${Math.max(1, d.pct)}%`, backgroundColor: rankCol[i] ?? RAMP[2] }]} />
          </View>
        </View>
      ))}
    </Card>
  );
};

// Tick labels under the 24-hour bars. The two '6's are 6AM and 6PM — different
// ticks that legitimately render the same text, so these MUST be keyed by index:
// `key={t}` made React see two children with key `6` and warn "Encountered two
// children with the same key". Hoisted out of render so it isn't rebuilt per frame.
const HOUR_TICKS = ['12AM', '6', 'NOON', '6', '11PM'];

const Rhythm: React.FC<{ data: Insights }> = ({ data }) => {
  const mx = Math.max(1, ...data.hours);
  return (
    <Card label="YOUR RHYTHM">
      <View style={styles.hours}>
        {data.hours.map((v, i) => (
          <View key={i} style={[styles.hourBar, {
            height: `${Math.max(4, Math.round((v / mx) * 100))}%`,
            backgroundColor: i === data.peakHour ? colors.primary : 'rgba(240,240,240,0.14)',
          }]} />
        ))}
      </View>
      <View style={styles.hourAxis}>
        {HOUR_TICKS.map((t, i) => (
          <Text key={i} variant="metaSm" color={colors.textSubtle} style={{ fontSize: 9 }}>{t}</Text>
        ))}
      </View>
      <Text variant="caption" color={colors.textSubtle} style={{ marginTop: 10, fontSize: 12 }}>
        {data.peakHour != null ? (
          <>Peak hour <Text variant="caption" style={{ fontFamily: 'Geist_600SemiBold', fontSize: 12, color: colors.textPrimary }}>{fmtHour(data.peakHour)}</Text>
            {data.morningShare != null ? <> — mornings carry <Text variant="caption" style={{ fontFamily: 'Geist_600SemiBold', fontSize: 12, color: colors.textPrimary }}>{data.morningShare}%</Text> of your words</> : null}</>
        ) : 'Your daily pattern appears here as you dictate.'}
      </Text>
    </Card>
  );
};

const Card: React.FC<{ label: string; trailing?: string; children: React.ReactNode }> = ({ label, trailing, children }) => (
  <View style={styles.card}>
    <View style={styles.cardHead}>
      <Text variant="metaSm" color={colors.textMuted} style={{ fontSize: 10, letterSpacing: 1.6 }}>{label}</Text>
      {trailing ? <Text variant="metaSm" color={colors.textSubtle} style={{ fontSize: 10, textTransform: 'none', letterSpacing: 0.2 }}>{trailing}</Text> : null}
    </View>
    {children}
  </View>
);

const styles = StyleSheet.create({
  seg: {
    flexDirection: 'row', gap: 4, padding: 3, alignSelf: 'center', marginTop: 12,
    backgroundColor: colors.surface2, borderRadius: 10,
  },
  segBtn: { paddingVertical: 6, paddingHorizontal: 14, borderRadius: 8, maxWidth: 160 },
  segBtnOn: { backgroundColor: colors.surface3 },
  root: { flex: 1, backgroundColor: colors.bgScreen, paddingHorizontal: 18 },
  topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  iconCircle: { width: 34, height: 34, borderRadius: 17, backgroundColor: colors.surface2, alignItems: 'center', justifyContent: 'center' },
  empty: { alignItems: 'center', paddingTop: 90, paddingHorizontal: 20 },
  emptyMic: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primaryBorder, alignItems: 'center', justifyContent: 'center', marginBottom: 18 },
  hero: { backgroundColor: colors.surface1, borderWidth: 1, borderColor: colors.borderSubtle, borderRadius: 20, paddingVertical: 22, paddingHorizontal: 16, alignItems: 'center', marginBottom: 12 },
  // lineHeight MUST be set: the shared <Text> defaults to the `body` variant
  // (lineHeight 25), and iOS clips glyphs to the line box — a 52px number in
  // a 25px box lost its top half (reported 2026-08-26). Box bottom lands
  // ~15px above the SVG's bottom edge, mirroring desktop's -78px/62px.
  heroNum: { fontFamily: 'Geist_600SemiBold', fontSize: 52, lineHeight: 56, letterSpacing: -2, color: colors.textPrimary, marginTop: -70 },
  badge: { marginTop: 12, backgroundColor: colors.inkLight, borderRadius: 999, paddingVertical: 7, paddingHorizontal: 15 },
  badgeTx: { fontFamily: 'Geist_600SemiBold', fontSize: 12, color: colors.primaryInk },
  syncHint: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.surface2, borderRadius: 12, paddingVertical: 9, paddingHorizontal: 12, marginBottom: 12 },
  band: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 12 },
  tile: { flexBasis: '47%', flexGrow: 1, borderRadius: 18, padding: 14, minHeight: 104, justifyContent: 'flex-end' },
  card: { backgroundColor: colors.surface1, borderWidth: 1, borderColor: colors.borderSubtle, borderRadius: 18, padding: 16, marginBottom: 12 },
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 13 },
  hmFoot: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 12 },
  barRow: { flexDirection: 'row', alignItems: 'baseline', gap: 10, marginBottom: 5 },
  track: { height: 7, borderRadius: 4, backgroundColor: 'rgba(240,240,240,0.05)' },
  fill: { height: '100%', borderRadius: 4 },
  hours: { flexDirection: 'row', alignItems: 'flex-end', gap: 3, height: 64 },
  hourBar: { flex: 1, borderRadius: 3, minHeight: 2 },
  hourAxis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 },
});

export default InsightsScreen;
