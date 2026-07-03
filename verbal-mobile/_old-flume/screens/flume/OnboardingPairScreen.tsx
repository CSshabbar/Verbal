import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, type, space, radius } from '../../lib/flumeTokens';

export default function OnboardingPairScreen({ navigation }: { navigation: any }) {
  return (
    <View style={s.root}>
      <SafeAreaView style={s.safeArea} edges={['top']}>
        <ScrollView 
          contentContainerStyle={s.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Step Label */}
          <Text style={s.stepLabel}>Step 3 of 3</Text>

          {/* Title */}
          <Text style={s.title}>Connect a computer.</Text>
          <Text style={s.sub}>
            Install Flume on Mac or Windows. You'll pair it next.
          </Text>

          {/* Download Options */}
          <View style={s.downloadOptions}>
            {/* macOS */}
            <TouchableOpacity style={s.downloadRow} activeOpacity={0.7}>
              <Ionicons name="laptop-outline" size={18} color={colors.textPrimary} />
              <Text style={s.downloadText}>Download for macOS</Text>
              <Ionicons name="download-outline" size={16} color={colors.textSubtle} />
            </TouchableOpacity>

            {/* Windows */}
            <TouchableOpacity style={s.downloadRow} activeOpacity={0.7}>
              <Ionicons name="desktop-outline" size={18} color={colors.textPrimary} />
              <Text style={s.downloadText}>Download for Windows</Text>
              <Ionicons name="download-outline" size={16} color={colors.textSubtle} />
            </TouchableOpacity>
          </View>

          {/* Spacer */}
          <View style={s.spacer} />

          {/* Primary Button */}
          <TouchableOpacity 
            style={s.primaryBtn}
            onPress={() => navigation.navigate('MainTabs')}
            activeOpacity={0.7}
          >
            <Text style={s.primaryBtnText}>I'm ready to pair</Text>
          </TouchableOpacity>

          {/* Skip Button */}
          <TouchableOpacity 
            style={s.ghostBtn}
            onPress={() => navigation.navigate('MainTabs')}
            activeOpacity={0.7}
          >
            <Text style={s.ghostBtnText}>Skip for now</Text>
          </TouchableOpacity>
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
    paddingTop: space.l,
    paddingHorizontal: space.l,
  },
  stepLabel: {
    ...type.meta,
    color: colors.textMuted,
    marginBottom: space.s,
  },
  title: {
    ...type.displaySm,
    color: colors.textPrimary,
    marginBottom: 8,
  },
  sub: {
    ...type.body,
    color: colors.textMuted,
    marginBottom: 32,
  },
  downloadOptions: {
    gap: 8,
    marginBottom: 40,
  },
  downloadRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.l,
    backgroundColor: colors.surface1,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    paddingVertical: 14,
    paddingHorizontal: space.l,
  },
  downloadText: {
    flex: 1,
    ...type.button,
    color: colors.textPrimary,
  },
  spacer: {
    flex: 1,
  },
  primaryBtn: {
    backgroundColor: colors.primary,
    borderRadius: radius.xl,
    paddingVertical: 13,
    paddingHorizontal: 18,
    alignItems: 'center',
    marginBottom: 12,
  },
  primaryBtnText: {
    ...type.buttonPrimary,
    color: colors.primaryInk,
  },
  ghostBtn: {
    backgroundColor: 'transparent',
    borderRadius: radius.xl,
    paddingVertical: 13,
    paddingHorizontal: 18,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.borderStrong,
  },
  ghostBtnText: {
    ...type.button,
    color: colors.textPrimary,
  },
});
