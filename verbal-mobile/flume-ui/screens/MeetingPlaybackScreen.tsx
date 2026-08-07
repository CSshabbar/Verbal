/**
 * MeetingPlaybackScreen — plays the meeting audio with the transcript synced:
 * the current utterance highlights as audio plays; tapping a line seeks to it.
 * Read-only. Falls back to a static transcript when there is no audio.
 */
import React, { useMemo, useRef, useEffect, useState } from 'react';
import { View, StyleSheet, Pressable, FlatList } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { Text } from '../components';
import { colors, radius, pressedStyle } from '../theme';
import { useMeetings, MeetingUtterance } from '../hooks/useMeetings';
import { resolvePlaybackUrl } from '../../lib/recordings';

type Props = {
  meetingId: string;
  onBack: () => void;
};

function fmtT(secs: number): string {
  const m = Math.floor(secs / 60);
  return `${m}:${String(Math.floor(secs % 60)).padStart(2, '0')}`;
}

export const MeetingPlaybackScreen: React.FC<Props> = ({ meetingId, onBack }) => {
  const insets = useSafeAreaInsets();
  const { getMeeting } = useMeetings();
  const meeting = getMeeting(meetingId);
  const listRef = useRef<FlatList<MeetingUtterance>>(null);

  // meeting-audio is private (MER-27) — resolve a signed URL before playing.
  // Long TTL: a meeting can run long, and the URL must stay valid for the whole
  // playback+scrub session, not just the first byte.
  //
  // The resolution used to be one-shot with no `.catch`: a rejection left
  // `signedUrl` null forever (a dead play button and no explanation), and a
  // session outliving the 3600 s TTL had no way to get a fresh URL. Now a
  // failure is a visible state with a Retry that RE-RESOLVES (IDI-175 §5).
  const [signedUrl, setSignedUrl] = useState<string | null>(null);
  const [urlError, setUrlError] = useState(false);
  const [resolveNonce, setResolveNonce] = useState(0);
  useEffect(() => {
    setSignedUrl(null);
    setUrlError(false);
    if (!meeting?.audioUrl) return;
    let cancelled = false;
    resolvePlaybackUrl(meeting.audioUrl, 'meeting-audio', 3600)
      .then((url) => {
        if (cancelled) return;
        if (url) setSignedUrl(url);
        else setUrlError(true);
      })
      .catch(() => { if (!cancelled) setUrlError(true); });
    return () => { cancelled = true; };
  }, [meeting?.audioUrl, resolveNonce]);

  const player = useAudioPlayer(signedUrl ? { uri: signedUrl } : null);
  const status = useAudioPlayerStatus(player);
  const currentTime = status?.currentTime ?? 0;
  const playing = !!status?.playing;

  const activeIdx = useMemo(() => {
    const tx = meeting?.transcript ?? [];
    for (let i = tx.length - 1; i >= 0; i--) {
      if (currentTime >= tx[i].t0 - 0.25) return i;
    }
    return -1;
  }, [meeting, currentTime]);

  // Keep the active utterance in view while playing.
  useEffect(() => {
    if (playing && activeIdx >= 0 && listRef.current) {
      try {
        listRef.current.scrollToIndex({ index: activeIdx, viewPosition: 0.4, animated: true });
      } catch { /* index not measured yet */ }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIdx, playing]);

  if (!meeting) {
    return (
      <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
        <Pressable onPress={onBack} hitSlop={12} style={({ pressed }) => [styles.backBtn, pressed && pressedStyle]}>
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </Pressable>
      </View>
    );
  }

  const hasAudio = !!meeting.audioUrl;

  const togglePlay = () => {
    try {
      if (playing) player.pause();
      else player.play();
    } catch { /* audio is best-effort */ }
  };

  const seekTo = (secs: number) => {
    try {
      player.seekTo(Math.max(0, secs));
      if (!playing) player.play();
    } catch { /* ignore */ }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} style={({ pressed }) => [styles.backBtn, pressed && pressedStyle]}>
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text variant="metaSm" color={colors.textMuted}>TRANSCRIPT</Text>
          <Text variant="subtitle" numberOfLines={1}>{meeting.title}</Text>
        </View>
      </View>

      <FlatList
        ref={listRef}
        data={meeting.transcript}
        keyExtractor={(_, i) => String(i)}
        onScrollToIndexFailed={() => {}}
        contentContainerStyle={{ paddingBottom: insets.bottom + 140 }}
        ListEmptyComponent={
          <Text variant="bodyXs" color={colors.textMuted} style={{ marginTop: 24, textAlign: 'center' }}>
            This meeting has no transcript.
          </Text>
        }
        renderItem={({ item, index }) => {
          const active = index === activeIdx && playing;
          return (
            <Pressable
              style={({ pressed }) => [styles.utt, active && styles.uttActive, pressed && pressedStyle]}
              onPress={() => hasAudio && seekTo(item.t0)}
            >
              <View style={styles.uttHead}>
                <Text variant="metaSm" color={item.speaker === 'self' ? '#e6c890' : colors.primaryAccent}>
                  {meeting.speakers[item.speaker] || item.speaker}
                </Text>
                <Text variant="metaSm" color={colors.textSubtle}>{fmtT(item.t0)}</Text>
              </View>
              <Text variant="bodyXs" color={active ? colors.textPrimary : colors.textSecondary}
                style={{ lineHeight: 20 }}>
                {item.text}
              </Text>
            </Pressable>
          );
        }}
      />

      {hasAudio && urlError && (
        <View style={[styles.playerBar, { bottom: insets.bottom + 20 }]}>
          <Ionicons name="alert-circle-outline" size={18} color={colors.primaryAccent} />
          <Text variant="metaSm" color={colors.textMuted} style={{ flex: 1 }}>
            Couldn't load the audio — the transcript is above.
          </Text>
          <Pressable
            onPress={() => setResolveNonce((n) => n + 1)}
            hitSlop={8}
            style={({ pressed }) => pressed && pressedStyle}
            accessibilityRole="button"
            accessibilityLabel="Retry loading audio"
          >
            <Text variant="metaSm" color={colors.textPrimary}>RETRY</Text>
          </Pressable>
        </View>
      )}

      {hasAudio && !urlError && (
        <View style={[styles.playerBar, { bottom: insets.bottom + 20 }]}>
          <Pressable
            style={({ pressed }) => [styles.playBtn, pressed && pressedStyle, !signedUrl && { opacity: 0.5 }]}
            disabled={!signedUrl}
            onPress={togglePlay}
          >
            <Ionicons name={playing ? 'pause' : 'play'} size={20} color={colors.primaryInk} />
          </Pressable>
          <Text variant="metaSm" color={colors.textPrimary}>
            {fmtT(currentTime)} / {fmtT(meeting.durationSeconds)}
          </Text>
          <View style={styles.progress}>
            <View
              style={[styles.progressFill,
                { width: `${Math.min(100, (currentTime / Math.max(1, meeting.durationSeconds)) * 100)}%` }]}
            />
          </View>
        </View>
      )}
      {/* MER-31: audio was reaped by the retention policy — transcript above is
          still intact, only playback is gone. Never an error state. */}
      {!hasAudio && meeting.audioExpired && (
        <View style={[styles.playerBar, { bottom: insets.bottom + 20, justifyContent: 'center' }]}>
          <Text variant="metaSm" color={colors.textMuted}>Audio expired — transcript kept</Text>
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bgScreen, paddingHorizontal: 20 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 },
  backBtn: {
    width: 36, height: 36, borderRadius: radius.pill, backgroundColor: colors.surface2,
    alignItems: 'center', justifyContent: 'center',
  },
  utt: { paddingVertical: 8, paddingHorizontal: 10, borderRadius: radius.sm, marginBottom: 4 },
  uttActive: { backgroundColor: colors.primarySoft },
  uttHead: { flexDirection: 'row', gap: 8, marginBottom: 2, alignItems: 'baseline' },
  playerBar: {
    position: 'absolute', left: 20, right: 20, flexDirection: 'row', alignItems: 'center',
    gap: 12, backgroundColor: colors.surface1, borderWidth: 1, borderColor: colors.borderDefault,
    borderRadius: radius.pill, paddingHorizontal: 14, paddingVertical: 10,
  },
  playBtn: {
    width: 38, height: 38, borderRadius: radius.pill, backgroundColor: colors.inkLight,
    alignItems: 'center', justifyContent: 'center',
  },
  progress: {
    flex: 1, height: 4, borderRadius: 999, backgroundColor: colors.surface3, overflow: 'hidden',
  },
  progressFill: { height: '100%', backgroundColor: colors.primary, borderRadius: 999 },
});

export default MeetingPlaybackScreen;
