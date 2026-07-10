import React, { useState, useMemo, useEffect } from 'react';
import { View, StyleSheet, ScrollView, Pressable, TextInput, AccessibilityInfo } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text } from '../components';
import { colors, radius } from '../theme';
import { useNotes, Note } from '../hooks/useNotes';
import { searchNotes } from '../../lib/notesSearch';

type Props = {
  onOpen: (note: Note) => void;
  onCreate: () => void;
};

const CARD_CREAM = '#EADFCE';
const CARD_CREAM_INK = '#2a1f18';

/**
 * Screen 7b — Notes dashboard (minimalist dark): count header, segmented
 * pills, a featured pastel note card, then "This week" note cards. Notes v2 adds
 * live full-text search (Feature 1) at the top, gated by the search feature flag.
 */
export const NotesListScreen: React.FC<Props> = ({ onOpen, onCreate }) => {
  const insets = useSafeAreaInsets();
  const { notes, flags } = useNotes();
  const [filter, setFilter] = useState<'all' | 'voice' | 'typed'>('all');
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState('');

  const base = useMemo(() => {
    if (filter === 'all') return notes;
    return notes.filter(n => (filter === 'voice' ? n.isVoice : !n.isVoice));
  }, [notes, filter]);

  const searching = flags.search && searchOpen && query.trim().length > 0;
  const results = useMemo(
    () => (searching ? searchNotes(base, query) : base),
    [searching, base, query],
  );

  // Announce result count to screen readers as the query changes (Decision 8).
  useEffect(() => {
    if (searching) {
      AccessibilityInfo.announceForAccessibility(
        `${results.length} ${results.length === 1 ? 'result' : 'results'} for ${query.trim()}`,
      );
    }
  }, [searching, results.length, query]);

  const weekAgo = Date.now() - 7 * 86_400_000;
  const thisWeek = useMemo(() => notes.filter(n => n.updatedAt >= weekAgo).length, [notes, weekAgo]);

  const featured = results[0];
  const rest = results.slice(1);

  const closeSearch = () => { setSearchOpen(false); setQuery(''); };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 10 }]}>
      <View style={styles.header}>
        <View>
          <Text variant="caption" color={colors.textSubtle} style={{ marginBottom: 2 }}>
            {notes.length} total · {thisWeek} this week
          </Text>
          <Text variant="titleSm">Notes</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {flags.search ? (
            <Pressable
              onPress={() => setSearchOpen(o => !o)}
              style={[styles.iconCircle, searchOpen && { backgroundColor: colors.primarySoft }]}
              accessibilityRole="button"
              accessibilityLabel={searchOpen ? 'Close search' : 'Search notes'}
            >
              <Ionicons name="search-outline" size={16} color={searchOpen ? colors.primary : colors.textSecondary} />
            </Pressable>
          ) : null}
          <Pressable onPress={onCreate} style={[styles.iconCircle, { backgroundColor: colors.primarySoft }]} accessibilityRole="button" accessibilityLabel="New note">
            <Ionicons name="add" size={18} color={colors.primary} />
          </Pressable>
        </View>
      </View>

      {flags.search && searchOpen ? (
        <View style={styles.searchBar}>
          <Ionicons name="search-outline" size={16} color={colors.textMuted} />
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="Search notes…"
            placeholderTextColor={colors.textSubtle}
            style={styles.searchInput}
            autoFocus
            autoCorrect={false}
            returnKeyType="search"
            accessibilityLabel="Search notes"
          />
          {query.length > 0 ? (
            <Pressable onPress={() => setQuery('')} hitSlop={8} accessibilityRole="button" accessibilityLabel="Clear search">
              <Ionicons name="close-circle" size={18} color={colors.textMuted} />
            </Pressable>
          ) : null}
        </View>
      ) : null}

      {!searching ? (
        <View style={styles.filters}>
          <Pill label="All" active={filter === 'all'} onPress={() => setFilter('all')} />
          <Pill label="Voice" active={filter === 'voice'} onPress={() => setFilter('voice')} />
          <Pill label="Typed" active={filter === 'typed'} onPress={() => setFilter('typed')} />
        </View>
      ) : null}

      <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingBottom: insets.bottom + 90 }}>
        {searching ? (
          results.length === 0 ? (
            <View style={styles.empty}>
              <Text variant="bodySm" color={colors.textSubtle} align="center">No notes match “{query.trim()}”.</Text>
              <Pressable onPress={() => setQuery('')} style={styles.clearBtn} accessibilityRole="button" accessibilityLabel="Clear search">
                <Text variant="buttonSm" color={colors.primary}>Clear search</Text>
              </Pressable>
            </View>
          ) : (
            <View style={{ gap: 10 }} accessibilityLabel={`${results.length} results`}>
              {results.map(n => <NoteRow key={n.id} note={n} onOpen={onOpen} />)}
            </View>
          )
        ) : featured ? (
          <>
            <Pressable onPress={() => onOpen(featured)} style={[styles.featured, { backgroundColor: CARD_CREAM }]}>
              <View style={styles.featuredTop}>
                <View style={[styles.featuredIcon, { backgroundColor: '#1a1512' }]}>
                  <Ionicons name={featured.isVoice ? 'mic-outline' : 'create-outline'} size={14} color={CARD_CREAM} />
                </View>
                <View style={styles.badge}>
                  <View style={styles.badgeDot} />
                  <Text style={{ fontSize: 10, fontFamily: 'Geist_600SemiBold', color: CARD_CREAM_INK, letterSpacing: 0.6 }}>
                    {featured.isVoice ? 'VOICE' : 'NOTE'}
                  </Text>
                </View>
              </View>
              <Text style={{ fontSize: 17, fontFamily: 'Geist_600SemiBold', color: CARD_CREAM_INK, letterSpacing: -0.3, marginBottom: 5 }} numberOfLines={1}>
                {featured.title || 'Untitled note'}
              </Text>
              <Text style={{ fontSize: 11.5, lineHeight: 17, fontFamily: 'Geist_400Regular', color: CARD_CREAM_INK, opacity: 0.65, marginBottom: 14 }} numberOfLines={2}>
                {featured.preview || 'No content yet'}
              </Text>
              <View style={styles.featuredFoot}>
                <Text style={{ fontSize: 10.5, fontFamily: 'Geist_500Medium', color: CARD_CREAM_INK, opacity: 0.6 }}>{featured.dateLabel}</Text>
                <View style={styles.featuredChevron}>
                  <Ionicons name="chevron-forward" size={11} color={CARD_CREAM_INK} />
                </View>
              </View>
            </Pressable>

            {rest.length > 0 && (
              <>
                <View style={styles.sectionHead}>
                  <Text variant="subtitle" style={{ fontSize: 16 }}>Recent</Text>
                  <Text variant="buttonSm" color={colors.textMuted}>See all</Text>
                </View>
                <View style={{ gap: 10 }}>
                  {rest.map(n => <NoteRow key={n.id} note={n} onOpen={onOpen} />)}
                </View>
              </>
            )}
          </>
        ) : (
          <View style={styles.empty}>
            <Text variant="bodySm" color={colors.textSubtle} align="center">No notes yet — dictate one to get started.</Text>
          </View>
        )}
      </ScrollView>
    </View>
  );
};

const NoteRow: React.FC<{ note: Note; onOpen: (n: Note) => void }> = ({ note: n, onOpen }) => (
  <Pressable onPress={() => onOpen(n)} style={styles.noteCard} accessibilityRole="button" accessibilityLabel={n.title || 'Untitled note'}>
    <View style={styles.noteCardHead}>
      <Text variant="caption" color={colors.textSubtle}>{n.dateLabel}</Text>
      <View style={styles.noteIcon}>
        <Ionicons name={n.isVoice ? 'mic-outline' : 'create-outline'} size={13} color={colors.textMuted} />
      </View>
    </View>
    <Text variant="button" style={{ fontSize: 14, marginBottom: 5 }} numberOfLines={1}>
      {n.title || 'Untitled note'}
    </Text>
    <Text variant="bodyXs" color={colors.textMuted} numberOfLines={2} style={n.isVoice ? { marginBottom: 12 } : undefined}>
      {n.preview}
    </Text>
    {n.isVoice ? (
      <View style={styles.voiceTag}>
        <Text style={{ fontSize: 10.5, fontFamily: 'Geist_600SemiBold', color: colors.tagMacInk }}>Voice</Text>
      </View>
    ) : null}
  </Pressable>
);

const Pill: React.FC<{ label: string; active: boolean; onPress: () => void }> = ({ label, active, onPress }) => (
  <Pressable onPress={onPress} style={[styles.pill, active ? styles.pillActive : styles.pillIdle]} accessibilityRole="button" accessibilityState={{ selected: active }} accessibilityLabel={label}>
    <Text variant="buttonSm" color={active ? colors.primaryInk : colors.textSecondary}>{label}</Text>
  </Pressable>
);

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bgScreen, paddingHorizontal: 18 },
  header: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 18 },
  iconCircle: { width: 34, height: 34, borderRadius: 17, backgroundColor: colors.surface2, alignItems: 'center', justifyContent: 'center' },
  searchBar: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: colors.surface2, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.borderSubtle,
    paddingHorizontal: 12, marginBottom: 16,
  },
  searchInput: { flex: 1, color: colors.textPrimary, paddingVertical: 11, fontFamily: 'Geist_400Regular', fontSize: 15 },
  filters: { flexDirection: 'row', gap: 7, marginBottom: 18 },
  pill: { paddingVertical: 9, paddingHorizontal: 16, borderRadius: 999 },
  pillActive: { backgroundColor: colors.inkLight },
  pillIdle: { backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.borderStrong },
  featured: { borderRadius: 18, padding: 14, paddingBottom: 16, marginBottom: 22 },
  featuredTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 },
  featuredIcon: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  badge: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999, backgroundColor: 'rgba(42,31,24,0.08)' },
  badgeDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.primary },
  featuredFoot: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  featuredChevron: { width: 26, height: 26, borderRadius: 13, backgroundColor: 'rgba(42,31,24,0.1)', alignItems: 'center', justifyContent: 'center' },
  empty: { paddingVertical: 28, alignItems: 'center', gap: 12 },
  clearBtn: { paddingVertical: 8, paddingHorizontal: 16, borderRadius: 999, backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primaryBorder },
  sectionHead: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12 },
  noteCard: { padding: 14, borderRadius: 16, backgroundColor: colors.surface1, borderWidth: 1, borderColor: colors.borderSubtle },
  noteCardHead: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 },
  noteIcon: { width: 26, height: 26, borderRadius: 8, backgroundColor: colors.surface2, alignItems: 'center', justifyContent: 'center' },
  voiceTag: { alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 7, backgroundColor: colors.tagMac },
});

export default NotesListScreen;
