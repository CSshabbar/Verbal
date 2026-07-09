import React, { useState, useEffect } from 'react';
import { View, Pressable, StyleSheet, Alert } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { NavigationContainer, DefaultTheme, Theme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';

import {
  WelcomeScreen,
  OnboardingScreen,
  HomeScreen,
  RecordingScreen,
  ConfirmationScreen,
  HistoryListScreen,
  HistoryDetailScreen,
  PairDeviceScreen,
  DevicesScreen,
  SnippetsScreen,
  NotesListScreen,
  NoteEditorScreen,
  CanvasScreen,
  SettingsScreen,
} from '../screens';
import * as Clipboard from 'expo-clipboard';
import { colors, type } from '../theme';
import { useAuth } from '../hooks/useAuth';
import { ConfirmHost } from '../components/ConfirmDialog';
import { useHistory } from '../hooks/useHistory';
import { useDevices } from '../hooks/useDevices';
import { consumeLastRecording } from '../hooks/useRecorder';

import {
  RootStackParamList,
  TabsParamList,
  NotesStackParamList,
  HistoryStackParamList,
  SettingsStackParamList,
} from './types';

const flumeTheme: Theme = {
  dark: true,
  colors: {
    primary:      colors.primary,
    background:   colors.bgScreen,
    card:         colors.bgScreen,
    text:         colors.textPrimary,
    border:       colors.borderSubtle,
    notification: colors.primary,
  },
  // React Navigation v7 reads theme.fonts.{regular,medium,bold,heavy};
  // reuse its built-ins so the tab bar / headers don't crash.
  fonts: DefaultTheme.fonts,
};

/* ────────────────────────────────────────────────────────────────
 * Sub-stacks
 * ──────────────────────────────────────────────────────────────── */

const NotesStack = createNativeStackNavigator<NotesStackParamList>();
function NotesNavigator() {
  return (
    <NotesStack.Navigator screenOptions={{ headerShown: false }}>
      <NotesStack.Screen name="NotesList">
        {({ navigation }) => (
          <NotesListScreen
            onCreate={() => navigation.navigate('NoteEditor', { noteId: null })}
            onOpen={(n) => navigation.navigate('NoteEditor', { noteId: n.id })}
          />
        )}
      </NotesStack.Screen>
      <NotesStack.Screen name="NoteEditor">
        {({ route, navigation }) => (
          <NoteEditorScreen
            noteId={route.params.noteId}
            onBack={() => navigation.goBack()}
          />
        )}
      </NotesStack.Screen>
    </NotesStack.Navigator>
  );
}

const HistoryStack = createNativeStackNavigator<HistoryStackParamList>();
function HistoryNavigator() {
  return (
    <HistoryStack.Navigator screenOptions={{ headerShown: false }}>
      <HistoryStack.Screen name="HistoryList">
        {({ navigation }) => (
          <HistoryListScreen
            onOpen={(item) => navigation.navigate('HistoryDetail', { itemId: item.id })}
          />
        )}
      </HistoryStack.Screen>
      <HistoryStack.Screen name="HistoryDetail">
        {({ route, navigation }) => <HistoryDetail itemId={route.params.itemId} onBack={() => navigation.goBack()} />}
      </HistoryStack.Screen>
    </HistoryStack.Navigator>
  );
}

const HistoryDetail: React.FC<{ itemId: string; onBack: () => void }> = ({ itemId, onBack }) => {
  const { items, addTranscription, retryEntry, playEntry } = useHistory();
  const { target } = useDevices();
  const item = items.find(i => i.id === itemId);
  if (!item) return null;
  const copy = () => { Clipboard.setStringAsync(item.text); };
  return (
    <HistoryDetailScreen
      item={item}
      onBack={onBack}
      onEdit={copy}
      onCopy={copy}
      onPlay={item.hasAudio ? () => { playEntry(item.id); } : undefined}
      onRetry={item.status === 'failed' ? async () => {
        const r = await retryEntry(item.id);
        if (!r.ok) Alert.alert('Retry failed', r.error || 'Please try again.');
      } : undefined}
      onResend={() => {
        // Re-send: copy locally + push to the current target device.
        Clipboard.setStringAsync(item.text);
        addTranscription(item.text, target?.name ?? item.deviceTag, 0, target?.id ?? null);
        onBack();
      }}
    />
  );
};

const SettingsStack = createNativeStackNavigator<SettingsStackParamList>();
function SettingsNavigator() {
  return (
    <SettingsStack.Navigator screenOptions={{ headerShown: false }}>
      <SettingsStack.Screen name="Settings">
        {({ navigation }) => (
          <SettingsScreen
            onOpenDevices={() => navigation.navigate('Devices')}
            onOpenSnippets={() => navigation.navigate('Snippets')}
          />
        )}
      </SettingsStack.Screen>
      <SettingsStack.Screen name="Snippets">
        {({ navigation }) => (
          <SnippetsScreen onBack={() => navigation.goBack()} />
        )}
      </SettingsStack.Screen>
      <SettingsStack.Screen name="Devices">
        {({ navigation }) => (
          <DevicesScreen
            onBack={() => navigation.goBack()}
            onAddDevice={() => navigation.navigate('PairDevice')}
          />
        )}
      </SettingsStack.Screen>
      <SettingsStack.Screen name="PairDevice" options={{ presentation: 'modal' }}>
        {({ navigation }) => (
          <PairDeviceScreen
            onBack={() => navigation.goBack()}
            onScan={async (payload) => {
              try {
                const { claimPairing } = await import('../../lib/pairing');
                const info = await claimPairing(payload);
                // user_id + sync just changed — re-subscribe the realtime channel
                // on the new account so this device RECEIVES from the host too.
                try {
                  const hist = await import('../hooks/historyStore');
                  await hist.refresh();
                } catch {}
                Alert.alert('Paired', `This device now syncs with ${info.hostDevice || 'your account'}.`);
                navigation.goBack();
              } catch (e: any) {
                Alert.alert('Pairing failed', e?.message || String(e));
                navigation.goBack();
              }
            }}
            onUseCode={() => {/* TODO: code-entry screen */}}
          />
        )}
      </SettingsStack.Screen>
    </SettingsStack.Navigator>
  );
}

/* ────────────────────────────────────────────────────────────────
 * Tabs
 * ──────────────────────────────────────────────────────────────── */

const Tabs = createBottomTabNavigator<TabsParamList>();

type TabsNavigatorProps = {
  onRecord: () => void;
  onOpenSettings: () => void;
};

const EmptyTab = () => null;

/**
 * Minimalist-dark tab bar (wireframe 7a/8e): Home · Notes · [center mic] ·
 * Canvas · History. The mic is a floating white button that opens the
 * Recording modal — it's the primary action, so it sits in the center.
 * Settings is reached from the Home header gear.
 */
function TabsNavigator({ onRecord, onOpenSettings }: TabsNavigatorProps) {
  const insets = useSafeAreaInsets();
  return (
    <Tabs.Navigator
      screenOptions={{
        headerShown: false,
        tabBarShowLabel: false,
        tabBarStyle: {
          backgroundColor: colors.bgScreen,
          borderTopColor: colors.borderSubtle,
          borderTopWidth: 1,
          height: 72 + insets.bottom,
          paddingTop: 10,
          paddingBottom: insets.bottom + 14,
        },
        tabBarActiveTintColor: colors.textPrimary,
        tabBarInactiveTintColor: colors.textDisabled,
      }}
    >
      <Tabs.Screen
        name="HomeTab"
        options={{ tabBarIcon: ({ color }) => <Ionicons name="home-outline" size={24} color={color} /> }}
      >
        {() => <HomeScreen onOpenSettings={onOpenSettings} />}
      </Tabs.Screen>
      <Tabs.Screen
        name="NotesTab"
        component={NotesNavigator}
        options={{ tabBarIcon: ({ color }) => <Ionicons name="reorder-three-outline" size={27} color={color} /> }}
      />
      <Tabs.Screen
        name="RecordTab"
        component={EmptyTab}
        options={{
          tabBarButton: () => (
            <View style={navStyles.centerWrap} pointerEvents="box-none">
              <Pressable
                onPress={onRecord}
                style={({ pressed }) => [navStyles.centerMic, pressed && { opacity: 0.9 }]}
              >
                <Ionicons name="mic" size={26} color={colors.primaryInk} />
              </Pressable>
            </View>
          ),
        }}
      />
      <Tabs.Screen
        name="CanvasTab"
        component={CanvasScreen}
        options={{ tabBarIcon: ({ color }) => <Ionicons name="grid-outline" size={23} color={color} /> }}
      />
      <Tabs.Screen
        name="HistoryTab"
        component={HistoryNavigator}
        options={{ tabBarIcon: ({ color }) => <Ionicons name="time-outline" size={24} color={color} /> }}
      />
    </Tabs.Navigator>
  );
}

const navStyles = StyleSheet.create({
  centerWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  centerMic: {
    top: -16,
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: colors.inkLight,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 8,
  },
});

/* ────────────────────────────────────────────────────────────────
 * Root
 * ──────────────────────────────────────────────────────────────── */

const Root = createNativeStackNavigator<RootStackParamList>();

const ONBOARDED_KEY = 'flume_onboarded';

export const RootNavigator: React.FC = () => {
  const { user, isLoading, signOut } = useAuth();
  const { addTranscription } = useHistory();
  const { target } = useDevices();
  const isSignedIn = !!user;

  // Onboarding is gated by its OWN flag, independent of auth — so a first-run
  // user always sees it even if a (mock) session is already stored.
  const [onboarded, setOnboarded] = useState<boolean | null>(null);
  useEffect(() => {
    AsyncStorage.getItem(ONBOARDED_KEY)
      .then(v => setOnboarded(v === '1'))
      .catch(() => setOnboarded(false));
  }, []);

  const completeOnboarding = async () => {
    // Clear any stale/mock session so the intended first-run Welcome (sign-in)
    // step shows instead of bouncing straight to Home.
    await signOut().catch(() => {});
    await AsyncStorage.setItem(ONBOARDED_KEY, '1').catch(() => {});
    setOnboarded(true);
  };

  // Wait for both auth restore and the onboarding flag before deciding.
  if (isLoading || onboarded === null) {
    return <View style={{ flex: 1, backgroundColor: colors.bgScreen }} />;
  }

  return (
    <NavigationContainer theme={flumeTheme}>
      <StatusBar style="light" />
      <Root.Navigator screenOptions={{ headerShown: false }}>
        {!onboarded ? (
          <Root.Screen name="Onboarding">
            {() => (
              <OnboardingScreen
                onDone={completeOnboarding}
                onSkip={completeOnboarding}
              />
            )}
          </Root.Screen>
        ) : !isSignedIn ? (
          <Root.Screen name="Welcome" component={WelcomeScreen} />
        ) : (
          <>
            <Root.Screen name="Main">
              {({ navigation }) => (
                <TabsNavigator
                  onRecord={() => navigation.navigate('Recording')}
                  onOpenSettings={() => navigation.navigate('Settings')}
                />
              )}
            </Root.Screen>
            <Root.Screen
              name="Recording"
              options={{ presentation: 'modal', gestureEnabled: false }}
            >
              {({ navigation }) => (
                <RecordingScreen
                  onCancel={() => navigation.goBack()}
                  onComplete={(_uri, durationMs) => {
                    const last = consumeLastRecording();
                    const failed = last?.status === 'failed';
                    const hasSpeech = !!last?.text?.trim();
                    const deviceName = target?.name ?? 'Local';
                    const transcript = failed
                      ? 'Transcription failed — your audio is saved. Retry it from History.'
                      : hasSpeech ? last!.text : 'No speech detected.';
                    const wordCount = hasSpeech ? last!.text.trim().split(/\s+/).length : 0;

                    if (failed) {
                      // Keep the audio; save a retryable entry.
                      addTranscription('', deviceName, durationMs, target?.id ?? null, last?.uri, 'failed');
                    } else if (hasSpeech) {
                      Clipboard.setStringAsync(last!.text);
                      addTranscription(last!.text, deviceName, durationMs, target?.id ?? null, last?.uri, 'done');
                    }

                    navigation.replace('Confirmation', {
                      transcript,
                      deviceName,
                      durationSeconds: Math.round(durationMs / 1000),
                      wordCount,
                      transcribeMs: last?.transcribeMs ?? 0,
                    });
                  }}
                />
              )}
            </Root.Screen>
            <Root.Screen name="Settings" options={{ presentation: 'modal', gestureEnabled: true }}>
              {() => <SettingsNavigator />}
            </Root.Screen>
            <Root.Screen
              name="Confirmation"
              options={{ presentation: 'modal', gestureEnabled: true }}
            >
              {({ route, navigation }) => (
                <ConfirmationScreen
                  {...route.params}
                  onDone={() => navigation.popToTop()}
                  onCopyAgain={() => Clipboard.setStringAsync(route.params.transcript ?? '')}
                  onEditInHistory={() => {
                    navigation.popToTop();
                    (navigation as any).navigate('Main', { screen: 'HistoryTab' });
                  }}
                  onResendToAnother={() => {
                    Clipboard.setStringAsync(route.params.transcript ?? '');
                    if (route.params.transcript) {
                      addTranscription(route.params.transcript, target?.name ?? 'Local', route.params.durationSeconds * 1000, target?.id ?? null);
                    }
                    navigation.popToTop();
                  }}
                />
              )}
            </Root.Screen>
          </>
        )}
      </Root.Navigator>
      <ConfirmHost />
    </NavigationContainer>
  );
};

export default RootNavigator;
