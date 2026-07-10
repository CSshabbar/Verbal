import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { View, StyleSheet, Pressable, TextInput, ScrollView, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text, Visualizer, MarkdownNote, AudioSegmentPlayer } from '../components';
import { colors, radius } from '../theme';
import { useNotes, Note } from '../hooks/useNotes';
import { useRecorder } from '../hooks/useRecorder';

type Props = {
  noteId: string | null; // null = create new
  onBack: () => void;
};

// A note carries markdown structure worth rendering (headings / bullets /
// task-list items) rather than being shown as a raw text field.
const MARKDOWN_RE = /(^|\n)\s*(#{1,3}\s|[-*]\s\[[ xX]\]|[-*]\s)/;

/**
 * Screen 4b — Note editor. Voice-typing-first, now Notes-v2 aware
 * (NOTES_ENHANCEMENT_SWARM.md): dictation runs through the AI-cleanup + audio
 * linkage save path, formatted content renders as interactive markdown/checklists,
 * "show original" reveals the raw transcript, and "Reformat"/"Retry formatting"
 * re-runs cleanup. Everything fails closed — a formatting or playback problem
 * never breaks the record→transcribe→save path.
 */
export const NoteEditorScreen: React.FC<Props> = ({ noteId, onBack }) => {
  const insets = useSafeAreaInsets();
  const { getNote, updateNote, createNote, saveDictation, reformatNote, flags } = useNotes();
  const [note, setNote] = useState<Note | null>(() => (noteId ? getNote(noteId) : null));
  const [title, setTitle] = useState(note?.title ?? '');
  const [body, setBody] = useState(note?.body ?? '');
  const [dictating, setDictating] = useState(false);
  const [busy, setBusy] = useState(false);         // AI cleanup call in flight
  const [showOriginal, setShowOriginal] = useState(false);
  const [editingRaw, setEditingRaw] = useState(false);

  // Adopt an existing note from the store once it loads (avoids creating a
  // duplicate when the notes list hasn't hydrated yet); create only for a genuine
  // new-note intent (noteId === null).
  useEffect(() => {
    if (note) return;
    if (noteId) {
      const found = getNote(noteId);
      if (found) { setNote(found); setTitle(found.title); setBody(found.body); }
    } else {
      setNote(createNote({ title, body }));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [note, noteId, getNote]);

  // Auto-save typed edits. Typed edits NEVER trigger AI cleanup (Design
  // Decision 2) — that only happens via the dictation path / explicit Reformat.
  useEffect(() => {
    if (!note) return;
    updateNote(note.id, { title, body });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, body]);

  const { start, stop, durationMs, partialText } = useRecorder();

  const hasMarkdown = useMemo(() => MARKDOWN_RE.test(body), [body]);
  const segments = note?.audioSegments ?? [];
  const canReformat = !!(note && ((note.rawContent && note.rawContent.trim()) || body.trim()));

  const toggleDictate = useCallback(async () => {
    if (dictating) {
      setDictating(false);
      let result;
      try {
        result = await stop();
      } catch {
        return; // recorder already surfaced the error; keep existing content
      }
      if (!result?.text) return;

      // Make sure a note row exists to attach the dictation to.
      let target = note;
      if (!target) { target = createNote({ title, body }); setNote(target); }

      // Route through the AI-cleanup + audio-linkage save path (runs cleanup once
      // for this segment, unions the recording into audio_segments).
      setBusy(true);
      try {
        const saved = await saveDictation(target.id, { rawText: result.text, recordingUri: result.uri });
        if (saved) {
          setNote(saved);
          setTitle(saved.title);
          setBody(saved.body);
          setEditingRaw(false);
          setShowOriginal(false);
        } else {
          // Fail closed: never lose the transcript even if the save path bailed.
          setBody(b => (b ? b + ' ' : '') + result!.text);
        }
      } finally {
        setBusy(false);
      }
    } else {
      try {
        await start();
        setDictating(true);
      } catch {
        /* permission/hardware error already logged by the recorder */
      }
    }
  }, [dictating, stop, start, note, title, body, createNote, saveDictation]);

  const doReformat = useCallback(async () => {
    if (!note) return;
    setBusy(true);
    try {
      const saved = await reformatNote(note.id);
      if (saved) {
        setNote(saved);
        setTitle(saved.title);
        setBody(saved.body);
        setEditingRaw(false);
        setShowOriginal(false);
      }
    } finally {
      setBusy(false);
    }
  }, [note, reformatNote]);

  // Flip a task-list item on its ORIGINAL source line and persist (autosave).
  const toggleChecklistLine = useCallback((lineIndex: number) => {
    setBody(prev => {
      const lines = prev.split('\n');
      const ln = lines[lineIndex];
      if (ln == null) return prev;
      if (/[-*]\s+\[\s\]/.test(ln)) lines[lineIndex] = ln.replace(/([-*]\s+)\[\s\]/, '$1[x]');
      else if (/[-*]\s+\[[xX]\]/.test(ln)) lines[lineIndex] = ln.replace(/([-*]\s+)\[[xX]\]/, '$1[ ]');
      else return prev;
      return lines.join('\n');
    });
  }, []);

  const renderMarkdown = hasMarkdown && !editingRaw && !showOriginal;

  return (
    <View style={[styles.root, { paddingTop: insets.top + 10, paddingBottom: insets.bottom + 6 }]}>
      <View style={styles.topBar}>
        <Pressable onPress={onBack} accessibilityRole="button" accessibilityLabel="Back">
          <Ionicons name="chevron-back" size={24} color={colors.textSecondary} />
        </Pressable>
        <SavedIndicator busy={busy} />
        {hasMarkdown && !showOriginal ? (
          <Pressable
            onPress={() => setEditingRaw(e => !e)}
            accessibilityRole="button"
            accessibilityLabel={editingRaw ? 'Done editing' : 'Edit raw text'}
          >
            <Ionicons name={editingRaw ? 'checkmark' : 'create-outline'} size={22} color={colors.textSecondary} />
          </Pressable>
        ) : (
          <View style={{ width: 22 }} />
        )}
      </View>

      <TextInput
        value={title}
        onChangeText={setTitle}
        placeholder="Untitled note"
        placeholderTextColor={colors.textSubtle}
        style={styles.title}
        multiline={false}
        accessibilityLabel="Note title"
      />

      {/* Notes-v2 affordances: reformat / retry, show original. */}
      {(canReformat || note?.rawContent) ? (
        <View style={styles.affordances}>
          {note?.formatFailed ? (
            <Chip icon="refresh" label="Retry formatting" onPress={doReformat} disabled={busy} accent />
          ) : canReformat ? (
            <Chip icon="sparkles-outline" label="Reformat" onPress={doReformat} disabled={busy} />
          ) : null}
          {note?.rawContent ? (
            <Chip
              icon={showOriginal ? 'document-text-outline' : 'reader-outline'}
              label={showOriginal ? 'Show formatted' : 'Show original'}
              onPress={() => setShowOriginal(s => !s)}
              disabled={busy}
            />
          ) : null}
        </View>
      ) : null}

      {/* Per-segment playback (Feature 4). No control at all when there's no audio. */}
      {flags.audio && segments.length > 0 ? (
        <View style={styles.segments}>
          {segments.map((seg, i) => (
            <AudioSegmentPlayer key={seg.id} url={seg.url} createdAt={seg.created_at} index={i} />
          ))}
        </View>
      ) : null}

      <ScrollView style={{ flex: 1 }} keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingBottom: 40 }}>
        {showOriginal ? (
          <View>
            <Text variant="metaSm" color={colors.textSubtle} style={{ marginBottom: 8 }}>ORIGINAL TRANSCRIPT</Text>
            <Text variant="bodyXs" color={colors.textMuted} selectable style={{ lineHeight: 21 }}>
              {note?.rawContent}
            </Text>
          </View>
        ) : renderMarkdown ? (
          <MarkdownNote content={body} onToggleLine={toggleChecklistLine} />
        ) : (
          <TextInput
            value={body}
            onChangeText={setBody}
            placeholder="Tap the mic to dictate, or type…"
            placeholderTextColor={colors.textSubtle}
            style={styles.body}
            multiline
            textAlignVertical="top"
            accessibilityLabel="Note content"
          />
        )}
        {dictating && partialText ? (
          <Text variant="bodySm" style={{ backgroundColor: colors.primarySoft, color: colors.primaryAccent, paddingHorizontal: 2, marginTop: 8 }}>
            {' '}{partialText}
          </Text>
        ) : null}
      </ScrollView>

      {dictating ? (
        <View style={styles.dictStrip}>
          <Visualizer active heights={[14, 16, 14, 16, 14]} barWidth={3} gap={3} style={{ height: 16 }} />
          <Text variant="bodyXs" color={colors.primaryAccent} style={{ flex: 1 }}>
            Listening{partialText ? `… "${partialText.slice(-32)}"` : '…'}
          </Text>
          <Text variant="metaSm" color={colors.primary}>{fmt(durationMs)}</Text>
        </View>
      ) : busy ? (
        <View style={styles.dictStrip}>
          <ActivityIndicator size="small" color={colors.primary} />
          <Text variant="bodyXs" color={colors.primaryAccent} style={{ flex: 1 }}>Formatting…</Text>
        </View>
      ) : null}

      <View style={styles.dock}>
        <Pressable style={styles.iconDock} accessibilityRole="button" accessibilityLabel="Keyboard">
          <Ionicons name={'keyboard-outline' as any} size={24} color={colors.textSecondary} />
        </Pressable>
        <Pressable
          onPress={toggleDictate}
          disabled={busy}
          style={[styles.micDock, dictating && { transform: [{ scale: 1.05 }] }, busy && { opacity: 0.5 }]}
          accessibilityRole="button"
          accessibilityLabel={dictating ? 'Stop dictation' : 'Start dictation'}
        >
          <Ionicons name={dictating ? 'square' : 'mic'} size={30} color={colors.primaryInk} />
        </Pressable>
        <Pressable onPress={onBack} style={{ padding: 10 }} accessibilityRole="button" accessibilityLabel="Done">
          <Text variant="button" color={colors.primary}>Done</Text>
        </Pressable>
      </View>
    </View>
  );
};

const Chip: React.FC<{
  icon: any; label: string; onPress: () => void; disabled?: boolean; accent?: boolean;
}> = ({ icon, label, onPress, disabled, accent }) => (
  <Pressable
    onPress={onPress}
    disabled={disabled}
    style={[styles.chip, accent && styles.chipAccent, disabled && { opacity: 0.4 }]}
    accessibilityRole="button"
    accessibilityLabel={label}
    hitSlop={6}
  >
    <Ionicons name={icon} size={13} color={accent ? colors.primary : colors.textSecondary} />
    <Text variant="buttonSm" color={accent ? colors.primary : colors.textSecondary} style={{ fontSize: 13 }}>{label}</Text>
  </Pressable>
);

const SavedIndicator: React.FC<{ busy?: boolean }> = ({ busy }) => (
  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
    <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: busy ? colors.primary : colors.online }} />
    <Text variant="caption" color={colors.textSubtle}>{busy ? 'Formatting…' : 'Saved'}</Text>
  </View>
);

function fmt(ms: number) {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bgScreen, paddingHorizontal: 18 },
  topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 },
  title: {
    color: colors.textPrimary,
    fontFamily: 'Geist_600SemiBold',
    fontSize: 22,
    letterSpacing: -0.3,
    paddingVertical: 6,
    marginBottom: 8,
  },
  affordances: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingVertical: 6, paddingHorizontal: 11, borderRadius: 999,
    backgroundColor: colors.surface2, borderWidth: 1, borderColor: colors.borderSubtle,
  },
  chipAccent: { backgroundColor: colors.primarySoft, borderColor: colors.primaryBorder },
  segments: { gap: 8, marginBottom: 12 },
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
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.surface2,
    alignItems: 'center', justifyContent: 'center',
  },
  micDock: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: colors.inkLight,
    alignItems: 'center', justifyContent: 'center',
  },
});

export default NoteEditorScreen;
