import React from 'react';
import { View, StyleSheet, FlatList, Pressable, Image } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { Text, Chip, ChipDot, Card } from '../components';
import { colors, radius } from '../theme';
import { useCanvas, CanvasItem } from '../hooks/useCanvas';
import { useDevices } from '../hooks/useDevices';

type Props = {};

/**
 * Screen 4c — Canvas. Drop & send to computer's clipboard.
 *
 * Each card is a single payload (text, link, or image). Tapping "Save → Device"
 * sends that payload to the paired device's clipboard.
 */
export const CanvasScreen: React.FC<Props> = () => {
  const insets = useSafeAreaInsets();
  const { items, save, discard, addText, addLink, addPhoto } = useCanvas();
  const { target } = useDevices();

  return (
    <View style={[styles.root, { paddingTop: insets.top + 10 }]}>
      <View style={styles.header}>
        <Text variant="titleSm">Canvas</Text>
        <Chip label={target?.name ?? 'No device'} active leading={<ChipDot />} />
      </View>

      <Text variant="bodyXs" color={colors.textMuted} style={{ marginBottom: 14 }}>
        Add anything here — saving it copies to your computer's clipboard.
      </Text>

      <FlatList
        data={items}
        keyExtractor={i => i.id}
        renderItem={({ item }) => <Item item={item} onSave={save} onDiscard={discard} targetName={target?.name ?? ''} />}
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
    style={({ pressed }) => [styles.actionBtn, pressed && { opacity: 0.8 }]}
  >
    <Ionicons name={icon} size={16} color={colors.textPrimary} />
    <Text variant="buttonSm">{label}</Text>
  </Pressable>
);

const Item: React.FC<{
  item: CanvasItem;
  onSave: (id: string) => void;
  onDiscard: (id: string) => void;
  targetName: string;
}> = ({ item, onSave, onDiscard, targetName }) => {
  const isDraft = item.state === 'draft';
  const isSent  = item.state === 'sent';

  return (
    <Card padding={12} emphasis={isDraft ? 'draft' : 'default'}>
      {item.kind === 'text' && (
        <Text variant="bodySm" style={{ marginBottom: 8 }}>"{item.text}"</Text>
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
            <Pressable onPress={() => onDiscard(item.id)} style={{ padding: 4 }}>
              <Text variant="buttonSm" color={colors.textMuted}>Discard</Text>
            </Pressable>
            <Pressable onPress={() => onSave(item.id)} style={styles.savePill}>
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
