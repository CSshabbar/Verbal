/**
 * MeetingListScreen — read-only list of meetings captured on the desktop
 * (MEETINGS_DESIGN_HANDOFF.md 31f, mobile). Mobile cannot start a meeting —
 * the empty state says so instead of erroring.
 */
import React, { useMemo } from 'react';
import { View, StyleSheet, Pressable, FlatList, ActivityIndicator, RefreshControl } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text } from '../components';
import { colors, radius } from '../theme';
import { useMeetings, Meeting } from '../hooks/useMeetings';

type Props = {
  onBack: () => void;
  onOpen: (meetingId: string) => void;
};

function groupLabel(m: Meeting): string {
  const d = new Date(m.startedAt);
  const now = new Date();
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86_400_000);
  if (diff <= 0) return 'Today';
  if (diff < 7) return 'This week';
  return 'Earlier';
}

function fmtDur(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

// v2 speaker dot palette (matches desktop widget kit): self=ochre, others cycle
const SPEAKER_PAL = ['#D98A72', '#8FA7C2', '#A9BD98', '#D9B36B'];
function speakerDot(sid: string, i: number): string {
  return sid === 'self' ? '#D9B36B' : SPEAKER_PAL[i % SPEAKER_PAL.length];
}

export const MeetingListScreen: React.FC<Props> = ({ onBack, onOpen }) => {
  const insets = useSafeAreaInsets();
  const { meetings, loading, refresh } = useMeetings();
  const [refreshing, setRefreshing] = React.useState(false);

  // widget kit v2 (33j compact-mobile): rows live inside ONE parent card per
  // group — group headers are eyebrows outside the cards.
  const groups = useMemo(() => {
    const out: Array<{ label: string; items: Meeting[] }> = [];
    for (const m of meetings) {
      const g = groupLabel(m);
      if (!out.length || out[out.length - 1].label !== g) out.push({ label: g, items: [] });
      out[out.length - 1].items.push(m);
    }
    return out;
  }, [meetings]);

  const onRefresh = async () => {
    setRefreshing(true);
    await refresh();
    setRefreshing(false);
  };

  const totalMin = Math.round(meetings.reduce((a, m) => a + m.durationSeconds, 0) / 60);

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text variant="metaSm" color={colors.textMuted}>
            {meetings.length} MEETINGS · {totalMin} MIN
          </Text>
          <Text variant="subtitle">Meetings</Text>
        </View>
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={colors.primary} /></View>
      ) : meetings.length === 0 ? (
        <View style={styles.center}>
          <View style={styles.emptyDisc}>
            <Ionicons name="mic-outline" size={26} color={colors.primary} />
          </View>
          <Text variant="label" style={{ marginTop: 14 }}>No meetings yet</Text>
          <Text variant="bodyXs" color={colors.textMuted} style={styles.emptyBody}>
            Meetings are recorded on your Mac — start one from the Flume desktop
            app and it will appear here, with the transcript, your notes, and the
            AI summary.
          </Text>
        </View>
      ) : (
        <FlatList
          data={groups}
          keyExtractor={(g) => g.label}
          contentContainerStyle={{ paddingBottom: insets.bottom + 90 }}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh}
              tintColor={colors.textMuted} />
          }
          renderItem={({ item: group }) => (
            <View>
              <Text variant="metaSm" color={colors.textSubtle} style={styles.groupHead}>
                {group.label.toUpperCase()}
              </Text>
              <View style={styles.groupCard}>
                {group.items.map((m, i) => {
                  const sids = Object.keys(m.speakers);
                  const preview =
                    m.status === 'processing' ? 'Summarizing…'
                    : m.status === 'failed' ? 'Summary failed — transcript saved'
                    : m.summary || 'No summary';
                  return (
                    <Pressable
                      key={m.id}
                      style={[styles.row, i > 0 && styles.rowDivider]}
                      onPress={() => onOpen(m.id)}
                    >
                      <View style={styles.metaCol}>
                        <Text variant="metaSm" color={colors.textSubtle} numberOfLines={1}>
                          {m.dateLabel}
                        </Text>
                        <Text variant="metaSm" color={colors.textMuted}>
                          {fmtDur(m.durationSeconds)}
                        </Text>
                      </View>
                      <View style={{ flex: 1, minWidth: 0 }}>
                        <Text variant="label" numberOfLines={1}>{m.title}</Text>
                        <Text variant="bodyXs" color={colors.textMuted} numberOfLines={1}>
                          {preview}
                        </Text>
                      </View>
                      <View style={styles.pRow}>
                        {sids.slice(0, 3).map((sid, j) => (
                          <View key={sid} style={styles.pChip}>
                            <View style={[styles.pDot, { backgroundColor: speakerDot(sid, j) }]} />
                            <Text variant="metaSm" color={colors.textMuted}>
                              {(m.speakers[sid] || '?').trim().charAt(0).toUpperCase()}
                            </Text>
                          </View>
                        ))}
                        {sids.length > 3 && (
                          <Text variant="metaSm" color={colors.textSubtle}>+{sids.length - 3}</Text>
                        )}
                      </View>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          )}
        />
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bgScreen, paddingHorizontal: 20 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 },
  backBtn: {
    width: 36, height: 36, borderRadius: radius.pill, backgroundColor: colors.surface2,
    alignItems: 'center', justifyContent: 'center',
  },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 28 },
  emptyDisc: {
    width: 64, height: 64, borderRadius: radius.pill, backgroundColor: colors.primarySoft,
    alignItems: 'center', justifyContent: 'center',
  },
  emptyBody: { textAlign: 'center', marginTop: 8, lineHeight: 20 },
  groupHead: { marginTop: 14, marginBottom: 6 },
  groupCard: {
    backgroundColor: colors.surface1, borderRadius: radius.md, borderWidth: 1,
    borderColor: colors.borderSubtle, paddingHorizontal: 14, marginBottom: 8,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 },
  rowDivider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.borderSubtle },
  metaCol: { width: 52 },
  pRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  pChip: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  pDot: { width: 6, height: 6, borderRadius: 3 },
});

export default MeetingListScreen;
