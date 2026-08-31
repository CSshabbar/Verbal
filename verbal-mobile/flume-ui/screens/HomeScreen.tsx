import React from 'react';
import { View, StyleSheet, ScrollView, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { Text, LogoMark } from '../components';
import { colors, pressedStyle } from '../theme';
import { useDevices } from '../hooks/useDevices';
import { useHistory } from '../hooks/useHistory';
import { useNotes } from '../hooks/useNotes';
import { useAuth } from '../hooks/useAuth';
import { DeviceTag } from './HistoryListScreen';

type Props = { onOpenMenu: () => void };

// Muted pastel feature-card backgrounds (minimalist-dark, wireframe 7a).
const CARD_CREAM = '#EADFCE';
const CARD_CREAM_INK = '#2a1f18';
const CARD_SAGE = '#DDE4D3';
const CARD_SAGE_INK = '#1e2418';
const CARD_PLUM = '#e6dae4';
const CARD_PLUM_INK = '#221820';

/**
 * Screen 7a — Home dashboard (minimalist dark): greeting, device pills,
 * two feature cards, recent list. Recording lives on the center tab-bar mic.
 */
export const HomeScreen: React.FC<Props> = ({ onOpenMenu }) => {
  const insets = useSafeAreaInsets();
  const nav = useNavigation<any>();
  const { user } = useAuth();
  const { devices, target, mode, setTarget, setSendMode } = useDevices();
  const { items } = useHistory();
  const { notes } = useNotes();

  const onlineNames = devices.map(d => d.name).join(' · ') || 'No devices';
  const recent = items.slice(0, 4);

  const openDevices = () => nav.navigate('Menu', { screen: 'Devices' });
  const openNotes = () => nav.navigate('NotesTab');
  const openHistory = () => nav.navigate('HistoryTab');

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <LogoMark size={34} />
          <Text variant="subtitle" style={{ fontSize: 15 }}>Hi, {user?.firstName ?? 'there'}</Text>
        </View>
        <Pressable onPress={onOpenMenu} style={({ pressed }) => [styles.iconCircle, pressed && pressedStyle]} accessibilityRole="button" accessibilityLabel="Open menu">
          <Ionicons name="menu" size={18} color={colors.textSecondary} />
        </Pressable>
      </View>

      <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: insets.bottom + 24 }}>
        {/* Device target pills */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 7, paddingRight: 16 }} style={{ marginBottom: 20, flexGrow: 0 }}>
          <Pill label="This phone" active={mode === 'none'} onPress={() => setSendMode('none')} />
          <Pill label="All" active={mode === 'all'} onPress={() => setTarget(null)} />
          {devices.map(d => (
            <Pill key={d.id} label={d.name} active={mode === 'device' && target?.id === d.id} onPress={() => setTarget(d)} />
          ))}
        </ScrollView>

        {/* Feature cards */}
        <View style={styles.featureRow}>
          <FeatureCard bg={CARD_CREAM} ink={CARD_CREAM_INK} icon="mic-outline" big={`${devices.length} online`} title="Devices ready" sub={onlineNames} onPress={openDevices} />
          <FeatureCard bg={CARD_SAGE} ink={CARD_SAGE_INK} icon="document-text-outline" big={`${notes.length} notes`} title="Your notebook" sub={notes.length ? 'Tap to open' : 'No notes yet'} onPress={openNotes} />
        </View>

        {/* Insights strip */}
        <Pressable
          onPress={() => nav.navigate('InsightsTab')}
          style={({ pressed }) => [styles.insightsRow, pressed && pressedStyle]}
          accessibilityRole="button" accessibilityLabel="Open insights"
        >
          <View style={[styles.featureIcon, { backgroundColor: CARD_PLUM_INK, width: 28, height: 28, borderRadius: 14 }]}>
            <Ionicons name="pulse-outline" size={14} color={CARD_PLUM} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 13, fontFamily: 'Geist_600SemiBold', color: CARD_PLUM_INK }}>Insights</Text>
            <Text style={{ fontSize: 11, fontFamily: 'Geist_400Regular', color: CARD_PLUM_INK, opacity: 0.6 }}>Your words, speed & streaks</Text>
          </View>
          <Ionicons name="chevron-forward" size={13} color={CARD_PLUM_INK} style={{ opacity: 0.5 }} />
        </Pressable>

        {/* Recent */}
        <View style={styles.recentHead}>
          <Text variant="subtitle" style={{ fontSize: 16 }}>Recent</Text>
          <Pressable onPress={openHistory} hitSlop={8} style={({ pressed }) => pressed && pressedStyle}>
            <Text variant="buttonSm" color={colors.textMuted}>See all</Text>
          </Pressable>
        </View>

        {recent.length === 0 ? (
          <View style={styles.emptyRecent}>
            <Text variant="bodySm" color={colors.textSubtle}>Nothing yet — tap the mic to record.</Text>
          </View>
        ) : (
          <View style={{ gap: 10 }}>
            {recent.map(item => (
              <Pressable
                key={item.id}
                // `initial: false` seeds HistoryList underneath, so Back from the
                // detail goes to the History list, not Home (rule #46).
                onPress={() => nav.navigate('HistoryTab', { screen: 'HistoryDetail', params: { itemId: item.id }, initial: false })}
                style={({ pressed }) => [styles.recentCard, pressed && pressedStyle]}
                accessibilityRole="button"
                accessibilityLabel={`Open transcription: ${item.text.slice(0, 60)}`}
              >
                <View style={styles.recentCardHead}>
                  <Text variant="caption" color={colors.textSubtle}>{item.dayLabel} · {item.timeOfDay}</Text>
                  <View style={styles.recentIcon}>
                    <Ionicons name="chatbubble-outline" size={13} color={colors.textMuted} />
                  </View>
                </View>
                <Text variant="bodySm" numberOfLines={2} style={{ marginBottom: 10 }}>{item.text}</Text>
                <DeviceTag tag={item.deviceTag} />
              </Pressable>
            ))}
          </View>
        )}
      </ScrollView>
    </View>
  );
};

const Pill: React.FC<{ label: string; active: boolean; onPress: () => void }> = ({ label, active, onPress }) => (
  <Pressable onPress={onPress} style={({ pressed }) => [styles.pill, active ? styles.pillActive : styles.pillIdle, pressed && pressedStyle]}>
    <Text variant="buttonSm" color={active ? colors.primaryInk : colors.textSecondary}>{label}</Text>
  </Pressable>
);

const FeatureCard: React.FC<{
  bg: string; ink: string; icon: keyof typeof Ionicons.glyphMap; big: string; title: string; sub: string; onPress?: () => void;
}> = ({ bg, ink, icon, big, title, sub, onPress }) => (
  <Pressable style={({ pressed }) => [styles.feature, { backgroundColor: bg }, pressed && pressedStyle]} onPress={onPress} accessibilityRole="button" accessibilityLabel={title}>
    <View style={styles.featureTop}>
      <View style={[styles.featureIcon, { backgroundColor: ink }]}>
        <Ionicons name={icon} size={15} color={bg} />
      </View>
      <Ionicons name="chevron-forward" size={13} color={ink} style={{ opacity: 0.5 }} />
    </View>
    <Text style={{ fontSize: 22, fontFamily: 'Geist_600SemiBold', color: ink, letterSpacing: -0.4, marginBottom: 3 }}>{big}</Text>
    <Text style={{ fontSize: 13, fontFamily: 'Geist_600SemiBold', color: ink, marginBottom: 2 }}>{title}</Text>
    <Text style={{ fontSize: 11, fontFamily: 'Geist_400Regular', color: ink, opacity: 0.6 }} numberOfLines={1}>{sub}</Text>
  </Pressable>
);

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bgScreen, paddingHorizontal: 18 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 11 },
  iconCircle: { width: 34, height: 34, borderRadius: 17, backgroundColor: colors.surface2, alignItems: 'center', justifyContent: 'center' },
  pill: { paddingVertical: 9, paddingHorizontal: 16, borderRadius: 999 },
  pillActive: { backgroundColor: colors.inkLight },
  pillIdle: { backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.borderStrong },
  featureRow: { flexDirection: 'row', gap: 10, marginBottom: 10 },
  insightsRow: { flexDirection: 'row', alignItems: 'center', gap: 11, backgroundColor: CARD_PLUM, borderRadius: 16, paddingVertical: 11, paddingHorizontal: 13, marginBottom: 24 },
  feature: { flex: 1, borderRadius: 18, padding: 14, paddingBottom: 16 },
  featureTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 26 },
  featureIcon: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  recentHead: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12 },
  emptyRecent: { paddingVertical: 24, alignItems: 'center' },
  recentCard: { padding: 14, borderRadius: 16, backgroundColor: colors.surface1, borderWidth: 1, borderColor: colors.borderSubtle },
  recentCardHead: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 },
  recentIcon: { width: 26, height: 26, borderRadius: 8, backgroundColor: colors.surface2, alignItems: 'center', justifyContent: 'center' },
});

export default HomeScreen;
