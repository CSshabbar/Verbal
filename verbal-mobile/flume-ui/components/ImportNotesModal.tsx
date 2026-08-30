import React, { useMemo, useState } from 'react';
import { View, StyleSheet, Modal, Pressable, TextInput, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Text } from './Text';
import { colors, radius, pressedStyle } from '../theme';
import { useMeetings, Meeting } from '../hooks/useMeetings';
import { useHistory } from '../hooks/useHistory';
import type { HistoryItem } from '../hooks/historyStore';

/**
 * ImportNotesModal (Notes v3.2) — pick a meeting or a past transcription and
 * turn it into a note. Mirrors the desktop import picker: one tap = one note;
 * content is composed CLIENT-side as markdown and handed back via onImport —
 * the screen owns note creation/navigation. A JS <Modal> is fine here: the
 * host (NotesListScreen) is a tab screen, not a native-stack modal
 * (Hard Rule #14 only bans this inside native-stack modals).
 */

type Props = {
  visible: boolean;
  onClose: () => void;
  onImport: (data: { title: string; body: string }) => void;
};

const firstWords = (t: string, n = 5) => t.trim().split(/\s+/).slice(0, n).join(' ');

/** Compose a note from a meeting — same shape as the desktop importMeeting. */
export function meetingToNote(m: Meeting): { title: string; body: string } {
  const lines: string[] = [];
  if ((m.summary || '').trim()) lines.push(m.summary.trim());
  if (m.decisions.length) {
    lines.push('', '## Decisions');
    m.decisions.forEach(d => lines.push(`- ${d}`));
  }
  if (m.actionItems.length) {
    lines.push('', '## Action items');
    m.actionItems.forEach(it => {
      const owner = it.owner && m.speakers[it.owner] ? ` — **${m.speakers[it.owner]}**` : '';
      const due = it.due ? ` (due ${it.due})` : '';
      lines.push(`- [${it.done ? 'x' : ' '}] ${it.task}${owner}${due}`);
    });
  }
  if (!lines.length) {
    const t = m.transcript.map(s => s.text).join(' ').trim();
    if (t) lines.push(t);
  }
  lines.push('', `*Imported from the meeting “${m.title || 'Meeting'}” · ${(m.startedAt || '').slice(0, 10)}*`);
  return { title: m.title || 'Meeting', body: lines.join('\n').trim() };
}

/** Compose a note from a history transcription. */
export function historyToNote(h: HistoryItem): { title: string; body: string } {
  const t = (h.text || '').trim();
  return {
    title: firstWords(t) || 'Untitled',
    body: `${t}\n\n*Imported from dictation · ${h.dayLabel} ${h.timeOfDay}*`,
  };
}

export const ImportNotesModal: React.FC<Props> = ({ visible, onClose, onImport }) => {
  const [tab, setTab] = useState<'meetings' | 'hist'>('meetings');
  const [query, setQuery] = useState('');
  const { meetings } = useMeetings();
  const { items } = useHistory();

  const q = query.trim().toLowerCase();
  const meetingRows = useMemo(() => {
    let ms = meetings.filter(m => m.status !== 'processing');
    if (q) ms = ms.filter(m => `${m.title} ${m.summary}`.toLowerCase().includes(q));
    return ms;
  }, [meetings, q]);
  const histRows = useMemo(() => {
    let hs = items.filter(h => h.status !== 'failed' && (h.text || '').trim());
    if (q) hs = hs.filter(h => h.text.toLowerCase().includes(q));
    return hs.slice(0, 120);
  }, [items, q]);

  const close = () => { setQuery(''); setTab('meetings'); onClose(); };
  const pick = (data: { title: string; body: string }) => { setQuery(''); setTab('meetings'); onImport(data); };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={close}>
      <View style={styles.backdrop}>
        <Pressable style={{ flex: 1 }} onPress={close} accessibilityRole="button" accessibilityLabel="Close import" />
        <View style={styles.sheet}>
          <View style={styles.head}>
            <Text variant="titleSm" style={{ fontSize: 17 }}>Import into Notes</Text>
            <Pressable onPress={close} hitSlop={8} style={({ pressed }) => pressed && pressedStyle} accessibilityRole="button" accessibilityLabel="Close">
              <Ionicons name="close" size={20} color={colors.textSecondary} />
            </Pressable>
          </View>
          <View style={styles.tabs}>
            <TabPill label="Meetings" active={tab === 'meetings'} onPress={() => setTab('meetings')} />
            <TabPill label="Transcriptions" active={tab === 'hist'} onPress={() => setTab('hist')} />
          </View>
          <View style={styles.search}>
            <Ionicons name="search-outline" size={15} color={colors.textMuted} />
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder={tab === 'meetings' ? 'Search meetings…' : 'Search transcriptions…'}
              placeholderTextColor={colors.textSubtle}
              style={styles.searchInput}
              autoCorrect={false}
              accessibilityLabel="Search"
            />
          </View>
          <ScrollView style={{ flexGrow: 0 }} contentContainerStyle={{ paddingBottom: 8 }} keyboardShouldPersistTaps="handled">
            {tab === 'meetings' ? (
              meetingRows.length === 0 ? (
                <Text variant="bodySm" color={colors.textSubtle} align="center" style={styles.empty}>
                  {q ? 'No meetings match.' : 'No meetings yet — capture one on your Mac first.'}
                </Text>
              ) : meetingRows.map(m => (
                <Row
                  key={m.id}
                  icon="people-outline"
                  title={m.title || 'Meeting'}
                  meta={`${m.dateLabel} · ${Math.max(1, Math.round(m.durationSeconds / 60))} min`}
                  onPress={() => pick(meetingToNote(m))}
                />
              ))
            ) : histRows.length === 0 ? (
              <Text variant="bodySm" color={colors.textSubtle} align="center" style={styles.empty}>
                {q ? 'No transcriptions match.' : 'No transcriptions yet — dictate something first.'}
              </Text>
            ) : histRows.map(h => (
              <Row
                key={h.id}
                icon="mic-outline"
                title={firstWords(h.text)}
                meta={`${h.dayLabel} · ${h.wordCount} words`}
                onPress={() => pick(historyToNote(h))}
              />
            ))}
          </ScrollView>
          <Text variant="caption" color={colors.textSubtle} style={styles.hint}>
            {tab === 'meetings'
              ? 'A meeting becomes a note with its summary, decisions and action-item checklist.'
              : 'A transcription becomes a note with its text — reformat it afterwards if you like.'}
          </Text>
        </View>
      </View>
    </Modal>
  );
};

const TabPill: React.FC<{ label: string; active: boolean; onPress: () => void }> = ({ label, active, onPress }) => (
  <Pressable
    onPress={onPress}
    style={({ pressed }) => [styles.tab, active && styles.tabOn, pressed && pressedStyle]}
    accessibilityRole="button"
    accessibilityState={{ selected: active }}
    accessibilityLabel={label}
  >
    <Text variant="buttonSm" color={active ? colors.primary : colors.textSecondary}>{label}</Text>
  </Pressable>
);

const Row: React.FC<{ icon: any; title: string; meta: string; onPress: () => void }> = ({ icon, title, meta, onPress }) => (
  <Pressable
    onPress={onPress}
    style={({ pressed }) => [styles.row, pressed && pressedStyle]}
    accessibilityRole="button"
    accessibilityLabel={`Import ${title}`}
  >
    <View style={styles.rowDisc}>
      <Ionicons name={icon} size={14} color={colors.textMuted} />
    </View>
    <View style={{ flex: 1, minWidth: 0 }}>
      <Text variant="label" numberOfLines={1}>{title}</Text>
      <Text variant="caption" color={colors.textSubtle} numberOfLines={1}>{meta}</Text>
    </View>
    <Ionicons name="download-outline" size={16} color={colors.primary} />
  </Pressable>
);

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(6,7,8,0.62)', justifyContent: 'flex-end' },
  sheet: {
    maxHeight: '78%',
    backgroundColor: colors.bgScreen,
    borderTopLeftRadius: 22, borderTopRightRadius: 22,
    borderWidth: 1, borderColor: colors.borderSubtle,
    paddingHorizontal: 16, paddingTop: 14,
  },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  tabs: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  tab: {
    paddingVertical: 8, paddingHorizontal: 15, borderRadius: 999,
    borderWidth: 1, borderColor: colors.borderStrong, backgroundColor: 'transparent',
  },
  tabOn: { backgroundColor: colors.primarySoft, borderColor: colors.primaryBorder },
  search: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: colors.surface2, borderRadius: 999,
    borderWidth: 1, borderColor: colors.borderSubtle,
    paddingHorizontal: 14, marginBottom: 10,
  },
  searchInput: { flex: 1, color: colors.textPrimary, paddingVertical: 10, fontFamily: 'Geist_400Regular', fontSize: 14 },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 11,
    paddingVertical: 10, paddingHorizontal: 8, borderRadius: radius.md,
  },
  rowDisc: {
    width: 32, height: 32, borderRadius: 16, backgroundColor: colors.surface2,
    alignItems: 'center', justifyContent: 'center',
  },
  empty: { paddingVertical: 26 },
  hint: { paddingVertical: 12, textAlign: 'center' },
});

export default ImportNotesModal;
