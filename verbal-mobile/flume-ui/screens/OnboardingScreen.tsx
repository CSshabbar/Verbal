import React, { useState } from 'react';
import { View, StyleSheet, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text, Button, PageDots, LogoMark } from '../components';
import { colors, radius, space } from '../theme';

type Props = { onDone: () => void; onSkip?: () => void };

/**
 * Screens 3b/1, 3b/2, 3b/3 — onboarding with internal step state.
 * Three slides, three CTAs.
 */
export const OnboardingScreen: React.FC<Props> = ({ onDone, onSkip }) => {
  const insets = useSafeAreaInsets();
  const [step, setStep] = useState(0);

  const next = () => (step >= 2 ? onDone() : setStep(s => s + 1));

  return (
    <View
      style={[
        styles.root,
        { paddingTop: insets.top + 12, paddingBottom: insets.bottom + 14 },
      ]}
    >
      {step === 0 && <Slide1 />}
      {step === 1 && <Slide2 />}
      {step === 2 && <Slide3 />}

      <View style={{ gap: 14 }}>
        <Button
          label={step === 0 ? 'Begin →' : step === 1 ? 'Next' : "I'm ready to pair"}
          onPress={next}
        />
        {step === 2 ? (
          <Pressable onPress={onSkip} style={{ alignItems: 'center', paddingVertical: 4 }}>
            <Text variant="buttonSm" color={colors.textMuted}>Set up later</Text>
          </Pressable>
        ) : null}
        <PageDots count={3} active={step} />
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

const Slide3: React.FC = () => (
  <View style={{ flex: 1, justifyContent: 'center', gap: 20 }}>
    <View>
      <Text variant="meta" color={colors.textSubtle} style={{ marginBottom: 12 }}>STEP 3 OF 3</Text>
      <Text variant="displaySm" style={{ marginBottom: 12 }}>Connect a computer.</Text>
      <Text variant="body" color={colors.textMuted}>
        Install Flume on Mac or Windows. You'll pair it next.
      </Text>
    </View>
    <View style={{ gap: 10 }}>
      <DownloadRow icon="logo-apple" label="Download for macOS" />
      <DownloadRow icon="logo-windows" label="Download for Windows" />
    </View>
  </View>
);

const DownloadRow: React.FC<{ icon: any; label: string }> = ({ icon, label }) => (
  <View style={styles.dlRow}>
    <Ionicons name={icon} size={24} color={colors.textPrimary} />
    <Text variant="bodySm" style={{ flex: 1 }}>{label}</Text>
    <Ionicons name="arrow-down" size={18} color={colors.textSubtle} />
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
  dlRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 14,
    paddingHorizontal: 14,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.borderStrong,
  },
});

export default OnboardingScreen;
