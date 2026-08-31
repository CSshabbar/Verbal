import React, { useEffect, useState } from 'react';
import {
  View, StyleSheet, ScrollView, TextInput, Switch, Pressable, Alert,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Haptics from 'expo-haptics';
import { Text, Card, ListRow, Button } from '../components';
import { confirm } from '../components/ConfirmDialog';
import { Dictionary, fetchRemote, saveDictionaryChecked } from '../../lib/dictionary';
import { getSpokenLanguage, setSpokenLanguage, SPOKEN_LANGUAGES } from '../../lib/groq';
import { colors, radius, type, pressedStyle } from '../theme';
import { useAuth } from '../hooks/useAuth';
import { useSyncEnabled, setSyncEnabled } from '../hooks/useSyncEnabled';
import { useOrganization } from '../hooks/useOrganization';
import {
  getDeviceName, setDeviceName,
  getUserId, setUserId, setPairedUserId, getStoredUserId, clearAccountData,
  clearHistory,
  getNotesFeatureFlags, setNotesFeatureFlag,
  DEFAULT_NOTES_FLAGS, type NotesFeatureFlags,
  getClipboardHistoryEnabled, setClipboardHistoryEnabled,
  getTransformEnabled, setTransformEnabled,
} from '../../lib/storage';

type Props = { onBack: () => void; onOpenDevices: () => void;
               onOpenSnippets: () => void; onOpenModels: () => void };

/**
 * Settings — keys & preferences, in the Flume visual language.
 * Reads/writes the local settings store directly (lib/storage).
 */
export const SettingsScreen: React.FC<Props> = ({ onBack, onOpenDevices, onOpenSnippets, onOpenModels }) => {
  const insets = useSafeAreaInsets();
  const team = useOrganization();

  const leaveTeam = async () => {
    const ok = await confirm({
      title: 'Leave this team?',
      message: 'You keep your own dictionary and history; the shared ones stop applying.',
      confirmLabel: 'Leave',
      destructive: true,
    });
    if (ok) await team.leave();
  };
  const { user, signOut, deleteAccount } = useAuth();
  const [deletingAccount, setDeletingAccount] = useState(false);

  const [deviceName, setDeviceNameState] = useState('');
  const [userId, setUserIdState] = useState('');
  // Live value from the ONE sync store (IDI-171) — no local copy to drift from
  // the Menu toggle or the Devices self-row switch.
  const sync = useSyncEnabled();
  const [savedName, setSavedName] = useState(false);
  const [savedUser, setSavedUser] = useState(false);

  const [dict, setDict] = useState<Dictionary>({ vocabulary: [], replacements: [], snippets: [] });
  // The initial state above is EMPTY, and this screen mounts long before
  // fetchRemote() resolves. Editing in that window used to push the empty
  // dictionary over the real one (wiping snippets in particular), so every
  // mutation is gated on `loaded` (IDI-174).
  const [dictLoaded, setDictLoaded] = useState(false);
  const [dictSyncError, setDictSyncError] = useState(false);
  const [newWord, setNewWord] = useState('');
  const [repFrom, setRepFrom] = useState('');
  const [repTo, setRepTo] = useState('');

  const [notesFlags, setNotesFlags] = useState<NotesFeatureFlags>(DEFAULT_NOTES_FLAGS);
  const [clipboardHistory, setClipboardHistory] = useState(true);
  const [transformOnKeyboard, setTransformOnKeyboard] = useState(false);
  const [spokenLang, setSpokenLang] = useState('en');

  useEffect(() => {
    (async () => {
      setDeviceNameState(await getDeviceName());
      setUserIdState(await getUserId());
      try { setDict(await fetchRemote()); } finally { setDictLoaded(true); }
      setNotesFlags(await getNotesFeatureFlags());
      setClipboardHistory(await getClipboardHistoryEnabled());
      setTransformOnKeyboard(await getTransformEnabled());
      setSpokenLang(await getSpokenLanguage());
    })();
  }, []);

  // Optimistic: the chip highlights immediately, then the write (+ the keyboard
  // snapshot resync inside setSpokenLanguage) lands. A failed write only costs
  // the setting, never a dictation.
  const pickSpokenLang = async (code: string) => {
    if (code === spokenLang) return;
    setSpokenLang(code);
    try { await setSpokenLanguage(code); } catch { /* best effort */ }
  };

  const toggleNotesFlag = async (key: keyof NotesFeatureFlags, val: boolean) => {
    setNotesFlags(prev => ({ ...prev, [key]: val }));
    await setNotesFeatureFlag(key, val);
  };

  const toggleClipboardHistory = async (v: boolean) => {
    setClipboardHistory(v);
    await setClipboardHistoryEnabled(v);
  };

  const toggleTransformOnKeyboard = async (v: boolean) => {
    setTransformOnKeyboard(v);
    await setTransformEnabled(v);
  };

  const persistDict = async (d: Dictionary) => {
    if (!dictLoaded) return;
    setDict(d);
    const { dict: saved, error } = await saveDictionaryChecked(d);
    setDict(saved);            // a CAS conflict may have merged in another device's edit
    setDictSyncError(!!error);
  };
  const addWord = async () => {
    const w = newWord.trim(); if (!w) return;
    if (!dict.vocabulary.some(x => x.toLowerCase() === w.toLowerCase())) {
      await persistDict({ ...dict, vocabulary: [...dict.vocabulary, w] });
    }
    setNewWord('');
  };
  const removeWord = async (i: number) =>
    persistDict({ ...dict, vocabulary: dict.vocabulary.filter((_, idx) => idx !== i) });
  const addRep = async () => {
    const f = repFrom.trim(), t = repTo.trim(); if (!f || !t) return;
    const reps = dict.replacements.filter(r => r.from.toLowerCase() !== f.toLowerCase());
    await persistDict({ ...dict, replacements: [...reps, { from: f, to: t }] });
    setRepFrom(''); setRepTo('');
  };
  const removeRep = async (i: number) =>
    persistDict({ ...dict, replacements: dict.replacements.filter((_, idx) => idx !== i) });

  const saveName = async () => {
    await setDeviceName(deviceName.trim());
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setSavedName(true);
    setTimeout(() => setSavedName(false), 1600);
  };

  const saveUser = async () => {
    // Manual account link (IDI-156): writes the paired-account OVERRIDE, which
    // outranks the session id in getUserId() — a bare setUserId() was dead UI
    // (the session write-back reverted it on the next read). Same teardown +
    // store-reset rules as QR pairing so caches never leak across accounts.
    const id = userId.trim();
    if (!id) return;
    const prev = await getStoredUserId();
    if (prev && prev !== id) {
      try { await clearAccountData(); } catch { /* best effort */ }
    }
    await setPairedUserId(id);
    await setUserId(id);
    try {
      const hist = await import('../hooks/historyStore');
      await hist.reset();
      await hist.refresh();
    } catch { /* best effort */ }
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setSavedUser(true);
    setTimeout(() => setSavedUser(false), 1600);
  };

  // Writing the store is the whole toggle: it re-renders every reader and fires
  // the live catch-up (ON) / channel teardown (OFF) listeners.
  const toggleSync = (v: boolean) => { setSyncEnabled(v); };

  const confirmClearHistory = async () => {
    const ok = await confirm({
      title: 'Clear history?',
      message: 'This removes all saved transcriptions on this device.',
      confirmLabel: 'Clear', cancelLabel: 'Cancel', destructive: true,
    });
    if (ok) await clearHistory();
  };

  const replayOnboarding = async () => {
    const ok = await confirm({
      title: 'Replay onboarding?',
      message: 'The intro will show next time you open the app.',
      confirmLabel: 'OK', cancelLabel: 'Cancel',
    });
    if (ok) await AsyncStorage.removeItem('flume_onboarded');
  };

  const confirmSignOut = () => {
    // Native Alert (not the custom confirm modal): Settings is presented as a
    // native-stack MODAL, and a JS <Modal> shown over it doesn't reliably receive
    // touches on iOS — the reason the sign-out button appeared dead.
    Alert.alert(
      'Sign out?',
      'You can sign back in with Google any time.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Sign out', style: 'destructive', onPress: () => { signOut(); } },
      ],
      { cancelable: true },
    );
  };

  // MER-32: two native Alerts in sequence (same reasoning as confirmSignOut —
  // this screen is a native-stack modal, so the custom `confirm()` JS modal
  // wouldn't reliably receive touches here). Destructive + irreversible, so it
  // gets a harder second confirmation than sign-out.
  const confirmDeleteAccount = () => {
    Alert.alert(
      'Delete account?',
      'This permanently erases your account and all cloud data — history, notes, dictionary, meetings, recordings — on every device. This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete', style: 'destructive', onPress: () => {
            Alert.alert(
              'Are you absolutely sure?',
              'This is your last chance to cancel — confirming will delete everything permanently.',
              [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Delete forever', style: 'destructive', onPress: doDeleteAccount },
              ],
              { cancelable: true },
            );
          },
        },
      ],
      { cancelable: true },
    );
  };

  const doDeleteAccount = async () => {
    setDeletingAccount(true);
    const result = await deleteAccount();
    setDeletingAccount(false);
    if (!result.ok) {
      Alert.alert('Could not delete account', result.error || 'Unknown error — please try again.');
    }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 12 }]}>
      {/* Settings is a leaf of the Menu modal stack, reached from the SidePanel.
          It had NO back affordance — a swipe-down on the modal was the only way
          out, which iPhone users have no reason to guess (and there is no
          hardware back button to fall back on). Same chevron-back topBar every
          other secondary screen uses. `onBack` is goBack(), which finds nothing
          to pop inside this single-route stack and so bubbles to the root
          navigator, dismissing the modal — the intended destination. */}
      <View style={styles.topBar}>
        <Pressable
          onPress={onBack}
          style={({ pressed }) => pressed && pressedStyle}
          accessibilityRole="button"
          accessibilityLabel="Back"
          hitSlop={8}
        >
          <Ionicons name="chevron-back" size={24} color={colors.textSecondary} />
        </Pressable>
        <Text variant="titleSm">Settings</Text>
        <View style={{ width: 24 }} />
      </View>
      <Text variant="bodyXs" color={colors.textMuted} style={{ textAlign: 'center' }}>
        Keys & preferences
      </Text>

      <ScrollView
        style={{ flex: 1 }}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingTop: 20, paddingBottom: insets.bottom + 28, gap: 26 }}
      >
        {/* Account */}
        <Section label="ACCOUNT">
          <ListRow
            icon="person-circle-outline"
            title={user?.firstName || user?.email || 'Signed in'}
            subtitle={user?.email}
            trailing={null}
          />
        </Section>

        {/* Team privacy — the toggles used to live on the Team screen, which meant
            "where do I turn that off?" had two answers. Rendered only when the user
            is actually on a team; a privacy section about a team you are not in is
            a section nobody needed. */}
        {team.hasTeam && (
          <Section label="TEAM PRIVACY">
            <ListRow
              icon="stats-chart-outline"
              title="Let admins see my counts"
              subtitle={`What ${team.org.name || 'your team'}'s admins can see about your dictation`}
              trailing={
                <Switch
                  value={team.org.usage_consent}
                  onValueChange={(v) => { void team.saveConsent(v, v); }}
                  trackColor={{ false: colors.surface3, true: colors.primary }}
                  thumbColor="#fff"
                />
              }
            />
            <Card padding={14}>
              <Text variant="bodyXs" color={colors.textMuted}>
                What you dictate — the text, the audio, your notes — is never shared with your team,
                whatever these are set to. Admins see counts, durations and the names of the apps you
                dictate into — never what you said in them. Turning this off hides all of it, including
                you on the team ranking, and nobody else can turn it back on for you. Whether the ranking
                is shown at all is the team owner's call.
              </Text>
              {/* An owner genuinely cannot leave — org_remove_member returns
                  cannot_remove_owner — so don't offer a button that always fails. */}
              {team.isOwner ? (
                <Text variant="bodyXs" color={colors.textMuted} style={{ marginTop: 10 }}>
                  You own {team.org.name || 'this team'}. An owner cannot leave — hand it over first.
                </Text>
              ) : (
                <Button label="Leave team" variant="ghost" onPress={leaveTeam} style={{ marginTop: 12 }} />
              )}
            </Card>
          </Section>
        )}

        {/* Voice — spoken language + snippets (spoken phrase → full text) */}
        <Section label="VOICE">
          {/* Models — pipeline + transcription engine. Its own screen because the
              choice has real consequences (speed vs accuracy vs dictionary biasing)
              and does not belong inline with the language chips. */}
          <ListRow
            icon="layers-outline"
            title="Models"
            subtitle="Speed and transcription engine"
            onPress={onOpenModels}
          />
          {/* Whisper language hint (IDI-180). Applies to in-app dictation AND the
              native keyboards (the value ships in the keyboard config snapshot).
              A wrapping chip row, matching the dictionary's vocabulary chips —
              10 options fit in three rows with no extra navigation. */}
          <Card padding={14}>
            <Text variant="button" style={{ marginBottom: 2 }}>Spoken language</Text>
            <Text variant="bodyXs" color={colors.textMuted} style={{ marginBottom: 10 }}>
              The language you dictate in. Auto-detect lets Whisper decide.
            </Text>
            <View style={styles.chipWrap}>
              {SPOKEN_LANGUAGES.map(({ code, label }) => {
                const on = code === spokenLang;
                return (
                  <Pressable
                    key={code}
                    onPress={() => pickSpokenLang(code)}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: on }}
                    accessibilityLabel={label}
                    style={({ pressed }) => [styles.langChip, on && styles.langChipOn, pressed && pressedStyle]}
                  >
                    <Text variant="caption" color={on ? colors.primary : colors.textMuted}>{label}</Text>
                  </Pressable>
                );
              })}
            </View>
          </Card>

          <Pressable onPress={onOpenSnippets} style={({ pressed }) => [styles.snippetCard, pressed && pressedStyle]}>
            <View style={styles.snippetIcon}>
              <Ionicons name="flash" size={20} color={colors.primary} />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text variant="button">Snippets</Text>
              <Text variant="caption" color={colors.textMuted} style={{ marginTop: 2 }}>
                Say a phrase, get the full text
              </Text>
            </View>
            <Text variant="metaSm" color={colors.textSubtle}>{dict.snippets?.length ?? 0}</Text>
            <Ionicons name="chevron-forward" size={20} color={colors.textSubtle} />
          </Pressable>
        </Section>

        {/* Notes features (Notes v2 — per-user feature flags) */}
        <Section label="NOTES">
          <FlagRow
            icon="search-outline"
            title="Search"
            subtitle="Full-text search across your notes"
            value={notesFlags.search}
            onChange={v => toggleNotesFlag('search', v)}
          />
          <FlagRow
            icon="pricetag-outline"
            title="Auto-titling"
            subtitle="Name a dictated note automatically"
            value={notesFlags.autotitle}
            onChange={v => toggleNotesFlag('autotitle', v)}
          />
          <FlagRow
            icon="checkbox-outline"
            title="Structure detection"
            subtitle="Turn spoken lists into checklists"
            value={notesFlags.structure}
            onChange={v => toggleNotesFlag('structure', v)}
          />
          <FlagRow
            icon="mic-outline"
            title="Audio linkage"
            subtitle="Keep the recording behind a voice note"
            value={notesFlags.audio}
            onChange={v => toggleNotesFlag('audio', v)}
          />
        </Section>

        {/* Custom dictionary */}
        <Section label="CUSTOM DICTIONARY">
          <Card padding={14}>
            {dictSyncError ? (
              <Text variant="bodyXs" color={colors.primary} style={{ marginBottom: 8 }}>
                Couldn't sync — will retry.
              </Text>
            ) : null}
            <Text variant="button" style={{ marginBottom: 2 }}>Vocabulary</Text>
            <Text variant="bodyXs" color={colors.textMuted} style={{ marginBottom: 10 }}>
              Names, products, acronyms — spelled how you want them.
            </Text>
            <View style={styles.chipWrap}>
              {dict.vocabulary.length === 0 ? (
                <Text variant="caption" color={colors.textSubtle}>{dictLoaded ? 'No words yet.' : 'Loading…'}</Text>
              ) : dict.vocabulary.map((w, i) => (
                <Pressable key={`${w}-${i}`} onPress={() => removeWord(i)} style={({ pressed }) => [styles.chip, pressed && pressedStyle]}>
                  <Text variant="caption" color={colors.primary}>{w}</Text>
                  <Ionicons name="close" size={12} color={colors.primary} />
                </Pressable>
              ))}
            </View>
            <View style={styles.dictRow}>
              <TextInput
                value={newWord} onChangeText={setNewWord} placeholder="Add a word…"
                placeholderTextColor={colors.textMuted} style={styles.dictInput}
                autoCapitalize="none" onSubmitEditing={addWord} returnKeyType="done"
              />
              <Button label="Add" variant="ghost" onPress={addWord} disabled={!dictLoaded} style={{ flex: 0 }} />
            </View>

            <View style={{ height: 1, backgroundColor: colors.borderSubtle, marginVertical: 14 }} />

            <Text variant="button" style={{ marginBottom: 2 }}>Replacement rules</Text>
            <Text variant="bodyXs" color={colors.textMuted} style={{ marginBottom: 10 }}>
              Fix persistent mishearings. Editing a transcription teaches one automatically.
            </Text>
            {dict.replacements.map((r, i) => (
              <View key={`${r.from}-${i}`} style={styles.repRow}>
                <Text variant="caption" color={colors.textMuted}>{r.from}</Text>
                <Ionicons name="arrow-forward" size={12} color={colors.textSubtle} />
                <Text variant="caption" style={{ flex: 1 }}>{r.to}</Text>
                <Pressable onPress={() => removeRep(i)} style={({ pressed }) => pressed && pressedStyle} hitSlop={8}>
                  <Ionicons name="close" size={14} color={colors.textMuted} />
                </Pressable>
              </View>
            ))}
            <View style={styles.dictRow}>
              <TextInput
                value={repFrom} onChangeText={setRepFrom} placeholder="heard…"
                placeholderTextColor={colors.textMuted} style={[styles.dictInput, { flex: 1 }]}
                autoCapitalize="none"
              />
              <Ionicons name="arrow-forward" size={14} color={colors.textSubtle} />
              <TextInput
                value={repTo} onChangeText={setRepTo} placeholder="correct…"
                placeholderTextColor={colors.textMuted} style={[styles.dictInput, { flex: 1 }]}
              />
              <Button label="Add" variant="ghost" onPress={addRep} disabled={!dictLoaded} style={{ flex: 0 }} />
            </View>
          </Card>
        </Section>

        {/* Device */}
        <Section label="DEVICE">
          <Card padding={14} style={{ marginBottom: 8 }}>
            <Text variant="button" style={{ marginBottom: 2 }}>Device name</Text>
            <Text variant="bodyXs" color={colors.textMuted}>Shown on your other devices</Text>
            <View style={styles.inputRow}>
              <TextInput
                value={deviceName}
                onChangeText={setDeviceNameState}
                placeholder="My iPhone"
                placeholderTextColor={colors.textDisabled}
                autoCapitalize="words"
                style={styles.input}
              />
            </View>
            <Button
              label={savedName ? 'Saved ✓' : 'Save name'}
              variant={savedName ? 'ghost' : 'primary'}
              onPress={saveName}
            />
          </Card>
          <ListRow icon="laptop-outline" title="Your devices" subtitle="Manage paired computers" onPress={onOpenDevices} />
        </Section>

        {/* Sync */}
        {/* Keyboard clipboard history (quick-paste chip + clipboard overlay on the
            custom keyboards) — captured/stored entirely on-device by the keyboard
            extension itself; this toggle just gates whether it runs at all. */}
        <Section label="KEYBOARD">
          <FlagRow
            icon="clipboard-outline"
            title="Clipboard history on keyboard"
            subtitle="Quick-paste recent copies from the Flume keyboard"
            value={clipboardHistory}
            onChange={toggleClipboardHistory}
          />
          {/* Select text elsewhere → tap Transform → instruction (typed/spoken/preset) →
              LLM rewrite → preview → replace. Mirrors desktop's Transform (Mode B); off
              by default like desktop, since it's an LLM-driven feature. */}
          <FlagRow
            icon="sparkles-outline"
            title="Transform on keyboard"
            subtitle="Select text anywhere, then rewrite it with an instruction"
            value={transformOnKeyboard}
            onChange={toggleTransformOnKeyboard}
          />
        </Section>

        <Section label="CROSS-DEVICE SYNC">
          <ListRow
            icon="sync-outline"
            title="Enable sync"
            subtitle="Sync history & clipboard across devices"
            trailing={
              <Switch
                value={sync}
                onValueChange={toggleSync}
                trackColor={{ false: colors.surface3, true: colors.primary }}
                thumbColor="#fff"
              />
            }
          />
          <Card padding={14}>
            <Text variant="button" style={{ marginBottom: 2 }}>Account ID</Text>
            <Text variant="bodyXs" color={colors.textMuted}>
              Use the SAME ID on your phone and computer to link them
            </Text>
            <View style={styles.inputRow}>
              <TextInput
                value={userId}
                onChangeText={setUserIdState}
                placeholder="your@email.com or any shared ID"
                placeholderTextColor={colors.textDisabled}
                autoCapitalize="none"
                autoCorrect={false}
                style={styles.input}
              />
            </View>
            <Button
              label={savedUser ? 'Linked ✓' : 'Save ID'}
              variant={savedUser ? 'ghost' : 'primary'}
              onPress={saveUser}
            />
          </Card>
        </Section>

        {/* Data */}
        <Section label="DATA">
          <ListRow icon="trash-outline" title="Clear history" subtitle="Delete saved transcriptions" onPress={confirmClearHistory} trailing={null} />
          <View style={{ height: 8 }} />
          <ListRow icon="refresh-outline" title="Replay onboarding" subtitle="Show the intro again" onPress={replayOnboarding} trailing={null} />
        </Section>

        {/* Account actions + about */}
        <Section label="ABOUT">
          <ListRow icon="information-circle-outline" title="Flume" subtitle="v1.0 · Voice dictation" trailing={null} />
          <View style={{ height: 12 }} />
          <Button label="Sign out" variant="ghost" onPress={confirmSignOut} />
          <View style={{ height: 8 }} />
          <Button
            label={deletingAccount ? 'Deleting…' : 'Delete account'}
            variant="ghost"
            loading={deletingAccount}
            onPress={confirmDeleteAccount}
          />
        </Section>
      </ScrollView>
    </View>
  );
};

const Section: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <View style={{ gap: 8 }}>
    <Text variant="meta" color={colors.textSubtle} style={{ marginLeft: 2 }}>{label}</Text>
    {children}
  </View>
);

const FlagRow: React.FC<{
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  subtitle: string;
  value: boolean;
  onChange: (v: boolean) => void;
}> = ({ icon, title, subtitle, value, onChange }) => (
  <ListRow
    icon={icon}
    title={title}
    subtitle={subtitle}
    trailing={
      <Switch
        value={value}
        onValueChange={onChange}
        trackColor={{ false: colors.surface3, true: colors.primary }}
        thumbColor="#fff"
        accessibilityLabel={title}
      />
    }
  />
);

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 18,
  },
  topBar: {
    flexDirection: 'row', alignItems: 'center',
    justifyContent: 'space-between', marginBottom: 2,
  },
  snippetCard: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    padding: 14,
    borderRadius: radius.lg,
    backgroundColor: colors.surface1,
    borderWidth: 1, borderColor: colors.borderSubtle,
  },
  snippetIcon: {
    width: 42, height: 42, borderRadius: radius.md,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: colors.primarySoft,
    borderWidth: 1, borderColor: colors.primaryBorder,
  },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 },
  langChip: {
    backgroundColor: colors.surface2, borderWidth: 1, borderColor: colors.borderSubtle,
    borderRadius: 999, paddingVertical: 6, paddingHorizontal: 12,
  },
  langChipOn: { backgroundColor: colors.primarySoft, borderColor: colors.primaryBorder },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primaryBorder,
    borderRadius: 999, paddingVertical: 5, paddingHorizontal: 11,
  },
  dictRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dictInput: {
    backgroundColor: colors.surface2, borderRadius: 8, paddingVertical: 9, paddingHorizontal: 12,
    color: colors.textPrimary, fontSize: 14,
  },
  repRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: colors.surface2, borderRadius: 8, paddingVertical: 8, paddingHorizontal: 12,
    marginBottom: 8,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface2,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    paddingHorizontal: 12,
    marginBottom: 10,
  },
  input: {
    flex: 1,
    color: colors.textPrimary,
    paddingVertical: 12,
    ...type.body,
  },
  eyeBtn: {
    paddingLeft: 8,
    paddingVertical: 8,
  },
});

export default SettingsScreen;
