import React, { useState } from 'react';
import {
  View, StyleSheet, ScrollView, Pressable, Switch, TextInput, RefreshControl, ActivityIndicator,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text, Button } from '../components';
import { colors, radius, space, pressedStyle } from '../theme';
import { confirm } from '../components/ConfirmDialog';
import { useOrganization } from '../hooks/useOrganization';
import type { OrgMember } from '../hooks/useOrganization';

// Flume's pastels, in the order the design system uses them for categorical data.
const APP_COLORS = ['#C85A3E', '#EADFCE', '#A8BCA1', '#C3AECB', '#8a7d74'];

type Props = { onBack: () => void };

const initial = (m: { display_name?: string; email?: string }) =>
  ((m.display_name || m.email || '?').trim()[0] || '?').toUpperCase();

const minutes = (ms: number) => {
  const m = Math.round((ms || 0) / 60000);
  return m >= 60 ? `${(m / 60).toFixed(1)}h` : `${m}m`;
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
 * Reached from the SidePanel under Workspace, and hosted in the `Menu` modal
 * stack — so it carries its own chevron-back (conventions §Back affordances) and
 * uses native Alert-backed `confirm()` rather than the JS ConfirmDialog, which
 * doesn't reliably receive touches over a native-stack modal (Hard Rule #14).
 */
export const TeamScreen: React.FC<Props> = ({ onBack }) => {
  const insets = useSafeAreaInsets();
  const t = useOrganization();
  const [refreshing, setRefreshing] = useState(false);

  // Create / join
  const [name, setName] = useState('');
  const [company, setCompany] = useState('');
  const [token, setToken] = useState('');
  // Invite
  const [email, setEmail] = useState('');
  const [inviteAdmin, setInviteAdmin] = useState(false);
  const [busy, setBusy] = useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    await t.reload(true);
    setRefreshing(false);
  };

  const guard = async (fn: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  const header = (
    <View style={styles.header}>
      <Pressable onPress={onBack} hitSlop={12} style={({ pressed }) => pressed && pressedStyle}>
        <Ionicons name="chevron-back" size={26} color={colors.textPrimary} />
      </Pressable>
      <Text variant="metaSm" color={colors.textMuted} style={styles.eyebrow}>
        Workspace
      </Text>
    </View>
  );

  if (t.loading && !t.hasTeam) {
    return (
      <View style={[styles.screen, { paddingTop: insets.top + space.s }]}>
        {header}
        <ActivityIndicator color={colors.textMuted} style={{ marginTop: space.xl }} />
      </View>
    );
  }

  // ── no team ────────────────────────────────────────────────────────────────
  if (!t.hasTeam) {
    return (
      <View style={[styles.screen, { paddingTop: insets.top + space.s }]}>
        {header}
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={{ paddingBottom: insets.bottom + space.xxl }}
          keyboardShouldPersistTaps="handled"
        >
          <Text variant="title" style={styles.title}>
            Team
          </Text>
          <Text variant="bodyXs" color={colors.textMuted} style={styles.lead}>
            Share a dictionary and snippets with everyone who dictates the same names, products and
            jargon.
          </Text>

          <View style={styles.card}>
            <Text variant="label" style={styles.cardTitle}>
              Create a team
            </Text>
            <Text variant="caption" color={colors.textMuted} style={styles.cardSub}>
              You'll be the owner, and can invite people by email straight after.
            </Text>
            <TextInput
              style={styles.input}
              value={name}
              onChangeText={setName}
              placeholder="Team name"
              placeholderTextColor={colors.textDisabled}
              autoCapitalize="words"
            />
            <TextInput
              style={styles.input}
              value={company}
              onChangeText={setCompany}
              placeholder="Company (optional)"
              placeholderTextColor={colors.textDisabled}
              autoCapitalize="words"
            />
            <Button
              label="Create team"
              disabled={busy}
              onPress={() => guard(() => t.createTeam(name.trim(), company.trim()))}
              style={{ marginTop: space.s }}
            />
          </View>

          <View style={styles.card}>
            <Text variant="label" style={styles.cardTitle}>
              Have an invite?
            </Text>
            <Text variant="caption" color={colors.textMuted} style={styles.cardSub}>
              Paste the link from your invite email. It only works for the address it was sent to.
            </Text>
            <TextInput
              style={styles.input}
              value={token}
              onChangeText={setToken}
              placeholder="Invite link or code"
              placeholderTextColor={colors.textDisabled}
              autoCapitalize="none"
              autoCorrect={false}
            />
            <Button
              label="Join team"
              variant="ghost"
              disabled={busy}
              onPress={() => guard(() => t.joinTeam(token))}
              style={{ marginTop: space.s }}
            />
          </View>

          {!!t.error && (
            <Text variant="caption" color={colors.textMuted} style={styles.errorNote}>
              {t.error}
            </Text>
          )}
        </ScrollView>
      </View>
    );
  }

  // ── in a team ──────────────────────────────────────────────────────────────
  const { org } = t;
  const dict = org.dictionary;

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

  const removeOne = async (m: OrgMember) => {
    const ok = await confirm({
      title: `Remove ${m.display_name || m.email}?`,
      message: 'They keep their own dictionary and history. The shared ones stop applying.',
      confirmLabel: 'Remove',
      destructive: true,
    });
    if (ok) await guard(() => t.remove(m.user_id));
  };

  const onLeave = async () => {
    const ok = await confirm({
      title: 'Leave this team?',
      message: 'You keep your own dictionary and history; the shared ones stop applying.',
      confirmLabel: 'Leave',
      destructive: true,
    });
    if (ok) await guard(() => t.leave());
  };

  return (
    <View style={[styles.screen, { paddingTop: insets.top + space.s }]}>
      {header}
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingBottom: insets.bottom + space.xxl }}
        keyboardShouldPersistTaps="handled"
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.textMuted} />
        }
      >
        <View style={styles.titleRow}>
          <View style={{ flex: 1 }}>
            <Text variant="title" style={styles.title}>
              {org.name || 'Team'}
            </Text>
            {!!org.company_name && (
              <Text variant="bodyXs" color={colors.textMuted}>
                {org.company_name}
              </Text>
            )}
          </View>
          <View style={styles.rolePill}>
            <Text variant="metaSm" color={colors.textSecondary}>
              {org.role}
            </Text>
          </View>
        </View>

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

        {/* Members */}
        <Text variant="label" style={styles.section}>
          Members
        </Text>
        {org.members.map((m) => (
          <View key={m.user_id} style={styles.row}>
            <View style={styles.avatar}>
              <Text variant="caption">{initial(m)}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text variant="label" numberOfLines={1}>
                {m.display_name || m.email || 'Member'}
              </Text>
              <Text variant="caption" color={colors.textMuted} numberOfLines={1}>
                {m.email}
              </Text>
            </View>
            {t.isAdmin && m.role !== 'owner' ? (
              <>
                <Pressable
                  onPress={() => guard(() => t.setRole(m.user_id, m.role === 'admin' ? 'member' : 'admin'))}
                  style={({ pressed }) => [styles.miniBtn, pressed && pressedStyle]}
                >
                  <Text variant="metaSm" color={colors.textSecondary}>
                    {m.role}
                  </Text>
                </Pressable>
                <Pressable
                  onPress={() => removeOne(m)}
                  hitSlop={10}
                  style={({ pressed }) => pressed && pressedStyle}
                >
                  <Ionicons name="close" size={18} color={colors.textMuted} />
                </Pressable>
              </>
            ) : (
              <Text variant="metaSm" color={colors.textMuted}>
                {m.role}
              </Text>
            )}
          </View>
        ))}

        {/* Invites (admins) */}
        {t.isAdmin && (
          <>
            {t.invites.length > 0 && (
              <>
                <Text variant="label" style={styles.section}>
                  Pending invites
                </Text>
                {t.invites.map((iv) => (
                  <View key={iv.id} style={styles.row}>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text variant="caption" color={colors.textMuted} numberOfLines={1}>
                        {iv.email}
                      </Text>
                    </View>
                    <Text variant="metaSm" color={colors.textMuted}>
                      {iv.role}
                    </Text>
                    <Pressable
                      onPress={() => guard(() => t.revoke(iv.id))}
                      hitSlop={10}
                      style={({ pressed }) => pressed && pressedStyle}
                    >
                      <Ionicons name="close" size={18} color={colors.textMuted} />
                    </Pressable>
                  </View>
                ))}
              </>
            )}

            <Text variant="label" style={styles.section}>
              Invite someone
            </Text>
            <Text variant="caption" color={colors.textMuted} style={styles.sectionSub}>
              They get a one-time link that expires in 7 days and only works for that address.
            </Text>
            <TextInput
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              placeholder="name@company.com"
              placeholderTextColor={colors.textDisabled}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
            />
            <View style={styles.switchRow}>
              <Text variant="caption" color={colors.textSecondary}>
                Invite as admin
              </Text>
              <Switch
                value={inviteAdmin}
                onValueChange={setInviteAdmin}
                trackColor={{ true: colors.primary, false: colors.surface3 }}
              />
            </View>
            <Button
              label="Send invite"
              disabled={busy}
              onPress={() =>
                guard(async () => {
                  const res = await t.invite(email.trim(), inviteAdmin ? 'admin' : 'member');
                  if (res.ok) setEmail('');
                })
              }
              style={{ marginTop: space.s }}
            />
          </>
        )}

        {/* Shared dictionary — a POINTER, not an editor. The editing lives on the
            Dictionary screen under a Team scope, so there is one place to learn. */}
        <Text variant="label" style={styles.section}>
          Shared dictionary
        </Text>
        <Text variant="caption" color={colors.textMuted} style={styles.sectionSub}>
          {(dict.vocabulary ?? []).length + (dict.replacements ?? []).length + (dict.snippets ?? []).length > 0
            ? `${(dict.vocabulary ?? []).length} words, ${(dict.replacements ?? []).length} rules and ${(dict.snippets ?? []).length} snippets apply to everyone on ${org.name || 'the team'}.`
            : 'Nothing shared yet. Names, jargon and product words the whole team should get right belong here.'}
          {'\n'}Edit it under Dictionary → {org.name || 'Team'}. Your own entries always win a clash.
        </Text>

        {/* Usage — for EVERYONE. A plain member's `ranked` holds exactly their own
            row (the RPC does that split), so this section is their own numbers
            rather than nothing at all. It used to be admin-gated, which meant a
            member's whole team view was zeroes. */}
        {(
          <>
            <Text variant="label" style={styles.section}>
              {t.isAdmin ? 'Usage' : 'Your usage on this team'}
            </Text>
            {!t.isAdmin && (
              <Text variant="caption" color={colors.textMuted} style={styles.sectionSub}>
                Only your own numbers appear here. Your admins see the team's totals.
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
                {t.isAdmin
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
              {t.isAdmin ? 'Where the team writes' : 'Where you write'}
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

        {/* Leaderboard */}
        <Text variant="label" style={styles.section}>
          Leaderboard
        </Text>
        {!org.leaderboard_enabled ? (
          <>
            <Text variant="caption" color={colors.textMuted} style={styles.sectionSub}>
              {t.isOwner
                ? 'A team-visible ranking by words dictated. People appear only if they opt in themselves.'
                : "Your team owner hasn't turned this on."}
            </Text>
            {t.isOwner && (
              <View style={styles.switchRow}>
                <Text variant="caption" color={colors.textSecondary}>
                  Enable for this team
                </Text>
                <Switch
                  value={false}
                  onValueChange={() => guard(() => t.saveSettings({ leaderboard_enabled: true }))}
                  trackColor={{ true: colors.primary, false: colors.surface3 }}
                />
              </View>
            )}
          </>
        ) : (
          <>
            {board.rows.length === 0 ? (
              <Text variant="caption" color={colors.textDisabled} style={styles.sectionSub}>
                Nobody has opted in yet.
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
            {t.isOwner && (
              <View style={styles.switchRow}>
                <Text variant="caption" color={colors.textSecondary}>
                  Visible to the team
                </Text>
                <Switch
                  value
                  onValueChange={() => guard(() => t.saveSettings({ leaderboard_enabled: false }))}
                  trackColor={{ true: colors.primary, false: colors.surface3 }}
                />
              </View>
            )}
          </>
        )}

        {/* Privacy — a POINTER. The toggles live in Settings → TEAM PRIVACY, the
            same place every other "what does this app do with my data" switch is,
            so there is one answer to "where do I turn that off?". */}
        <Text variant="label" style={styles.section}>
          Your privacy
        </Text>
        <Text variant="caption" color={colors.textMuted} style={styles.sectionSub}>
          {org.usage_consent
            ? `You are sharing your dictation counts with admins${org.leaderboard_opt_in ? ' and appearing on the ranking' : ', and staying off the ranking'}.`
            : 'You are not sharing anything — your numbers appear in no admin view.'}
          {'\n'}What you dictate is never shared either way. Change it under Settings → Team privacy.
        </Text>

        {!!t.error && (
          <Text variant="caption" color={colors.textMuted} style={styles.errorNote}>
            {t.error}
          </Text>
        )}
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bgScreen, paddingHorizontal: space.base },
  header: { flexDirection: 'row', alignItems: 'center', gap: space.s, marginBottom: space.s },
  eyebrow: { marginTop: 2 },
  title: { marginBottom: 4 },
  titleRow: { flexDirection: 'row', alignItems: 'flex-start', gap: space.s },
  lead: { marginBottom: space.base },
  rolePill: {
    paddingHorizontal: space.s,
    paddingVertical: 5,
    borderRadius: radius.xs,
    backgroundColor: colors.surface2,
  },
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
  card: {
    backgroundColor: colors.surface1,
    borderRadius: radius.md,
    padding: space.m,
    marginBottom: space.m,
  },
  cardTitle: { marginBottom: 4 },
  cardSub: { marginBottom: space.s },
  input: {
    backgroundColor: colors.surface2,
    borderRadius: radius.xs,
    paddingHorizontal: space.s,
    paddingVertical: 11,
    color: colors.textPrimary,
    fontSize: 15,
    marginBottom: space.xs,
  },
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
  avatar: {
    width: 32,
    height: 32,
    borderRadius: radius.xs,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  miniBtn: {
    paddingHorizontal: space.xs,
    paddingVertical: 5,
    borderRadius: radius.xs,
    backgroundColor: colors.surface2,
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.s,
    paddingVertical: space.xs,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.xs, marginBottom: space.s },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: space.s,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.surface2,
  },
  addRow: { flexDirection: 'row', alignItems: 'center', gap: space.xs, marginBottom: space.s },
  addBtn: {
    width: 42,
    height: 42,
    borderRadius: radius.xs,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
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
  errorNote: { marginTop: space.m },
});
