import React, { useCallback, useEffect, useState } from 'react';
import { View, StyleSheet, Pressable, ScrollView, Switch, RefreshControl } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text } from '../components';
import { colors, radius, pressedStyle } from '../theme';
import {
  fetchAccountDevices, setDeviceSync, isDeviceOnline, AccountDevice,
} from '../../lib/deviceSync';
import { useSyncEnabled } from '../hooks/useSyncEnabled';

type Props = {
  onBack: () => void;
  onAddDevice: () => void;
};

function iconFor(type: string | null): keyof typeof Ionicons.glyphMap {
  const t = (type || '').toLowerCase();
  if (t.includes('ios') || t.includes('iphone') || t.includes('android') || t.includes('phone')) return 'phone-portrait-outline';
  if (t.includes('win')) return 'desktop-outline';
  return 'laptop-outline';
}

/**
 * Screen 3i — Your devices. Every device on the account with a PER-DEVICE sync
 * switch (cloud `devices.sync_enabled`; this device also drives local sync).
 */
export const DevicesScreen: React.FC<Props> = ({ onBack, onAddDevice }) => {
  const insets = useSafeAreaInsets();
  const [devices, setDevices] = useState<AccountDevice[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  // THIS device's row is driven by the local sync store, not by the cloud
  // `devices.sync_enabled` snapshot (IDI-171). The cloud column is still written
  // (setDeviceSync mirrors both ways), but the store is what actually gates
  // realtime here — so this switch can never disagree with the Menu / Settings
  // toggles, and a stale row read can't show "on" while sync is off.
  const localSync = useSyncEnabled();
  const valueFor = (d: AccountDevice) => (d.isSelf ? localSync : d.syncEnabled);

  const load = useCallback(async () => {
    setDevices(await fetchAccountDevices());
  }, []);
  useEffect(() => { load(); }, [load]);

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const toggle = async (d: AccountDevice, value: boolean) => {
    setDevices((r) => (r ? r.map((x) => (x.deviceId === d.deviceId ? { ...x, syncEnabled: value } : x)) : r));
    await setDeviceSync(d.deviceId, value);
  };

  const list = devices || [];

  return (
    <View style={[styles.root, { paddingTop: insets.top + 10, paddingBottom: insets.bottom + 14 }]}>
      <View style={styles.topBar}>
        <Pressable onPress={onBack} style={({ pressed }) => [styles.backBtn, pressed && pressedStyle]}>
          <Ionicons name="chevron-back" size={22} color={colors.textSecondary} />
          <Text variant="titleSm" style={{ fontSize: 20 }}>Your devices</Text>
        </Pressable>
        <Pressable onPress={onAddDevice} style={({ pressed }) => [styles.addBtn, pressed && pressedStyle]}>
          <Ionicons name="add" size={22} color={colors.primary} />
        </Pressable>
      </View>

      <Text variant="meta" color={colors.textSubtle} style={{ marginBottom: 8 }}>
        {list.length} DEVICE{list.length === 1 ? '' : 'S'} · SYNC PER DEVICE
      </Text>

      <ScrollView
        contentContainerStyle={{ gap: 8 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.textMuted} />}
      >
        {list.map(d => (
          <View key={d.deviceId} style={styles.row}>
            <View style={styles.rowIcon}>
              <Ionicons name={iconFor(d.type)} size={17} color={colors.textSecondary} />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <View style={styles.nameRow}>
                <Text variant="label" numberOfLines={1}>{d.name}</Text>
                {d.isSelf && (
                  <View style={styles.thisTag}>
                    <Text variant="metaSm" color={colors.primaryAccent}>THIS DEVICE</Text>
                  </View>
                )}
              </View>
              <View style={styles.statusRow}>
                <View style={[styles.dot, { backgroundColor: isDeviceOnline(d) ? colors.online : colors.offline }]} />
                <Text variant="metaSm" color={colors.textSubtle}>
                  {isDeviceOnline(d) ? 'Online' : 'Offline'} · sync {valueFor(d) ? 'on' : 'off'}
                </Text>
              </View>
            </View>
            <Switch
              value={valueFor(d)}
              onValueChange={(v) => toggle(d, v)}
              trackColor={{ true: colors.primary, false: colors.surface3 }}
              thumbColor="#fff"
            />
          </View>
        ))}
      </ScrollView>

      <View style={{ flex: 1 }} />

      <Pressable onPress={onAddDevice} style={({ pressed }) => [styles.dashedCta, pressed && pressedStyle]}>
        <View style={styles.plusDisc}>
          <Ionicons name="add" size={22} color={colors.primary} />
        </View>
        <Text variant="button" color={colors.primary}>Pair another device</Text>
      </Pressable>
    </View>
  );
};

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
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface1, borderRadius: radius.md, borderWidth: 1,
    borderColor: colors.borderSubtle, padding: 12,
  },
  rowIcon: { width: 34, height: 34, borderRadius: 10, backgroundColor: colors.surface2, alignItems: 'center', justifyContent: 'center' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  thisTag: { backgroundColor: colors.primarySoft, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 3 },
  dot: { width: 6, height: 6, borderRadius: 3 },
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
