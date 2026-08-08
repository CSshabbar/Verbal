import React, { useMemo, useState } from 'react';
import {
  View, StyleSheet, ScrollView, TextInput, Pressable, Modal,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text } from '../components';
import { confirm } from '../components/ConfirmDialog';
import { colors, radius, fonts, shadowFab, pressedStyle } from '../theme';
import { useSnippets, Snippet } from '../hooks/useSnippets';

type Props = { onBack: () => void };

// UI caps (match the "0/40" / "0/500" counters in the mockups). The storage
// layer caps more generously; these keep the on-screen counters honest.
const TRIGGER_MAX = 40;
const EXPANSION_MAX = 500;

type Draft = { id: string | null; label: string; trigger: string; expansion: string };

const EMPTY_DRAFT: Draft = { id: null, label: '', trigger: '', expansion: '' };

/**
 * Snippets — say a phrase, get the full text.
 * List of saved expansions + a bottom-sheet New/Edit form. Reachable from
 * Settings → Snippets (same sub-stack pattern as Settings → Devices).
 */
export const SnippetsScreen: React.FC<Props> = ({ onBack }) => {
  const insets = useSafeAreaInsets();
  const { snippets, createSnippet, updateSnippet, removeSnippet } = useSnippets();

  const [query, setQuery] = useState('');
  const [sheetOpen, setSheetOpen] = useState(false);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return snippets;
    return snippets.filter(s =>
      s.trigger.toLowerCase().includes(q) ||
      s.label.toLowerCase().includes(q) ||
      s.expansion.toLowerCase().includes(q),
    );
  }, [snippets, query]);

  const openNew = () => { setDraft(EMPTY_DRAFT); setSheetOpen(true); };
  const openEdit = (s: Snippet) => {
    setDraft({ id: s.id, label: s.label, trigger: s.trigger, expansion: s.expansion });
    setSheetOpen(true);
  };
  const closeSheet = () => setSheetOpen(false);

  const canSave = draft.trigger.trim().length > 0 && draft.expansion.trim().length > 0;

  const save = async () => {
    if (!canSave) return;
    const trigger = draft.trigger.trim();
    const expansion = draft.expansion;
    const label = draft.label.trim();
    if (draft.id) {
      await updateSnippet(draft.id, { trigger, expansion, label });
    } else {
      await createSnippet(trigger, expansion, label);
    }
    setSheetOpen(false);
  };

  const del = async () => {
    if (!draft.id) return;
    const ok = await confirm({
      title: 'Delete snippet?',
      message: 'This spoken phrase will stop expanding.',
      confirmLabel: 'Delete', cancelLabel: 'Cancel', destructive: true,
    });
    if (ok) { await removeSnippet(draft.id); setSheetOpen(false); }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 10 }]}>
      {/* Back + title */}
      <Pressable onPress={onBack} style={({ pressed }) => [styles.backBtn, pressed && pressedStyle]} hitSlop={8}>
        <Ionicons name="chevron-back" size={20} color={colors.textSecondary} />
        <Text variant="button" color={colors.textSecondary}>Settings</Text>
      </Pressable>

      <Text variant="titleSm" style={{ marginTop: 10, marginBottom: 2 }}>Snippets</Text>
      <Text variant="bodyXs" color={colors.textMuted}>Say a phrase, get the full text.</Text>

      {/* Search + count */}
      <View style={styles.searchRow}>
        <Ionicons name="search" size={16} color={colors.textSubtle} />
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Search snippets…"
          placeholderTextColor={colors.textSubtle}
          autoCapitalize="none"
          autoCorrect={false}
          style={styles.searchInput}
        />
        <Text variant="metaSm" color={colors.textSubtle}>{filtered.length}</Text>
      </View>

      {/* List */}
      {filtered.length === 0 ? (
        <EmptyState hasSnippets={snippets.length > 0} onNew={openNew} />
      ) : (
        <ScrollView
          style={{ flex: 1 }}
          showsVerticalScrollIndicator={false}
          contentContainerStyle={{ paddingTop: 14, paddingBottom: insets.bottom + 110, gap: 10 }}
        >
          {filtered.map(s => (
            <Pressable
              key={s.id}
              onPress={() => openEdit(s)}
              style={({ pressed }) => [styles.card, pressed && pressedStyle]}
            >
              <View style={styles.cardTop}>
                <Text variant="button" numberOfLines={1} style={{ flex: 1 }}>
                  {s.label || s.trigger}
                </Text>
                <Text style={styles.triggerText} numberOfLines={1}>
                  {s.trigger}
                </Text>
              </View>
              <Text variant="caption" color={colors.textMuted} numberOfLines={2} style={{ marginTop: 6 }}>
                {preview(s.expansion)}
              </Text>
            </Pressable>
          ))}
        </ScrollView>
      )}

      {/* + New FAB */}
      <Pressable
        onPress={openNew}
        style={({ pressed }) => [
          styles.fab,
          { bottom: insets.bottom + 20 },
          pressed && pressedStyle,
        ]}
      >
        <Ionicons name="add" size={20} color={colors.primaryInk} />
        <Text variant="button" color={colors.primaryInk}>New</Text>
      </Pressable>

      {/* New/Edit bottom sheet */}
      <Modal
        visible={sheetOpen}
        transparent
        animationType="slide"
        onRequestClose={closeSheet}
      >
        <View style={styles.sheetScrim}>
          {/* Invisible backdrop scrim — tap-to-dismiss only, so it deliberately
              has NO pressed feedback (nothing is rendered to dim). */}
          <Pressable style={{ flex: 1 }} onPress={closeSheet} />
          <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
            <View style={[styles.sheet, { paddingBottom: insets.bottom + 18 }]}>
              {/* Sheet header */}
              <View style={styles.sheetHead}>
                <Pressable onPress={closeSheet} hitSlop={8} style={({ pressed }) => pressed && pressedStyle}>
                  <Text variant="button" color={colors.textMuted}>Cancel</Text>
                </Pressable>
                <Text variant="button">{draft.id ? 'Edit snippet' : 'New snippet'}</Text>
                <Pressable onPress={save} hitSlop={8} disabled={!canSave} style={({ pressed }) => pressed && pressedStyle}>
                  <Text variant="button" color={canSave ? colors.primary : colors.textDisabled}>Save</Text>
                </Pressable>
              </View>

              <ScrollView
                style={{ flexShrink: 1 }}
                keyboardShouldPersistTaps="handled"
                showsVerticalScrollIndicator={false}
                contentContainerStyle={{ gap: 18, paddingTop: 6 }}
              >
                {/* Label */}
                <Field label="LABEL" hint="optional">
                  <TextInput
                    value={draft.label}
                    onChangeText={t => setDraft(d => ({ ...d, label: t }))}
                    placeholder="e.g. LinkedIn"
                    placeholderTextColor={colors.textSubtle}
                    style={styles.input}
                  />
                </Field>

                {/* Trigger */}
                <Field label="TRIGGER PHRASE" hint={`${draft.trigger.length}/${TRIGGER_MAX}`}>
                  <TextInput
                    value={draft.trigger}
                    onChangeText={t => setDraft(d => ({ ...d, trigger: t.slice(0, TRIGGER_MAX) }))}
                    placeholder="Say this to trigger…"
                    placeholderTextColor={colors.textSubtle}
                    maxLength={TRIGGER_MAX}
                    autoCapitalize="none"
                    style={[styles.input, styles.triggerInput]}
                  />
                  <Text variant="caption" color={colors.textSubtle} style={{ marginTop: 6 }}>
                    Say naturally, mid-sentence. Flume expands it automatically.
                  </Text>
                </Field>

                {/* Expansion */}
                <Field label="EXPANSION" hint={`${draft.expansion.length}/${EXPANSION_MAX}`}>
                  <TextInput
                    value={draft.expansion}
                    onChangeText={t => setDraft(d => ({ ...d, expansion: t.slice(0, EXPANSION_MAX) }))}
                    placeholder="What Flume should type instead…"
                    placeholderTextColor={colors.textSubtle}
                    maxLength={EXPANSION_MAX}
                    multiline
                    style={[styles.input, styles.expansionInput]}
                  />
                </Field>

                {draft.id ? (
                  <Pressable onPress={del} style={({ pressed }) => [styles.deleteBtn, pressed && pressedStyle]} hitSlop={8}>
                    <Ionicons name="trash-outline" size={16} color={colors.primary} />
                    <Text variant="button" color={colors.primary}>Delete snippet</Text>
                  </Pressable>
                ) : null}
              </ScrollView>
            </View>
          </KeyboardAvoidingView>
        </View>
      </Modal>
    </View>
  );
};

function preview(expansion: string): string {
  const flat = expansion.replace(/\s+/g, ' ').trim();
  return flat.length > 80 ? `${flat.slice(0, 80)}…` : flat;
}

const EmptyState: React.FC<{ hasSnippets: boolean; onNew: () => void }> = ({ hasSnippets, onNew }) => (
  <View style={styles.empty}>
    {hasSnippets ? (
      <Text variant="body" color={colors.textMuted} align="center">No snippets match your search.</Text>
    ) : (
      <>
        <Text variant="metaSm" color={colors.primary} style={{ marginBottom: 12 }}>TRY ONE</Text>
        <Text variant="subtitle" align="center" style={{ marginBottom: 4 }}>
          Say <Text variant="subtitle" color={colors.primary}>"my linkedin"</Text>
        </Text>
        <Text variant="body" color={colors.textMuted} align="center" style={{ marginBottom: 22 }}>
          — get your full URL every time.
        </Text>
        <Pressable onPress={onNew} style={({ pressed }) => [styles.emptyCta, pressed && pressedStyle]}>
          <Ionicons name="add" size={18} color={colors.primary} />
          <Text variant="button" color={colors.primary}>Create your first snippet</Text>
        </Pressable>
        <View style={styles.chipRow}>
          {['Calendar link', 'Email signature', 'Home address', 'Product blurb'].map(c => (
            <View key={c} style={styles.chip}>
              <Text variant="caption" color={colors.textMuted}>{c}</Text>
            </View>
          ))}
        </View>
      </>
    )}
  </View>
);

const Field: React.FC<{ label: string; hint?: string; children: React.ReactNode }> = ({ label, hint, children }) => (
  <View style={{ gap: 8 }}>
    <View style={styles.fieldHead}>
      <Text variant="metaSm" color={colors.textSubtle}>{label}</Text>
      {hint ? <Text variant="metaSm" color={colors.textSubtle}>{hint}</Text> : null}
    </View>
    {children}
  </View>
);

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 18,
  },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 2, marginLeft: -4 },
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 16,
    backgroundColor: colors.surface2,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    paddingHorizontal: 12,
    paddingVertical: Platform.OS === 'ios' ? 11 : 4,
  },
  searchInput: {
    flex: 1,
    color: colors.textPrimary,
    fontFamily: fonts.regular,
    fontSize: 15,
    padding: 0,
  },
  card: {
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surface1,
    padding: 15,
  },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  triggerText: {
    fontFamily: fonts.mono,
    fontSize: 13,
    letterSpacing: 0.2,
    color: colors.primary,
    textAlign: 'right',
    maxWidth: '55%',
  },
  fab: {
    position: 'absolute',
    right: 18,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingLeft: 16,
    paddingRight: 20,
    height: 50,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    ...shadowFab,
  },
  // Empty state
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingBottom: 60 },
  emptyCta: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingVertical: 12, paddingHorizontal: 18,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
    borderWidth: 1, borderColor: colors.primaryBorder,
  },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 8, marginTop: 26 },
  chip: {
    paddingVertical: 6, paddingHorizontal: 12,
    borderRadius: radius.pill,
    backgroundColor: colors.surface2,
    borderWidth: 1, borderColor: colors.borderSubtle,
  },
  // Sheet
  sheetScrim: { flex: 1, backgroundColor: colors.scrim, justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: colors.surface1,
    borderTopLeftRadius: radius.xxl,
    borderTopRightRadius: radius.xxl,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    paddingHorizontal: 18,
    paddingTop: 14,
    maxHeight: '86%',
  },
  sheetHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 14,
  },
  fieldHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  input: {
    backgroundColor: colors.surface2,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: colors.textPrimary,
    fontFamily: fonts.regular,
    fontSize: 16,
  },
  triggerInput: {
    fontFamily: fonts.mono,
    fontSize: 15,
    borderColor: colors.primaryBorder,
  },
  expansionInput: {
    minHeight: 110,
    textAlignVertical: 'top',
  },
  deleteBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    paddingVertical: 12,
    marginTop: 4,
  },
});

export default SnippetsScreen;
