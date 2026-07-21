import React, { useState } from 'react';
import { View, StyleSheet, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Text, Button, PageDots, LogoMark } from '../components';
import { colors, radius } from '../theme';

type Props = { onDone: () => void; onSkip?: () => void };

/**
 * Onboarding — two slides: the voice-to-text hero, then how it works.
 * (The old "Connect a computer / pair a device" slide was removed — pairing is
 * handled after sign-in via the devices sheet, not during onboarding.)
 */
export const OnboardingScreen: React.FC<Props> = ({ onDone, onSkip }) => {
  const insets = useSafeAreaInsets();
  const [step, setStep] = useState(0);
  const LAST = 1;

  const next = () => (step >= LAST ? onDone() : setStep(s => s + 1));

  return (
    <View
      style={[
        styles.root,
        { paddingTop: insets.top + 12, paddingBottom: insets.bottom + 14 },
      ]}
    >
      {step === 0 && <Slide1 />}
      {step === 1 && <Slide2 />}

      <View style={{ gap: 14 }}>
        <Button
          label={step === LAST ? 'Get started' : 'Begin →'}
          onPress={next}
        />
        {step === LAST && onSkip ? (
          <Pressable onPress={onSkip} style={{ alignItems: 'center', paddingVertical: 4 }}>
            <Text variant="buttonSm" color={colors.textMuted}>Skip for now</Text>
          </Pressable>
        ) : null}
        <PageDots count={2} active={step} />
      </View>
    </View>
  );
};

/* ─────────── slides ─────────── */

const Slide1: React.FC = () => (
  <View style={{ flex: 1, justifyContent: 'center', gap: 18, paddingHorizontal: 6 }}>
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14, marginBottom: 14 }}>
      <LogoMark size={38} />
      <Text variant="wordmark">FLUME</Text>
    </View>
    <Text variant="displayXL">
      Voice{'\n'}to text,{'\n'}
      <Text variant="displayXL" color={colors.primary}>anywhere.</Text>
    </Text>
    <Text variant="body" color={colors.textMuted} style={{ marginTop: 4 }}>
      Speak into your phone. Watch it appear on your laptop.
    </Text>
  </View>
);

const Slide2: React.FC = () => (
  <View style={{ flex: 1, justifyContent: 'center', gap: 22 }}>
    <Step n="01" title="Speak" sub="Hold the mic, talk freely" />
    <Step n="02" title="Transcribe" sub="Words appear in seconds" />
    <Step n="03" title="Paste" sub="Lands in your computer" />
  </View>
);

const Step: React.FC<{ n: string; title: string; sub: string }> = ({ n, title, sub }) => (
  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 18 }}>
    <View style={styles.stepNum}>
      <Text variant="mono" color={colors.primary} style={{ fontSize: 18, letterSpacing: 0 }}>{n}</Text>
    </View>
    <View>
      <Text variant="button">{title}</Text>
      <Text variant="bodyXs" color={colors.textMuted}>{sub}</Text>
    </View>
  </View>
);

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 26,
    justifyContent: 'space-between',
  },
  stepNum: {
    width: 52,
    height: 52,
    borderRadius: radius.md,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default OnboardingScreen;
