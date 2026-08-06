/**
 * DevicesSyncSheet — the "you're signed in on these devices" popup.
 *
 * Shown right after sign-in (and reachable from Settings). Lists every device on
 * the account with a PER-DEVICE sync switch, backed by the cloud
 * `devices.sync_enabled` column. Toggling THIS device also mirrors to the local
 * `verbal_sync_enabled` flag that `lib/useSync` reads, so sync reacts immediately.
 *
 * Imperative, like ConfirmDialog:
 *   import { showDevicesSheet } from '../components/DevicesSyncSheet';
 *   await showDevicesSheet();      // resolves when dismissed
 * Mount <DevicesSyncHost /> once near the app root.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Modal, View, Pressable, StyleSheet, Switch, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Text } from './Text';
import { colors, radius, pressedStyle } from '../theme';
import {
  fetchAccountDevices, setDeviceSync, isDeviceOnline, AccountDevice,
} from '../../lib/deviceSync';

let _open: (() => Promise<void>) | null = null;

/** Open the devices/sync sheet. Resolves when the user dismisses it. */
export function showDevicesSheet(): Promise<void> {
  return _open ? _open() : Promise.resolve();
}

function iconFor(type: string | null): keyof typeof Ionicons.glyphMap {
  const t = (type || '').toLowerCase();
  if (t.includes('ios') || t.includes('iphone') || t.includes('android') || t.includes('phone')) return 'phone-portrait-outline';
  if (t.includes('win')) return 'desktop-outline';
  return 'laptop-outline';
}

export const DevicesSyncHost: React.FC = () => {
  const [visible, setVisible] = useState(false);
  const [resolver, setResolver] = useState<(() => void) | null>(null);
  const [rows, setRows] = useState<AccountDevice[] | null>(null);

  useEffect(() => {
    _open = () =>
      new Promise<void>((resolve) => {
        setResolver(() => resolve);
        setVisible(true);
      });
    return () => { _open = null; };
  }, []);

  const load = useCallback(async () => {
    setRows(null);
    setRows(await fetchAccountDevices());
  }, []);

  useEffect(() => { if (visible) load(); }, [visible, load]);

  const toggle = async (row: AccountDevice, value: boolean) => {
    setRows((r) => (r ? r.map((d) => (d.deviceId === row.deviceId ? { ...d, syncEnabled: value } : d)) : r));
    await setDeviceSync(row.deviceId, value);
  };

  const done = () => { setVisible(false); resolver?.(); setResolver(null); };

  return (
    <Modal transparent animationType="fade" visible={visible} onRequestClose={done}>
      {/* Backdrop = tap-to-dismiss scrim, card = tap swallower. Neither gets a
          pressed state on purpose — dimming the whole sheet would read as a bug. */}
      <Pressable style={styles.backdrop} onPress={done}>
        <Pressable style={styles.card} onPress={() => {}}>
          <Text variant="subtitle" style={styles.title}>Your devices</Text>
          <Text variant="bodyXs" color={colors.textMuted} style={styles.sub}>
            Turn sync on for each device you want to share your dictation, notes and canvas with.
          </Text>

          {rows === null ? (
            <View style={styles.loading}><ActivityIndicator color={colors.primary} /></View>
          ) : rows.length === 0 ? (
            <Text variant="bodyXs" color={colors.textMuted} style={{ paddingVertical: 18 }}>
              No devices found on this account yet.
            </Text>
          ) : (
            <View style={styles.list}>
              {rows.map((r) => (
                <View key={r.deviceId} style={styles.row}>
                  <View style={styles.rowIcon}>
                    <Ionicons name={iconFor(r.type)} size={17} color={colors.textSecondary} />
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <View style={styles.nameRow}>
                      <Text variant="label" numberOfLines={1}>{r.name}</Text>
                      {r.isSelf && (
                        <View style={styles.thisTag}>
                          <Text variant="metaSm" color={colors.primaryAccent}>THIS DEVICE</Text>
                        </View>
                      )}
                    </View>
                    <View style={styles.statusRow}>
                      <View style={[styles.dot, { backgroundColor: isDeviceOnline(r) ? '#7fae7a' : colors.textDisabled }]} />
                      <Text variant="metaSm" color={colors.textSubtle}>{isDeviceOnline(r) ? 'Online' : 'Offline'}</Text>
                    </View>
                  </View>
                  <Switch
                    value={r.syncEnabled}
                    onValueChange={(v) => toggle(r, v)}
                    trackColor={{ true: colors.primary, false: colors.surface3 }}
                    thumbColor="#fff"
                  />
                </View>
              ))}
            </View>
          )}

          <Pressable style={({ pressed }) => [styles.doneBtn, pressed && pressedStyle]} onPress={done}>
            <Text variant="button" color={colors.primaryInk}>Done</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
};

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', alignItems: 'center', justifyContent: 'center', padding: 24 },
  card: { width: '100%', maxWidth: 380, backgroundColor: colors.surface1, borderRadius: 20, borderWidth: 1, borderColor: colors.borderDefault, padding: 20 },
  title: { fontSize: 20, lineHeight: 25, marginBottom: 6 },
  sub: { marginBottom: 16, lineHeight: 18 },
  loading: { paddingVertical: 26, alignItems: 'center' },
  list: { gap: 4 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 11, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.borderSubtle },
  rowIcon: { width: 34, height: 34, borderRadius: 10, backgroundColor: colors.surface2, alignItems: 'center', justifyContent: 'center' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  thisTag: { backgroundColor: colors.primarySoft, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 3 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  doneBtn: { marginTop: 18, backgroundColor: colors.primary, borderRadius: 12, paddingVertical: 13, alignItems: 'center' },
});
