import React from 'react';
import { View, StyleSheet, Pressable } from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { Text } from './Text';
import { colors, radius, space, pressedStyle } from '../theme';
import type { useOrganization } from '../hooks/useOrganization';

type Org = ReturnType<typeof useOrganization>;

const APP_COLORS = ['#C85A3E', '#EADFCE', '#A8BCA1', '#C3AECB', '#8a7d74'];

/** SVG path for a member's daily-words sparkline over the trailing `days`
 *  window. Gap days are honest zeroes, so a quiet week reads flat rather than
 *  connecting two spikes. Returns null when there's nothing to draw. */
const sparkPath = (
  pairs: Array<[string, number]> | undefined, days: number, w: number, h: number,
): string | null => {
  if (!pairs || pairs.length === 0) return null;
  const byDay = new Map(pairs);
  const vals: number[] = [];
  const d = new Date();
  d.setDate(d.getDate() - (days - 1));
  for (let i = 0; i < days; i++) {
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    vals.push(Number(byDay.get(key) ?? 0));
    d.setDate(d.getDate() + 1);
  }
  const max = Math.max(...vals);
  if (max <= 0) return null;
  const step = w / (days - 1);
  return vals
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(h - (v / max) * (h - 1)).toFixed(1)}`)
    .join(' ');
};

const whenLabel = (iso: string | null) => {
  if (!iso) return '—';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '—';
  const days = Math.floor((Date.now() - t) / 86400000);
  return days <= 0 ? 'today' : days === 1 ? 'yesterday' : `${days}d ago`;
};

/**
 * Team — the organization layer on mobile (IDI-216 Phase 6).
 *
 * One screen, four states: no team (create/join), member, admin, owner. Role
 * gating is enforced server-side by RLS + the RPCs; the checks here only decide
 * what to DRAW, so a stale cached role can never turn into an actual privilege.
 *
 * In a team the screen is split in two (2026-08-26): the MAIN view is read-only
 * numbers (stats, usage ranking, app mix, leaderboard); everything you *manage* —
 * roster roles/removal, pending invites, the invite form, the owner's leaderboard
 * and team-wide-visibility switches, the dictionary/privacy pointers and Leave
 * team — sits behind the gear in the title row as "Team settings".
 *
 * Reached from the SidePanel under Workspace, and hosted in the `Menu` modal
 * stack — so it carries its own chevron-back (conventions §Back affordances) and
 * uses native Alert-backed `confirm()` rather than the JS ConfirmDialog, which
 * doesn't reliably receive touches over a native-stack modal (Hard Rule #14).
 */
/**
 * TeamInsights — the team's read-only numbers: stat tiles, the usage ranking
 * (with per-member sparklines), "Where the team writes" and the opt-in
 * leaderboard. Rendered by the Team screen's main view AND by Insights under
 * its `<team>` scope (user request, 2026-08-27), so the two never drift.
 * Caller guarantees `t.hasTeam`. Role gating is server-side; the checks here
 * only choose copy and what to draw.
 */
export const TeamInsights: React.FC<{ t: Org }> = ({ t }) => {
  const { org } = t;
  // Owner opened per-person stats to the whole team (2026-08-25): members then
  // read the same usage rows admins do, so the copy switches voice with the data.
  const seeAll = t.isAdmin || !!org.stats_visible_to_members;
  // ── ranking + app mix ────────────────────────────────────────────────────
  // Ranked from t.usage, which is admin-only and gated on each member's
  // usage_consent. The separate opt-in `board` is what non-admins see; this list
  // is only rendered inside the isAdmin branch below.
  const ranked = [...t.usage.rows].sort((a, b) => (b.words || 0) - (a.words || 0));
  const rankMax = Math.max(1, ...ranked.map((r) => r.words || 0));
  // Words ÷ minutes of speech, and only with enough measured audio to mean
  // anything — duration_ms is NULL on older rows, so a thin sample would invent
  // a number rather than report one.
  const wpmOf = (r: { words: number; speech_ms: number }) =>
    r.speech_ms >= 120_000 ? `${Math.round(r.words / (r.speech_ms / 60_000))} wpm` : '';
  const topAppOf = (uid: string) => {
    const a = (t.apps[uid] ?? [])[0];
    return a ? `mostly ${a.app}` : '';
  };
  const appMembers = (org.members ?? [])
    .map((member) => {
      const apps = t.apps[member.user_id] ?? [];
      return { member, apps, total: apps.reduce((sum, a) => sum + (a.dictations || 0), 0) };
    })
    .filter((x) => x.apps.length > 0 && x.total > 0);
  const board = t.board;
  const maxWords = Math.max(1, ...board.rows.map((r) => r.words || 0));


  return (
    <>
        <View style={styles.stats}>
          <View style={styles.stat}>
            <Text variant="metaSm" color={colors.textMuted}>
              Members
            </Text>
            <Text variant="subtitle">{`${org.members.length}/${org.seats}`}</Text>
          </View>
          <View style={styles.stat}>
            <Text variant="metaSm" color={colors.textMuted}>
              Plan
            </Text>
            <Text variant="bodyLg">{org.plan}</Text>
          </View>
          <View style={styles.stat}>
            <Text variant="metaSm" color={colors.textMuted}>
              Top
            </Text>
            <Text variant="subtitle">{board.rows.length ? board.rows[0].words : 0}</Text>
          </View>
        </View>

        {/* Usage — for EVERYONE. A plain member's `ranked` holds exactly their own
            row (the RPC does that split), so this section is their own numbers
            rather than nothing at all. It used to be admin-gated, which meant a
            member's whole team view was zeroes. */}
        {(
          <>
            <Text variant="label" style={styles.section}>
              {seeAll ? 'Usage' : 'Your usage on this team'}
            </Text>
            {!seeAll && (
              <Text variant="caption" color={colors.textMuted} style={styles.sectionSub}>
                Only your own numbers appear here. Your admins see the team's totals.
              </Text>
            )}
            {seeAll && ranked.length > 0 && (
              <Text variant="caption" color={colors.textMuted} style={styles.sectionSub}>
                {`${org.name || 'The team'} spoke ${ranked
                  .reduce((a, r) => a + (r.words || 0), 0)
                  .toLocaleString('en-US')} words in the last ${t.usageDays} days.`}
              </Text>
            )}
            <View style={styles.segRow}>
              {[7, 30, 90].map((d) => (
                <Pressable
                  key={d}
                  onPress={() => t.setUsageDays(d)}
                  style={({ pressed }) => [
                    styles.seg,
                    t.usageDays === d && styles.segOn,
                    pressed && pressedStyle,
                  ]}
                >
                  <Text variant="metaSm" color={t.usageDays === d ? colors.textPrimary : colors.textMuted}>
                    {`${d}d`}
                  </Text>
                </Pressable>
              ))}
            </View>
            {ranked.length === 0 ? (
              <Text variant="caption" color={colors.textDisabled} style={styles.sectionSub}>
                {seeAll
                  ? 'Nobody on the team has dictated in this window yet.'
                  : `You haven't dictated in the last ${t.usageDays} days.`}
              </Text>
            ) : (
              ranked.map((r, i) => (
                <View key={r.user_id} style={[styles.rankRow, i === 0 && styles.rankRowTop]}>
                  {/* The bar sits behind the text rather than beside it: at phone
                      width a separate chart column leaves no room for the name. */}
                  <View
                    style={[
                      styles.rankFill,
                      i === 0 && styles.rankFillTop,
                      { width: `${Math.max(3, Math.round(((r.words || 0) / rankMax) * 100))}%` },
                    ]}
                  />
                  <Text variant="metaSm" color={i === 0 ? colors.primary : colors.textMuted} style={styles.rankNum}>
                    {i + 1}
                  </Text>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text variant="label" numberOfLines={1}>
                      {r.display_name || r.email}
                    </Text>
                    <Text variant="caption" color={colors.textMuted} numberOfLines={1}>
                      {[
                        `${r.dictations} dictation${r.dictations === 1 ? '' : 's'}`,
                        wpmOf(r),
                        topAppOf(r.user_id),
                        whenLabel(r.last_active),
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </Text>
                    {(() => {
                      const p = sparkPath(t.series[r.user_id], 42, 120, 16);
                      return p ? (
                        <Svg width={120} height={16} style={{ marginTop: 3 }}>
                          <Path d={p} stroke={i === 0 ? colors.primary : colors.textDisabled} strokeWidth={1.4} fill="none" />
                        </Svg>
                      ) : null;
                    })()}
                  </View>
                  <Text variant="label">{r.words.toLocaleString('en-US')}</Text>
                </View>
              ))
            )}
            <Text variant="caption" color={colors.textMuted} style={styles.sectionSub}>
              Counts, durations and the names of the apps people dictate into — never what they
              actually said, to anyone.
            </Text>

            {/* Where the team writes */}
            <Text variant="label" style={styles.section}>
              {seeAll ? 'Where the team writes' : 'Where you write'}
            </Text>
            {appMembers.length === 0 ? (
              <Text variant="caption" color={colors.textDisabled} style={styles.sectionSub}>
                Nothing here yet. Flume only started recording which app a dictation went into on
                21 Aug 2026, and only on desktop — a phone has no frontmost app to read. This fills
                in as {t.isAdmin ? 'the team dictates' : 'you dictate'}; nothing from before then can be
                recovered.
              </Text>
            ) : (
              appMembers.map(({ member, apps, total }) => (
                <View key={member.user_id} style={{ marginBottom: space.m }}>
                  <View style={styles.appHead}>
                    <Text variant="label" numberOfLines={1} style={{ flex: 1, minWidth: 0 }}>
                      {member.display_name || member.email}
                    </Text>
                    <Text variant="metaSm" color={colors.textMuted}>
                      {`${apps[0].app} · ${total}`}
                    </Text>
                  </View>
                  <View style={styles.appBar}>
                    {apps.slice(0, 5).map((a, i) => (
                      <View
                        key={a.app}
                        style={{
                          width: `${(a.dictations / total) * 100}%`,
                          height: '100%',
                          backgroundColor: APP_COLORS[i],
                        }}
                      />
                    ))}
                  </View>
                  <View style={styles.appLegend}>
                    {apps.slice(0, 5).map((a, i) => (
                      <View key={a.app} style={styles.appLegendItem}>
                        <View style={[styles.appDot, { backgroundColor: APP_COLORS[i] }]} />
                        <Text variant="caption" color={colors.textMuted}>
                          {`${a.app} ${Math.round((a.dictations / total) * 100)}%`}
                        </Text>
                      </View>
                    ))}
                  </View>
                </View>
              ))
            )}
          </>
        )}

        {/* Leaderboard — list only; the owner's enable switch is in Team settings. */}
        {org.leaderboard_enabled && (
          <>
            <Text variant="label" style={styles.section}>
              Leaderboard
            </Text>
            {board.rows.length === 0 ? (
              <Text variant="caption" color={colors.textDisabled} style={styles.sectionSub}>
                Nobody on the team has dictated in this window yet.
              </Text>
            ) : (
              board.rows.map((r, i) => (
                <View key={r.user_id} style={styles.row}>
                  <Text variant="metaSm" color={colors.textMuted} style={{ width: 20 }}>
                    {i + 1}
                  </Text>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text variant="label" numberOfLines={1}>
                      {r.display_name || 'Member'}
                    </Text>
                    <View style={styles.bar}>
                      <View style={[styles.barFill, { width: `${Math.round(((r.words || 0) / maxWords) * 100)}%` }]} />
                    </View>
                  </View>
                  <Text variant="caption" color={colors.textMuted}>
                    {`${r.words} words`}
                  </Text>
                </View>
              ))
            )}
          </>
        )}

    </>
  );
};

const styles = StyleSheet.create({
  stats: { flexDirection: 'row', gap: space.s, marginTop: space.m, marginBottom: space.xs },
  stat: {
    flex: 1,
    backgroundColor: colors.surface1,
    borderRadius: radius.md,
    padding: space.s,
    gap: 4,
  },
  section: { marginTop: space.base, marginBottom: space.xs },
  sectionSub: { marginBottom: space.s },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.s,
    paddingVertical: space.s,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderSubtle,
  },
  rankRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.s,
    paddingVertical: space.s,
    paddingHorizontal: space.s,
    borderRadius: radius.sm,
    overflow: 'hidden',
    marginBottom: 2,
  },
  rankRowTop: { borderWidth: 1, borderColor: colors.primaryBorder },
  rankFill: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    backgroundColor: 'rgba(240,240,240,0.045)',
  },
  rankFillTop: { backgroundColor: 'rgba(200,90,62,0.16)' },
  rankNum: { width: 18, textAlign: 'center' },
  appHead: { flexDirection: 'row', alignItems: 'baseline', gap: space.s, marginBottom: 6 },
  appBar: { flexDirection: 'row', height: 9, borderRadius: 999, overflow: 'hidden', backgroundColor: colors.surface2 },
  appLegend: { flexDirection: 'row', flexWrap: 'wrap', gap: space.s, marginTop: 6 },
  appLegendItem: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  appDot: { width: 7, height: 7, borderRadius: 2 },
  segRow: { flexDirection: 'row', gap: space.xs, marginBottom: space.s },
  seg: {
    paddingHorizontal: space.s,
    paddingVertical: 6,
    borderRadius: radius.xs,
    backgroundColor: colors.surface2,
  },
  segOn: { backgroundColor: colors.surface3 },
  bar: { height: 5, borderRadius: 3, backgroundColor: colors.surface2, marginTop: 5, overflow: 'hidden' },
  barFill: { height: '100%', backgroundColor: colors.primary, borderRadius: 3 },
});
