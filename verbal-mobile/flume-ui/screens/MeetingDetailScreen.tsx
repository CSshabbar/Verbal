/**
 * MeetingDetailScreen — read-only meeting summary (31e, mobile) with ONE
 * editable element: the user scratchpad, which syncs back to the desktop.
 * No regenerate / no capture controls on mobile (by design).
 */
import React, { useState, useEffect } from 'react';
import { View, StyleSheet, Pressable, ScrollView, TextInput, KeyboardAvoidingView, Platform } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text } from '../components';
import { colors, radius, fonts, pressedStyle } from '../theme';
import { useMeetings } from '../hooks/useMeetings';
import { updateActionItemsRemote } from '../../lib/meetings';

type Props = {
  meetingId: string;
  onBack: () => void;
  onOpenPlayback: (meetingId: string) => void;
  onOpenNotes: (meetingId: string) => void;
};

const CHIP_COLORS = [colors.primarySoft, 'rgba(74,100,148,0.25)', 'rgba(221,228,211,0.16)', 'rgba(199,154,74,0.2)'];
const CHIP_INK = [colors.primaryAccent, '#a9c2e8', '#cfdac2', '#e6c890'];

function chipStyle(sid: string) {
  if (sid === 'self') return { bg: 'rgba(199,154,74,0.2)', ink: '#e6c890' };
  const n = parseInt(sid.replace(/[^0-9]/g, ''), 10) || 1;
  return { bg: CHIP_COLORS[(n - 1) % 4], ink: CHIP_INK[(n - 1) % 4] };
}

function fmtDur(secs: number): string {
  const m = Math.floor(secs / 60);
  return `${m}:${String(Math.floor(secs % 60)).padStart(2, '0')}`;
}

export const MeetingDetailScreen: React.FC<Props> = ({ meetingId, onBack, onOpenPlayback, onOpenNotes }) => {
  const insets = useSafeAreaInsets();
  const { getMeeting, updateScratchpad } = useMeetings();
  const meeting = getMeeting(meetingId);
  const [pad, setPad] = useState(meeting?.scratchpad ?? '');
  const [items, setItems] = useState(meeting?.actionItems ?? []);

  useEffect(() => {
    if (meeting) setItems(meeting.actionItems);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meeting?.id, meeting?.actionItems?.length]);

  const toggleItem = (idx: number) => {
    if (!meeting) return;
    const next = items.map((it, i) => (i === idx ? { ...it, done: !it.done } : it));
    setItems(next);
    updateActionItemsRemote(meeting.id, next);   // full loaded list — never partial
  };

  useEffect(() => {
    // Adopt the loaded value once the row arrives (list may hydrate after mount).
    if (meeting && pad === '' && meeting.scratchpad) setPad(meeting.scratchpad);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meeting?.id]);

  if (!meeting) {
    return (
      <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
        <Pressable onPress={onBack} hitSlop={12} style={({ pressed }) => [styles.backBtn, pressed && pressedStyle]}>
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </Pressable>
        <View style={styles.center}>
          <Text variant="bodyXs" color={colors.textMuted}>Meeting not found.</Text>
        </View>
      </View>
    );
  }

  const onPadChange = (t: string) => {
    setPad(t);
    updateScratchpad(meeting.id, t);
  };

  const speakers = Object.entries(meeting.speakers);

  return (
    <KeyboardAvoidingView
      style={[styles.container, { paddingTop: insets.top + 8 }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} style={({ pressed }) => [styles.backBtn, pressed && pressedStyle]}>
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text variant="metaSm" color={colors.textMuted}>
            MEETING · {meeting.dateLabel.toUpperCase()}
          </Text>
          <Text variant="subtitle" numberOfLines={1}>{meeting.title}</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 90, gap: 12 }}
        showsVerticalScrollIndicator={false}>
        {/* meta */}
        <View style={styles.metaRow}>
          <Text variant="metaSm" color={colors.textMuted}>{fmtDur(meeting.durationSeconds)}</Text>
          {speakers.map(([sid, name]) => {
            const c = chipStyle(sid);
            return (
              <View key={sid} style={[styles.chip, { backgroundColor: c.bg }]}>
                <Text variant="metaSm" color={c.ink}>{name}</Text>
              </View>
            );
          })}
        </View>

        {/* summary */}
        <View style={styles.card}>
          <Text variant="metaSm" color={colors.primary}>SUMMARY</Text>
          {meeting.status === 'processing' ? (
            <Text variant="bodyXs" color={colors.textMuted} style={{ marginTop: 6 }}>
              Summarizing on your Mac…
            </Text>
          ) : meeting.status === 'failed' ? (
            <Text variant="bodyXs" color={colors.textMuted} style={{ marginTop: 6 }}>
              Summary failed — retry it from the desktop app. The transcript is saved.
            </Text>
          ) : (
            <Text variant="bodyXs" style={{ marginTop: 6, lineHeight: 20 }}>
              {meeting.summary || 'No speech was detected in this meeting.'}
            </Text>
          )}
        </View>

        {/* full AI notes page */}
        <Pressable style={({ pressed }) => [styles.notesBtn, pressed && pressedStyle]} onPress={() => onOpenNotes(meeting.id)}>
          <Ionicons name="document-text-outline" size={16} color={colors.primaryAccent} />
          <View style={{ flex: 1 }}>
            <Text variant="label">Meeting notes</Text>
            <Text variant="metaSm" color={colors.textMuted}>
              {meeting.notesMd ? 'Full AI notes of this meeting' : 'Generate the full AI notes'}
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={colors.textSubtle} />
        </Pressable>

        {/* notes — hybrid render + the ONE editable field */}
        <View style={styles.card}>
          <View style={styles.cardHeadRow}>
            <Text variant="metaSm" color={colors.textMuted}>YOUR NOTES</Text>
            <Text variant="metaSm" color={colors.textSubtle}>SYNCS TO MAC</Text>
          </View>
          {meeting.hybridNotes.length > 0 ? (
            meeting.hybridNotes.map((h, i) => (
              <View key={i} style={styles.hybridRow}>
                <Text variant="bodyXs">{h.user_line}</Text>
                {!!h.ai_addition && (
                  <Text variant="bodyXs" color={colors.textMuted} style={styles.aiLine}>
                    → {h.ai_addition}
                  </Text>
                )}
              </View>
            ))
          ) : null}
          <TextInput
            style={styles.padInput}
            value={pad}
            onChangeText={onPadChange}
            placeholder="Add or edit your notes…"
            placeholderTextColor={colors.textDisabled}
            multiline
          />
        </View>

        {/* decisions */}
        <View style={styles.card}>
          <Text variant="metaSm" color={colors.primary}>DECISIONS</Text>
          {meeting.decisions.length ? meeting.decisions.map((d, i) => (
            <Text key={i} variant="bodyXs" style={styles.bullet}>•  {d}</Text>
          )) : (
            <Text variant="bodyXs" color={colors.textMuted} style={{ marginTop: 6 }}>
              No explicit decisions found.
            </Text>
          )}
        </View>

        {/* action items */}
        <View style={styles.card}>
          <Text variant="metaSm" color={colors.primary}>ACTION ITEMS</Text>
          {items.length ? items.map((it, i) => {
            const name = it.owner ? meeting.speakers[it.owner] : null;
            const c = it.owner ? chipStyle(it.owner) : null;
            return (
              <Pressable key={i} style={({ pressed }) => [styles.aiRow, pressed && pressedStyle]} onPress={() => toggleItem(i)}>
                <View style={[styles.checkbox, it.done && styles.checkboxOn]}>
                  {it.done && <Ionicons name="checkmark" size={11} color="#0a1f0d" />}
                </View>
                {name && c ? (
                  <View style={[styles.chip, { backgroundColor: c.bg }]}>
                    <Text variant="metaSm" color={c.ink}>{name}</Text>
                  </View>
                ) : (
                  <View style={[styles.chip, { backgroundColor: colors.surface2 }]}>
                    <Text variant="metaSm" color={colors.textMuted}>?</Text>
                  </View>
                )}
                <Text variant="bodyXs"
                  style={[{ flex: 1 }, it.done && styles.doneTask]}>{it.task}</Text>
                {!!it.due && (
                  <Text variant="metaSm" color={colors.primaryAccent}>{String(it.due).toUpperCase()}</Text>
                )}
              </Pressable>
            );
          }) : (
            <Text variant="bodyXs" color={colors.textMuted} style={{ marginTop: 6 }}>
              No action items found.
            </Text>
          )}
        </View>

        {/* marked moments */}
        {meeting.markedMoments.length > 0 && (
          <View style={styles.card}>
            <Text variant="metaSm" color={colors.primary}>★ MARKED MOMENTS</Text>
            {meeting.markedMoments.map((m, i) => (
              <View key={i} style={{ marginTop: 10 }}>
                <View style={styles.aiRow0}>
                  <Text variant="metaSm" color={colors.primaryAccent}>{fmtDur(m.t)}</Text>
                  <Text variant="bodyXs" style={{ flex: 1 }}>{m.label || 'Marked moment'}</Text>
                </View>
                {!!m.note && (
                  <Text variant="metaSm" color={colors.textMuted} style={styles.markNote}>
                    YOUR NOTE — {m.note}
                  </Text>
                )}
              </View>
            ))}
          </View>
        )}

        {/* playback */}
        <Pressable
          style={({ pressed }) => [styles.playBtn, pressed && pressedStyle, !meeting.audioUrl && !meeting.transcript.length && { opacity: 0.4 }]}
          disabled={!meeting.audioUrl && !meeting.transcript.length}
          onPress={() => onOpenPlayback(meeting.id)}
        >
          <Ionicons name="play" size={16} color={colors.primaryInk} />
          <Text variant="buttonSm" color={colors.primaryInk} style={{ fontFamily: fonts.semibold }}>
            {meeting.audioUrl ? 'Play with transcript' : 'View transcript'}
          </Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bgScreen, paddingHorizontal: 20 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 },
  backBtn: {
    width: 36, height: 36, borderRadius: radius.pill, backgroundColor: colors.surface2,
    alignItems: 'center', justifyContent: 'center',
  },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  chip: { borderRadius: radius.xs, paddingHorizontal: 8, paddingVertical: 3 },
  card: {
    backgroundColor: colors.surface1, borderRadius: radius.md, borderWidth: 1,
    borderColor: colors.borderSubtle, padding: 14,
  },
  cardHeadRow: { flexDirection: 'row', justifyContent: 'space-between' },
  hybridRow: {
    borderLeftWidth: 2, borderLeftColor: colors.primary, paddingLeft: 10, marginTop: 10,
  },
  aiLine: { fontStyle: 'italic', marginTop: 2 },
  padInput: {
    color: colors.textPrimary, fontFamily: fonts.regular, fontSize: 15, lineHeight: 21,
    marginTop: 10, minHeight: 60, textAlignVertical: 'top',
    borderTopWidth: 1, borderTopColor: colors.borderSubtle, paddingTop: 10,
  },
  bullet: { marginTop: 8, lineHeight: 20 },
  aiRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10 },
  aiRow0: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  checkbox: {
    width: 17, height: 17, borderRadius: 4, borderWidth: 1.4, borderColor: colors.textMuted,
    alignItems: 'center', justifyContent: 'center',
  },
  checkboxOn: { backgroundColor: '#7fae7a', borderColor: '#7fae7a' },
  doneTask: { textDecorationLine: 'line-through', color: colors.textMuted },
  markNote: { marginTop: 3, marginLeft: 44 },
  notesBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.surface1, borderRadius: radius.md, borderWidth: 1,
    borderColor: colors.borderSubtle, padding: 14,
  },
  playBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: colors.inkLight, borderRadius: radius.md, paddingVertical: 13,
  },
});

export default MeetingDetailScreen;
