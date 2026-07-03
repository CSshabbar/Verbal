import React, { useState, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  Alert, TextInput, Share, Animated, Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import { Ionicons } from '@expo/vector-icons';
import { colors, fonts, radius } from '../lib/theme';
import { flumeColors, flumeFonts, flumeSpacing, flumeRadius } from '../lib/flumeTheme';
import {
  getHistory, clearHistory, updateEntry, deleteEntry,
  HistoryEntry, getDeviceId, getSyncEnabled,
} from '../lib/storage';
import { supabase } from '../lib/supabase';
import { useSync } from '../lib/useSync';

type Filter = 'all' | 'mine' | 'others' | 'pinned';

// ── Floating context menu ─────────────────────────────────────────────────────
interface MenuItem { icon: string; label: string; onPress: () => void; danger?: boolean }

function ContextMenu({
  items, top, right, onClose,
}: {
  items: MenuItem[]; top: number; right: number; onClose: () => void;
}) {
  const anim = useRef(new Animated.Value(0)).current;

  React.useEffect(() => {
    Animated.spring(anim, { toValue: 1, useNativeDriver: true, tension: 120, friction: 8 }).start();
  }, []);

  const dismiss = (fn?: () => void) => {
    Animated.timing(anim, { toValue: 0, duration: 120, useNativeDriver: true }).start(() => {
      onClose();
      fn?.();
    });
  };

  return (
    <>
      {/* Invisible full-screen tap-away */}
      <TouchableOpacity style={cm.backdrop} activeOpacity={1} onPress={() => dismiss()} />

      <Animated.View style={[
        cm.menu,
        { top, right },
        {
          opacity: anim,
          transform: [
            { scale: anim.interpolate({ inputRange: [0, 1], outputRange: [0.85, 1] }) },
            { translateY: anim.interpolate({ inputRange: [0, 1], outputRange: [-6, 0] }) },
          ],
        },
      ]}>
        {items.map((item, i) => (
          <React.Fragment key={item.label}>
            {i > 0 && <View style={cm.sep} />}
            <TouchableOpacity
              style={cm.row}
              activeOpacity={0.65}
              onPress={() => dismiss(item.onPress)}
            >
              <Ionicons
                name={item.icon as any}
                size={15}
                color={item.danger ? flumeColors.accent : flumeColors.textPrimary}
                style={cm.icon}
              />
              <Text style={[cm.label, item.danger && cm.labelDanger]}>{item.label}</Text>
            </TouchableOpacity>
          </React.Fragment>
        ))}
      </Animated.View>
    </>
  );
}

const cm = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, zIndex: 10 },
  menu: {
    position: 'absolute', zIndex: 20,
    backgroundColor: flumeColors.surface,
    borderRadius: flumeRadius.lg,
    minWidth: 180,
    shadowColor: '#000', shadowOpacity: 0.2, shadowRadius: 20, shadowOffset: { width: 0, height: 6 },
    elevation: 14,
    overflow: 'hidden',
    borderWidth: 1, borderColor: flumeColors.border,
  },
  row:        { flexDirection: 'row', alignItems: 'center', paddingHorizontal: flumeSpacing.lg, paddingVertical: flumeSpacing.md },
  icon:       { marginRight: flumeSpacing.md, width: 18 },
  label:      { fontSize: flumeFonts.md, color: flumeColors.textPrimary, fontWeight: flumeFonts.medium },
  labelDanger:{ color: flumeColors.accent },
  sep:        { height: 1, backgroundColor: flumeColors.border, marginHorizontal: flumeSpacing.lg },
});


export default function HistoryScreen() {
  const [history,    setHistory]    = useState<HistoryEntry[]>([]);
  const [filter,     setFilter]     = useState<Filter>('all');
  const [copied,     setCopied]     = useState<string | null>(null);
  const [editingId,  setEditingId]  = useState<string | null>(null);
  const [editText,   setEditText]   = useState('');
  const [myDeviceId, setMyDeviceId] = useState('');
  const [sheetEntry, setSheetEntry] = useState<HistoryEntry | null>(null);
  const [menuPos,    setMenuPos]    = useState({ top: 0, right: 16 });

  useFocusEffect(useCallback(() => { getDeviceId().then(setMyDeviceId); }, []));
  useFocusEffect(useCallback(() => { getHistory().then(setHistory); }, []));
  useSync(setHistory);

  // Deduplicated + filtered list
  const filtered = (() => {
    const seen = new Set<string>();
    return history.filter(e => {
      if (!e?.id || seen.has(e.id)) return false;
      seen.add(e.id);
      if (filter === 'mine')   return e.device_id === myDeviceId;
      if (filter === 'others') return e.device_id !== myDeviceId;
      if (filter === 'pinned') return e.is_pinned;
      return true;
    });
  })();

  const listData = [
    ...filtered.filter(e => e.is_pinned),
    ...filtered.filter(e => !e.is_pinned),
  ].filter((e, i, arr) => arr.findIndex(x => x.id === e.id) === i);

  // ── Actions ────────────────────────────────────────────────────────────────
  const copy = async (text: string, id: string) => {
    await Clipboard.setStringAsync(text);
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setCopied(id);
    setTimeout(() => setCopied(null), 1500);
  };

  const togglePin = async (entry: HistoryEntry) => {
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const updated = await updateEntry(entry.id, { is_pinned: !entry.is_pinned });
    setHistory(updated);
    const syncOn = await getSyncEnabled();
    if (syncOn && !entry.id.startsWith('local_')) {
      await supabase.from('transcriptions').update({ is_pinned: !entry.is_pinned }).eq('id', entry.id);
    }
  };

  const startEdit = (entry: HistoryEntry) => {
    setEditingId(entry.id);
    setEditText(entry.text ?? '');
  };

  const saveEdit = async (entry: HistoryEntry) => {
    if (!editText.trim()) { setEditingId(null); return; }
    const updated = await updateEntry(entry.id, { text: editText.trim() });
    setHistory(updated);
    setEditingId(null);
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    const syncOn = await getSyncEnabled();
    if (syncOn && !entry.id.startsWith('local_')) {
      await supabase.from('transcriptions').update({ edited_text: editText.trim() }).eq('id', entry.id);
    }
  };

  const handleDelete = (entry: HistoryEntry) => {
    Alert.alert('Delete', 'Remove this transcription?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete', style: 'destructive',
        onPress: async () => {
          const updated = await deleteEntry(entry.id);
          setHistory(updated);
          const syncOn = await getSyncEnabled();
          if (syncOn && !entry.id.startsWith('local_')) {
            await supabase.from('transcriptions').delete().eq('id', entry.id);
          }
        },
      },
    ]);
  };

  // ── Long-press → floating context menu ───────────────────────────────────
  const showActions = async (entry: HistoryEntry, cardY: number) => {
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    // Position menu below the card, pinned to right edge
    setMenuPos({ top: cardY, right: 16 });
    setSheetEntry(entry);
  };

  const menuItems = (entry: HistoryEntry): MenuItem[] => {
    const text     = entry.text ?? '';
    const isMine   = entry.device_id === myDeviceId;
    const pinLabel = entry.is_pinned ? 'Unpin' : 'Pin to top';
    const pinIcon  = entry.is_pinned ? 'bookmark' : 'bookmark-outline';
    return [
      { icon: 'copy-outline',   label: 'Copy',     onPress: () => copy(text, entry.id) },
      { icon: 'share-outline',  label: 'Share',    onPress: () => Share.share({ message: text }) },
      { icon: pinIcon,          label: pinLabel,   onPress: () => togglePin(entry) },
      ...(isMine ? [
        { icon: 'pencil-outline', label: 'Edit',   onPress: () => startEdit(entry) },
        { icon: 'trash-outline',  label: 'Delete', onPress: () => handleDelete(entry), danger: true },
      ] : []),
    ];
  };

  // ── Card ───────────────────────────────────────────────────────────────────
  const renderCard = ({ item, index }: { item: HistoryEntry; index: number }) => {
    const isEditing = editingId === item.id;
    const isMine    = item.device_id === myDeviceId;
    const text      = item.text ?? '';
    const wc        = text.split(/\s+/).filter(Boolean).length;

    return (
      <TouchableOpacity
        activeOpacity={0.85}
        onLongPress={(e) => {
          const y = e.nativeEvent.pageY - 20;
          showActions(item, y);
        }}
        delayLongPress={350}
        style={[s.card, item.is_pinned && s.cardPinned]}
      >
        <View style={[s.badge, item.is_pinned && s.badgePinned]}>
          {item.is_pinned
            ? <Text style={s.pinEmoji}>📌</Text>
            : <Text style={s.badgeTxt}>{String(index + 1).padStart(2, '0')}</Text>
          }
        </View>

        <View style={s.body}>
          {isEditing ? (
            <TextInput
              style={s.editInput}
              value={editText}
              onChangeText={setEditText}
              multiline
              autoFocus
              onBlur={() => saveEdit(item)}
            />
          ) : (
            <Text style={s.cardTxt} numberOfLines={2}>{text}</Text>
          )}
          <View style={s.metaRow}>
            <Text style={s.meta}>{wc} words</Text>
            {!isMine && (
              <View style={s.deviceTag}>
                <Ionicons name="phone-portrait-outline" size={10} color={flumeColors.textTertiary} />
                <Text style={s.deviceTxt}>{item.device_name}</Text>
              </View>
            )}
            <Text style={s.holdHint}>Hold for options</Text>
          </View>
        </View>

        <TouchableOpacity style={s.copyBtn} onPress={() => copy(text, item.id)}>
          <Ionicons
            name={copied === item.id ? 'checkmark' : 'copy-outline'}
            size={17}
            color={copied === item.id ? flumeColors.success : flumeColors.textSecondary}
          />
        </TouchableOpacity>
      </TouchableOpacity>
    );
  };

  const FILTERS: { key: Filter; label: string }[] = [
    { key: 'all',    label: 'All' },
    { key: 'mine',   label: 'Mine' },
    { key: 'others', label: 'Others' },
    { key: 'pinned', label: 'Pinned' },
  ];

  return (
    <View style={s.root}>
      {sheetEntry && (
        <ContextMenu
          items={menuItems(sheetEntry)}
          top={menuPos.top}
          right={menuPos.right}
          onClose={() => setSheetEntry(null)}
        />
      )}
      <View style={s.hero}>
        <SafeAreaView edges={['top']}>
          <Text style={s.headline}>History</Text>
          <Text style={s.sub}>{filtered.length} transcriptions</Text>
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

      <View style={s.sheet}>
        {listData.length === 0 ? (
          <View style={s.empty}>
            <Ionicons name="mic-outline" size={40} color={flumeColors.textTertiary} />
            <Text style={s.emptyTxt}>No transcriptions</Text>
            <Text style={s.emptySub}>
              {filter === 'pinned'  ? 'Hold a card and tap Pin' :
               filter === 'others' ? 'No transcriptions from other devices' :
               'Record something on the Home tab'}
            </Text>
          </View>
        ) : (
          <FlatList
            data={listData}
            keyExtractor={item => item.id}
            contentContainerStyle={{ paddingBottom: 40 }}
            showsVerticalScrollIndicator={false}
            ListHeaderComponent={
              <TouchableOpacity style={s.clearBtn} onPress={() =>
                Alert.alert('Clear all', 'Remove all local transcriptions?', [
                  { text: 'Cancel', style: 'cancel' },
                  { text: 'Clear', style: 'destructive', onPress: async () => { await clearHistory(); setHistory([]); } },
                ])
              }>
                <Text style={s.clearTxt}>Clear local</Text>
              </TouchableOpacity>
            }
            renderItem={renderCard}
          />
        )}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root:          { flex: 1, backgroundColor: flumeColors.background },
  hero:          { backgroundColor: flumeColors.background, paddingHorizontal: flumeSpacing.xl, paddingBottom: flumeSpacing.lg },
  headline:      { fontSize: flumeFonts.xxxl, fontWeight: flumeFonts.light, color: flumeColors.textPrimary, marginTop: flumeSpacing.md, letterSpacing: -0.5 },
  sub:           { fontSize: flumeFonts.sm, color: flumeColors.textSecondary, marginTop: 4, marginBottom: flumeSpacing.lg },
  pills:         { flexDirection: 'row', gap: flumeSpacing.sm },
  pill:          { paddingHorizontal: flumeSpacing.lg, paddingVertical: flumeSpacing.sm, borderRadius: flumeRadius.full, backgroundColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderColor: flumeColors.border },
  pillActive:    { backgroundColor: flumeColors.accent, borderColor: flumeColors.accent },
  pillTxt:       { fontSize: flumeFonts.sm, color: flumeColors.textSecondary, fontWeight: flumeFonts.medium },
  pillTxtActive: { color: flumeColors.buttonPrimaryText },
  sheet:         { flex: 1, backgroundColor: flumeColors.surface, borderTopLeftRadius: flumeRadius.xxl, borderTopRightRadius: flumeRadius.xxl, paddingTop: flumeSpacing.xl, paddingHorizontal: flumeSpacing.lg },
  empty:         { flex: 1, alignItems: 'center', justifyContent: 'center', gap: flumeSpacing.lg, paddingBottom: 80 },
  emptyTxt:      { fontSize: flumeFonts.lg, color: flumeColors.textPrimary, fontWeight: flumeFonts.medium },
  emptySub:      { fontSize: flumeFonts.md, color: flumeColors.textSecondary, textAlign: 'center', paddingHorizontal: 32 },
  clearBtn:      { alignSelf: 'flex-end', marginBottom: flumeSpacing.md, paddingVertical: flumeSpacing.xs, paddingHorizontal: flumeSpacing.sm },
  clearTxt:      { fontSize: flumeFonts.sm, color: flumeColors.textTertiary },
  card:          { flexDirection: 'row', alignItems: 'flex-start', backgroundColor: flumeColors.background, borderRadius: flumeRadius.lg, padding: flumeSpacing.lg, marginBottom: flumeSpacing.md, shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 10, shadowOffset: { width: 0, height: 3 }, elevation: 2, borderWidth: 1, borderColor: flumeColors.border },
  cardPinned:    { backgroundColor: flumeColors.accentDim, borderWidth: 1.5, borderColor: flumeColors.borderActive },
  badge:         { width: 36, height: 36, borderRadius: flumeRadius.md, backgroundColor: 'rgba(255,255,255,0.06)', alignItems: 'center', justifyContent: 'center', marginRight: flumeSpacing.md, marginTop: 2 },
  badgePinned:   { backgroundColor: flumeColors.accentDim },
  badgeTxt:      { fontSize: flumeFonts.sm, fontWeight: flumeFonts.semibold, color: flumeColors.textTertiary },
  pinEmoji:      { fontSize: 16 },
  body:          { flex: 1 },
  cardTxt:       { fontSize: flumeFonts.md, color: flumeColors.textPrimary, fontWeight: flumeFonts.medium, lineHeight: 22 },
  editInput:     { fontSize: flumeFonts.md, color: flumeColors.textPrimary, lineHeight: 22, borderWidth: 1, borderColor: flumeColors.accent, borderRadius: flumeRadius.md, padding: flumeSpacing.md, minHeight: 60, backgroundColor: flumeColors.accentDim },
  metaRow:       { flexDirection: 'row', alignItems: 'center', gap: flumeSpacing.md, marginTop: flumeSpacing.sm, flexWrap: 'wrap' },
  meta:          { fontSize: flumeFonts.xs, color: flumeColors.textTertiary },
  deviceTag:     { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: 'rgba(255,255,255,0.06)', paddingHorizontal: flumeSpacing.sm, paddingVertical: 2, borderRadius: flumeRadius.sm },
  deviceTxt:     { fontSize: flumeFonts.xs, color: flumeColors.textTertiary },
  holdHint:      { fontSize: flumeFonts.xs, color: flumeColors.textTertiary, fontStyle: 'italic' },
  copyBtn:       { padding: flumeSpacing.sm, marginLeft: 4 },
});
