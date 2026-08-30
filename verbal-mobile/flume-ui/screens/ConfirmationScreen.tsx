import React from 'react';
import { View, StyleSheet, Pressable, ScrollView } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { Text, Button, Card, SuccessBadge } from '../components';
import { colors, radius, pressedStyle } from '../theme';

type Variant = 'sent' | 'saved' | 'failed' | 'empty';

type Props = {
  deviceName: string;
  transcript: string;
  durationSeconds: number;
  wordCount: number;
  transcribeMs: number;
  /** Truthful outcome — see RootStackParamList.Confirmation (IDI-159). */
  variant?: Variant;
  onDone: () => void;
  onCopyAgain: () => void;
  onEditInHistory: () => void;
  onResendToAnother: () => void;
};

/**
 * Screen 3e / 8d — post-recording confirmation. Renders the TRUE outcome:
 * sent-to-device / saved-locally / failed (retryable) / no speech — the old
 * unconditional "Pasted to X" + success badge lied for three of the four.
 * Scrolls (long transcripts) with a pinned Done button. Manual dismiss.
 */
export const ConfirmationScreen: React.FC<Props> = ({
  deviceName, transcript, durationSeconds, wordCount, transcribeMs,
  variant = 'saved',
  onDone, onCopyAgain, onEditInHistory, onResendToAnother,
}) => {
  const insets = useSafeAreaInsets();
  const ok = variant === 'sent' || variant === 'saved';

  React.useEffect(() => {
    Haptics.notificationAsync(
      ok ? Haptics.NotificationFeedbackType.Success
         : Haptics.NotificationFeedbackType.Warning,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const title =
    variant === 'sent'   ? `Sent to ${deviceName}`
    : variant === 'saved' ? 'Saved to history'
    : variant === 'failed' ? 'Transcription failed'
    : 'No speech detected';

  const meta = ok
    ? `${durationSeconds} sec · ${wordCount} words · ${(transcribeMs / 1000).toFixed(1)}s to transcribe`
    : variant === 'failed'
      ? `${durationSeconds} sec recorded · audio saved for retry`
      : `${durationSeconds} sec recorded`;

  return (
    <View style={[styles.root, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 14 }]}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingBottom: 16 }}
        style={{ flex: 1 }}
      >
        <View style={styles.header}>
          {ok ? (
            <SuccessBadge size={72} />
          ) : (
            <View style={styles.warnBadge}>
              <Ionicons
                name={variant === 'failed' ? 'alert' : 'mic-off-outline'}
                size={34}
                color={variant === 'failed' ? colors.primary : colors.textSubtle}
              />
            </View>
          )}
          <Text variant="subtitle">{title}</Text>
          <Text variant="bodyXs" color={colors.textMuted}>{meta}</Text>
          {variant === 'saved' && (
            <Text variant="bodyXs" color={colors.textMuted}>Copied to clipboard</Text>
          )}
        </View>

        <Card padding={14}>
          <Text variant="meta" color={colors.textSubtle} style={{ marginBottom: 8 }}>
            {ok ? 'TRANSCRIPT' : 'DETAILS'}
          </Text>
          <Text variant="bodySm">{transcript}</Text>
        </Card>

        <View style={{ gap: 8, marginTop: 14 }}>
          {ok && <Action icon="copy-outline" label="Copy again" onPress={onCopyAgain} />}
          {variant !== 'empty' && (
            <Action
              icon="time-outline"
              label={variant === 'failed' ? 'Retry from History' : 'Edit in History'}
              onPress={onEditInHistory}
            />
          )}
          {ok && <Action icon="paper-plane-outline" label="Resend to another device" onPress={onResendToAnother} />}
        </View>
      </ScrollView>

      <Button label="Done" onPress={onDone} style={{ marginTop: 12 }} />
    </View>
  );
};

const Action: React.FC<{ icon: any; label: string; onPress: () => void }> = ({ icon, label, onPress }) => (
  <Pressable
    onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); onPress(); }}
    style={({ pressed }) => [styles.action, pressed && pressedStyle]}
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
  warnBadge: {
    width: 72,
    height: 72,
    borderRadius: 36,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface1,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
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
