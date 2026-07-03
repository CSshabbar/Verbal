import React, { useState, useEffect, useCallback } from 'react';
import { View, StyleSheet, Pressable, TextInput, ScrollView } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text, Visualizer } from '../components';
import { colors, radius } from '../theme';
import { useNotes, Note } from '../hooks/useNotes';
import { useRecorder } from '../hooks/useRecorder';

type Props = {
  noteId: string | null; // null = create new
  onBack: () => void;
};

/**
 * Screen 4b — Note editor. Voice-typing-first.
 * Bottom dock: keyboard toggle · big mic · Done.
 * When dictating, a strip above the dock shows live partial transcription.
 */
export const NoteEditorScreen: React.FC<Props> = ({ noteId, onBack }) => {
  const insets = useSafeAreaInsets();
  const { getNote, updateNote, createNote } = useNotes();
  const [note, setNote] = useState<Note | null>(() => noteId ? getNote(noteId) : null);
  const [title, setTitle] = useState(note?.title ?? '');
  const [body, setBody] = useState(note?.body ?? '');
  const [dictating, setDictating] = useState(false);

  // Auto-save on changes (debounced in the hook).
  useEffect(() => {
    if (!note) {
      const created = createNote({ title, body });
      setNote(created);
      return;
    }
    updateNote(note.id, { title, body });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, body]);

  const { start, stop, durationMs, status, partialText } = useRecorder();

  const toggleDictate = useCallback(async () => {
    if (dictating) {
      const result = await stop();
      // Append final transcribed text into the body.
      if (result?.text) setBody(b => (b ? b + ' ' : '') + result.text);
      setDictating(false);
    } else {
      await start();
      setDictating(true);
    }
  }, [dictating, start, stop]);

  return (
    <View style={[styles.root, { paddingTop: insets.top + 10, paddingBottom: insets.bottom + 6 }]}>
      <View style={styles.topBar}>
        <Pressable onPress={onBack}>
          <Ionicons name="chevron-back" size={24} color={colors.textSecondary} />
        </Pressable>
        <SavedIndicator />
        <Pressable>
          <Ionicons name="ellipsis-horizontal" size={24} color={colors.textSecondary} />
        </Pressable>
      </View>

      <TextInput
        value={title}
        onChangeText={setTitle}
        placeholder="Untitled note"
        placeholderTextColor={colors.textSubtle}
        style={styles.title}
        multiline={false}
      />

      <ScrollView style={{ flex: 1 }} keyboardShouldPersistTaps="handled">
        <TextInput
          value={body}
          onChangeText={setBody}
          placeholder="Tap the mic to dictate, or type…"
          placeholderTextColor={colors.textSubtle}
          style={styles.body}
          multiline
          textAlignVertical="top"
        />
        {dictating && partialText ? (
          <Text variant="bodySm" style={{ backgroundColor: colors.primarySoft, color: colors.primaryAccent, paddingHorizontal: 2 }}>
            {' '}{partialText}
          </Text>
        ) : null}
      </ScrollView>

      {dictating ? (
        <View style={styles.dictStrip}>
          <Visualizer
            active
            heights={[14, 16, 14, 16, 14]}
            barWidth={3}
            gap={3}
            style={{ height: 16 }}
          />
          <Text variant="bodyXs" color={colors.primaryAccent} style={{ flex: 1 }}>
            Listening{partialText ? `… "${partialText.slice(-32)}"` : '…'}
          </Text>
          <Text variant="metaSm" color={colors.primary}>{fmt(durationMs)}</Text>
        </View>
      ) : null}

      <View style={styles.dock}>
        <Pressable style={styles.iconDock}>
          <Ionicons name={'keyboard-outline' as any} size={24} color={colors.textSecondary} />
        </Pressable>
        <Pressable
          onPress={toggleDictate}
          style={[
            styles.micDock,
            dictating && { transform: [{ scale: 1.05 }] },
          ]}
        >
          <Ionicons
            name={dictating ? 'square' : 'mic'}
            size={30}
            color={colors.primaryInk}
          />
        </Pressable>
        <Pressable onPress={onBack} style={{ padding: 10 }}>
          <Text variant="button" color={colors.primary}>Done</Text>
        </Pressable>
      </View>
    </View>
  );
};

const SavedIndicator: React.FC = () => (
  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
    <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.online }} />
    <Text variant="caption" color={colors.textSubtle}>Saved</Text>
  </View>
);

function fmt(ms: number) {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 18,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  title: {
    color: colors.textPrimary,
    fontFamily: 'Geist_600SemiBold',
    fontSize: 22,
    letterSpacing: -0.3,
    paddingVertical: 6,
    marginBottom: 8,
  },
  body: {
    color: 'rgba(240, 240, 240, 0.85)',
    fontFamily: 'Geist_400Regular',
    fontSize: 13,
    lineHeight: 21,
    minHeight: 200,
    paddingBottom: 40,
  },
  dictStrip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: radius.lg,
    backgroundColor: colors.primarySoft,
    borderWidth: 1,
    borderColor: colors.primaryBorder,
    marginTop: 8,
    marginBottom: 8,
  },
  dock: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 4,
    paddingTop: 12,
  },
  iconDock: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  micDock: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.inkLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default NoteEditorScreen;
