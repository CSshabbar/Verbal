import React from 'react';
import { View, StyleSheet, Pressable, ScrollView } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text, ListRow, Chip } from '../components';
import { colors, radius } from '../theme';
import { useDevices, Device } from '../hooks/useDevices';

type Props = {
  onBack: () => void;
  onAddDevice: () => void;
};

/**
 * Screen 3i — Your devices. Lists paired devices, default toggle, dashed add.
 */
export const DevicesScreen: React.FC<Props> = ({ onBack, onAddDevice }) => {
  const insets = useSafeAreaInsets();
  const { devices, makeDefault } = useDevices();

  return (
    <View style={[styles.root, { paddingTop: insets.top + 10, paddingBottom: insets.bottom + 14 }]}>
      <View style={styles.topBar}>
        <Pressable onPress={onBack} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.textSecondary} />
          <Text variant="titleSm" style={{ fontSize: 20 }}>Your devices</Text>
        </Pressable>
        <Pressable onPress={onAddDevice} style={styles.addBtn}>
          <Ionicons name="add" size={22} color={colors.primary} />
        </Pressable>
      </View>

      <Text variant="meta" color={colors.textSubtle} style={{ marginBottom: 8 }}>
        PAIRED · {devices.length}
      </Text>

      <ScrollView contentContainerStyle={{ gap: 8 }} showsVerticalScrollIndicator={false}>
        {devices.map(d => (
          <ListRow
            key={d.id}
            icon={iconFor(d)}
            title={d.name}
            subtitle={subtitleFor(d)}
            statusColor={d.status === 'online' ? colors.online : colors.offline}
            dimmed={d.status === 'offline'}
            trailing={d.isDefault ? <Chip size="sm" label="DEFAULT" active /> : undefined}
            onPress={() => makeDefault(d.id)}
          />
        ))}
      </ScrollView>

      <View style={{ flex: 1 }} />

      <Pressable onPress={onAddDevice} style={styles.dashedCta}>
        <View style={styles.plusDisc}>
          <Ionicons name="add" size={22} color={colors.primary} />
        </View>
        <Text variant="button" color={colors.primary}>Pair another device</Text>
      </Pressable>
    </View>
  );
};

function iconFor(d: Device) {
  switch (d.platform) {
    case 'macos': return 'laptop-outline';
    case 'windows': return 'desktop-outline';
    case 'linux': return 'desktop-outline';
    default: return 'desktop-outline';
  }
}

function subtitleFor(d: Device) {
  if (d.status === 'online') {
    return d.isDefault ? 'online · default target' : 'online';
  }
  return d.lastSeen ? `offline · last seen ${d.lastSeen}` : 'offline';
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
    marginBottom: 18,
  },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  addBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dashedCta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: radius.lg,
    backgroundColor: colors.primarySofter,
    borderWidth: 1,
    borderColor: colors.primaryDashed,
    borderStyle: 'dashed',
  },
  plusDisc: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default DevicesScreen;
