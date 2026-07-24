/**
 * AudioSegmentPlayer — labelled per-segment playback for a voice note's source
 * recordings (NOTES_ENHANCEMENT_SWARM.md, Feature 4).
 *
 * One instance per `audio_segments[]` entry. Uses expo-audio's `useAudioPlayer`
 * (each row is its own component so the hook count stays stable). The play
 * control carries a real text accessibility label ("Play recording from …"), not
 * just an icon (Design Decision 8). Fail-closed: a source that won't load simply
 * stays idle — it never throws into the editor.
 *
 * The caller only renders this when there ARE segments AND the audio-linkage flag
 * is on; there is deliberately no disabled/empty state here.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { View, StyleSheet, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { Text } from './Text';
import { colors, radius } from '../theme';
import { resolvePlaybackUrl } from '../../lib/recordings';

function segTime(createdAt: string): string {
  const d = new Date(createdAt);
  if (isNaN(d.getTime())) return 'recording';
  let h = d.getHours();
  const m = d.getMinutes();
  const ampm = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  return `${h}:${String(m).padStart(2, '0')} ${ampm}`;
}

export type AudioSegmentPlayerProps = {
  url: string;
  createdAt: string;
  index: number;
};

export const AudioSegmentPlayer: React.FC<AudioSegmentPlayerProps> = ({ url, createdAt, index }) => {
  // recordings is private (MER-27) — resolve a signed URL before playing.
  const [signedUrl, setSignedUrl] = useState<string | null>(null);
  useEffect(() => {
    setSignedUrl(null);
    if (!url) return;
    let cancelled = false;
    resolvePlaybackUrl(url, 'recordings').then((u) => { if (!cancelled) setSignedUrl(u); });
    return () => { cancelled = true; };
  }, [url]);

  const player = useAudioPlayer(signedUrl);
  const status = useAudioPlayerStatus(player);
  const playing = !!status?.playing;
  const label = segTime(createdAt);

  const toggle = useCallback(() => {
    try {
      if (playing) {
        player.pause();
      } else {
        if (status?.didJustFinish || (status?.duration && status.currentTime >= status.duration)) {
          player.seekTo(0);
        }
        player.play();
      }
    } catch {
      /* fail closed — playback issues never break the editor */
    }
  }, [player, playing, status]);

  return (
    <Pressable
      onPress={toggle}
      style={styles.row}
      accessibilityRole="button"
      accessibilityLabel={`${playing ? 'Pause' : 'Play'} recording ${index + 1} from ${label}`}
    >
      <View style={styles.playIcon}>
        <Ionicons name={playing ? 'pause' : 'play'} size={14} color={colors.primary} />
      </View>
      <Text variant="bodyXs" color={colors.textSecondary} style={{ flex: 1 }}>
        Recording {index + 1}
      </Text>
      <Text variant="metaSm" color={colors.textSubtle}>{label}</Text>
    </Pressable>
  );
};

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 9,
    paddingHorizontal: 12,
    borderRadius: radius.md,
    backgroundColor: colors.surface1,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  playIcon: {
    width: 28, height: 28, borderRadius: 14,
    backgroundColor: colors.primarySoft,
    borderWidth: 1, borderColor: colors.primaryBorder,
    alignItems: 'center', justifyContent: 'center',
  },
});

export default AudioSegmentPlayer;
