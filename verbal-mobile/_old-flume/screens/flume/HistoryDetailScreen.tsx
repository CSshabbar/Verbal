import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, type, space, radius } from '../../lib/flumeTokens';

export default function HistoryDetailScreen({ navigation, route }: any) {
  const { item } = route.params;

  return (
    <View style={s.root}>
      <SafeAreaView style={s.safeArea} edges={['top']}>
        <ScrollView 
          contentContainerStyle={s.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Top Bar */}
          <View style={s.topBar}>
            <TouchableOpacity 
              style={s.backBtn}
              onPress={() => navigation.goBack()}
              activeOpacity={0.7}
            >
              <Ionicons name="chevron-back" size={18} color={colors.textPrimary} />
              <Text style={s.backText}>History</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.overflowBtn} activeOpacity={0.7}>
              <Ionicons name="ellipsis-horizontal" size={16} color={colors.textPrimary} />
            </TouchableOpacity>
          </View>

          {/* Meta Block */}
          <Text style={s.metaLabel}>Today · 9:24 AM</Text>
          <View style={s.deviceRow}>
            <View style={s.deviceTile}>
              <Ionicons name="laptop-outline" size={14} color={colors.textPrimary} />
            </View>
            <Text style={s.deviceName}>MacBook Pro · 14s · {item.words} words</Text>
          </View>

          {/* Playback Bar */}
          <View style={s.playbackBar}>
            <TouchableOpacity style={s.playBtn}>
              <Ionicons name="play" size={11} color={colors.primaryInk} />
            </TouchableOpacity>
            <View style={s.waveform}>
              {/* Played portion (5 bars) */}
              {[6, 12, 18, 10, 20].map((h, i) => (
                <View key={`played-${i}`} style={[s.waveBar, { height: h, backgroundColor: colors.primary }]} />
              ))}
              {/* Unplayed portion (15 bars) */}
              {[8, 14, 18, 6, 12, 16, 8, 14, 20, 8, 18, 10, 14, 6, 12].map((h, i) => (
                <View key={`unplayed-${i}`} style={[s.waveBar, { height: h, backgroundColor: colors.textDisabled }]} />
              ))}
            </View>
            <View style={s.timeRow}>
              <Text style={s.currentTime}>0:04</Text>
              <Text style={s.totalTime}>0:14</Text>
            </View>
          </View>

          {/* Transcript Card */}
          <Text style={s.transcriptLabel}>Transcript</Text>
          <View style={s.transcriptCard}>
            <Text style={s.transcriptText}>
              {item.text}
            </Text>
          </View>

          {/* Spacer */}
          <View style={s.spacer} />

          {/* Action Row */}
          <View style={s.actionRow}>
            <TouchableOpacity style={s.ghostBtn} activeOpacity={0.7}>
              <Text style={s.ghostBtnText}>Edit</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.ghostBtn} activeOpacity={0.7}>
              <Text style={s.ghostBtnText}>Copy</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.primaryBtn} activeOpacity={0.7}>
              <Text style={s.primaryBtnText}>Resend</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </SafeAreaView>
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
    paddingBottom: space.xl,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.l,
  },
  backBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  backText: {
    ...type.button,
    color: colors.textPrimary,
  },
  overflowBtn: {
    width: 28,
    height: 28,
    borderRadius: radius.sm,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  metaLabel: {
    ...type.meta,
    color: colors.textMuted,
    marginBottom: 8,
  },
  deviceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: space.l,
  },
  deviceTile: {
    width: 20,
    height: 20,
    borderRadius: radius.xs,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  deviceName: {
    ...type.button,
    color: colors.textPrimary,
  },
  playbackBar: {
    backgroundColor: colors.surface1,
    borderRadius: radius.lg,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    marginBottom: space.l,
  },
  playBtn: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 8,
  },
  waveform: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    marginBottom: 6,
  },
  waveBar: {
    width: 2,
    borderRadius: 1,
  },
  timeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  currentTime: {
    ...type.metaSm,
    color: colors.textSubtle,
  },
  totalTime: {
    ...type.metaSm,
    color: colors.textSubtle,
  },
  transcriptLabel: {
    ...type.meta,
    color: colors.textMuted,
    marginBottom: 8,
  },
  transcriptCard: {
    backgroundColor: colors.surface1,
    borderRadius: radius.lg,
    padding: 14,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    marginBottom: space.l,
  },
  transcriptText: {
    ...type.bodySm,
    color: colors.textPrimary,
    lineHeight: 19,
  },
  spacer: {
    flex: 1,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 20,
  },
  ghostBtn: {
    flex: 1,
    backgroundColor: 'transparent',
    borderRadius: radius.lg,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    alignItems: 'center',
  },
  ghostBtnText: {
    ...type.button,
    color: colors.textPrimary,
  },
  primaryBtn: {
    flex: 1.3,
    backgroundColor: colors.primary,
    borderRadius: radius.lg,
    paddingVertical: 12,
    paddingHorizontal: 14,
    alignItems: 'center',
  },
  primaryBtnText: {
    ...type.button,
    color: colors.primaryInk,
  },
});
