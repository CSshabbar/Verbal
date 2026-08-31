import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { View, StyleSheet, ScrollView, Pressable, TextInput, AccessibilityInfo, RefreshControl, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { Text, ImportNotesModal, MenuButton } from '../components';
import { confirm } from '../components/ConfirmDialog';
import { colors, radius, pressedStyle } from '../theme';
import { useNotes, Note } from '../hooks/useNotes';
import { searchNotes } from '../../lib/notesSearch';
import { askNotes } from '../../lib/groq';

type Props = {
  onOpen: (note: Note) => void;
  onCreate: () => void;
  /** Opens the Meetings folder (read-only desktop-captured meetings). */
  onOpenMeetings?: () => void;
};

const CARD_CREAM = '#EADFCE';
const CARD_CREAM_INK = '#2a1f18';

/**
 * Screen 7b — Notes dashboard (minimalist dark): count header, segmented
 * pills, a featured pastel note card, then "This week" note cards. Notes v2 adds
 * live full-text search (Feature 1) at the top, gated by the search feature flag.
 */
export const NotesListScreen: React.FC<Props> = ({ onOpen, onCreate, onOpenMeetings }) => {
  const insets = useSafeAreaInsets();
  const { notes, flags, reloadFlags, reload, removeNotes, createNote } = useNotes();
  const [filter, setFilter] = useState<'all' | 'voice' | 'typed'>('all');
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  // Import (Notes v3.2): one pick = one note, created here and opened at once.
  const handleImport = useCallback((data: { title: string; body: string }) => {
    setImportOpen(false);
    const note = createNote({ title: data.title, body: data.body });
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    onOpen(note);
  }, [createNote, onOpen]);

  // Settings toggles (search / audio / autotitle / structure) apply as soon as
  // the user comes back to this screen — they used to need an app relaunch.
  useFocusEffect(
    useCallback(() => { reloadFlags().catch(() => {}); }, [reloadFlags]),
  );

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    try { await reload(); } finally { setRefreshing(false); }
  }, [reload]);

  // Multi-select: long-press a note to enter select mode, tap to toggle.
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const exitSelect = useCallback(() => { setSelectMode(false); setSelected(new Set()); }, []);

  const enterSelect = useCallback((id: string) => {
    Haptics.selectionAsync();
    setSelectMode(true);
    setSelected(new Set([id]));
  }, []);

  const toggleSelect = useCallback((id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  // Tap handler: in select mode a tap toggles; otherwise it opens the note.
  const handlePress = useCallback((n: Note) => {
    if (selectMode) toggleSelect(n.id); else onOpen(n);
  }, [selectMode, toggleSelect, onOpen]);

  const deleteSelected = useCallback(async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) { exitSelect(); return; }
    const ok = await confirm({
      title: `Delete ${ids.length} note${ids.length === 1 ? '' : 's'}?`,
      message: 'This removes them from every signed-in device. This cannot be undone.',
      confirmLabel: 'Delete',
      destructive: true,
    });
    if (ok) { removeNotes(ids); Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); }
    exitSelect();
  }, [selected, removeNotes, exitSelect]);

  const base = useMemo(() => {
    if (filter === 'all') return notes;
    return notes.filter(n => (filter === 'voice' ? n.isVoice : !n.isVoice));
  }, [notes, filter]);

  const searching = flags.search && searchOpen && query.trim().length > 0;
  const results = useMemo(
    () => (searching ? searchNotes(base, query) : base),
    [searching, base, query],
  );

  /* ── Ask your notes (Notes v3) — explicit action only (submit / Ask row) ── */
  const [asking, setAsking] = useState(false);
  const [askAnswer, setAskAnswer] = useState<string | null>(null);
  useEffect(() => { setAskAnswer(null); }, [query]);

  const runAsk = useCallback(async () => {
    const q = query.trim();
    if (!q || asking || notes.length === 0) return;
    setAsking(true);
    setAskAnswer(null);
    try {
      // Same token-overlap ranking as desktop ask_notes: title 3×, body 1×.
      const toks = (q.toLowerCase().match(/[a-z0-9]+/g) ?? []).filter(t => t.length > 2);
      const score = (n: Note) => {
        const t = (n.title || '').toLowerCase(), b = (n.body || '').toLowerCase();
        let s = 0;
        for (const k of toks) { if (t.includes(k)) s += 3; if (b.includes(k)) s += 1; }
        return s;
      };
      const ranked = [...notes].sort((a, b) => score(b) - score(a)).slice(0, 6);
      const r = await askNotes(q, ranked.map(n => ({
        title: n.title, content: n.body, updatedAt: new Date(n.updatedAt).toISOString(),
      })));
      setAskAnswer(r.ok ? r.answer : "Couldn't get an answer — check your connection and try again.");
    } finally {
      setAsking(false);
    }
  }, [query, notes, asking]);

  // Pinned notes surface in their own labeled section (never while searching).
  const pinnedNotes = useMemo(() => results.filter(n => n.isPinned), [results]);
  const unpinned = useMemo(() => results.filter(n => !n.isPinned), [results]);

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

  const featured = unpinned[0];
  const rest = unpinned.slice(1);

  const closeSearch = () => { setSearchOpen(false); setQuery(''); };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 10 }]}>
      {selectMode ? (
        <View style={styles.header}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <Pressable onPress={exitSelect} style={({ pressed }) => [styles.iconCircle, pressed && pressedStyle]} accessibilityRole="button" accessibilityLabel="Cancel selection">
              <Ionicons name="close" size={18} color={colors.textSecondary} />
            </Pressable>
            <Text variant="titleSm">{selected.size} selected</Text>
          </View>
          <Pressable
            onPress={deleteSelected}
            disabled={selected.size === 0}
            style={({ pressed }) => [styles.iconCircle, { backgroundColor: colors.primarySoft }, pressed && pressedStyle, selected.size === 0 && { opacity: 0.4 }]}
            accessibilityRole="button"
            accessibilityLabel={`Delete ${selected.size} selected`}
          >
            <Ionicons name="trash-outline" size={17} color={colors.primaryAccent} />
          </Pressable>
        </View>
      ) : (
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
                style={({ pressed }) => [styles.iconCircle, searchOpen && { backgroundColor: colors.primarySoft }, pressed && pressedStyle]}
                accessibilityRole="button"
                accessibilityLabel={searchOpen ? 'Close search' : 'Search notes'}
              >
                <Ionicons name="search-outline" size={16} color={searchOpen ? colors.primary : colors.textSecondary} />
              </Pressable>
            ) : null}
            <Pressable
              onPress={() => setImportOpen(true)}
              style={({ pressed }) => [styles.iconCircle, pressed && pressedStyle]}
              accessibilityRole="button"
              accessibilityLabel="Import from meetings or transcriptions"
            >
              <Ionicons name="download-outline" size={16} color={colors.textSecondary} />
            </Pressable>
            <Pressable onPress={onCreate} style={({ pressed }) => [styles.iconCircle, { backgroundColor: colors.primarySoft }, pressed && pressedStyle]} accessibilityRole="button" accessibilityLabel="New note">
              <Ionicons name="add" size={18} color={colors.primary} />
            </Pressable>
            <MenuButton />
          </View>
        </View>
      )}

      <ImportNotesModal visible={importOpen} onClose={() => setImportOpen(false)} onImport={handleImport} />

      {flags.search && searchOpen ? (
        <View style={styles.searchBar}>
          <Ionicons name="search-outline" size={16} color={colors.textMuted} />
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="Search or ask your notes…"
            placeholderTextColor={colors.textSubtle}
            style={styles.searchInput}
            autoFocus
            autoCorrect={false}
            returnKeyType="search"
            onSubmitEditing={runAsk}
            accessibilityLabel="Search notes"
          />
          {query.length > 0 ? (
            <Pressable onPress={() => setQuery('')} hitSlop={8} style={({ pressed }) => pressed && pressedStyle} accessibilityRole="button" accessibilityLabel="Clear search">
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

      {!searching && !selectMode && onOpenMeetings ? (
        <Pressable
          style={({ pressed }) => [styles.meetingsRow, pressed && pressedStyle]}
          onPress={onOpenMeetings}
          accessibilityRole="button"
          accessibilityLabel="Open meetings"
        >
          <View style={styles.meetingsDisc}>
            <Ionicons name="people-outline" size={15} color={colors.primary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text variant="label">Meetings</Text>
            <Text variant="caption" color={colors.textMuted}>Captured on your Mac · transcripts &amp; summaries</Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={colors.textSubtle} />
        </Pressable>
      ) : null}

      <ScrollView
        style={{ flex: 1 }}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingBottom: insets.bottom + 90 }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.textMuted} />
        }
      >
        {searching ? (
          <>
            {/* Ask-your-notes (Notes v3): explicit action — submit or this row. */}
            {asking ? (
              <View style={styles.askCard}>
                <ActivityIndicator size="small" color={colors.primary} />
                <Text variant="bodyXs" color={colors.primaryAccent}>Thinking…</Text>
              </View>
            ) : askAnswer ? (
              <View style={styles.askCard}>
                <View style={{ flex: 1 }}>
                  <Text variant="metaSm" color={colors.primaryAccent} style={{ marginBottom: 4 }}>
                    {query.trim().toUpperCase()}
                  </Text>
                  <Text variant="bodyXs" color={colors.textPrimary} selectable style={{ lineHeight: 19 }}>
                    {askAnswer}
                  </Text>
                </View>
                <Pressable onPress={() => setAskAnswer(null)} hitSlop={8} accessibilityRole="button" accessibilityLabel="Dismiss answer">
                  <Ionicons name="close" size={15} color={colors.textMuted} />
                </Pressable>
              </View>
            ) : results.length > 0 ? (
              <Pressable onPress={runAsk} style={({ pressed }) => [styles.askRow, pressed && pressedStyle]} accessibilityRole="button" accessibilityLabel={`Ask AI about ${query.trim()}`}>
                <Ionicons name="sparkles-outline" size={14} color={colors.primary} />
                <Text variant="buttonSm" color={colors.primary}>Ask AI about “{query.trim()}”</Text>
              </Pressable>
            ) : null}
            {results.length === 0 ? (
              <View style={styles.empty}>
                <Text variant="bodySm" color={colors.textSubtle} align="center">No notes match “{query.trim()}”.</Text>
                {!asking && !askAnswer ? (
                  <Pressable onPress={runAsk} style={({ pressed }) => [styles.clearBtn, pressed && pressedStyle]} accessibilityRole="button" accessibilityLabel="Ask AI">
                    <Text variant="buttonSm" color={colors.primary}>Ask AI</Text>
                  </Pressable>
                ) : null}
                <Pressable onPress={() => setQuery('')} style={({ pressed }) => [styles.clearBtn, pressed && pressedStyle]} accessibilityRole="button" accessibilityLabel="Clear search">
                  <Text variant="buttonSm" color={colors.primary}>Clear search</Text>
                </Pressable>
              </View>
            ) : (
              <View style={{ gap: 10 }} accessibilityLabel={`${results.length} results`}>
                {results.map(n => (
                  <NoteRow key={n.id} note={n} selectMode={selectMode} selected={selected.has(n.id)} onPress={handlePress} onLongPress={enterSelect} />
                ))}
              </View>
            )}
          </>
        ) : (pinnedNotes.length > 0 || featured) ? (
          <>
            {pinnedNotes.length > 0 && (
              <>
                <View style={styles.sectionHead}>
                  <Text variant="metaSm" color={colors.textSubtle}>PINNED</Text>
                </View>
                <View style={{ gap: 10, marginBottom: 20 }}>
                  {pinnedNotes.map(n => (
                    <NoteRow key={n.id} note={n} selectMode={selectMode} selected={selected.has(n.id)} onPress={handlePress} onLongPress={enterSelect} />
                  ))}
                </View>
              </>
            )}
            {featured ? (
            <Pressable
              onPress={() => handlePress(featured)}
              onLongPress={() => enterSelect(featured.id)}
              delayLongPress={300}
              style={({ pressed }) => [styles.featured, { backgroundColor: CARD_CREAM }, selectMode && selected.has(featured.id) && styles.cardSelected, pressed && pressedStyle]}
            >
              <View style={styles.featuredTop}>
                <View style={[styles.featuredIcon, { backgroundColor: '#1a1512' }]}>
                  <Ionicons name={selectMode ? (selected.has(featured.id) ? 'checkmark-circle' : 'ellipse-outline') : (featured.isVoice ? 'mic-outline' : 'create-outline')} size={14} color={CARD_CREAM} />
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
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Text style={{ fontSize: 10.5, fontFamily: 'Geist_500Medium', color: CARD_CREAM_INK, opacity: 0.6 }}>{featured.dateLabel}</Text>
                  {featured.conflict ? (
                    <View style={styles.conflictTagOnCream}>
                      <Ionicons name="git-compare-outline" size={11} color={CARD_CREAM_INK} />
                      <Text style={{ fontSize: 10.5, fontFamily: 'Geist_600SemiBold', color: CARD_CREAM_INK }}>Conflict</Text>
                    </View>
                  ) : null}
                </View>
                <View style={styles.featuredChevron}>
                  <Ionicons name="chevron-forward" size={11} color={CARD_CREAM_INK} />
                </View>
              </View>
            </Pressable>
            ) : null}

            {rest.length > 0 && (
              <>
                <View style={styles.sectionHead}>
                  <Text variant="subtitle" style={{ fontSize: 16 }}>Recent</Text>
                </View>
                <View style={{ gap: 10 }}>
                  {rest.map(n => (
                    <NoteRow key={n.id} note={n} selectMode={selectMode} selected={selected.has(n.id)} onPress={handlePress} onLongPress={enterSelect} />
                  ))}
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

const NoteRow: React.FC<{
  note: Note;
  selectMode: boolean;
  selected: boolean;
  onPress: (n: Note) => void;
  onLongPress: (id: string) => void;
}> = ({ note: n, selectMode, selected, onPress, onLongPress }) => (
  <Pressable
    onPress={() => onPress(n)}
    onLongPress={() => onLongPress(n.id)}
    delayLongPress={300}
    style={({ pressed }) => [styles.noteCard, selectMode && selected && styles.cardSelected, pressed && pressedStyle]}
    accessibilityRole="button"
    accessibilityState={{ selected: selectMode ? selected : undefined }}
    accessibilityLabel={n.title || 'Untitled note'}
  >
    <View style={styles.noteCardHead}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
        {n.isPinned ? <Ionicons name="star" size={11} color={colors.primary} /> : null}
        <Text variant="caption" color={colors.textSubtle}>{n.dateLabel}</Text>
      </View>
      <View style={[styles.noteIcon, selectMode && selected && { backgroundColor: colors.primarySoft }]}>
        <Ionicons
          name={selectMode ? (selected ? 'checkmark-circle' : 'ellipse-outline') : (n.isVoice ? 'mic-outline' : 'create-outline')}
          size={13}
          color={selectMode && selected ? colors.primary : colors.textMuted}
        />
      </View>
    </View>
    <Text variant="button" style={{ fontSize: 14, marginBottom: 5 }} numberOfLines={1}>
      {n.title || 'Untitled note'}
    </Text>
    <Text variant="bodyXs" color={colors.textMuted} numberOfLines={2} style={(n.isVoice || n.conflict) ? { marginBottom: 12 } : undefined}>
      {n.preview}
    </Text>
    <View style={styles.tagRow}>
      {n.isVoice ? (
        <View style={styles.voiceTag}>
          <Text style={{ fontSize: 10.5, fontFamily: 'Geist_600SemiBold', color: colors.tagMacInk }}>Voice</Text>
        </View>
      ) : null}
      {/* IDI-176 §9: the note is one half of an unresolved conflict pair. Opening
          it shows the "Edited on two devices" banner. */}
      {n.conflict ? <ConflictBadge /> : null}
    </View>
  </Pressable>
);

const ConflictBadge: React.FC = () => (
  <View style={styles.conflictTag} accessibilityLabel="Edited on two devices">
    <Ionicons name="git-compare-outline" size={11} color={colors.primary} />
    <Text style={{ fontSize: 10.5, fontFamily: 'Geist_600SemiBold', color: colors.primary }}>Conflict</Text>
  </View>
);

const Pill: React.FC<{ label: string; active: boolean; onPress: () => void }> = ({ label, active, onPress }) => (
  <Pressable onPress={onPress} style={({ pressed }) => [styles.pill, active ? styles.pillActive : styles.pillIdle, pressed && pressedStyle]} accessibilityRole="button" accessibilityState={{ selected: active }} accessibilityLabel={label}>
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
  meetingsRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14,
    backgroundColor: colors.surface1, borderWidth: 1, borderColor: colors.borderSubtle,
    borderRadius: radius.md, paddingHorizontal: 12, paddingVertical: 10,
  },
  meetingsDisc: {
    width: 30, height: 30, borderRadius: radius.sm, backgroundColor: colors.primarySoft,
    alignItems: 'center', justifyContent: 'center',
  },
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
  askRow: {
    flexDirection: 'row', alignItems: 'center', gap: 7, alignSelf: 'flex-start',
    paddingVertical: 8, paddingHorizontal: 13, borderRadius: 999, marginBottom: 12,
    backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primaryBorder,
  },
  askCard: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 10,
    padding: 13, borderRadius: radius.md, marginBottom: 14,
    backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primaryBorder,
  },
  sectionHead: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12 },
  noteCard: { padding: 14, borderRadius: 16, backgroundColor: colors.surface1, borderWidth: 1, borderColor: colors.borderSubtle },
  cardSelected: { borderColor: colors.primary, borderWidth: 2 },
  noteCardHead: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 },
  noteIcon: { width: 26, height: 26, borderRadius: 8, backgroundColor: colors.surface2, alignItems: 'center', justifyContent: 'center' },
  voiceTag: { alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 7, backgroundColor: colors.tagMac },
  tagRow: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  conflictTag: {
    flexDirection: 'row', alignItems: 'center', gap: 5, alignSelf: 'flex-start',
    paddingHorizontal: 9, paddingVertical: 5, borderRadius: 7,
    backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primaryBorder,
  },
  conflictTagOnCream: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999,
    backgroundColor: 'rgba(42,31,24,0.1)',
  },
});

export default NotesListScreen;
