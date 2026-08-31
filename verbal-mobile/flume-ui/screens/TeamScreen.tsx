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
import { TeamInsights } from '../components/TeamInsights';
import type { OrgMember } from '../hooks/useOrganization';

type Props = { onBack: () => void };

const initial = (m: { display_name?: string; email?: string }) =>
  ((m.display_name || m.email || '?').trim()[0] || '?').toUpperCase();

export const TeamScreen: React.FC<Props> = ({ onBack }) => {
  const insets = useSafeAreaInsets();
  const t = useOrganization();
  const [refreshing, setRefreshing] = useState(false);

  // Create / join
  const [name, setName] = useState('');
  const [company, setCompany] = useState('');
  const [token, setToken] = useState('');
  // Invite. The form opens on demand (user request, 2026-08-25) — a permanently
  // expanded email field read as "the screen wants something from me" on every
  // visit; desktop's roster has the same shape ("Add teammate" opens the form).
  const [email, setEmail] = useState('');
  const [inviteAdmin, setInviteAdmin] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  // Team settings live behind a gear (user request, 2026-08-26): the roster,
  // invites, owner toggles and pointers all on one scroll read as "complicated".
  // The main view is now just the numbers; everything you *manage* is one tap away.
  const [showSettings, setShowSettings] = useState(false);

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

  // ── team settings (behind the gear) ───────────────────────────────────────
  if (showSettings) {
    return (
      <View style={[styles.screen, { paddingTop: insets.top + space.s }]}>
        <View style={styles.header}>
          <Pressable
            onPress={() => {
              setShowSettings(false);
              setInviteOpen(false);
              setEmail('');
            }}
            hitSlop={12}
            style={({ pressed }) => pressed && pressedStyle}
          >
            <Ionicons name="chevron-back" size={26} color={colors.textPrimary} />
          </Pressable>
          <Text variant="metaSm" color={colors.textMuted} style={styles.eyebrow}>
            {org.name || 'Team'}
          </Text>
        </View>
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={{ paddingBottom: insets.bottom + space.xxl }}
          keyboardShouldPersistTaps="handled"
        >
          <Text variant="title" style={styles.title}>
            Team settings
          </Text>

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

            {!inviteOpen ? (
              <Button
                label="Invite someone"
                onPress={() => setInviteOpen(true)}
                style={{ marginTop: space.m }}
              />
            ) : (
              <>
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
                  autoFocus
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
                      if (res.ok) {
                        setEmail('');
                        setInviteOpen(false);
                      }
                    })
                  }
                  style={{ marginTop: space.s }}
                />
                <Button
                  label="Cancel"
                  variant="ghost"
                  onPress={() => {
                    setInviteOpen(false);
                    setEmail('');
                  }}
                  style={{ marginTop: space.xs }}
                />
              </>
            )}
          </>
        )}

        {/* Leaderboard (owner switch) */}
        {t.isOwner && (
          <>
            <Text variant="label" style={styles.section}>
              Leaderboard
            </Text>
            <Text variant="caption" color={colors.textMuted} style={styles.sectionSub}>
              A team-visible ranking by words dictated. On for everyone or off for everyone — every member who shares counts appears.
            </Text>
            <View style={styles.switchRow}>
              <Text variant="caption" color={colors.textSecondary}>
                Visible to the team
              </Text>
              <Switch
                value={!!org.leaderboard_enabled}
                onValueChange={(v) => guard(() => t.saveSettings({ leaderboard_enabled: v }))}
                trackColor={{ true: colors.primary, false: colors.surface3 }}
              />
            </View>
          </>
        )}
        {/* Team-wide stats visibility (owner-only, 2026-08-25): by default only
            owners/admins see the roster's numbers; this opens the same
            consenting-member stats to every member. An individual's own
            sharing switch still wins — the org flag widens the audience,
            never overrides an opt-out (same contract as the leaderboard). */}
        {t.isOwner && (
          <>
            <Text variant="label" style={styles.section}>
              Team-wide visibility
            </Text>
            <Text variant="caption" color={colors.textMuted} style={styles.sectionSub}>
              Let every member see the same per-person stats admins do. Anyone who turned off sharing
              stays hidden from everyone.
            </Text>
            <View style={styles.switchRow}>
              <Text variant="caption" color={colors.textSecondary}>
                {"Everyone sees everyone's stats"}
              </Text>
              <Switch
                value={!!org.stats_visible_to_members}
                onValueChange={(v) => guard(() => t.saveSettings({ stats_visible_to_members: v }))}
                trackColor={{ true: colors.primary, false: colors.surface3 }}
              />
            </View>
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

        {/* Privacy — a POINTER. The toggles live in Settings → TEAM PRIVACY, the
            same place every other "what does this app do with my data" switch is,
            so there is one answer to "where do I turn that off?". */}
        <Text variant="label" style={styles.section}>
          Your privacy
        </Text>
        <Text variant="caption" color={colors.textMuted} style={styles.sectionSub}>
          {org.usage_consent
            ? `You are sharing your dictation counts with admins${org.leaderboard_enabled ? ' and appear on the team ranking' : ''}.`
            : 'You are not sharing anything — your numbers appear in no admin view.'}
          {'\n'}What you dictate is never shared either way. Change it under Settings → Team privacy.
        </Text>


          {/* Hidden for the owner: org_remove_member returns cannot_remove_owner,
              so the button would always fail for the one person most likely to press it. */}
          {!t.isOwner && (
            <Button
              label="Leave team"
              variant="ghost"
              disabled={busy}
              onPress={onLeave}
              style={{ marginTop: space.xl }}
            />
          )}

          {!!t.error && (
            <Text variant="caption" color={colors.textMuted} style={styles.errorNote}>
              {t.error}
            </Text>
          )}
        </ScrollView>
      </View>
    );
  }

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
          <Pressable
            onPress={() => setShowSettings(true)}
            hitSlop={10}
            accessibilityLabel="Team settings"
            style={({ pressed }) => [styles.gearBtn, pressed && pressedStyle]}
          >
            <Ionicons name="settings-outline" size={20} color={colors.textSecondary} />
          </Pressable>
        </View>

        <TeamInsights t={t} />
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
  gearBtn: {
    width: 34,
    height: 34,
    borderRadius: radius.xs,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
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
