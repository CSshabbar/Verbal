import React, { useEffect, useState } from 'react';
import { View, StyleSheet, ScrollView, TextInput, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text, Card, Button } from '../components';
import { Dictionary, fetchRemote, saveDictionary } from '../../lib/dictionary';
import { colors, radius } from '../theme';

type Props = { onBack: () => void };

/**
 * Dictionary — vocabulary (bias words) + replacement rules, as a standalone page
 * reached from the Menu. Same store as everywhere else (lib/dictionary:
 * fetchRemote/saveDictionary); editing a transcription still teaches a rule
 * automatically elsewhere. Snippets have their own screen.
 */
export const DictionaryScreen: React.FC<Props> = ({ onBack }) => {
  const insets = useSafeAreaInsets();
  const [dict, setDict] = useState<Dictionary>({ vocabulary: [], replacements: [] });
  const [newWord, setNewWord] = useState('');
  const [repFrom, setRepFrom] = useState('');
  const [repTo, setRepTo] = useState('');

  useEffect(() => { (async () => setDict(await fetchRemote()))(); }, []);

  const persistDict = async (d: Dictionary) => { setDict(d); await saveDictionary(d); };
  const addWord = async () => {
    const w = newWord.trim(); if (!w) return;
    if (!dict.vocabulary.some(x => x.toLowerCase() === w.toLowerCase())) {
      await persistDict({ ...dict, vocabulary: [...dict.vocabulary, w] });
    }
    setNewWord('');
  };
  const removeWord = async (i: number) =>
    persistDict({ ...dict, vocabulary: dict.vocabulary.filter((_, idx) => idx !== i) });
  const addRep = async () => {
    const f = repFrom.trim(), t = repTo.trim(); if (!f || !t) return;
    const reps = dict.replacements.filter(r => r.from.toLowerCase() !== f.toLowerCase());
    await persistDict({ ...dict, replacements: [...reps, { from: f, to: t }] });
    setRepFrom(''); setRepTo('');
  };
  const removeRep = async (i: number) =>
    persistDict({ ...dict, replacements: dict.replacements.filter((_, idx) => idx !== i) });

  return (
    <View style={[styles.root, { paddingTop: insets.top + 12 }]}>
      <View style={styles.topBar}>
        <Pressable onPress={onBack} accessibilityRole="button" accessibilityLabel="Back" hitSlop={8}>
          <Ionicons name="chevron-back" size={24} color={colors.textSecondary} />
        </Pressable>
        <Text variant="titleSm">Dictionary</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingTop: 16, paddingBottom: insets.bottom + 28, gap: 20 }}
      >
        <Card padding={14}>
          <Text variant="button" style={{ marginBottom: 2 }}>Vocabulary</Text>
          <Text variant="bodyXs" color={colors.textMuted} style={{ marginBottom: 10 }}>
            Names, products, acronyms — spelled how you want them. Tap a word to remove it.
          </Text>
          <View style={styles.chipWrap}>
            {dict.vocabulary.length === 0 ? (
              <Text variant="caption" color={colors.textSubtle}>No words yet.</Text>
            ) : dict.vocabulary.map((w, i) => (
              <Pressable key={`${w}-${i}`} onPress={() => removeWord(i)} style={styles.chip}>
                <Text variant="caption" color={colors.primary}>{w}</Text>
                <Ionicons name="close" size={12} color={colors.primary} />
              </Pressable>
            ))}
          </View>
          <View style={styles.dictRow}>
            <TextInput
              value={newWord} onChangeText={setNewWord} placeholder="Add a word…"
              placeholderTextColor={colors.textMuted} style={[styles.dictInput, { flex: 1 }]}
              autoCapitalize="none" onSubmitEditing={addWord} returnKeyType="done"
            />
            <Button label="Add" variant="ghost" onPress={addWord} style={{ flex: 0 }} />
          </View>
        </Card>

        <Card padding={14}>
          <Text variant="button" style={{ marginBottom: 2 }}>Replacement rules</Text>
          <Text variant="bodyXs" color={colors.textMuted} style={{ marginBottom: 10 }}>
            Fix persistent mishearings. Editing a transcription teaches one automatically.
          </Text>
          {dict.replacements.map((r, i) => (
            <View key={`${r.from}-${i}`} style={styles.repRow}>
              <Text variant="caption" color={colors.textMuted}>{r.from}</Text>
              <Ionicons name="arrow-forward" size={12} color={colors.textSubtle} />
              <Text variant="caption" style={{ flex: 1 }}>{r.to}</Text>
              <Pressable onPress={() => removeRep(i)} hitSlop={8}>
                <Ionicons name="close" size={14} color={colors.textMuted} />
              </Pressable>
            </View>
          ))}
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
        </Card>
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bgScreen, paddingHorizontal: 18 },
  topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 },
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
