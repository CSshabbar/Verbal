import React from 'react';
import { View, StyleSheet, Pressable, ScrollView } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { Text, Button, Card, SuccessBadge } from '../components';
import { colors, radius } from '../theme';

type Props = {
  deviceName: string;
  transcript: string;
  durationSeconds: number;
  wordCount: number;
  transcribeMs: number;
  onDone: () => void;
  onCopyAgain: () => void;
  onEditInHistory: () => void;
  onResendToAnother: () => void;
};

/**
 * Screen 3e / 8d — Pasted confirmation.
 * Scrolls (long transcripts) with a pinned Done button. Manual dismiss.
 */
export const ConfirmationScreen: React.FC<Props> = ({
  deviceName, transcript, durationSeconds, wordCount, transcribeMs,
  onDone, onCopyAgain, onEditInHistory, onResendToAnother,
}) => {
  const insets = useSafeAreaInsets();

  React.useEffect(() => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  }, []);

  return (
    <View style={[styles.root, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 14 }]}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingBottom: 16 }}
        style={{ flex: 1 }}
      >
        <View style={styles.header}>
          <SuccessBadge size={72} />
          <Text variant="subtitle">Pasted to {deviceName}</Text>
          <Text variant="bodyXs" color={colors.textMuted}>
            {durationSeconds} sec · {wordCount} words · {(transcribeMs / 1000).toFixed(1)}s to transcribe
          </Text>
        </View>

        <Card padding={14}>
          <Text variant="meta" color={colors.textSubtle} style={{ marginBottom: 8 }}>TRANSCRIPT</Text>
          <Text variant="bodySm">{transcript}</Text>
        </Card>

        <View style={{ gap: 8, marginTop: 14 }}>
          <Action icon="copy-outline" label="Copy again" onPress={onCopyAgain} />
          <Action icon="time-outline" label="Edit in History" onPress={onEditInHistory} />
          <Action icon="paper-plane-outline" label="Resend to another device" onPress={onResendToAnother} />
        </View>
      </ScrollView>

      <Button label="Done" onPress={onDone} style={{ marginTop: 12 }} />
    </View>
  );
};

const Action: React.FC<{ icon: any; label: string; onPress: () => void }> = ({ icon, label, onPress }) => (
  <Pressable
    onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); onPress(); }}
    style={({ pressed }) => [styles.action, pressed && { opacity: 0.85 }]}
  >
    <Ionicons name={icon} size={20} color={colors.textPrimary} />
    <Text variant="button" style={{ flex: 1 }}>{label}</Text>
    <Ionicons name="chevron-forward" size={15} color={colors.textSubtle} />
  </Pressable>
);

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 18,
  },
  header: {
    alignItems: 'center',
    gap: 10,
    marginBottom: 22,
    marginTop: 8,
  },
  action: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 13,
    paddingHorizontal: 14,
    borderRadius: radius.lg,
    backgroundColor: colors.surface1,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
});

export default ConfirmationScreen;
