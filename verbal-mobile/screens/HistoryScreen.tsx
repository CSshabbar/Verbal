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
                color={item.danger ? colors.accent : colors.cardText}
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
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    minWidth: 160,
    shadowColor: '#000', shadowOpacity: 0.14, shadowRadius: 16, shadowOffset: { width: 0, height: 4 },
    elevation: 12,
    overflow: 'hidden',
  },
  row:        { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 11 },
  icon:       { marginRight: 10, width: 18 },
  label:      { fontSize: 14, color: colors.cardText, fontWeight: fonts.medium },
  labelDanger:{ color: colors.accent },
  sep:        { height: 1, backgroundColor: colors.divider, marginHorizontal: 10 },
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
                <Ionicons name="phone-portrait-outline" size={10} color={colors.cardSub} />
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
            color={copied === item.id ? colors.green : colors.cardSub}
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
            <Ionicons name="mic-outline" size={40} color={colors.cardSub} />
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
  root:          { flex: 1, backgroundColor: colors.heroBg },
  hero:          { backgroundColor: colors.heroBg, paddingHorizontal: 20, paddingBottom: 16 },
  headline:      { fontSize: 30, fontWeight: fonts.bold, color: colors.heroText, marginTop: 8 },
  sub:           { fontSize: 13, color: colors.heroMuted, marginTop: 2, marginBottom: 14 },
  pills:         { flexDirection: 'row', gap: 8 },
  pill:          { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.08)' },
  pillActive:    { backgroundColor: colors.accent },
  pillTxt:       { fontSize: 12, color: colors.heroMuted, fontWeight: fonts.medium },
  pillTxtActive: { color: '#fff' },
  sheet:         { flex: 1, backgroundColor: colors.sheetBg, borderTopLeftRadius: 28, borderTopRightRadius: 28, paddingTop: 16, paddingHorizontal: 14 },
  empty:         { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 8, paddingBottom: 80 },
  emptyTxt:      { fontSize: 16, color: colors.cardText, fontWeight: fonts.medium },
  emptySub:      { fontSize: 13, color: colors.cardSub, textAlign: 'center', paddingHorizontal: 32 },
  clearBtn:      { alignSelf: 'flex-end', marginBottom: 10, paddingVertical: 4, paddingHorizontal: 8 },
  clearTxt:      { fontSize: 12, color: colors.cardSub },
  card:          { flexDirection: 'row', alignItems: 'flex-start', backgroundColor: colors.cardBg, borderRadius: radius.md, padding: 12, marginBottom: 8, shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 1 },
  cardPinned:    { backgroundColor: '#FFF7F2', borderWidth: 1.5, borderColor: 'rgba(224,90,43,0.25)' },
  badge:         { width: 34, height: 34, borderRadius: 10, backgroundColor: colors.iconGray, alignItems: 'center', justifyContent: 'center', marginRight: 10, marginTop: 2 },
  badgePinned:   { backgroundColor: '#FFE8D6' },
  badgeTxt:      { fontSize: 11, fontWeight: fonts.semibold, color: colors.cardSub },
  pinEmoji:      { fontSize: 14 },
  body:          { flex: 1 },
  cardTxt:       { fontSize: 13, color: colors.cardText, fontWeight: fonts.medium, lineHeight: 18 },
  editInput:     { fontSize: 13, color: colors.cardText, lineHeight: 18, borderWidth: 1, borderColor: colors.accent, borderRadius: 8, padding: 8, minHeight: 60, backgroundColor: '#FFF7F2' },
  metaRow:       { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4, flexWrap: 'wrap' },
  meta:          { fontSize: 11, color: colors.cardSub },
  deviceTag:     { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: colors.iconGray, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  deviceTxt:     { fontSize: 10, color: colors.cardSub },
  holdHint:      { fontSize: 10, color: colors.cardBorder, fontStyle: 'italic' },
  copyBtn:       { padding: 6, marginLeft: 4 },
});
