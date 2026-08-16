import React from 'react';
import { View, StyleSheet, FlatList, Pressable, Image, TextInput } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { Text, Chip, ChipDot, Card } from '../components';
import { colors, radius, pressedStyle } from '../theme';
import { useCanvas, CanvasItem } from '../hooks/useCanvas';
import { useDevices } from '../hooks/useDevices';

// onBack appeared with the V2 nav redesign (2026-08-16): Canvas moved from a
// tab to the SidePanel → Menu modal stack, so it needs its own way home.
type Props = { onBack?: () => void };

/**
 * Screen 4c — Canvas. Drop & send to computer's clipboard.
 *
 * Each card is a single payload (text, link, or image). Tapping "Save → Device"
 * sends that payload to the paired device's clipboard.
 */
export const CanvasScreen: React.FC<Props> = ({ onBack }) => {
  const insets = useSafeAreaInsets();
  const { items, save, discard, addText, addLink, addPhoto, updateText, refresh, toast, dismissToast } = useCanvas();
  const { target } = useDevices();

  return (
    <View style={[styles.root, { paddingTop: insets.top + 10 }]}>
      {toast ? (
        <Pressable onPress={dismissToast} style={({ pressed }) => [styles.toast, { top: insets.top + 6 }, pressed && pressedStyle]} accessibilityRole="button" accessibilityLabel={toast}>
          <Ionicons name="checkmark-circle" size={16} color={colors.online} />
          <Text variant="buttonSm" style={{ flex: 1 }} numberOfLines={2}>{toast}</Text>
        </Pressable>
      ) : null}
      <View style={styles.header}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          {onBack ? (
            <Pressable onPress={onBack} hitSlop={8} style={({ pressed }) => pressed && pressedStyle}
              accessibilityRole="button" accessibilityLabel="Back">
              <Ionicons name="chevron-back" size={22} color={colors.textSecondary} />
            </Pressable>
          ) : null}
          <Text variant="titleSm">Canvas</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Pressable
            onPress={() => { Haptics.selectionAsync(); refresh(); }}
            style={({ pressed }) => [styles.refreshBtn, pressed && pressedStyle]}
            hitSlop={8}
          >
            <Ionicons name="refresh" size={18} color={colors.textSecondary} />
          </Pressable>
          <Chip label={target?.name ?? 'No device'} active leading={<ChipDot />} />
        </View>
      </View>

      <Text variant="bodyXs" color={colors.textMuted} style={{ marginBottom: 14 }}>
        Add anything here — saving it copies to your computer's clipboard.
      </Text>

      <FlatList
        data={items}
        keyExtractor={i => i.id}
        renderItem={({ item }) => <Item item={item} onSave={save} onDiscard={discard} onEditText={updateText} targetName={target?.name ?? ''} />}
        ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
        contentContainerStyle={{ paddingBottom: insets.bottom + 16 }}
        showsVerticalScrollIndicator={false}
      />

      <View style={[styles.actionBar, { paddingBottom: insets.bottom + 8 }]}>
        <ActionBtn icon="image-outline"  label="Photo" onPress={addPhoto} />
        <ActionBtn icon="text-outline"   label="Text"  onPress={addText} />
        <ActionBtn icon="link-outline"   label="Paste" onPress={addLink} />
      </View>
    </View>
  );
};

const ActionBtn: React.FC<{ icon: any; label: string; onPress: () => void }> = ({
  icon, label, onPress,
}) => (
  <Pressable
    onPress={() => { Haptics.selectionAsync(); onPress(); }}
    style={({ pressed }) => [styles.actionBtn, pressed && pressedStyle]}
  >
    <Ionicons name={icon} size={16} color={colors.textPrimary} />
    <Text variant="buttonSm">{label}</Text>
  </Pressable>
);

const Item: React.FC<{
  item: CanvasItem;
  onSave: (id: string) => void;
  onDiscard: (id: string) => void;
  onEditText: (id: string, text: string) => void;
  targetName: string;
}> = ({ item, onSave, onDiscard, onEditText, targetName }) => {
  const isDraft = item.state === 'draft';
  const isSent  = item.state === 'sent';

  return (
    <Card padding={12} emphasis={isDraft ? 'draft' : 'default'}>
      {item.kind === 'text' && (
        isDraft ? (
          <TextInput
            value={item.text}
            onChangeText={(t) => onEditText(item.id, t)}
            placeholder="Type text to send…"
            placeholderTextColor={colors.textMuted}
            multiline
            autoFocus={item.text === ''}
            style={styles.textInput}
          />
        ) : (
          <Text variant="bodySm" style={{ marginBottom: 8 }}>"{item.text}"</Text>
        )
      )}
      {item.kind === 'link' && (
        <View style={{ flexDirection: 'row', gap: 10, marginBottom: 8 }}>
          <View style={styles.linkIcon}>
            <Ionicons name="link-outline" size={18} color={colors.textPrimary} />
          </View>
          <View style={{ flex: 1, justifyContent: 'center', minWidth: 0 }}>
            <Text variant="button" numberOfLines={1}>{item.url}</Text>
          </View>
        </View>
      )}
      {item.kind === 'image' && (
        <View style={{ flexDirection: 'row', gap: 10, marginBottom: 8 }}>
          <Image
            source={{ uri: item.uri }}
            style={styles.thumb}
            resizeMode="cover"
          />
          <View style={{ flex: 1, justifyContent: 'center' }}>
            <Text variant="button">{item.filename}</Text>
            <Text variant="caption" color={colors.textMuted}>
              {item.sizeLabel ?? ''} {item.dimensions ? `· ${item.dimensions}` : ''}
            </Text>
          </View>
        </View>
      )}

      {isDraft ? (
        <View style={styles.footerRow}>
          <Text variant="metaSm" color={colors.primary}>DRAFT · {item.kind.toUpperCase()}</Text>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            <Pressable onPress={() => onDiscard(item.id)} style={({ pressed }) => [{ padding: 4 }, pressed && pressedStyle]}>
              <Text variant="buttonSm" color={colors.textMuted}>Discard</Text>
            </Pressable>
            <Pressable onPress={() => onSave(item.id)} style={({ pressed }) => [styles.savePill, pressed && pressedStyle]}>
              <Text variant="buttonSm" color={colors.primaryInk}>
                Save → {targetName.split(' ')[0]}
              </Text>
            </Pressable>
          </View>
        </View>
      ) : (
        <View style={styles.footerRow}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
            <View style={{ width: 5, height: 5, borderRadius: 2.5, backgroundColor: colors.online }} />
            <Text variant="metaSm" color={colors.online}>
              SENT · {item.sentAt} · {item.kind.toUpperCase()}
            </Text>
          </View>
        </View>
      )}
    </Card>
  );
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 18,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 14,
  },
  refreshBtn: {
    width: 34, height: 34, borderRadius: 10,
    backgroundColor: colors.surface2,
    alignItems: 'center', justifyContent: 'center',
  },
  toast: {
    position: 'absolute', left: 18, right: 18, zIndex: 20,
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingVertical: 10, paddingHorizontal: 14, borderRadius: radius.lg,
    backgroundColor: colors.surface2, borderWidth: 1, borderColor: colors.borderSubtle,
  },
  textInput: {
    color: colors.textPrimary,
    fontSize: 15,
    lineHeight: 21,
    minHeight: 44,
    marginBottom: 8,
    padding: 0,
  },
  actionBar: {
    flexDirection: 'row',
    gap: 6,
    paddingTop: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderSubtle,
  },
  actionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    borderRadius: radius.lg,
    backgroundColor: colors.surface2,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  linkIcon: {
    width: 42,
    height: 42,
    borderRadius: radius.sm,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  thumb: {
    width: 60,
    height: 60,
    borderRadius: radius.sm,
    backgroundColor: colors.surface2,
  },
  footerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  savePill: {
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: radius.xs,
    backgroundColor: colors.primary,
  },
});

export default CanvasScreen;
