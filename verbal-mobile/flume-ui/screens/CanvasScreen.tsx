/**
 * Canvas — the shared clipboard, M1 "Slot & feed" redesign (2026-08-17).
 *
 * Layout: the LIVE slot as a hero card (clamped, with origin + freshness +
 * Copy/Clear), an "Earlier" device-local feed of compact rows, and a chat-style
 * composer pinned at the bottom (type/paste text, attach a photo, or dictate
 * with the mic — the transcript lands in the field for review, send is manual).
 * Long content never takes the screen: tapping the slot or a feed row opens an
 * in-tree expand overlay (NOT an RN <Modal> — this screen lives inside the
 * native-stack Menu modal, where JS modals drop touches; Hard Rule #14).
 */
import React, { useCallback, useMemo, useState } from 'react';
import {
  View, StyleSheet, Pressable, TextInput, FlatList, Image,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import * as Clipboard from 'expo-clipboard';
import { Text } from '../components';
import { colors, pressedStyle } from '../theme';
import { useCanvas, FeedEntry, LiveSlot } from '../hooks/useCanvas';
import { useRecorder } from '../hooks/useRecorder';

type Props = { onBack?: () => void };

function relTime(iso: string): string {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  if (isNaN(t)) return '';
  const min = Math.round((Date.now() - t) / 60_000);
  if (min < 1) return 'just now';
  if (min < 60) return `${min} min ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return day === 1 ? 'yesterday' : `${day} days ago`;
}
const kindIcon = (k: FeedEntry['kind']): keyof typeof Ionicons.glyphMap =>
  k === 'image' ? 'image-outline' : k === 'link' ? 'link-outline' : 'document-text-outline';

export const CanvasScreen: React.FC<Props> = ({ onBack }) => {
  const insets = useSafeAreaInsets();
  const {
    live, feed, sendText, sendPhoto, copyLive, clearLive, copyFeedEntry,
    refresh, toast, dismissToast,
  } = useCanvas();

  const [draft, setDraft] = useState('');
  const [expanded, setExpanded] = useState<{ title: string; body: string } | null>(null);
  const [sending, setSending] = useState(false);
  const { start, stop, cancel, status } = useRecorder();
  const recording = status === 'recording';

  const doSend = useCallback(async () => {
    if (sending || !draft.trim()) return;
    setSending(true);
    try {
      if (await sendText(draft)) setDraft('');
    } finally { setSending(false); }
  }, [draft, sendText, sending]);

  const micPress = useCallback(async () => {
    // Mic when the field is empty: dictate → transcript lands in the field for
    // review; send stays a deliberate tap. Never auto-sends.
    if (recording) {
      const r = await stop();
      if (r?.text) setDraft(d => (d ? d + ' ' : '') + r.text);
      return;
    }
    Haptics.selectionAsync();
    await start();
  }, [recording, start, stop]);

  const openLive = useCallback(() => {
    if (!live || live.kind === 'empty' || live.kind === 'image') return;
    setExpanded({
      title: `FROM ${live.own ? 'THIS PHONE' : live.from.toUpperCase()} · ${relTime(live.at).toUpperCase()}`,
      body: live.text ?? '',
    });
  }, [live]);

  const header = useMemo(() => (
    <>
      <LiveCard live={live} onCopy={copyLive} onClear={clearLive} onExpand={openLive} />
      {feed.length > 0 && (
        <Text variant="metaSm" color={colors.textSubtle} style={{ fontSize: 10, letterSpacing: 1.5, marginBottom: 8, marginLeft: 2 }}>
          EARLIER
        </Text>
      )}
    </>
  ), [live, feed.length, copyLive, clearLive, openLive]);

  return (
    <KeyboardAvoidingView
      style={[styles.root, { paddingTop: insets.top + 12 }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      {toast ? (
        <Pressable onPress={dismissToast} style={({ pressed }) => [styles.toast, { top: insets.top + 6 }, pressed && pressedStyle]} accessibilityRole="button" accessibilityLabel={toast}>
          <Ionicons name="checkmark-circle" size={16} color={colors.online} />
          <Text variant="buttonSm" style={{ flex: 1 }} numberOfLines={2}>{toast}</Text>
        </Pressable>
      ) : null}

      <View style={styles.topBar}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          {onBack ? (
            <Pressable onPress={onBack} hitSlop={8} style={({ pressed }) => pressed && pressedStyle}
              accessibilityRole="button" accessibilityLabel="Back">
              <Ionicons name="chevron-back" size={22} color={colors.textSecondary} />
            </Pressable>
          ) : null}
          <Text variant="titleSm">Canvas</Text>
        </View>
        <Pressable onPress={() => { Haptics.selectionAsync(); refresh(); }} hitSlop={8}
          style={({ pressed }) => [styles.iconCircle, pressed && pressedStyle]}
          accessibilityRole="button" accessibilityLabel="Refresh">
          <Ionicons name="refresh" size={17} color={colors.textSecondary} />
        </Pressable>
      </View>

      <FlatList
        data={feed}
        keyExtractor={e => e.id}
        ListHeaderComponent={header}
        renderItem={({ item }) => (
          <FeedRow
            entry={item}
            onPress={() => {
              if (item.kind === 'image') { copyFeedEntry(item.id); return; }
              setExpanded({
                title: `FROM ${item.own ? 'THIS PHONE' : item.from.toUpperCase()} · ${relTime(item.at).toUpperCase()}`,
                body: item.text,
              });
            }}
            onCopy={() => copyFeedEntry(item.id)}
          />
        )}
        ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
        contentContainerStyle={{ paddingBottom: 12 }}
        showsVerticalScrollIndicator={false}
        style={{ flex: 1 }}
      />

      {/* Chat composer */}
      <View style={[styles.composer, { paddingBottom: insets.bottom + 8 }]}>
        <Pressable onPress={sendPhoto} style={({ pressed }) => [styles.cIcon, pressed && pressedStyle]}
          accessibilityRole="button" accessibilityLabel="Send a photo">
          <Ionicons name="image-outline" size={19} color={colors.textSecondary} />
        </Pressable>
        <TextInput
          value={draft}
          onChangeText={setDraft}
          placeholder={recording ? 'Listening…' : 'Type or paste to send…'}
          placeholderTextColor={recording ? colors.primaryAccent : colors.textSubtle}
          style={styles.cField}
          multiline
          accessibilityLabel="Canvas message"
        />
        {draft.trim() ? (
          <Pressable onPress={doSend} disabled={sending}
            style={({ pressed }) => [styles.cSend, sending && { opacity: 0.6 }, pressed && pressedStyle]}
            accessibilityRole="button" accessibilityLabel="Send to devices">
            <Ionicons name="arrow-up" size={19} color="#fff5ea" />
          </Pressable>
        ) : (
          <Pressable onPress={micPress} onLongPress={recording ? () => { cancel(); } : undefined}
            style={({ pressed }) => [styles.cSend, recording && styles.cSendRec, pressed && pressedStyle]}
            accessibilityRole="button"
            accessibilityLabel={recording ? 'Stop dictation' : 'Dictate onto the canvas'}>
            <Ionicons name={recording ? 'stop' : 'mic'} size={18} color="#fff5ea" />
          </Pressable>
        )}
      </View>

      {/* In-tree expand overlay (long content never owns the screen) */}
      {expanded ? (
        <View style={StyleSheet.absoluteFill}>
          <Pressable style={[StyleSheet.absoluteFill, styles.scrim]} onPress={() => setExpanded(null)}
            accessibilityLabel="Close" />
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 16 }]}>
            <View style={styles.sheetHead}>
              <Text variant="metaSm" color={colors.textSubtle} style={{ fontSize: 10, letterSpacing: 1.2, flex: 1 }} numberOfLines={1}>
                {expanded.title} · {expanded.body.trim().split(/\s+/).length} WORDS
              </Text>
              <Pressable onPress={() => setExpanded(null)} hitSlop={10} accessibilityRole="button" accessibilityLabel="Close">
                <Ionicons name="close" size={18} color={colors.textMuted} />
              </Pressable>
            </View>
            <FlatList
              data={[expanded.body]}
              keyExtractor={(_, i) => String(i)}
              renderItem={({ item }) => (
                <Text variant="bodyXs" color={colors.textSecondary} style={{ fontSize: 14, lineHeight: 23 }}>{item}</Text>
              )}
              style={{ flexGrow: 0, maxHeight: 420 }}
            />
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 14 }}>
              <ActionPill label="Copy" primary onPress={() => {
                Clipboard.setStringAsync(expanded.body).catch(() => {});
                setExpanded(null);
              }} />
              <ActionPill label="Close" onPress={() => setExpanded(null)} />
            </View>
          </View>
        </View>
      ) : null}
    </KeyboardAvoidingView>
  );
};

const LiveCard: React.FC<{
  live: LiveSlot | null;
  onCopy: () => void; onClear: () => void; onExpand: () => void;
}> = ({ live, onCopy, onClear, onExpand }) => {
  if (!live) {
    return (
      <View style={styles.slot}>
        <Text variant="bodyXs" color={colors.textSubtle}>Checking the canvas…</Text>
      </View>
    );
  }
  if (live.kind === 'empty') {
    return (
      <View style={[styles.slot, { borderColor: colors.borderSubtle }]}>
        <Text variant="metaSm" color={colors.textSubtle} style={{ fontSize: 9.5, letterSpacing: 1.3, marginBottom: 8 }}>
          ON THE CANVAS
        </Text>
        <Text variant="bodyXs" color={colors.textMuted}>
          Nothing shared right now — whatever you send lands on every device instantly.
        </Text>
      </View>
    );
  }
  const fromLabel = live.own ? 'from this phone' : `from ${live.from}`;
  return (
    <View style={styles.slot}>
      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
        <Text variant="metaSm" color={colors.primaryAccent} style={{ fontSize: 9.5, letterSpacing: 1.3 }}>
          ● ON THE CANVAS
        </Text>
        <Text variant="caption" color={colors.textSubtle} style={{ fontSize: 10.5, marginLeft: 'auto' }} numberOfLines={1}>
          {fromLabel}{live.at ? ` · ${relTime(live.at)}` : ''}
        </Text>
      </View>
      {live.kind === 'image' && live.imageUrl ? (
        <Image source={{ uri: live.imageUrl }} style={styles.slotImg} resizeMode="cover" />
      ) : (
        <Pressable onPress={onExpand} accessibilityRole="button" accessibilityLabel="Show full text">
          <Text variant="bodyXs" color={colors.textSecondary} numberOfLines={5} style={{ fontSize: 13, lineHeight: 20 }}>
            {live.text}
          </Text>
          {(live.text?.length ?? 0) > 220 ? (
            <Text variant="buttonSm" color={colors.primaryAccent} style={{ marginTop: 6, fontSize: 12 }}>Show more</Text>
          ) : null}
        </Pressable>
      )}
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
        <ActionPill label="Copy" icon="copy-outline" primary onPress={onCopy} />
        <ActionPill label="Clear" onPress={onClear} />
      </View>
    </View>
  );
};

const FeedRow: React.FC<{ entry: FeedEntry; onPress: () => void; onCopy: () => void }> =
  ({ entry, onPress, onCopy }) => (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.feedRow, pressed && pressedStyle]}
      accessibilityRole="button" accessibilityLabel={`${entry.kind} from ${entry.from}`}>
      {entry.kind === 'image' && entry.imageUrl ? (
        <Image source={{ uri: entry.imageUrl }} style={styles.feedThumb} />
      ) : (
        <View style={styles.feedIcon}>
          <Ionicons name={kindIcon(entry.kind)} size={14} color={colors.textMuted} />
        </View>
      )}
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text variant="bodyXs" color={colors.textSecondary} numberOfLines={2} style={{ fontSize: 12, lineHeight: 17 }}>
          {entry.text}
        </Text>
        <Text variant="caption" color={colors.textSubtle} style={{ fontSize: 10, marginTop: 2 }}>
          {relTime(entry.at)} · {entry.own ? 'from this phone' : `from ${entry.from}`}
        </Text>
      </View>
      <Pressable onPress={onCopy} hitSlop={8} style={({ pressed }) => [{ padding: 4 }, pressed && pressedStyle]}
        accessibilityRole="button" accessibilityLabel="Copy">
        <Ionicons name="copy-outline" size={15} color={colors.textSubtle} />
      </Pressable>
    </Pressable>
  );

const ActionPill: React.FC<{ label: string; icon?: keyof typeof Ionicons.glyphMap; primary?: boolean; onPress: () => void }> =
  ({ label, icon, primary, onPress }) => (
    <Pressable onPress={onPress}
      style={({ pressed }) => [styles.pill, primary && styles.pillPrimary, pressed && pressedStyle]}
      accessibilityRole="button" accessibilityLabel={label}>
      {icon ? <Ionicons name={icon} size={13} color={primary ? colors.primaryInk : colors.textPrimary} /> : null}
      <Text variant="buttonSm" color={primary ? colors.primaryInk : colors.textPrimary} style={{ fontSize: 12.5 }}>
        {label}
      </Text>
    </Pressable>
  );

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bgScreen, paddingHorizontal: 18 },
  topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 },
  iconCircle: { width: 34, height: 34, borderRadius: 17, backgroundColor: colors.surface2, alignItems: 'center', justifyContent: 'center' },
  toast: {
    position: 'absolute', left: 18, right: 18, zIndex: 20,
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: '#1c1f23', borderWidth: 1, borderColor: colors.borderDefault,
    borderRadius: 12, paddingVertical: 10, paddingHorizontal: 12,
  },
  slot: {
    backgroundColor: colors.surface1, borderWidth: 1, borderColor: colors.primaryBorder,
    borderRadius: 18, padding: 14, marginBottom: 14,
  },
  slotImg: { width: '100%', height: 160, borderRadius: 12, backgroundColor: colors.surface2 },
  feedRow: {
    flexDirection: 'row', gap: 10, alignItems: 'flex-start',
    backgroundColor: colors.surface1, borderWidth: 1, borderColor: colors.borderSubtle,
    borderRadius: 14, padding: 11,
  },
  feedIcon: { width: 28, height: 28, borderRadius: 9, backgroundColor: colors.surface2, alignItems: 'center', justifyContent: 'center' },
  feedThumb: { width: 36, height: 36, borderRadius: 9, backgroundColor: colors.surface2 },
  composer: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, paddingTop: 8 },
  cIcon: { width: 42, height: 42, borderRadius: 21, backgroundColor: colors.surface2, alignItems: 'center', justifyContent: 'center' },
  cField: {
    flex: 1, minHeight: 42, maxHeight: 120,
    backgroundColor: '#1a1d21', borderWidth: 1, borderColor: colors.borderDefault,
    borderRadius: 21, paddingHorizontal: 14, paddingTop: 11, paddingBottom: 11,
    color: colors.textPrimary, fontFamily: 'Geist_400Regular', fontSize: 13.5,
  },
  cSend: { width: 42, height: 42, borderRadius: 21, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  cSendRec: { backgroundColor: '#E05049' },
  pill: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    flex: 1, backgroundColor: colors.surface2, borderRadius: 11, paddingVertical: 9,
  },
  pillPrimary: { backgroundColor: colors.inkLight },
  scrim: { backgroundColor: 'rgba(0,0,0,0.6)' },
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: '#16181b', borderWidth: 1, borderColor: colors.borderDefault,
    borderTopLeftRadius: 26, borderTopRightRadius: 26,
    paddingHorizontal: 18, paddingTop: 14,
  },
  sheetHead: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 },
});

export default CanvasScreen;
