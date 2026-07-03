import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, type, space, radius } from '../../lib/flumeTokens';

export default function FlumeHomeScreen({ navigation }: { navigation: any }) {
  const [isRecording, setIsRecording] = useState(false);

  const handleMicPress = () => {
    if (!isRecording) {
      // Navigate to recording screen
      navigation.navigate('Recording');
    }
  };

  return (
    <View style={s.root}>
      <SafeAreaView style={s.safeArea} edges={['top']}>
        <ScrollView 
          contentContainerStyle={s.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Greeting Row */}
          <View style={s.greetingRow}>
            <View>
              <Text style={s.greetingLabel}>Good morning</Text>
              <Text style={s.greetingName}>Aman</Text>
            </View>
            <View style={s.logoCircle}>
              <Text style={s.logoEmoji}>🐦</Text>
            </View>
          </View>

          {/* Device Chips */}
          <View style={s.deviceChips}>
            <TouchableOpacity style={[s.chip, s.chipActive]} activeOpacity={0.7}>
              <View style={s.chipDot} />
              <Text style={s.chipTextActive}>MacBook Pro</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.chip} activeOpacity={0.7}>
              <Text style={s.chipText}>Desktop</Text>
            </TouchableOpacity>
          </View>

          {/* Last Sent Section */}
          <Text style={s.sectionLabel}>Last sent</Text>
          <TouchableOpacity style={s.historyCard} activeOpacity={0.7}>
            <Text style={s.cardText}>
              "Reschedule the design review to Thursday afternoon…"
            </Text>
            <View style={s.cardFooter}>
              <Text style={s.cardMeta}>2m · MacBook</Text>
              <Text style={s.resendText}>Resend</Text>
            </View>
          </TouchableOpacity>

          {/* Spacer */}
          <View style={s.spacer} />

          {/* Mic Group */}
          <View style={s.micGroup}>
            <Text style={s.micLabel}>Hold to speak</Text>
            <TouchableOpacity 
              style={s.micButton}
              onPress={handleMicPress}
              activeOpacity={0.8}
            >
              <Ionicons name="mic" size={36} color={colors.primaryInk} />
              {/* Pulse rings */}
              <View style={[s.pulseRing, s.pulseRing1]} />
              <View style={[s.pulseRing, s.pulseRing2]} />
            </TouchableOpacity>
          </View>
        </ScrollView>
      </SafeAreaView>

      {/* Tab Bar */}
      <View style={s.tabBar}>
        <TouchableOpacity style={s.tab} activeOpacity={0.7}>
          <Ionicons name="mic" size={14} color={colors.primary} />
          <Text style={[s.tabLabel, { color: colors.primary }]}>Record</Text>
        </TouchableOpacity>
        <TouchableOpacity 
          style={s.tab} 
          activeOpacity={0.7}
          onPress={() => navigation.navigate('HistoryList')}
        >
          <Ionicons name="time-outline" size={14} color={colors.textDisabled} />
          <Text style={s.tabLabel}>History</Text>
        </TouchableOpacity>
        <TouchableOpacity 
          style={s.tab} 
          activeOpacity={0.7}
          onPress={() => navigation.navigate('Settings')}
        >
          <Ionicons name="settings-outline" size={14} color={colors.textDisabled} />
          <Text style={s.tabLabel}>Settings</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
  },
  safeArea: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    paddingTop: space.s,
    paddingHorizontal: space.l,
    paddingBottom: space.base,
  },
  greetingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.lg,
  },
  greetingLabel: {
    ...type.caption,
    color: colors.textMuted,
  },
  greetingName: {
    ...type.subtitle,
    color: colors.textPrimary,
  },
  logoCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#000',
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoEmoji: {
    fontSize: 20,
  },
  deviceChips: {
    flexDirection: 'row',
    gap: 6,
    marginBottom: space.lg,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.surface2,
    borderRadius: radius.pill,
    paddingVertical: 6,
    paddingHorizontal: 11,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  chipActive: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primaryBorder,
  },
  chipDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.primary,
  },
  chipText: {
    ...type.label,
    color: colors.textPrimary,
    opacity: 0.85,
  },
  chipTextActive: {
    ...type.label,
    color: colors.primaryAccent,
  },
  sectionLabel: {
    ...type.meta,
    color: colors.textMuted,
    marginBottom: 8,
  },
  historyCard: {
    backgroundColor: colors.surface1,
    borderRadius: radius.lg,
    padding: 14,
    borderWidth: 1,
    borderColor: 'rgba(245,237,228,0.05)',
    marginBottom: space.lg,
  },
  cardText: {
    ...type.bodySm,
    color: colors.textPrimary,
    opacity: 0.9,
    marginBottom: 8,
  },
  cardFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  cardMeta: {
    ...type.metaSm,
    color: colors.textSubtle,
  },
  resendText: {
    ...type.buttonSm,
    color: colors.primary,
  },
  spacer: {
    flex: 1,
  },
  micGroup: {
    alignItems: 'center',
    gap: 12,
    marginBottom: 20,
  },
  micLabel: {
    ...type.caption,
    color: colors.textMuted,
  },
  micButton: {
    width: 92,
    height: 92,
    borderRadius: 46,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  pulseRing: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 46,
    borderWidth: 2,
    borderColor: colors.primary,
    opacity: 0.4,
  },
  pulseRing1: {
    transform: [{ scale: 1.2 }],
  },
  pulseRing2: {
    transform: [{ scale: 1.4 }],
    opacity: 0.2,
  },
  tabBar: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingTop: 10,
    paddingBottom: 26,
    paddingHorizontal: 16,
    borderTopWidth: 1,
    borderTopColor: colors.borderSubtle,
    backgroundColor: colors.bgScreen,
  },
  tab: {
    alignItems: 'center',
    gap: 4,
  },
  tabLabel: {
    ...type.tabLabel,
    color: colors.textDisabled,
  },
});
