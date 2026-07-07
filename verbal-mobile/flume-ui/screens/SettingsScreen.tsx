import React, { useEffect, useState } from 'react';
import {
  View, StyleSheet, ScrollView, TextInput, Switch, Pressable,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Haptics from 'expo-haptics';
import { Text, Card, ListRow, Button } from '../components';
import { confirm } from '../components/ConfirmDialog';
import { colors, radius, type } from '../theme';
import { useAuth } from '../hooks/useAuth';
import {
  getGroqKey, setGroqKey,
  getDeviceName, setDeviceName,
  getSyncEnabled, setSyncEnabled,
  getUserId, setUserId,
  clearHistory,
} from '../../lib/storage';

type Props = { onOpenDevices: () => void };

/**
 * Settings — keys & preferences, in the Flume visual language.
 * Reads/writes the local settings store directly (lib/storage).
 */
export const SettingsScreen: React.FC<Props> = ({ onOpenDevices }) => {
  const insets = useSafeAreaInsets();
  const { user, signOut } = useAuth();

  const [groqKey, setGroqKeyState] = useState('');
  const [deviceName, setDeviceNameState] = useState('');
  const [userId, setUserIdState] = useState('');
  const [sync, setSync] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [savedKey, setSavedKey] = useState(false);
  const [savedName, setSavedName] = useState(false);
  const [savedUser, setSavedUser] = useState(false);

  useEffect(() => {
    (async () => {
      setGroqKeyState(await getGroqKey());
      setDeviceNameState(await getDeviceName());
      setUserIdState(await getUserId());
      setSync(await getSyncEnabled());
    })();
  }, []);

  const saveKey = async () => {
    await setGroqKey(groqKey.trim());
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setSavedKey(true);
    setTimeout(() => setSavedKey(false), 1600);
  };

  const saveName = async () => {
    await setDeviceName(deviceName.trim());
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setSavedName(true);
    setTimeout(() => setSavedName(false), 1600);
  };

  const saveUser = async () => {
    await setUserId(userId.trim());
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setSavedUser(true);
    setTimeout(() => setSavedUser(false), 1600);
  };

  const toggleSync = async (v: boolean) => {
    setSync(v);
    await setSyncEnabled(v);
  };

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

  const confirmSignOut = async () => {
    const ok = await confirm({
      title: 'Sign out?',
      message: 'You can sign back in with Google any time.',
      confirmLabel: 'Sign out',
      cancelLabel: 'Cancel',
      destructive: true,
    });
    if (ok) signOut();
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 12 }]}>
      <Text variant="titleSm" style={{ marginBottom: 2 }}>Settings</Text>
      <Text variant="bodyXs" color={colors.textMuted}>Keys & preferences</Text>

      <ScrollView
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

        {/* Transcription */}
        <Section label="TRANSCRIPTION">
          <Card padding={14}>
            <View style={styles.cardHeader}>
              <View style={{ flex: 1 }}>
                <Text variant="button">Groq API key</Text>
                <Text variant="bodyXs" color={colors.textMuted}>Powers transcription + formatting</Text>
              </View>
            </View>
            <View style={styles.inputRow}>
              <TextInput
                value={groqKey}
                onChangeText={setGroqKeyState}
                placeholder="gsk_..."
                placeholderTextColor={colors.textDisabled}
                secureTextEntry={!showKey}
                autoCapitalize="none"
                autoCorrect={false}
                style={styles.input}
              />
              <Pressable onPress={() => setShowKey(s => !s)} hitSlop={8} style={styles.eyeBtn}>
                <Ionicons name={showKey ? 'eye-off-outline' : 'eye-outline'} size={22} color={colors.textMuted} />
              </Pressable>
            </View>
            <Button
              label={savedKey ? 'Saved ✓' : 'Save key'}
              variant={savedKey ? 'ghost' : 'primary'}
              onPress={saveKey}
            />
            <Text variant="caption" color={colors.textSubtle} style={{ marginTop: 8 }}>
              Free key at console.groq.com/keys
            </Text>
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
              label={savedUser ? 'Saved ✓ — reload to apply' : 'Save ID'}
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
          <ListRow icon="information-circle-outline" title="Verbal" subtitle="v1.0 · Voice dictation" trailing={null} />
          <View style={{ height: 12 }} />
          <Button label="Sign out" variant="ghost" onPress={confirmSignOut} />
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

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 18,
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
