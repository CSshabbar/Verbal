import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  TextInput, Modal, Alert, Animated, Platform, ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import * as Haptics from 'expo-haptics';
import { Ionicons } from '@expo/vector-icons';
import { colors, fonts, radius } from '../lib/theme';
import { supabase } from '../lib/supabase';
import { getGroqKey, getUserId, getDeviceName, getDeviceId } from '../lib/storage';
import { transcribeAudio, formatNotes } from '../lib/groq';
import {
  getCachedNotes, mergeRemoteNote, addCachedNote,
  updateCachedNote, removeCachedNote, NoteEntry,
} from '../lib/notesStorage';
import { useAudioRecorder, RecordingPresets, AudioModule } from 'expo-audio';

type Filter = 'all' | 'pinned';

export default function NotesScreen() {
  const [notes,        setNotes]        = useState<NoteEntry[]>([]);
  const [filter,       setFilter]       = useState<Filter>('all');
  const [myDeviceId,   setMyDeviceId]   = useState('');
  const [showEditor,   setShowEditor]   = useState(false);
  const [editingNote,  setEditingNote]  = useState<NoteEntry | null>(null);
  const [editorTitle,  setEditorTitle]  = useState('');
  const [editorContent,setEditorContent]= useState('');
  const [autoFormat,   setAutoFormat]   = useState(false);
  const [formatting,   setFormatting]   = useState(false);
  const [recording,    setRecording]    = useState(false);
  const [transcribing, setTranscribing] = useState(false);

  const audioRecorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const channelRef    = useRef<ReturnType<typeof supabase.channel> | null>(null);

  useFocusEffect(useCallback(() => { getDeviceId().then(setMyDeviceId); }, []));

  useEffect(() => {
    let mounted = true;
    (async () => {
      const uid = await getUserId();
      if (!mounted) return;
      loadNotes(uid);
      subscribeNotes(uid);
    })();
    return () => {
      mounted = false;
      if (channelRef.current) { supabase.removeChannel(channelRef.current); }
    };
  }, []);

  const loadNotes = async (uid: string) => {
    const { data } = await supabase
      .from('notes')
      .select('*')
      .eq('user_id', uid)
      .order('updated_at', { ascending: false })
      .limit(200);
    if (data) {
      const mapped: NoteEntry[] = data.map((r: any) => ({
        id:          r.id,
        title:       r.title ?? '',
        content:     r.content ?? '',
        folder:      r.folder ?? '',
        is_pinned:   r.is_pinned ?? false,
        device_name: r.device_name ?? '',
        created_at:  r.created_at,
        updated_at:  r.updated_at,
        source:      'remote' as const,
      }));
      for (const n of mapped) await mergeRemoteNote(n);
      setNotes(await getCachedNotes());
    }
  };

  const subscribeNotes = (uid: string) => {
    if (channelRef.current) supabase.removeChannel(channelRef.current);
    channelRef.current = supabase
      .channel(`notes_${uid}`)
      .on('postgres_changes', {
        event:  '*',
        schema: 'public',
        table:  'notes',
        filter: `user_id=eq.${uid}`,
      }, async (payload: any) => {
        const eventType = payload.eventType;
        if (eventType === 'DELETE') {
          const deletedId = (payload.old as any)?.id;
          if (deletedId) setNotes(await removeCachedNote(deletedId));
        } else {
          const r = payload.new;
          const dn = await getDeviceId();
          const entry: NoteEntry = {
            id:          r.id,
            title:       r.title ?? '',
            content:     r.content ?? '',
            folder:      r.folder ?? '',
            is_pinned:   r.is_pinned ?? false,
            device_name: r.device_name ?? '',
            created_at:  r.created_at,
            updated_at:  r.updated_at,
            source:      'remote' as const,
          };
          setNotes(await mergeRemoteNote(entry));
        }
      })
      .subscribe();
  };

  const filtered = notes.filter(n => {
    if (filter === 'pinned') return n.is_pinned;
    return true;
  });

  const sorted = [...filtered].sort((a, b) => {
    if (a.is_pinned && !b.is_pinned) return -1;
    if (!a.is_pinned && b.is_pinned) return 1;
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
  });

  // ── Editor ────────────────────────────────────────────────────────────
  const openEditor = (note?: NoteEntry) => {
    setEditingNote(note ?? null);
    setEditorTitle(note?.title ?? '');
    setEditorContent(note?.content ?? '');
    setShowEditor(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  };

  const insertAtCursor = (text: string) => {
    setEditorContent(prev => prev ? `${prev}\n\n${text}` : text);
  };

  const startDictation = async () => {
    try {
      const status = await AudioModule.requestRecordingPermissionsAsync();
      if (!status.granted) { Alert.alert('Permission needed', 'Microphone required.'); return; }
      await audioRecorder.prepareToRecordAsync();
      audioRecorder.record();
      setRecording(true);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch (e) {
      setRecording(false);
    }
  };

  const stopDictation = async () => {
    setRecording(false);
    setTranscribing(true);
    try {
      await audioRecorder.stop();
      const uri = audioRecorder.uri;
      if (!uri) throw new Error('No audio');
      const apiKey = await getGroqKey();
      if (!apiKey) { Alert.alert('No API Key', 'Add Groq key in Settings.'); setTranscribing(false); return; }
      let text = await transcribeAudio(uri, apiKey);
      if (!text) { setTranscribing(false); return; }
      if (autoFormat) {
        setTranscribing(false);
        setFormatting(true);
        text = await formatNotes(text, apiKey);
        setFormatting(false);
      }
      insertAtCursor(text);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch (e: any) {
      Alert.alert('Dictation failed', e.message);
    } finally {
      setTranscribing(false);
    }
  };

  const handleFormatAi = async () => {
    if (!editorContent.trim()) return;
    const apiKey = await getGroqKey();
    if (!apiKey) { Alert.alert('No API Key', 'Add Groq key in Settings.'); return; }
    setFormatting(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const formatted = await formatNotes(editorContent, apiKey);
    setEditorContent(formatted);
    setFormatting(false);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  };

  const handleDictationBtn = () => {
    if (recording) stopDictation();
    else startDictation();
  };

  const saveNote = async () => {
    const uid   = await getUserId();
    const dn    = await getDeviceName();
    const now   = new Date().toISOString();
    const title = editorTitle.trim();
    const content = editorContent;

    if (editingNote) {
      const { error } = await supabase.from('notes').update({
        title, content, device_name: dn, updated_at: now,
      }).eq('id', editingNote.id);
      if (error) { Alert.alert('Save failed', error.message); return; }
      setNotes(await updateCachedNote(editingNote.id, { title, content, updated_at: now }));
    } else {
      const { data, error } = await supabase.from('notes').insert({
        user_id: uid, title, content, device_name: dn,
        created_at: now, updated_at: now,
      }).select('id').single();
      if (error) { Alert.alert('Save failed', error.message); return; }
      const id = data?.id;
      if (id) {
        const entry: NoteEntry = {
          id, title, content, folder: '', is_pinned: false,
          device_name: dn, created_at: now, updated_at: now,
          source: 'local',
        };
        setNotes(await addCachedNote(entry));
      }
    }
    closeEditor();
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  };

  const closeEditor = () => {
    setShowEditor(false);
    setEditingNote(null);
    setEditorTitle('');
    setEditorContent('');
    setAutoFormat(false);
  };

  const togglePin = async (note: NoteEntry) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const newPin = !note.is_pinned;
    await supabase.from('notes').update({ is_pinned: newPin }).eq('id', note.id);
    setNotes(await updateCachedNote(note.id, { is_pinned: newPin }));
  };

  const handleDelete = (note: NoteEntry) => {
    Alert.alert('Delete note', `"${note.title || 'Untitled'}"?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete', style: 'destructive',
        onPress: async () => {
          await supabase.from('notes').delete().eq('id', note.id);
          setNotes(await removeCachedNote(note.id));
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
        },
      },
    ]);
  };

  // ── Formatting helpers ────────────────────────────────────────────────
  const formatAction = (prefix: string, suffix = '') => {
    setEditorContent(prev => {
      const lines = prev.split('\n');
      const last = lines[lines.length - 1];
      if (last.startsWith(prefix)) {
        lines[lines.length - 1] = last.slice(prefix.length);
        return lines.join('\n');
      }
      if (prev === '') return prefix;
      return `${prev}\n${prefix}`;
    });
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  };

  // ── Card ──────────────────────────────────────────────────────────────
  const renderCard = ({ item }: { item: NoteEntry }) => {
    const isEditing = editingNote?.id === item.id;
    const preview   = item.content?.replace(/[#*`>-]/g, '').slice(0, 100) ?? '';
    const wc        = item.content?.split(/\s+/).filter(Boolean).length ?? 0;
    const timeAgo   = item.updated_at
      ? _timeAgo(new Date(item.updated_at))
      : '';

    return (
      <TouchableOpacity
        style={[s.card, item.is_pinned && s.cardPinned]}
        activeOpacity={0.7}
        onPress={() => openEditor(item)}
        onLongPress={() => togglePin(item)}
      >
        <View style={[s.badge, item.is_pinned && s.badgePinned]}>
          {item.is_pinned ? (
            <Ionicons name="bookmark" size={14} color={colors.accent} />
          ) : (
            <Ionicons name="document-text-outline" size={14} color={colors.cardSub} />
          )}
        </View>
        <View style={s.cardBody}>
          <Text style={s.cardTitle} numberOfLines={1}>
            {item.title || 'Untitled'}
          </Text>
          {preview ? (
            <Text style={s.cardPreview} numberOfLines={2}>{preview}</Text>
          ) : null}
          <View style={s.cardMeta}>
            <Text style={s.cardMetaTxt}>{wc} words</Text>
            {timeAgo ? <Text style={s.cardMetaTxt}>· {timeAgo}</Text> : null}
            {item.device_name && !isEditing ? (
              <View style={s.deviceTag}>
                <Text style={s.deviceTxt}>{item.device_name}</Text>
              </View>
            ) : null}
          </View>
        </View>
        <TouchableOpacity style={s.deleteBtn} onPress={() => handleDelete(item)}>
          <Ionicons name="trash-outline" size={16} color={colors.cardSub} />
        </TouchableOpacity>
      </TouchableOpacity>
    );
  };

  const FILTERS: { key: Filter; label: string }[] = [
    { key: 'all',    label: 'All' },
    { key: 'pinned', label: 'Pinned' },
  ];

  return (
    <View style={s.root}>
      {/* ── Hero ── */}
      <View style={s.hero}>
        <SafeAreaView edges={['top']}>
          <View style={s.heroRow}>
            <View>
              <Text style={s.headline}>Notes</Text>
              <Text style={s.sub}>{sorted.length} notes</Text>
            </View>
            <TouchableOpacity style={s.refreshBtn} onPress={() => loadNotesInner()}>
              <Ionicons name="refresh-outline" size={18} color={colors.heroText} />
            </TouchableOpacity>
          </View>
          <View style={s.pills}>
            {FILTERS.map(f => (
              <TouchableOpacity
                key={f.key}
                style={[s.pill, filter === f.key && s.pillActive]}
                onPress={() => setFilter(f.key)}
              >
                <Text style={[s.pillTxt, filter === f.key && s.pillTxtActive]}>{f.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </SafeAreaView>
      </View>

      {/* ── Sheet ── */}
      <View style={s.sheet}>
        {sorted.length === 0 ? (
          <View style={s.empty}>
            <Ionicons name="document-text-outline" size={44} color={colors.cardSub} />
            <Text style={s.emptyTxt}>No notes yet</Text>
            <Text style={s.emptySub}>Tap + to create a voice note or idea</Text>
          </View>
        ) : (
          <FlatList
            data={sorted}
            keyExtractor={item => item.id}
            contentContainerStyle={{ paddingBottom: 100 }}
            showsVerticalScrollIndicator={false}
            renderItem={renderCard}
          />
        )}
      </View>

      {/* ── FAB ── */}
      <TouchableOpacity style={s.fab} onPress={() => openEditor()} activeOpacity={0.85}>
        <Ionicons name="add" size={28} color="#fff" />
      </TouchableOpacity>

      {/* ── Editor Modal ── */}
      <Modal visible={showEditor} animationType="slide" presentationStyle="fullScreen">
        <View style={s.editorRoot}>
          <SafeAreaView edges={['top']}>
            <View style={s.editorHeader}>
              <TouchableOpacity onPress={closeEditor}>
                <Ionicons name="close" size={22} color={colors.heroText} />
              </TouchableOpacity>
              <Text style={s.editorTitle}>
                {editingNote ? 'Edit Note' : 'New Note'}
              </Text>
              <TouchableOpacity onPress={saveNote}>
                <Text style={s.saveTxt}>Save</Text>
              </TouchableOpacity>
            </View>

            {/* Auto-format toggle */}
            <View style={s.autoRow}>
              <TouchableOpacity style={[s.autoBtn, autoFormat && s.autoBtnOn]} onPress={() => setAutoFormat(!autoFormat)}>
                <Ionicons name="flash-outline" size={13} color={autoFormat ? '#fff' : colors.heroMuted} />
                <Text style={[s.autoBtnTxt, autoFormat && s.autoBtnTxtOn]}>Auto AI</Text>
              </TouchableOpacity>
            </View>
          </SafeAreaView>

          {/* Title */}
          <TextInput
            style={s.titleInput}
            value={editorTitle}
            onChangeText={setEditorTitle}
            placeholder="Note title..."
            placeholderTextColor={colors.cardSub}
          />

          {/* Formatting toolbar */}
          <View style={s.toolbar}>
            <TouchableOpacity style={s.toolBtn} onPress={() => formatAction('## ')}>
              <Ionicons name="text" size={16} color={colors.cardText} />
            </TouchableOpacity>
            <TouchableOpacity style={s.toolBtn} onPress={() => formatAction('**', '**')}>
              <Ionicons name="text" size={16} color={colors.cardText} style={{ fontWeight: '700' }} />
            </TouchableOpacity>
            <TouchableOpacity style={s.toolBtn} onPress={() => formatAction('- ')}>
              <Ionicons name="list" size={16} color={colors.cardText} />
            </TouchableOpacity>
            <TouchableOpacity style={s.toolBtn} onPress={() => formatAction('1. ')}>
              <Ionicons name="list-circle-outline" size={16} color={colors.cardText} />
            </TouchableOpacity>
            <View style={{ flex: 1 }} />

            {/* Mic */}
            <TouchableOpacity
              style={[s.toolBtn, s.micBtn, recording && s.micBtnOn]}
              onPress={handleDictationBtn}
            >
              <Ionicons
                name={recording ? 'stop' : transcribing ? 'hourglass-outline' : 'mic'}
                size={16}
                color={recording ? '#fff' : colors.cardText}
              />
            </TouchableOpacity>

            {/* AI Format */}
            <TouchableOpacity
              style={[s.toolBtn, s.aiBtn, formatting && s.aiBtnOn]}
              onPress={handleFormatAi}
              disabled={formatting}
            >
              <Ionicons name="sparkles" size={15} color={formatting ? '#fff' : colors.accent} />
            </TouchableOpacity>

            {/* Delete (edit mode only) */}
            {editingNote ? (
              <TouchableOpacity style={[s.toolBtn, s.delBtn]} onPress={() => { closeEditor(); handleDelete(editingNote!); }}>
                <Ionicons name="trash-outline" size={16} color={colors.accent} />
              </TouchableOpacity>
            ) : null}
          </View>

          {/* Content editor */}
          <ScrollView style={s.editorBody} keyboardShouldPersistTaps="handled">
            <TextInput
              style={s.contentInput}
              value={editorContent}
              onChangeText={setEditorContent}
              multiline
              placeholder={recording ? 'Listening...' : 'Start typing or tap the mic...'}
              placeholderTextColor={colors.cardSub}
              textAlignVertical="top"
              autoCorrect
            />
            {formatting && (
              <View style={s.formattingOverlay}>
                <Ionicons name="sparkles" size={20} color={colors.accent} />
                <Text style={s.formattingTxt}>Formatting with AI...</Text>
              </View>
            )}
          </ScrollView>
        </View>
      </Modal>
    </View>
  );

  function loadNotesInner() {
    getUserId().then(loadNotes);
  }
}

// ── Time helper ──────────────────────────────────────────────────────────
function _timeAgo(date: Date): string {
  const now   = new Date();
  const diff  = now.getTime() - date.getTime();
  const mins  = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days  = Math.floor(diff / 86_400_000);
  if (mins < 1)    return 'now';
  if (mins < 60)   return `${mins}m ago`;
  if (hours < 24)  return `${hours}h ago`;
  if (days < 7)    return `${days}d ago`;
  return date.toLocaleDateString();
}

// ── Styles ───────────────────────────────────────────────────────────────
const s = StyleSheet.create({
  root:       { flex: 1, backgroundColor: colors.heroBg },
  hero:       { backgroundColor: colors.heroBg, paddingHorizontal: 20, paddingBottom: 14 },
  heroRow:    { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', marginTop: 8 },
  headline:   { fontSize: 28, fontWeight: fonts.bold, color: colors.heroText },
  sub:        { fontSize: 12, color: colors.heroMuted, marginTop: 3 },
  refreshBtn: { width: 34, height: 34, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.08)', alignItems: 'center', justifyContent: 'center', marginTop: 8 },
  pills:      { flexDirection: 'row', gap: 8, marginTop: 14 },
  pill:       { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.08)' },
  pillActive: { backgroundColor: colors.accent },
  pillTxt:    { fontSize: 12, color: colors.heroMuted, fontWeight: fonts.medium },
  pillTxtActive: { color: '#fff' },

  sheet:      { flex: 1, backgroundColor: colors.sheetBg, borderTopLeftRadius: 28, borderTopRightRadius: 28, paddingTop: 12, paddingHorizontal: 14 },

  empty:      { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 8, paddingBottom: 80 },
  emptyTxt:   { fontSize: 16, color: colors.cardText, fontWeight: fonts.medium },
  emptySub:   { fontSize: 13, color: colors.cardSub, textAlign: 'center', paddingHorizontal: 32 },

  card:          { flexDirection: 'row', alignItems: 'flex-start', backgroundColor: colors.cardBg, borderRadius: radius.md, padding: 12, marginBottom: 8, shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 1 },
  cardPinned:    { backgroundColor: '#FFF7F2', borderWidth: 1.5, borderColor: 'rgba(224,90,43,0.25)' },
  badge:         { width: 36, height: 36, borderRadius: 10, backgroundColor: colors.iconGray, alignItems: 'center', justifyContent: 'center', marginRight: 10, marginTop: 2 },
  badgePinned:   { backgroundColor: '#FFE8D6' },
  cardBody:      { flex: 1 },
  cardTitle:     { fontSize: 14, fontWeight: fonts.semibold, color: colors.cardText, marginBottom: 2 },
  cardPreview:   { fontSize: 12, color: colors.cardSub, lineHeight: 17, marginBottom: 4 },
  cardMeta:      { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  cardMetaTxt:   { fontSize: 11, color: colors.cardSub },
  deviceTag:     { backgroundColor: colors.iconGray, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  deviceTxt:     { fontSize: 10, color: colors.cardSub },
  deleteBtn:     { padding: 6, marginLeft: 4 },

  fab:       { position: 'absolute', bottom: 28, right: 22, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.accent, alignItems: 'center', justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.22, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 6 },

  // Editor
  editorRoot:   { flex: 1, backgroundColor: colors.heroBg },
  editorHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingVertical: 14 },
  editorTitle:  { fontSize: 16, fontWeight: fonts.semibold, color: colors.heroText },
  saveTxt:      { fontSize: 15, fontWeight: fonts.semibold, color: colors.accent },

  autoRow:      { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, marginBottom: 6 },
  autoBtn:      { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: 'rgba(255,255,255,0.08)', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16 },
  autoBtnOn:    { backgroundColor: colors.accent },
  autoBtnTxt:   { fontSize: 11, color: colors.heroMuted, fontWeight: fonts.medium },
  autoBtnTxtOn: { color: '#fff' },

  titleInput:   { fontSize: 20, fontWeight: fonts.bold, color: colors.heroText, paddingHorizontal: 20, paddingVertical: 14, backgroundColor: 'rgba(255,255,255,0.04)', marginHorizontal: 16, borderRadius: 12, marginBottom: 6 },

  toolbar:   { flexDirection: 'row', alignItems: 'center', gap: 2, paddingHorizontal: 16, paddingVertical: 8, backgroundColor: colors.sheetBg, borderTopLeftRadius: 16, borderTopRightRadius: 16 },
  toolBtn:   { width: 36, height: 36, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.iconGray },
  micBtn:    { backgroundColor: colors.heroBg, marginLeft: 4 },
  micBtnOn:  { backgroundColor: colors.accent },
  aiBtn:     { marginLeft: 4 },
  aiBtnOn:   { backgroundColor: colors.accent },
  delBtn:    { marginLeft: 4, backgroundColor: 'rgba(224,90,43,0.10)' },

  editorBody: { flex: 1, backgroundColor: colors.sheetBg, paddingHorizontal: 16 },
  contentInput: { fontSize: 15, color: colors.cardText, lineHeight: 24, fontWeight: fonts.light, minHeight: 200, paddingBottom: 40 },

  formattingOverlay: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 16, alignSelf: 'center' },
  formattingTxt:     { fontSize: 13, color: colors.accent, fontWeight: fonts.medium },
});
