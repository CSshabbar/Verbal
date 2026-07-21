/**
 * MeetingNotesScreen — the full AI meeting notes, beautifully rendered
 * (mirror of the desktop meeting window's Notes page). Read-first: shows the
 * cached `notes_md`; when absent the phone can generate them on-device via the
 * groq proxy (same MEETING_NOTES_SYSTEM prompt) and persists for every device.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { View, StyleSheet, Pressable, ScrollView, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text } from '../components';
import { colors, radius, fonts } from '../theme';
import { useMeetings } from '../hooks/useMeetings';
import { generateMeetingNotes } from '../../lib/groq';
import { updateNotesRemote } from '../../lib/meetings';

type Props = {
  meetingId: string;
  onBack: () => void;
};

const SPEAKER_DOT = '#D98A72';

/** Render **bold** and `code` spans inside one line. */
function Inline({ text, base }: { text: string; base?: object }) {
  const parts = useMemo(() => text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g), [text]);
  return (
    <Text variant="bodyXs" style={[{ lineHeight: 21 }, base as any]}>
      {parts.map((p, i) => {
        if (p.startsWith('**') && p.endsWith('**')) {
          return (
            <Text key={i} variant="bodyXs"
              style={{ fontFamily: fonts.semibold, lineHeight: 21 }}>
              {p.slice(2, -2)}
            </Text>
          );
        }
        if (p.startsWith('`') && p.endsWith('`')) {
          return (
            <Text key={i} variant="metaSm" style={styles.code}>{p.slice(1, -1)}</Text>
          );
        }
        return <Text key={i} variant="bodyXs" style={{ lineHeight: 21 }}>{p}</Text>;
      })}
    </Text>
  );
}

const isTableRow = (s: string) => /^\|.*\|\s*$/.test(s);
const isDivider = (s: string) => /^\|?[\s:|-]+\|[\s:|-]*$/.test(s) && s.indexOf('-') >= 0;
const rowCells = (s: string) =>
  s.replace(/^\||\|$/g, '').split('|').map((c) => c.trim());

/** Tiny GitHub-markdown renderer: ##/###, bullets, 1. lists, - [ ] tasks, tables. */
function MdView({ md }: { md: string }) {
  const lines = md.replace(/\r/g, '').split('\n');
  const out: React.ReactNode[] = [];
  let first = true;
  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].trim();
    if (!t) continue;
    let m;
    // Markdown table: header row + | --- | divider + body rows
    if (isTableRow(t) && i + 1 < lines.length && isDivider(lines[i + 1].trim())) {
      const header = rowCells(t);
      const body: string[][] = [];
      let j = i + 2;
      while (j < lines.length && isTableRow(lines[j].trim())) {
        body.push(rowCells(lines[j].trim()));
        j++;
      }
      out.push(
        <View key={i} style={styles.table}>
          <View style={styles.trHead}>
            {header.map((c, k) => (
              <View key={k} style={styles.cell}>
                <Text variant="metaSm" color={colors.primaryAccent} style={styles.th}>
                  {c.toUpperCase()}
                </Text>
              </View>
            ))}
          </View>
          {body.map((cells, r) => (
            <View key={r} style={[styles.tr, r === body.length - 1 && styles.trLast]}>
              {header.map((_, k) => (
                <View key={k} style={styles.cell}>
                  <Inline text={cells[k] ?? ''} />
                </View>
              ))}
            </View>
          ))}
        </View>,
      );
      first = false;
      i = j - 1;
      continue;
    }
    if ((m = t.match(/^##\s+(.+)$/))) {
      out.push(
        <Text key={i} variant="metaSm" color={colors.primaryAccent} style={styles.h2}>
          {m[1].toUpperCase()}
        </Text>,
      );
      first = false;
    } else if ((m = t.match(/^###\s+(.+)$/))) {
      out.push(
        <Text key={i} variant="label" style={{ marginTop: 12 }}>{m[1]}</Text>,
      );
    } else if ((m = t.match(/^- \[( |x|X)\]\s+(.+)$/))) {
      const done = m[1].toLowerCase() === 'x';
      out.push(
        <View key={i} style={styles.taskRow}>
          <View style={[styles.box, done && styles.boxDone]}>
            {done && <Ionicons name="checkmark" size={10} color="#0a1f0d" />}
          </View>
          <View style={{ flex: 1 }}>
            <Inline text={m[2]} base={done ? styles.strike : undefined} />
          </View>
        </View>,
      );
    } else if ((m = t.match(/^[-*]\s+(.+)$/))) {
      out.push(
        <View key={i} style={styles.liRow}>
          <View style={styles.dot} />
          <View style={{ flex: 1 }}><Inline text={m[1]} /></View>
        </View>,
      );
    } else if ((m = t.match(/^(\d+)[.)]\s+(.+)$/))) {
      out.push(
        <View key={i} style={styles.liRow}>
          <Text variant="metaSm" color={colors.textMuted} style={{ width: 18 }}>{m[1]}.</Text>
          <View style={{ flex: 1 }}><Inline text={m[2]} /></View>
        </View>,
      );
    } else {
      out.push(
        <View key={i} style={first ? styles.ctx : { marginTop: 8 }}>
          <Inline text={t} base={first ? { color: colors.textMuted } : undefined} />
        </View>,
      );
      first = false;
    }
  }
  return <View>{out}</View>;
}

export const MeetingNotesScreen: React.FC<Props> = ({ meetingId, onBack }) => {
  const insets = useSafeAreaInsets();
  const { getMeeting, refresh } = useMeetings();
  const meeting = getMeeting(meetingId);
  const [notes, setNotes] = useState<string | null>(meeting?.notesMd ?? null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (meeting?.notesMd && !notes) setNotes(meeting.notesMd);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meeting?.notesMd]);

  const generate = async () => {
    if (!meeting || busy) return;
    setBusy(true);
    setErr('');
    const md = await generateMeetingNotes(meeting);
    setBusy(false);
    if (md) {
      setNotes(md);
      updateNotesRemote(meeting.id, md).then(() => refresh());
    } else {
      setErr("Couldn't generate notes — check your connection and try again.");
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text variant="metaSm" color={colors.textMuted}>MEETING NOTES</Text>
          <Text variant="subtitle" numberOfLines={1}>{meeting?.title ?? 'Meeting'}</Text>
        </View>
      </View>

      {!meeting ? (
        <View style={styles.center}>
          <Text variant="bodyXs" color={colors.textMuted}>Meeting not found.</Text>
        </View>
      ) : notes ? (
        <ScrollView
          contentContainerStyle={{ paddingBottom: insets.bottom + 90 }}
          showsVerticalScrollIndicator={false}
        >
          <MdView md={notes} />
          <Pressable style={styles.regenBtn} disabled={busy} onPress={generate}>
            {busy
              ? <ActivityIndicator size="small" color={colors.textMuted} />
              : <Text variant="metaSm" color={colors.textMuted}>REGENERATE NOTES</Text>}
          </Pressable>
        </ScrollView>
      ) : (
        <View style={styles.center}>
          {busy ? (
            <>
              <ActivityIndicator color={colors.primary} />
              <Text variant="bodyXs" color={colors.textMuted} style={{ marginTop: 12 }}>
                Writing the notes…
              </Text>
            </>
          ) : (
            <>
              <Text variant="bodyXs" color={colors.textMuted} style={styles.emptyBody}>
                Full AI notes haven't been written for this meeting yet.
              </Text>
              {!!err && (
                <Text variant="bodyXs" color={colors.primaryAccent} style={{ marginTop: 8 }}>
                  {err}
                </Text>
              )}
              <Pressable style={styles.genBtn} onPress={generate}
                disabled={!meeting.transcript.length}>
                <Text variant="buttonSm" color={colors.primaryInk}
                  style={{ fontFamily: fonts.semibold }}>
                  Generate notes
                </Text>
              </Pressable>
              {!meeting.transcript.length && (
                <Text variant="metaSm" color={colors.textSubtle} style={{ marginTop: 8 }}>
                  No transcript on this meeting.
                </Text>
              )}
            </>
          )}
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
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24 },
  emptyBody: { textAlign: 'center', lineHeight: 20 },
  genBtn: {
    marginTop: 16, backgroundColor: colors.inkLight, borderRadius: radius.md,
    paddingVertical: 12, paddingHorizontal: 26,
  },
  regenBtn: {
    marginTop: 26, alignSelf: 'center', paddingVertical: 10, paddingHorizontal: 18,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.borderSubtle,
  },
  ctx: {
    borderLeftWidth: 2, borderLeftColor: colors.primary, paddingLeft: 12, marginBottom: 16,
  },
  h2: { marginTop: 20, marginBottom: 8, letterSpacing: 1.6 },
  liRow: { flexDirection: 'row', gap: 9, marginTop: 7, alignItems: 'flex-start' },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: SPEAKER_DOT, marginTop: 7 },
  taskRow: { flexDirection: 'row', gap: 9, marginTop: 8, alignItems: 'flex-start' },
  box: {
    width: 16, height: 16, borderRadius: 4, borderWidth: 1.4, borderColor: colors.textMuted,
    marginTop: 2, alignItems: 'center', justifyContent: 'center',
  },
  boxDone: { backgroundColor: '#7fae7a', borderColor: '#7fae7a' },
  strike: { textDecorationLine: 'line-through', color: colors.textMuted },
  code: {
    fontFamily: fonts.mono, backgroundColor: colors.surface2,
    paddingHorizontal: 4, borderRadius: 4,
  },
  table: { marginTop: 10, marginBottom: 16 },
  trHead: {
    flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: colors.borderStrong,
    paddingBottom: 7,
  },
  tr: {
    flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: colors.borderSubtle,
    paddingVertical: 8,
  },
  trLast: { borderBottomWidth: 0 },
  cell: { flex: 1, paddingRight: 10 },
  th: { letterSpacing: 1, lineHeight: 15 },
});

export default MeetingNotesScreen;
