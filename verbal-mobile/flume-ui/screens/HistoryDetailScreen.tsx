import React from 'react';
import { View, StyleSheet, Pressable, ScrollView } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text, Card, Button } from '../components';
import { colors, radius, pressedStyle } from '../theme';
import { HistoryItem } from '../hooks/useHistory';
import { DeviceTag } from './HistoryListScreen';

type Props = {
  item: HistoryItem;
  onBack: () => void;
  onCopy: () => void;
  onResend: () => void;
  onOverflow: () => void;
  onPlay?: () => void;
  onRetry?: () => void;
};

/**
 * Screen 3g — History detail. Audio playback bar + transcript + actions.
 */
export const HistoryDetailScreen: React.FC<Props> = ({
  item, onBack, onCopy, onResend, onOverflow, onPlay, onRetry,
}) => {
  const insets = useSafeAreaInsets();
  const failed = item.status === 'failed';

  return (
    <View style={[styles.root, { paddingTop: insets.top + 10, paddingBottom: insets.bottom + 14 }]}>
      <View style={styles.topBar}>
        <Pressable onPress={onBack} style={({ pressed }) => [styles.backBtn, pressed && pressedStyle]}>
          <Ionicons name="chevron-back" size={22} color={colors.textSecondary} />
          <Text variant="buttonSm">History</Text>
        </Pressable>
        <Pressable style={({ pressed }) => [styles.overflow, pressed && pressedStyle]} onPress={onOverflow} accessibilityRole="button" accessibilityLabel="More options">
          <Ionicons name="ellipsis-horizontal" size={18} color={colors.textPrimary} />
        </Pressable>
      </View>

      <View style={{ marginBottom: 14 }}>
        <Text variant="meta" color={colors.textSubtle} style={{ marginBottom: 6 }}>
          {item.dayLabel} · {item.timeOfDay}
        </Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <DeviceTag tag={failed ? 'Failed' : item.deviceTag} />
          <Text variant="metaSm" color={colors.textSubtle}>
            {item.durationLabel} · {item.wordCount} words
          </Text>
        </View>
      </View>

      {item.hasAudio && <PlaybackBar onPlay={onPlay} />}

      <Card padding={14} style={{ flex: 1, marginTop: 14 }}>
        <ScrollView style={{ flex: 1 }}>
          <Text variant="bodySm" color={failed ? colors.textMuted : colors.textPrimary}>
            {failed
              ? 'Transcription failed. Your audio is saved — retry when you are back online.'
              : item.text}
          </Text>
        </ScrollView>
      </Card>

      <View style={styles.actionRow}>
        {failed ? (
          <Button label="Retry transcription" onPress={() => onRetry?.()} style={{ flex: 1 }} />
        ) : (
          <>
            <Button label="Copy" variant="ghost" onPress={onCopy} style={{ flex: 1 }} />
            <Button label="Resend" onPress={onResend} style={{ flex: 1.3 }} />
          </>
        )}
      </View>
    </View>
  );
};

/** 20-line waveform with the first 5 colored = "played" position. */
const PlaybackBar: React.FC<{ onPlay?: () => void }> = ({ onPlay }) => {
  const heights = [6, 12, 18, 10, 20, 8, 14, 18, 6, 12, 16, 8, 14, 20, 8, 18, 10, 14, 6, 12];
  const playedTo = 5;
  return (
    <Card padding={12} style={{ paddingVertical: 12 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <Pressable style={({ pressed }) => [styles.playBtn, pressed && pressedStyle]} onPress={onPlay}>
          <Ionicons name="play" size={18} color={colors.primaryInk} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <View style={styles.waveRow}>
            {heights.map((h, i) => (
              <View
                key={i}
                style={{
                  width: 3,
                  height: h * 1.35,
                  borderRadius: 1.5,
                  backgroundColor: i < playedTo ? colors.textPrimary : colors.textDisabled,
                }}
              />
            ))}
          </View>
          <View style={styles.timeRow}>
            <Text variant="metaSm" color={colors.textMuted}>0:04</Text>
            <Text variant="metaSm" color={colors.textMuted}>0:14</Text>
          </View>
        </View>
      </View>
    </Card>
  );
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 18,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  overflow: {
    width: 36, height: 36, borderRadius: 10,
    backgroundColor: colors.surface2,
    alignItems: 'center', justifyContent: 'center',
  },
  deviceIcon: {
    width: 28, height: 28, borderRadius: 8,
    backgroundColor: colors.primarySoft,
    alignItems: 'center', justifyContent: 'center',
  },
  playBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.inkLight,
    alignItems: 'center', justifyContent: 'center',
  },
  waveRow: { flexDirection: 'row', alignItems: 'center', gap: 3, height: 30 },
  timeRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 },
  actionRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
  },
});

export default HistoryDetailScreen;
