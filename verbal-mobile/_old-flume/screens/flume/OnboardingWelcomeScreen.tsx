import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, type, space, radius } from '../../lib/flumeTokens';

export default function OnboardingWelcomeScreen({ navigation }: { navigation: any }) {
  return (
    <View style={s.root}>
      <SafeAreaView style={s.safeArea} edges={['top']}>
        <ScrollView 
          contentContainerStyle={s.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Brand Row */}
          <View style={s.brandRow}>
            <View style={s.brandLogo}>
              <Text style={s.brandEmoji}>🐦</Text>
            </View>
            <Text style={s.brandWordmark}>FLUME</Text>
          </View>

          {/* Hero Text */}
          <Text style={s.hero}>
            Voice{'\n'}
            to text,{'\n'}
            <Text style={s.heroAccent}>anywhere.</Text>
          </Text>

          <Text style={s.sub}>
            Speak into your phone. Watch it appear on your laptop.
          </Text>

          {/* Spacer */}
          <View style={s.spacer} />

          {/* Begin Button */}
          <TouchableOpacity 
            style={s.primaryBtn}
            onPress={() => navigation.navigate('OnboardingHow')}
            activeOpacity={0.7}
          >
            <Text style={s.primaryBtnText}>Begin →</Text>
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
  brandRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 40,
  },
  brandLogo: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#000',
    alignItems: 'center',
    justifyContent: 'center',
  },
  brandEmoji: {
    fontSize: 18,
  },
  brandWordmark: {
    fontSize: 15,
    fontWeight: '600',
    letterSpacing: 0.5,
    color: colors.textPrimary,
  },
  hero: {
    ...type.displayXL,
    color: colors.textPrimary,
    marginBottom: 12,
  },
  heroAccent: {
    color: colors.primary,
  },
  sub: {
    ...type.body,
    color: colors.textMuted,
    marginBottom: 40,
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
    marginBottom: 20,
  },
  primaryBtnText: {
    ...type.buttonPrimary,
    color: colors.primaryInk,
  },
});
