import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  View, StyleSheet, Pressable, TextInput, ScrollView, ActivityIndicator,
  KeyboardAvoidingView, Platform, AppState,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text, Visualizer, MarkdownNote, AudioSegmentPlayer } from '../components';
import { colors, radius, pressedStyle } from '../theme';
import { useNotes, Note } from '../hooks/useNotes';
import { useRecorder } from '../hooks/useRecorder';
import * as recordings from '../../lib/recordings';

/** Autosave debounce. The editor used to call updateNote on EVERY keystroke —
 *  one AsyncStorage write and one Supabase update per character, landing out of
 *  order (IDI-176 §7). */
const SAVE_DEBOUNCE_MS = 500;

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
  const {
    notes, getNote, updateNote, createNote, saveDictation, reformatNote, resolveConflict, flags,
  } = useNotes();
  const [note, setNote] = useState<Note | null>(() => (noteId ? getNote(noteId) : null));
  const [title, setTitle] = useState(note?.title ?? '');
  const [body, setBody] = useState(note?.body ?? '');
  const [busy, setBusy] = useState(false);         // AI cleanup call in flight
  const [showOriginal, setShowOriginal] = useState(false);
  const [editingRaw, setEditingRaw] = useState(false);
  const [message, setMessage] = useState('');      // dictation / conflict feedback

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

  /* ── debounced autosave (IDI-176 §7) ──────────────────────────────────────
   * Typed edits NEVER trigger AI cleanup (Design Decision 2) — that only
   * happens via the dictation path / explicit Reformat. */
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queued = useRef<{ id: string; title: string; body: string } | null>(null);

  const flushSave = useCallback(() => {
    if (saveTimer.current) { clearTimeout(saveTimer.current); saveTimer.current = null; }
    const q = queued.current;
    queued.current = null;
    if (q) updateNote(q.id, { title: q.title, body: q.body });
  }, [updateNote]);

  useEffect(() => {
    if (!note) return;
    // Nothing changed (mount, or a re-render after a dictation save) — don't
    // schedule a write of the values we just read.
    if (title === note.title && body === note.body) return;
    queued.current = { id: note.id, title, body };
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(flushSave, SAVE_DEBOUNCE_MS);
  }, [title, body, note, flushSave]);

  // The debounce window must never eat the last keystrokes: flush on unmount…
  useEffect(() => () => { flushSave(); }, [flushSave]);
  // …and when the app leaves the foreground.
  useEffect(() => {
    const sub = AppState.addEventListener('change', (s) => { if (s !== 'active') flushSave(); });
    return () => sub.remove();
  }, [flushSave]);

  const handleBack = useCallback(() => { flushSave(); onBack(); }, [flushSave, onBack]);

  const discardQueuedSave = useCallback(() => {
    if (saveTimer.current) { clearTimeout(saveTimer.current); saveTimer.current = null; }
    queued.current = null;
  }, []);

  /* ── conflict pair (IDI-176 §9) ───────────────────────────────────────────
   * `mergeRemoteNote` keeps BOTH versions when two devices edited the same note
   * inside the 60 s window: the newer keeps the canonical id, the older is
   * stored locally as `<id>::conflict::<updated_at>`. Until now nothing rendered
   * either flag, so the pair just sat there.
   *
   * "View other copy" SWAPS the editor onto the other member rather than
   * navigating — this screen has no navigator handle (RootNavigator owns
   * routing), and swapping keeps the whole flow inside the one screen.
   */
  const otherCopy = useMemo(() => {
    if (!note?.conflict) return null;
    return note.conflictOf
      ? notes.find((n) => n.id === note.conflictOf) ?? null
      : notes.find((n) => n.conflictOf === note.id) ?? null;
  }, [note, notes]);

  const adopt = useCallback((n: Note) => {
    setNote(n); setTitle(n.title); setBody(n.body);
    setShowOriginal(false); setEditingRaw(false);
  }, []);

  const viewOtherCopy = useCallback(() => {
    if (!otherCopy) return;
    flushSave();
    discardQueuedSave();
    adopt(otherCopy);
  }, [otherCopy, flushSave, discardQueuedSave, adopt]);

  const keepThisVersion = useCallback(async () => {
    if (!note) return;
    // The queued autosave may target the copy's id, which is about to be
    // deleted — drop it; the content is re-applied below instead.
    discardQueuedSave();
    const canonicalId = note.conflictOf ?? note.id;
    const keep = note.conflictOf ? 'copy' : 'canonical';
    const resolved = await resolveConflict(canonicalId, keep).catch(() => null);
    if (!resolved) { setMessage("Couldn't resolve — try again."); return; }
    if (title !== resolved.title || body !== resolved.body) {
      // Whatever is on screen IS "this version" — carry any unsaved keystrokes
      // onto the surviving note.
      updateNote(canonicalId, { title, body });
      setNote({ ...resolved, title, body });
    } else {
      adopt(resolved);
    }
    setMessage('Kept this version.');
  }, [note, title, body, resolveConflict, updateNote, discardQueuedSave, adopt]);

  const { start, stop, pause, resume, cancel, status, durationMs, partialText } = useRecorder();
  const recording = status !== 'idle';   // recording OR paused
  const paused = status === 'paused';

  const hasMarkdown = useMemo(() => MARKDOWN_RE.test(body), [body]);
  const segments = note?.audioSegments ?? [];
  const canReformat = !!(note && ((note.rawContent && note.rawContent.trim()) || body.trim()));

  const startDictate = useCallback(async () => {
    try {
      await start();
    } catch {
      /* permission/hardware error already logged by the recorder */
    }
  }, [start]);

  // Finalize: stop → transcribe → AI-cleanup + audio-linkage save path (runs
  // cleanup once for this segment, unions the recording into audio_segments).
  const finishDictate = useCallback(async () => {
    let result;
    setMessage('');
    try {
      result = await stop();
    } catch {
      setMessage("Couldn't finish the recording — nothing was added.");
      return; // recorder already surfaced the error; keep existing content
    }
    // This used to be a bare `if (!result?.text) return;` — the user got no
    // feedback at all, and the audio the recorder had already persisted was
    // orphaned on disk with nothing referencing it (IDI-176 §10). Audio is
    // linked ONLY on a successful transcript, so a failure cleans up after
    // itself.
    if (!result?.text) {
      if (result?.uri) recordings.remove(result.uri).catch(() => {});
      setMessage(result?.status === 'failed'
        ? "Dictation failed — check your connection and try again."
        : "Didn't catch that — nothing was added.");
      return;
    }

    // Make sure a note row exists to attach the dictation to.
    let target = note;
    if (!target) { target = createNote({ title, body }); setNote(target); }

    setBusy(true);
    try {
      // Feed the RAW transcript to the note formatter, not the dictation-cleaned
      // text (IDI-179): useRecorder now runs the AI cleanup pass, and notes have
      // their OWN formatter (formatNoteWithTitle). Passing `text` here would
      // clean the same words twice — a second LLM call per dictated note, which
      // Hard Rule #12 exists to prevent — and would put cleaned text in
      // `raw_content`, which "Show original" renders.
      const saved = await saveDictation(target.id, { rawText: result.raw, recordingUri: result.uri });
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
  }, [stop, note, title, body, createNote, saveDictation]);

  const pauseResume = useCallback(() => {
    if (paused) resume(); else pause();
  }, [paused, pause, resume]);

  // Discard the in-progress recording — nothing is transcribed or saved.
  const cancelDictate = useCallback(async () => {
    try { await cancel(); } catch { /* fail closed */ }
  }, [cancel]);

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
    <KeyboardAvoidingView
      style={[styles.root, { paddingTop: insets.top + 10, paddingBottom: insets.bottom + 6 }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.topBar}>
        <Pressable
          onPress={handleBack}
          style={({ pressed }) => pressed && pressedStyle}
          accessibilityRole="button"
          accessibilityLabel="Back"
        >
          <Ionicons name="chevron-back" size={24} color={colors.textSecondary} />
        </Pressable>
        <SavedIndicator busy={busy} />
        {hasMarkdown && !showOriginal ? (
          <Pressable
            onPress={() => setEditingRaw(e => !e)}
            style={({ pressed }) => pressed && pressedStyle}
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

      {/* Conflict pair — both versions were kept; the user picks one. */}
      {note?.conflict ? (
        <View style={styles.conflictBox}>
          <View style={styles.conflictHead}>
            <Ionicons name="git-compare-outline" size={14} color={colors.primary} />
            <Text variant="buttonSm" color={colors.primary} style={{ flex: 1, fontSize: 13 }}>
              Edited on two devices
            </Text>
          </View>
          <Text variant="caption" color={colors.textMuted} style={{ marginBottom: 8 }}>
            {note.conflictOf
              ? 'You are viewing the other copy.'
              : 'Both versions were kept so nothing is lost.'}
          </Text>
          <View style={styles.conflictActions}>
            <Chip icon="checkmark" label="Keep this version" onPress={keepThisVersion} disabled={busy} accent />
            {otherCopy ? (
              <Chip
                icon="swap-horizontal"
                label={note.conflictOf ? 'View original' : 'View other copy'}
                onPress={viewOtherCopy}
                disabled={busy}
              />
            ) : null}
          </View>
        </View>
      ) : null}

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
        {recording && partialText ? (
          <Text variant="bodySm" style={{ backgroundColor: colors.primarySoft, color: colors.primaryAccent, paddingHorizontal: 2, marginTop: 8 }}>
            {' '}{partialText}
          </Text>
        ) : null}
      </ScrollView>

      {recording ? (
        <View style={styles.dictStrip}>
          <Visualizer active={!paused} heights={[14, 16, 14, 16, 14]} barWidth={3} gap={3} style={{ height: 16 }} />
          <Text variant="bodyXs" color={colors.primaryAccent} style={{ flex: 1 }}>
            {paused ? 'Paused' : `Listening${partialText ? `… "${partialText.slice(-32)}"` : '…'}`}
          </Text>
          <Text variant="metaSm" color={colors.primary}>{fmt(durationMs)}</Text>
        </View>
      ) : busy ? (
        <View style={styles.dictStrip}>
          <ActivityIndicator size="small" color={colors.primary} />
          <Text variant="bodyXs" color={colors.primaryAccent} style={{ flex: 1 }}>Formatting…</Text>
        </View>
      ) : message ? (
        <Pressable onPress={() => setMessage('')} style={styles.dictStrip} accessibilityRole="button" accessibilityLabel="Dismiss message">
          <Ionicons name="information-circle-outline" size={16} color={colors.primaryAccent} />
          <Text variant="bodyXs" color={colors.primaryAccent} style={{ flex: 1 }}>{message}</Text>
          <Ionicons name="close" size={14} color={colors.textMuted} />
        </Pressable>
      ) : null}

      <View style={styles.dock}>
        {recording ? (
          // While recording/paused: Cancel (discard) · Stop-and-save (center) · Pause/Resume.
          <>
            <View style={styles.dockSide}>
              <Pressable onPress={cancelDictate} style={({ pressed }) => [styles.sideBtn, pressed && pressedStyle]} accessibilityRole="button" accessibilityLabel="Cancel recording">
                <Ionicons name="close" size={22} color={colors.textSecondary} />
              </Pressable>
            </View>
            <Pressable
              onPress={finishDictate}
              disabled={busy}
              style={({ pressed }) => [styles.micDock, pressed && pressedStyle, busy && { opacity: 0.5 }]}
              accessibilityRole="button"
              accessibilityLabel="Stop and save"
            >
              <Ionicons name="checkmark" size={32} color={colors.primaryInk} />
            </Pressable>
            <View style={[styles.dockSide, { alignItems: 'flex-end' }]}>
              <Pressable onPress={pauseResume} style={({ pressed }) => [styles.sideBtn, pressed && pressedStyle]} accessibilityRole="button" accessibilityLabel={paused ? 'Resume recording' : 'Pause recording'}>
                <Ionicons name={paused ? 'play' : 'pause'} size={20} color={colors.textSecondary} />
              </Pressable>
            </View>
          </>
        ) : (
          // Idle: empty spacers keep the mic perfectly centered; Done at the right.
          <>
            <View style={styles.dockSide} />
            <Pressable
              onPress={startDictate}
              disabled={busy}
              style={({ pressed }) => [styles.micDock, pressed && pressedStyle, busy && { opacity: 0.5 }]}
              accessibilityRole="button"
              accessibilityLabel="Start dictation"
            >
              <Ionicons name="mic" size={30} color={colors.primaryInk} />
            </Pressable>
            <View style={[styles.dockSide, { alignItems: 'flex-end' }]}>
              <Pressable onPress={handleBack} hitSlop={8} style={({ pressed }) => [{ padding: 6 }, pressed && pressedStyle]} accessibilityRole="button" accessibilityLabel="Done">
                <Text variant="button" color={colors.primary}>Done</Text>
              </Pressable>
            </View>
          </>
        )}
      </View>
    </KeyboardAvoidingView>
  );
};

const Chip: React.FC<{
  icon: any; label: string; onPress: () => void; disabled?: boolean; accent?: boolean;
}> = ({ icon, label, onPress, disabled, accent }) => (
  <Pressable
    onPress={onPress}
    disabled={disabled}
    style={({ pressed }) => [styles.chip, accent && styles.chipAccent, pressed && pressedStyle, disabled && { opacity: 0.4 }]}
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
  conflictBox: {
    backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primaryBorder,
    borderRadius: radius.md, padding: 12, marginBottom: 12,
  },
  conflictHead: { flexDirection: 'row', alignItems: 'center', gap: 7, marginBottom: 4 },
  conflictActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
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
    justifyContent: 'center',
    paddingHorizontal: 4,
    paddingTop: 12,
  },
  dockSide: { flex: 1, justifyContent: 'center' },
  sideBtn: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: colors.surface2,
    borderWidth: 1, borderColor: colors.borderSubtle,
    alignItems: 'center', justifyContent: 'center',
  },
  micDock: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: colors.inkLight,
    alignItems: 'center', justifyContent: 'center',
  },
});

export default NoteEditorScreen;
