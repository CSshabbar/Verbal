import React, { useEffect, useState } from 'react';
import { View, StyleSheet, ScrollView, TextInput, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text, Card, Button } from '../components';
import { Dictionary, fetchRemote, saveDictionaryChecked } from '../../lib/dictionary';
import { useOrganization } from '../hooks/useOrganization';
import { colors, radius, pressedStyle } from '../theme';

type Props = { onBack: () => void };

/**
 * Dictionary — vocabulary (bias words) + replacement rules, as a standalone page
 * reached from the Menu. Same store as everywhere else (lib/dictionary:
 * fetchRemote/saveDictionary); editing a transcription still teaches a rule
 * automatically elsewhere. Snippets have their own screen.
 *
 * The TEAM's shared set is a second scope on this same page rather than a card on
 * the Team screen. A dictionary is a dictionary — people look for one under
 * Dictionary, and two homes for one concept meant two places to learn. Personal
 * entries always beat shared ones at dictation time (lib/dictionary:mergeWithTeam),
 * which is the sentence the header has to make true and visible.
 */
export const DictionaryScreen: React.FC<Props> = ({ onBack }) => {
  const insets = useSafeAreaInsets();
  const [dict, setDict] = useState<Dictionary>({ vocabulary: [], replacements: [], snippets: [] });
  const [newWord, setNewWord] = useState('');
  const [repFrom, setRepFrom] = useState('');
  const [repTo, setRepTo] = useState('');
  // The initial state above is EMPTY. Editing before fetchRemote() resolves
  // would push that emptiness over the real dictionary, so every mutation is
  // gated on `loaded` (IDI-174). Set even when the fetch fails — it falls back
  // to the local cache, which is still the right base to edit.
  const [loaded, setLoaded] = useState(false);
  const [syncError, setSyncError] = useState(false);
  const [scope, setScope] = useState<'personal' | 'team'>('personal');

  const t = useOrganization();
  const teamDict: Dictionary = {
    vocabulary: t.org.dictionary?.vocabulary ?? [],
    replacements: t.org.dictionary?.replacements ?? [],
    snippets: t.org.dictionary?.snippets ?? [],
  };
  // A member can read the shared set but not change it; an owner/admin can.
  const canEditTeam = t.isAdmin;
  const teamScope = scope === 'team' && t.hasTeam;
  // Losing the team mid-session (removed, left, sync failure) must not leave the
  // page editing a dictionary that is no longer there.
  useEffect(() => { if (scope === 'team' && !t.hasTeam) setScope('personal'); }, [scope, t.hasTeam]);

  const view = teamScope ? teamDict : dict;
  const editable = teamScope ? canEditTeam : loaded;

  useEffect(() => {
    (async () => {
      try { setDict(await fetchRemote()); } finally { setLoaded(true); }
    })();
  }, []);

  // One write path per scope. Both are CAS-checked: the personal one against the
  // user's own updated_at, the shared one server-side, because two admins can be
  // editing the same team dictionary at once.
  const persistDict = async (d: Dictionary) => {
    if (teamScope) {
      if (!canEditTeam) return;
      const res = await t.saveTeamDictionary(d);
      setSyncError(!res.ok);
      return;
    }
    if (!loaded) return;
    setDict(d);
    const { dict: saved, error } = await saveDictionaryChecked(d);
    setDict(saved);            // a CAS conflict may have merged in another device's edit
    setSyncError(!!error);
  };
  const addWord = async () => {
    const w = newWord.trim(); if (!w) return;
    if (!view.vocabulary.some(x => x.toLowerCase() === w.toLowerCase())) {
      await persistDict({ ...view, vocabulary: [...view.vocabulary, w] });
    }
    setNewWord('');
  };
  const removeWord = async (i: number) =>
    persistDict({ ...view, vocabulary: view.vocabulary.filter((_, idx) => idx !== i) });
  const addRep = async () => {
    const f = repFrom.trim(), to = repTo.trim(); if (!f || !to) return;
    const reps = view.replacements.filter(r => r.from.toLowerCase() !== f.toLowerCase());
    await persistDict({ ...view, replacements: [...reps, { from: f, to: to }] });
    setRepFrom(''); setRepTo('');
  };
  const removeRep = async (i: number) =>
    persistDict({ ...view, replacements: view.replacements.filter((_, idx) => idx !== i) });

  return (
    <View style={[styles.root, { paddingTop: insets.top + 12 }]}>
      <View style={styles.topBar}>
        <Pressable onPress={onBack} style={({ pressed }) => pressed && pressedStyle} accessibilityRole="button" accessibilityLabel="Back" hitSlop={8}>
          <Ionicons name="chevron-back" size={24} color={colors.textSecondary} />
        </Pressable>
        <Text variant="titleSm">Dictionary</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView
        style={{ flex: 1 }}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingTop: 16, paddingBottom: insets.bottom + 28, gap: 20 }}
      >
        {syncError ? (
          <Text variant="bodyXs" color={colors.primary}>Couldn't sync — will retry.</Text>
        ) : null}

        {t.hasTeam ? (
          <View style={styles.seg}>
            {([['personal', 'Mine'], ['team', t.org.name || 'Team']] as const).map(([k, label]) => (
              <Pressable
                key={k}
                onPress={() => setScope(k as 'personal' | 'team')}
                accessibilityRole="button"
                accessibilityState={{ selected: scope === k }}
                style={({ pressed }) => [styles.segBtn, scope === k && styles.segBtnOn, pressed && pressedStyle]}
              >
                <Text variant="caption" color={scope === k ? colors.textPrimary : colors.textMuted} numberOfLines={1}>
                  {label}
                </Text>
              </Pressable>
            ))}
          </View>
        ) : null}

        {teamScope ? (
          <Text variant="bodyXs" color={colors.textMuted}>
            {canEditTeam
              ? `Everyone on ${t.org.name || 'the team'} dictates with these on top of their own.`
              : 'Your admins maintain these. They apply on top of your own words.'}
              {' '}Your own entries always win a clash — same word, same rule.
          </Text>
        ) : null}

        <Card padding={14}>
          <Text variant="button" style={{ marginBottom: 2 }}>{teamScope ? 'Shared vocabulary' : 'Vocabulary'}</Text>
          <Text variant="bodyXs" color={colors.textMuted} style={{ marginBottom: 10 }}>
            {teamScope
              ? canEditTeam
                ? 'Names & jargon the whole team should spell right. Tap a word to remove it.'
                : 'Names & jargon your team shares. Only admins can change these.'
              : 'Names, products, acronyms — spelled how you want them. Tap a word to remove it.'}
          </Text>
          <View style={styles.chipWrap}>
            {view.vocabulary.length === 0 ? (
              <Text variant="caption" color={colors.textSubtle}>
                {teamScope ? 'No shared words yet.' : loaded ? 'No words yet.' : 'Loading…'}
              </Text>
            ) : view.vocabulary.map((w, i) => (
              <Pressable
                key={`${w}-${i}`}
                onPress={editable ? () => removeWord(i) : undefined}
                disabled={!editable}
                style={({ pressed }) => [styles.chip, pressed && pressedStyle]}
              >
                <Text variant="caption" color={colors.primary}>{w}</Text>
                {editable ? <Ionicons name="close" size={12} color={colors.primary} /> : null}
              </Pressable>
            ))}
          </View>
          {editable ? (
            <View style={styles.dictRow}>
              <TextInput
                value={newWord} onChangeText={setNewWord}
                placeholder={teamScope ? 'Add a shared word…' : 'Add a word…'}
                placeholderTextColor={colors.textMuted} style={[styles.dictInput, { flex: 1 }]}
                autoCapitalize="none" onSubmitEditing={addWord} returnKeyType="done"
              />
              <Button label="Add" variant="ghost" onPress={addWord} style={{ flex: 0 }} />
            </View>
          ) : null}
        </Card>

        <Card padding={14}>
          <Text variant="button" style={{ marginBottom: 2 }}>{teamScope ? 'Shared rules' : 'Replacement rules'}</Text>
          <Text variant="bodyXs" color={colors.textMuted} style={{ marginBottom: 10 }}>
            {teamScope
              ? 'Always rewrite a misheard word, for everyone on the team.'
              : 'Fix persistent mishearings. Editing a transcription teaches one automatically.'}
          </Text>
          {view.replacements.length === 0 ? (
            <Text variant="caption" color={colors.textSubtle} style={{ marginBottom: 10 }}>
              {teamScope ? 'No shared rules yet.' : 'No rules yet.'}
            </Text>
          ) : null}
          {view.replacements.map((r, i) => (
            <View key={`${r.from}-${i}`} style={styles.repRow}>
              <Text variant="caption" color={colors.textMuted}>{r.from}</Text>
              <Ionicons name="arrow-forward" size={12} color={colors.textSubtle} />
              <Text variant="caption" style={{ flex: 1 }}>{r.to}</Text>
              {editable ? (
                <Pressable onPress={() => removeRep(i)} style={({ pressed }) => pressed && pressedStyle} hitSlop={8}>
                  <Ionicons name="close" size={14} color={colors.textMuted} />
                </Pressable>
              ) : null}
            </View>
          ))}
          {editable ? (
            <View style={styles.dictRow}>
              <TextInput
                value={repFrom} onChangeText={setRepFrom} placeholder="heard…"
                placeholderTextColor={colors.textMuted} style={[styles.dictInput, { flex: 1 }]}
                autoCapitalize="none"
              />
              <Ionicons name="arrow-forward" size={14} color={colors.textSubtle} />
              <TextInput
                value={repTo} onChangeText={setRepTo} placeholder="correct…"
                placeholderTextColor={colors.textMuted} style={[styles.dictInput, { flex: 1 }]}
              />
              <Button label="Add" variant="ghost" onPress={addRep} style={{ flex: 0 }} />
            </View>
          ) : null}
        </Card>
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bgScreen, paddingHorizontal: 18 },
  topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 },
  seg: {
    flexDirection: 'row', gap: 4, padding: 3, alignSelf: 'flex-start',
    backgroundColor: colors.surface2, borderRadius: radius.sm,
  },
  segBtn: { paddingVertical: 6, paddingHorizontal: 14, borderRadius: radius.sm - 2, maxWidth: 160 },
  segBtnOn: { backgroundColor: colors.surface3 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primaryBorder,
    borderRadius: 999, paddingVertical: 5, paddingHorizontal: 11,
  },
  dictRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dictInput: {
    backgroundColor: colors.surface2, borderRadius: 8, paddingVertical: 9, paddingHorizontal: 12,
    color: colors.textPrimary, fontSize: 14,
  },
  repRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: colors.surface2, borderRadius: 8, paddingVertical: 8, paddingHorizontal: 12,
    marginBottom: 8,
  },
});

export default DictionaryScreen;
