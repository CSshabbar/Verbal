import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, type, space, radius } from '../../lib/flumeTokens';

const steps = [
  {
    number: '01',
    title: 'Speak',
    subtitle: 'Hold the mic, talk freely',
  },
  {
    number: '02',
    title: 'Transcribe',
    subtitle: 'Words appear in seconds',
  },
  {
    number: '03',
    title: 'Paste',
    subtitle: 'Lands in your computer',
  },
];

export default function OnboardingHowScreen({ navigation }: { navigation: any }) {
  return (
    <View style={s.root}>
      <SafeAreaView style={s.safeArea} edges={['top']}>
        <ScrollView 
          contentContainerStyle={s.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Steps */}
          <View style={s.stepsContainer}>
            {steps.map((step, index) => (
              <View key={step.number} style={s.step}>
                <View style={s.stepNumber}>
                  <Text style={s.stepNumberText}>{step.number}</Text>
                </View>
                <View style={s.stepContent}>
                  <Text style={s.stepTitle}>{step.title}</Text>
                  <Text style={s.stepSubtitle}>{step.subtitle}</Text>
                </View>
              </View>
            ))}
          </View>

          {/* Spacer */}
          <View style={s.spacer} />

          {/* Next Button */}
          <TouchableOpacity 
            style={s.primaryBtn}
            onPress={() => navigation.navigate('OnboardingPair')}
            activeOpacity={0.7}
          >
            <Text style={s.primaryBtnText}>Next</Text>
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
  stepsContainer: {
    gap: 22,
    marginBottom: 40,
  },
  step: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.l,
  },
  stepNumber: {
    width: 38,
    height: 38,
    borderRadius: radius.md,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepNumberText: {
    ...type.body,
    color: colors.primary,
    fontFamily: 'Courier',
    fontWeight: '600',
    fontSize: 16,
  },
  stepContent: {
    flex: 1,
  },
  stepTitle: {
    ...type.button,
    color: colors.textPrimary,
    marginBottom: 2,
  },
  stepSubtitle: {
    ...type.bodyXs,
    color: colors.textMuted,
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
