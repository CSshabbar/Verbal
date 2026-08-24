import React, { useState, useEffect } from 'react';
import { View, Pressable, StyleSheet, Alert } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { NavigationContainer, DefaultTheme, Theme, getFocusedRouteNameFromRoute } from '@react-navigation/native';
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
  TeamScreen,
  InsightsScreen,
  ModelsScreen,
  NotesListScreen,
  NoteEditorScreen,
  MeetingListScreen,
  MeetingDetailScreen,
  MeetingPlaybackScreen,
  MeetingNotesScreen,
  MeetingLiveScreen,
  CanvasScreen,
  SettingsScreen,
  DictionaryScreen,
} from '../screens';
import { SidePanel } from '../components/SidePanel';
import * as Clipboard from 'expo-clipboard';
import { colors, type } from '../theme';
import { useAuth } from '../hooks/useAuth';
import { ConfirmHost } from '../components/ConfirmDialog';
import { DevicesSyncHost } from '../components/DevicesSyncSheet';
import { useHistory } from '../hooks/useHistory';
import { useDevices } from '../hooks/useDevices';
import { consumeLastRecording } from '../hooks/useRecorder';
import { getSyncEnabled } from '../../lib/storage';

import {
  RootStackParamList,
  TabsParamList,
  NotesStackParamList,
  HistoryStackParamList,
  MenuStackParamList,
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
            onOpenMeetings={() => navigation.navigate('MeetingList')}
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
      <NotesStack.Screen name="MeetingList">
        {({ navigation }) => (
          <MeetingListScreen
            onBack={() => navigation.goBack()}
            onOpen={(meetingId) => navigation.navigate('MeetingDetail', { meetingId })}
            onOpenLive={(meetingId) => navigation.navigate('MeetingLive', { meetingId })}
          />
        )}
      </NotesStack.Screen>
      <NotesStack.Screen name="MeetingDetail">
        {({ route, navigation }) => (
          <MeetingDetailScreen
            meetingId={route.params.meetingId}
            onBack={() => navigation.goBack()}
            onOpenPlayback={(meetingId) => navigation.navigate('MeetingPlayback', { meetingId })}
            onOpenNotes={(meetingId) => navigation.navigate('MeetingNotes', { meetingId })}
          />
        )}
      </NotesStack.Screen>
      <NotesStack.Screen name="MeetingPlayback">
        {({ route, navigation }) => (
          <MeetingPlaybackScreen
            meetingId={route.params.meetingId}
            onBack={() => navigation.goBack()}
          />
        )}
      </NotesStack.Screen>
      <NotesStack.Screen name="MeetingLive">
        {({ route, navigation }) => (
          <MeetingLiveScreen
            meetingId={route.params.meetingId}
            onBack={() => navigation.goBack()}
            onFinished={(meetingId) => navigation.replace('MeetingDetail', { meetingId })}
          />
        )}
      </NotesStack.Screen>
      <NotesStack.Screen name="MeetingNotes">
        {({ route, navigation }) => (
          <MeetingNotesScreen
            meetingId={route.params.meetingId}
            onBack={() => navigation.goBack()}
            onOpenPlayback={(meetingId) => navigation.navigate('MeetingPlayback', { meetingId })}
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
  const { items, addTranscription, retryEntry, playEntry, remove } = useHistory();
  const { target, mode } = useDevices();
  const item = items.find(i => i.id === itemId);
  if (!item) return null;
  const copy = () => { Clipboard.setStringAsync(item.text); };
  const overflow = () => {
    Alert.alert('Transcription', undefined, [
      { text: 'Copy', onPress: copy },
      {
        text: 'Delete', style: 'destructive',
        onPress: () => { remove(item.id); onBack(); },
      },
      { text: 'Cancel', style: 'cancel' },
    ]);
  };
  return (
    <HistoryDetailScreen
      item={item}
      onBack={onBack}
      onCopy={copy}
      onOverflow={overflow}
      onPlay={item.hasAudio ? () => { playEntry(item.id); } : undefined}
      onRetry={item.status === 'failed' ? async () => {
        const r = await retryEntry(item.id);
        if (!r.ok) Alert.alert('Retry failed', r.error || 'Please try again.');
      } : undefined}
      onResend={() => {
        // Re-send: copy locally + push to the current target device.
        Clipboard.setStringAsync(item.text);
        addTranscription(item.text, (mode === 'device' && target?.name) || item.deviceTag, 0, mode === 'device' ? target?.id ?? null : null);
        onBack();
      }}
    />
  );
};

const MenuStack = createNativeStackNavigator<MenuStackParamList>();
// V2 nav redesign (2026-08-16): the old MenuScreen hub is gone — the SidePanel
// owns navigation now. This modal stack hosts only the secondary destinations,
// each with its own back affordance (or swipe-down, it's a modal).
function MenuNavigator() {
  return (
    <MenuStack.Navigator screenOptions={{ headerShown: false }}>
      <MenuStack.Screen name="Canvas">
        {({ navigation }) => (
          <CanvasScreen onBack={() => navigation.getParent()?.goBack()} />
        )}
      </MenuStack.Screen>
      <MenuStack.Screen name="Settings">
        {({ navigation }) => (
          <SettingsScreen
            onBack={() => navigation.goBack()}
            onOpenDevices={() => navigation.navigate('Devices')}
            onOpenSnippets={() => navigation.navigate('Snippets')}
            onOpenModels={() => navigation.navigate('Models')}
          />
        )}
      </MenuStack.Screen>
      <MenuStack.Screen name="Dictionary">
        {({ navigation }) => (
          <DictionaryScreen onBack={() => navigation.goBack()} />
        )}
      </MenuStack.Screen>
      <MenuStack.Screen name="Team">
        {({ navigation }) => (
          <TeamScreen onBack={() => navigation.goBack()} />
        )}
      </MenuStack.Screen>
      <MenuStack.Screen name="Snippets">
        {({ navigation }) => (
          <SnippetsScreen onBack={() => navigation.goBack()} />
        )}
      </MenuStack.Screen>
      <MenuStack.Screen name="Models">
        {({ navigation }) => (
          <ModelsScreen onBack={() => navigation.goBack()} />
        )}
      </MenuStack.Screen>
      <MenuStack.Screen name="Devices">
        {({ navigation }) => (
          <DevicesScreen
            onBack={() => navigation.goBack()}
            onAddDevice={() => navigation.navigate('PairDevice')}
          />
        )}
      </MenuStack.Screen>
      <MenuStack.Screen name="PairDevice" options={{ presentation: 'modal' }}>
        {({ navigation }) => (
          <PairDeviceScreen
            onBack={() => navigation.goBack()}
            onScan={async (payload) => {
              try {
                const { claimPairing } = await import('../../lib/pairing');
                const info = await claimPairing(payload);
                // user_id + sync just changed — tear down the store (items +
                // realtime channel are keyed by the OLD account) and reload
                // under the host account so this device RECEIVES from it too.
                try {
                  const hist = await import('../hooks/historyStore');
                  await hist.reset();
                  await hist.refresh();
                } catch {}
                Alert.alert('Paired', `This device now syncs with ${info.hostDevice || 'your account'}.`);
                navigation.goBack();
              } catch (e: any) {
                Alert.alert('Pairing failed', e?.message || String(e));
                navigation.goBack();
              }
            }}
          />
        )}
      </MenuStack.Screen>
    </MenuStack.Navigator>
  );
}

/* ────────────────────────────────────────────────────────────────
 * Tabs
 * ──────────────────────────────────────────────────────────────── */

const Tabs = createBottomTabNavigator<TabsParamList>();

type TabsNavigatorProps = {
  onRecord: () => void;
  onOpenMenu: () => void;
};

const EmptyTab = () => null;

/**
 * "Daily Four" tab bar (V2 nav redesign, 2026-08-16): Home · Notes ·
 * [center mic] · History · Insights — the four daily surfaces one tap away,
 * dictation as the floating centerpiece. Canvas, Meetings and the tools live
 * in the SidePanel (Home ☰), which mirrors the desktop sidebar.
 */
function TabsNavigator({ onRecord, onOpenMenu }: TabsNavigatorProps) {
  const insets = useSafeAreaInsets();
  const tabBarStyle = {
    backgroundColor: colors.bgScreen,
    borderTopColor: colors.borderSubtle,
    borderTopWidth: 1,
    // Sit the icons just above the home indicator. paddingBottom = the safe-area
    // inset only (+4 breathing room); the previous `insets.bottom + 14` double-
    // counted the inset and floated the whole bar ~48px off the bottom.
    height: 56 + insets.bottom,
    paddingTop: 8,
    paddingBottom: insets.bottom + 4,
  } as const;
  return (
    <Tabs.Navigator
      screenOptions={{
        headerShown: false,
        tabBarShowLabel: false,
        tabBarStyle,
        tabBarActiveTintColor: colors.textPrimary,
        tabBarInactiveTintColor: colors.textDisabled,
      }}
    >
      <Tabs.Screen
        name="HomeTab"
        options={{ tabBarIcon: ({ color }) => <Ionicons name="home-outline" size={24} color={color} /> }}
      >
        {() => <HomeScreen onOpenMenu={onOpenMenu} />}
      </Tabs.Screen>
      <Tabs.Screen
        name="NotesTab"
        component={NotesNavigator}
        options={({ route }) => ({
          // Hide the whole bottom tab bar (incl. the floating center mic) while a
          // note or a meeting's full AI notes are open, so the screen owns the
          // whole view and shows a single, centered mic. Restored automatically
          // on returning to the notes list.
          tabBarStyle: ['NoteEditor', 'MeetingNotes'].includes(getFocusedRouteNameFromRoute(route) ?? 'NotesList')
            ? { display: 'none' }
            : tabBarStyle,
          tabBarIcon: ({ color }) => <Ionicons name="reorder-three-outline" size={27} color={color} />,
        })}
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
        name="HistoryTab"
        component={HistoryNavigator}
        options={{ tabBarIcon: ({ color }) => <Ionicons name="time-outline" size={24} color={color} /> }}
      />
      <Tabs.Screen
        name="InsightsTab"
        options={{ tabBarIcon: ({ color }) => <Ionicons name="pulse-outline" size={24} color={color} /> }}
      >
        {() => <InsightsScreen />}
      </Tabs.Screen>
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
 * Main = tabs + the SidePanel overlay (V2 nav redesign, 2026-08-16).
 * The panel is an in-tree Animated overlay (OTA-safe — no drawer package),
 * covering the tab bar too, and routes into the Menu modal stack / tab stacks.
 * ──────────────────────────────────────────────────────────────── */

function MainWithPanel({ navigation }: { navigation: any }) {
  const [panelOpen, setPanelOpen] = useState(false);
  const go = (dest: string) => {
    setPanelOpen(false);
    switch (dest) {
      case 'canvas':     navigation.navigate('Menu', { screen: 'Canvas' }); break;
      // `initial: false` is load-bearing. Without it, a nested navigate seeds the
      // Notes stack with MeetingList as its ONLY route (core/useNavigationBuilder
      // getStateFromParams: `params?.initial !== false`), so MeetingList's Back
      // has nothing to pop, bubbles to the tab navigator, and its default
      // backBehavior:'firstRoute' throws you to Home — leaving NotesTab parked on
      // MeetingList with NotesList unreachable. With it, NotesList sits underneath
      // and Back means "up to the notes list", same as entering via Notes → Meetings.
      case 'meetings':   navigation.navigate('Main', { screen: 'NotesTab', params: { screen: 'MeetingList', initial: false } }); break;
      case 'dictionary': navigation.navigate('Menu', { screen: 'Dictionary' }); break;
      case 'snippets':   navigation.navigate('Menu', { screen: 'Snippets' }); break;
      case 'team':       navigation.navigate('Menu', { screen: 'Team' }); break;
      case 'devices':    navigation.navigate('Menu', { screen: 'Devices' }); break;
      case 'settings':   navigation.navigate('Menu', { screen: 'Settings' }); break;
    }
  };
  return (
    <View style={{ flex: 1 }}>
      <TabsNavigator
        onRecord={() => navigation.navigate('Recording')}
        onOpenMenu={() => setPanelOpen(true)}
      />
      <SidePanel open={panelOpen} onClose={() => setPanelOpen(false)} onNavigate={go as any} />
    </View>
  );
}

/* ────────────────────────────────────────────────────────────────
 * Root
 * ──────────────────────────────────────────────────────────────── */

const Root = createNativeStackNavigator<RootStackParamList>();

const ONBOARDED_KEY = 'flume_onboarded';

export const RootNavigator: React.FC = () => {
  const { user, isLoading, signOut } = useAuth();
  const { addTranscription } = useHistory();
  const { target, mode } = useDevices();
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
    // Clear a stale/MOCK session so the intended first-run Welcome (sign-in)
    // step shows instead of bouncing straight to Home — but NEVER nuke a real
    // signed-in user (IDI-166): if `flume_onboarded` is ever lost while a live
    // session survives, finishing onboarding must not silently sign them out
    // and wipe their local caches.
    try {
      const { supabase } = await import('../../lib/supabase');
      const { data } = await supabase.auth.getSession();
      if (!data.session?.user?.id) await signOut().catch(() => {});
    } catch {
      await signOut().catch(() => {});
    }
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
                <MainWithPanel navigation={navigation} />
              )}
            </Root.Screen>
            <Root.Screen
              name="Recording"
              options={{ presentation: 'modal', gestureEnabled: false }}
            >
              {({ navigation }) => (
                <RecordingScreen
                  onCancel={() => navigation.goBack()}
                  onComplete={async (_uri, durationMs, send) => {
                    const last = consumeLastRecording();
                    const failed = last?.status === 'failed';
                    const hasSpeech = !!last?.text?.trim();
                    // WHAT THE USER SAW IS WHAT HAPPENS: `send` is the choice
                    // the recording screen displayed at Stop — never re-read
                    // the device store here (it may have adopted a target
                    // AFTER the chip said "This phone only").
                    const targetedId = send.mode === 'device' ? send.id : null;
                    const push = send.mode !== 'none';
                    const deviceName = send.mode === 'device' && send.name ? send.name
                      : send.mode === 'all' ? 'All devices' : 'Local';
                    const transcript = failed
                      ? 'Transcription failed — your audio is saved. Retry it from History.'
                      : hasSpeech ? last!.text : 'No speech detected.';
                    const wordCount = hasSpeech ? last!.text.trim().split(/\s+/).length : 0;

                    if (failed) {
                      // Keep the audio; save a retryable entry.
                      addTranscription('', deviceName, durationMs, targetedId, last?.uri, 'failed', push);
                    } else if (hasSpeech) {
                      Clipboard.setStringAsync(last!.text);
                      addTranscription(last!.text, deviceName, durationMs, targetedId, last?.uri, 'done', push);
                    }

                    // Only claim device delivery when it can actually happen:
                    // the cloud push is gated on the Sync toggle AND a target.
                    const syncOn = await getSyncEnabled().catch(() => false);
                    const sent = !failed && hasSpeech && syncOn && send.mode === 'device' && !!send.id;

                    navigation.replace('Confirmation', {
                      transcript,
                      deviceName,
                      durationSeconds: Math.round(durationMs / 1000),
                      wordCount,
                      transcribeMs: last?.transcribeMs ?? 0,
                      variant: failed ? 'failed' : !hasSpeech ? 'empty' : sent ? 'sent' : 'saved',
                    });
                  }}
                />
              )}
            </Root.Screen>
            <Root.Screen name="Menu" options={{ presentation: 'modal', gestureEnabled: true }}>
              {() => <MenuNavigator />}
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
                      addTranscription(route.params.transcript, (mode === 'device' && target?.name) || 'Local', route.params.durationSeconds * 1000, mode === 'device' ? target?.id ?? null : null);
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
      <DevicesSyncHost />
    </NavigationContainer>
  );
};

export default RootNavigator;
