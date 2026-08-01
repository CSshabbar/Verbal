import React, { useEffect, useRef, useState } from 'react';
import { View, StyleSheet, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { Text, Chip, ChipDot, Visualizer, IconButton } from '../components';
import { colors } from '../theme';
import { useRecorder } from '../hooks/useRecorder';
import { useDevices } from '../hooks/useDevices';

type Props = {
  onCancel: () => void;
  onComplete: (audioUri: string, durationMs: number) => void;
};

/**
 * Screen 3d — Recording. Modal-presented.
 * Visualizer + timer + cancel/stop/pause controls.
 */
export const RecordingScreen: React.FC<Props> = ({ onCancel, onComplete }) => {
  const insets = useSafeAreaInsets();
  const { start, stop, pause, resume, cancel, status, durationMs, uri } = useRecorder();
  const [paused, setPaused] = useState(false);
  const finalizedRef = useRef(false);

  useEffect(() => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    start();
    // Unexpected navigation must release the mic without saving/transcribing.
    return () => { if (!finalizedRef.current) void cancel(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { target } = useDevices();

  const handleStop = async () => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    const result = await stop();
    if (result?.uri) {
      finalizedRef.current = true;
      onComplete(result.uri, result.durationMs);
    }
  };

  const handleCancel = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    await cancel();
    finalizedRef.current = true;
    onCancel();
  };

  const handlePause = () => {
    if (paused) { resume(); setPaused(false); }
    else        { pause();  setPaused(true);  }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top, paddingBottom: insets.bottom + 4 }]}>
      <LinearGradient
        pointerEvents="none"
        colors={['rgba(200, 90, 62,0.12)', colors.bgScreen]}
        locations={[0, 0.6]}
        style={StyleSheet.absoluteFill}
      />

      <View style={styles.statusBar}>
        <Text variant="caption" color={colors.textSubtle}>9:41</Text>
        <Text variant="caption" color={colors.primary}>● REC</Text>
      </View>

      <View style={{ alignItems: 'center', marginTop: 14, marginBottom: 30 }}>
        <Chip
          label={`→ ${target?.name ?? 'No device'}`}
          active
          leading={<ChipDot />}
        />
      </View>

      <View style={styles.middle}>
        <Visualizer
          active={!paused && status === 'recording'}
          heights={[38, 76, 120, 94, 148, 108, 134, 80, 120, 54]}
          barWidth={6}
          gap={7}
          color={colors.textPrimary}
        />
        <Text variant="timer">{formatMs(durationMs)}</Text>
        <Text variant="bodySm" color={colors.textSubtle}>
          {paused ? 'Paused — tap pause to resume' : 'Listening — tap stop when done'}
        </Text>
      </View>

      <View style={[styles.controls, { paddingBottom: insets.bottom + 8 }]}>
        <IconButton icon="close" size={48} variant="surface" label="Cancel" onPress={handleCancel} />
        <View style={styles.stopGroup}>
          <Pressable onPress={handleStop} style={({ pressed }) => [styles.stopBtn, pressed && { opacity: 0.9 }]}>
            <Ionicons name="square" size={20} color={colors.primaryInk} />
          </Pressable>
          <Text variant="buttonSm" color={colors.textSubtle}>Stop</Text>
        </View>
        <IconButton
          icon={paused ? 'play' : 'pause'}
          size={48}
          variant="surface"
          label={paused ? 'Resume' : 'Pause'}
          onPress={handlePause}
        />
      </View>
    </View>
  );
};

function formatMs(ms: number) {
  const total = Math.floor(ms / 1000);
  const m = String(Math.floor(total / 60)).padStart(2, '0');
  const s = String(total % 60).padStart(2, '0');
  return `${m}:${s}`;
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 18,
  },
  statusBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 4,
    height: 32,
    alignItems: 'center',
  },
  middle: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 26,
  },
  controls: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    paddingVertical: 16,
  },
  stopGroup: { alignItems: 'center', gap: 6 },
  stopBtn: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.inkLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default RecordingScreen;
