/**
 * MeetingLiveScreen — watch a meeting being captured on the Mac, LIVE, from the
 * phone. The desktop pushes transcript chunks to the row every few seconds; we
 * subscribe to row UPDATEs (realtime) and stream them in. Two modes toggled by a
 * segmented control that slides between them:
 *   Transcript — auto-scrolling live transcript with speaker chips
 *   Notes      — your scratchpad, synced back to the meeting (debounced)
 *
 * Read-only capture (mobile never records) but the notes pad is a real write.
 * Falls back to the finished view once the meeting is no longer live.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, StyleSheet, Pressable, ScrollView, TextInput, Animated,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text } from '../components';
import { colors, radius, fonts } from '../theme';
import { fetchMeeting, updateScratchpadRemote, subscribeMeetings, isLiveNow } from '../../lib/meetings';
import type { Meeting } from '../../lib/meetings';
import { getUserId } from '../../lib/storage';

type Props = { meetingId: string; onBack: () => void; onFinished: (id: string) => void };

const PAL = ['#D98A72', '#8FA7C2', '#A9BD98', '#D9B36B'];
const dotFor = (sid: string, i: number) => (sid === 'self' ? '#D9B36B' : PAL[i % PAL.length]);

function fmtElapsed(s: number): string {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = Math.floor(s % 60);
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}`
           : `${m}:${String(x).padStart(2, '0')}`;
}

export const MeetingLiveScreen: React.FC<Props> = ({ meetingId, onBack, onFinished }) => {
  const insets = useSafeAreaInsets();
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [tab, setTab] = useState<'transcript' | 'notes'>('transcript');
  const [segW, setSegW] = useState(0);
  const [pad, setPad] = useState('');
  const padEdited = useRef(false);
  const scroller = useRef<ScrollView>(null);
  const padTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // segmented-control slide
  const slide = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.spring(slide, { toValue: tab === 'transcript' ? 0 : 1, useNativeDriver: true, speed: 20, bounciness: 6 }).start();
  }, [tab, slide]);

  // recording pulse
  const pulse = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(pulse, { toValue: 0.3, duration: 700, useNativeDriver: true }),
      Animated.timing(pulse, { toValue: 1, duration: 700, useNativeDriver: true }),
    ]));
    loop.start();
    return () => loop.stop();
  }, [pulse]);

  const load = useCallback(async () => {
    const m = await fetchMeeting(meetingId);
    if (m) {
      setMeeting(m);
      if (!padEdited.current) setPad(m.scratchpad || '');
      if (!isLiveNow(m) && m.status !== 'processing') onFinished(meetingId);
    }
  }, [meetingId, onFinished]);

  useEffect(() => {
    load();
    let dispose = () => {};
    (async () => {
      const uid = await getUserId();
      if (uid) dispose = subscribeMeetings(uid, load);
    })();
    return () => dispose();
  }, [load]);

  // Fallback poll while the meeting is live: realtime UPDATEs are the fast path, but
  // a dropped socket / flaky mobile network shouldn't freeze the transcript. Refetch
  // every few seconds until the meeting ends (then this effect tears the timer down).
  const live = meeting ? isLiveNow(meeting) : false;
  useEffect(() => {
    if (!live) return;
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [live, load]);

  // local ticking elapsed between server pushes (feels live, not steppy)
  const [nowTick, setNowTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setNowTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);
  const elapsed = useMemo(() => {
    if (!meeting) return 0;
    const base = meeting.durationSeconds || 0;
    const since = (Date.now() - new Date(meeting.updatedAt).getTime()) / 1000;
    return isLiveNow(meeting) ? base + Math.max(0, Math.min(since, 30)) : base;
  }, [meeting, nowTick]);

  // auto-scroll transcript to newest
  const uttCount = meeting?.transcript.length ?? 0;
  useEffect(() => {
    if (tab === 'transcript') {
      requestAnimationFrame(() => scroller.current?.scrollToEnd({ animated: true }));
    }
  }, [uttCount, tab]);

  const onPad = (t: string) => {
    padEdited.current = true;
    setPad(t);
    if (padTimer.current) clearTimeout(padTimer.current);
    padTimer.current = setTimeout(() => updateScratchpadRemote(meetingId, t), 700);
  };

  const speakerName = (sid: string) => meeting?.speakers[sid] || (sid === 'self' ? 'You' : sid);
  const speakerIdx = (sid: string) => Object.keys(meeting?.speakers || {}).indexOf(sid);

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={0}
    >
      <View style={{ paddingTop: insets.top + 8, paddingHorizontal: 20, flex: 1 }}>
        {/* header */}
        <View style={styles.header}>
          <Pressable onPress={onBack} hitSlop={12} style={styles.backBtn}>
            <Ionicons name="chevron-down" size={22} color={colors.textPrimary} />
          </Pressable>
          <View style={{ flex: 1, minWidth: 0 }}>
            <View style={styles.recRow}>
              {live ? (
                <>
                  <Animated.View style={[styles.recDot, { opacity: pulse }]} />
                  <Text variant="metaSm" color={colors.primaryAccent} style={styles.recTxt}>
                    LIVE · REC
                  </Text>
                </>
              ) : (
                <Text variant="metaSm" color={colors.textMuted}>
                  {meeting?.status === 'processing' ? 'FINISHING…' : 'ENDED'}
                </Text>
              )}
              <Text variant="metaSm" color={colors.textMuted} style={styles.timer}>
                {fmtElapsed(elapsed)}
              </Text>
            </View>
            <Text variant="subtitle" numberOfLines={1}>{meeting?.title ?? 'Meeting'}</Text>
          </View>
        </View>

        {/* source note */}
        <Text variant="metaSm" color={colors.textSubtle} style={{ marginBottom: 10 }}>
          {live
            ? `Recording on ${meeting?.deviceName || 'your Mac'} — following along live`
            : 'This meeting has ended.'}
        </Text>

        {/* segmented control */}
        <View style={styles.segment}
          onLayout={(e) => setSegW(e.nativeEvent.layout.width - 6)}>
          <Animated.View style={[styles.segThumb, { width: segW / 2 }, {
            transform: [{ translateX: slide.interpolate({ inputRange: [0, 1], outputRange: [0, segW / 2] }) }],
          }]} />
          <Pressable style={styles.segBtn} onPress={() => setTab('transcript')}>
            <Text variant="buttonSm" color={tab === 'transcript' ? colors.primaryInk : colors.textMuted}
              style={{ fontFamily: fonts.semibold }}>Transcript</Text>
          </Pressable>
          <Pressable style={styles.segBtn} onPress={() => setTab('notes')}>
            <Text variant="buttonSm" color={tab === 'notes' ? colors.primaryInk : colors.textMuted}
              style={{ fontFamily: fonts.semibold }}>Notes</Text>
          </Pressable>
        </View>

        {/* body */}
        {tab === 'transcript' ? (
          <ScrollView
            ref={scroller}
            style={{ flex: 1 }}
            contentContainerStyle={{ paddingBottom: insets.bottom + 20, paddingTop: 6 }}
            showsVerticalScrollIndicator={false}
          >
            {uttCount === 0 ? (
              <View style={styles.emptyLive}>
                <View style={styles.listenWave}>
                  {[0, 1, 2, 3, 4].map((i) => <WaveBar key={i} delay={i * 120} />)}
                </View>
                <Text variant="bodyXs" color={colors.textMuted} style={{ marginTop: 14 }}>
                  {live ? 'Listening — the transcript appears as people speak…' : 'No transcript.'}
                </Text>
              </View>
            ) : (
              meeting!.transcript.map((u, i) => (
                <View key={i} style={styles.utt}>
                  <View style={styles.uttHead}>
                    <View style={[styles.dot, { backgroundColor: dotFor(u.speaker, speakerIdx(u.speaker)) }]} />
                    <Text variant="metaSm" style={{ fontFamily: fonts.semibold }}>{speakerName(u.speaker)}</Text>
                    <Text variant="metaSm" color={colors.textSubtle}>{fmtElapsed(u.t0)}</Text>
                  </View>
                  <Text variant="bodyXs" color={colors.textSecondary} style={styles.uttBody}>{u.text}</Text>
                </View>
              ))
            )}
            {live && uttCount > 0 && (
              <View style={styles.streamingRow}>
                <WaveBar delay={0} /><WaveBar delay={120} /><WaveBar delay={240} />
              </View>
            )}
          </ScrollView>
        ) : (
          <View style={{ flex: 1 }}>
            <Text variant="metaSm" color={colors.textSubtle} style={{ marginBottom: 8 }}>
              Your private notes — synced to the Mac as you type.
            </Text>
            <TextInput
              style={styles.pad}
              value={pad}
              onChangeText={onPad}
              placeholder="Jot down what matters — decisions, follow-ups, questions…"
              placeholderTextColor={colors.textDisabled}
              multiline
              autoCorrect
              scrollEnabled
            />
          </View>
        )}
      </View>
    </KeyboardAvoidingView>
  );
};

function WaveBar({ delay }: { delay: number }) {
  const h = useRef(new Animated.Value(0.3)).current;
  useEffect(() => {
    const loop = Animated.loop(Animated.sequence([
      Animated.delay(delay),
      Animated.timing(h, { toValue: 1, duration: 400, useNativeDriver: false }),
      Animated.timing(h, { toValue: 0.3, duration: 400, useNativeDriver: false }),
    ]));
    loop.start();
    return () => loop.stop();
  }, [h, delay]);
  return (
    <Animated.View style={{
      width: 3, marginHorizontal: 2, borderRadius: 2, backgroundColor: colors.primary,
      height: h.interpolate({ inputRange: [0, 1], outputRange: [5, 20] }),
    }} />
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bgScreen },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 6 },
  backBtn: {
    width: 36, height: 36, borderRadius: radius.pill, backgroundColor: colors.surface2,
    alignItems: 'center', justifyContent: 'center',
  },
  recRow: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  recDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#E05049' },
  recTxt: { letterSpacing: 1.4 },
  timer: { marginLeft: 'auto', fontFamily: fonts.mono },
  segment: {
    flexDirection: 'row', backgroundColor: colors.surface1, borderRadius: radius.pill,
    padding: 3, marginBottom: 12, position: 'relative',
  },
  segThumb: {
    position: 'absolute', top: 3, left: 3, bottom: 3,
    backgroundColor: colors.inkLight, borderRadius: radius.pill,
  },
  segBtn: { flex: 1, alignItems: 'center', paddingVertical: 8, zIndex: 1 },
  utt: { marginBottom: 16 },
  uttHead: { flexDirection: 'row', alignItems: 'center', gap: 7, marginBottom: 4 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  uttBody: { lineHeight: 20 },
  emptyLive: { alignItems: 'center', justifyContent: 'center', paddingVertical: 60 },
  listenWave: { flexDirection: 'row', alignItems: 'center', height: 24 },
  streamingRow: { flexDirection: 'row', alignItems: 'center', height: 20, marginTop: 4, opacity: 0.7 },
  pad: {
    flex: 1, color: colors.textPrimary, fontFamily: fonts.regular, fontSize: 15, lineHeight: 22,
    textAlignVertical: 'top', backgroundColor: colors.surface1, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.borderSubtle, padding: 14,
  },
});

export default MeetingLiveScreen;
