/**
 * SidePanel — the app's navigation hub (V2 "Daily Four" redesign, 2026-08-16).
 *
 * A left slide-in panel mirroring the desktop sidebar: Workspace (Canvas,
 * Meetings), Tools (Dictionary, Snippets, Device pairing), live device
 * presence + the sync toggle, and the account footer (gear → Settings).
 * Replaces the old Menu modal as the home for everything that isn't a tab.
 *
 * Deliberately built on core `Animated` (no reanimated / drawer package) so it
 * ships as an OTA update — runtime 1.0.0 has no new native modules.
 */
import React, { useEffect, useRef, useState } from 'react';
import { View, StyleSheet, Pressable, Animated, Switch, Easing } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
// Direct imports (not the barrel): index.ts exports SidePanel, and importing
// the barrel from here would be a require cycle.
import { Text } from './Text';
import { LogoMark } from './LogoMark';
import { colors, pressedStyle } from '../theme';
import { useAuth } from '../hooks/useAuth';
import { useDevices } from '../hooks/useDevices';
import { useSyncEnabled, setSyncEnabled } from '../hooks/useSyncEnabled';

const WIDTH = 292;

export type SidePanelProps = {
  open: boolean;
  onClose: () => void;
  /** Navigate somewhere and close — the panel never owns routing itself. */
  onNavigate: (dest: 'canvas' | 'meetings' | 'dictionary' | 'snippets' | 'devices' | 'settings') => void;
};

export const SidePanel: React.FC<SidePanelProps> = ({ open, onClose, onNavigate }) => {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { devices } = useDevices();
  const sync = useSyncEnabled();

  const x = useRef(new Animated.Value(-WIDTH)).current;
  const scrim = useRef(new Animated.Value(0)).current;
  // Keep mounted while the close animation runs.
  const [visible, setVisible] = useState(open);

  useEffect(() => {
    if (open) setVisible(true);
    Animated.parallel([
      Animated.timing(x, {
        toValue: open ? 0 : -WIDTH,
        duration: 230,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
      Animated.timing(scrim, { toValue: open ? 1 : 0, duration: 230, useNativeDriver: true }),
    ]).start(({ finished }) => { if (finished && !open) setVisible(false); });
  }, [open, x, scrim]);

  if (!visible) return null;

  const go = (dest: Parameters<SidePanelProps['onNavigate']>[0]) => () => onNavigate(dest);

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents={open ? 'auto' : 'none'}>
      <Animated.View style={[StyleSheet.absoluteFill, styles.scrim, { opacity: scrim }]}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="Close menu" />
      </Animated.View>
      <Animated.View
        style={[styles.panel, { paddingTop: insets.top + 18, paddingBottom: insets.bottom + 14, transform: [{ translateX: x }] }]}
        accessibilityViewIsModal
      >
        <View style={styles.brand}>
          <LogoMark size={32} />
          <Text style={styles.brandName}>FLUME</Text>
        </View>

        <Section label="WORKSPACE">
          <Row icon="grid-outline" label="Canvas" onPress={go('canvas')} />
          <Row icon="people-outline" label="Meetings" onPress={go('meetings')} />
        </Section>

        <Section label="TOOLS">
          <Row icon="book-outline" label="Dictionary" onPress={go('dictionary')} />
          <Row icon="flash-outline" label="Snippets" onPress={go('snippets')} />
          <Row icon="laptop-outline" label="Device pairing" onPress={go('devices')} />
        </Section>

        <Section label="DEVICES">
          {devices.length ? devices.slice(0, 4).map(d => (
            <View key={d.id} style={styles.devRow}>
              <View style={[styles.dot, { backgroundColor: colors.online }]} />
              <Text variant="bodyXs" color={colors.textMuted} style={{ fontSize: 13 }} numberOfLines={1}>{d.name}</Text>
            </View>
          )) : (
            <View style={styles.devRow}>
              <View style={[styles.dot, { backgroundColor: colors.offline }]} />
              <Text variant="bodyXs" color={colors.textSubtle} style={{ fontSize: 13 }}>No other devices online</Text>
            </View>
          )}
          <View style={styles.syncRow}>
            <Ionicons name="sync-outline" size={17} color={colors.textMuted} />
            <Text variant="bodyXs" style={{ flex: 1, fontSize: 13 }} color={colors.textSecondary}>Sync</Text>
            <Switch
              value={sync}
              onValueChange={v => { setSyncEnabled(v); }}
              trackColor={{ false: colors.surface3, true: colors.primary }}
              thumbColor="#fff"
              accessibilityLabel="Enable sync"
            />
          </View>
        </Section>

        <View style={{ flex: 1 }} />

        <View style={styles.foot}>
          <View style={styles.avatar}>
            <Text style={{ fontFamily: 'Geist_600SemiBold', fontSize: 13, color: '#fff5ea' }}>
              {(user?.firstName?.[0] ?? 'V').toUpperCase()}
            </Text>
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={{ fontFamily: 'Geist_600SemiBold', fontSize: 13, color: colors.textPrimary }} numberOfLines={1}>
              {user?.firstName ?? 'You'}
            </Text>
            <Text variant="caption" color={colors.textSubtle} style={{ fontSize: 11 }} numberOfLines={1}>
              {user?.email ?? ''}
            </Text>
          </View>
          <Pressable onPress={go('settings')} hitSlop={8} style={({ pressed }) => pressed && pressedStyle}
            accessibilityRole="button" accessibilityLabel="Settings">
            <Ionicons name="settings-outline" size={19} color={colors.textMuted} />
          </Pressable>
        </View>
      </Animated.View>
    </View>
  );
};

const Section: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <View style={{ marginBottom: 6 }}>
    <Text variant="metaSm" color={colors.textSubtle} style={styles.secLabel}>{label}</Text>
    {children}
  </View>
);

const Row: React.FC<{ icon: keyof typeof Ionicons.glyphMap; label: string; onPress: () => void }> =
  ({ icon, label, onPress }) => (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.surface2 }]}
      accessibilityRole="button" accessibilityLabel={label}>
      <Ionicons name={icon} size={17} color={colors.textMuted} />
      <Text variant="bodyXs" style={{ fontSize: 13.5 }} color={colors.textSecondary}>{label}</Text>
    </Pressable>
  );

const styles = StyleSheet.create({
  scrim: { backgroundColor: 'rgba(0,0,0,0.55)' },
  panel: {
    position: 'absolute', top: 0, bottom: 0, left: 0, width: WIDTH,
    backgroundColor: '#111316',
    borderRightWidth: 1, borderRightColor: colors.borderDefault,
    borderTopRightRadius: 24, borderBottomRightRadius: 24,
    paddingHorizontal: 14,
  },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 8, marginBottom: 10 },
  brandName: { fontFamily: 'Geist_700Bold', fontSize: 14, letterSpacing: 0.6, color: colors.textPrimary },
  secLabel: { fontSize: 9.5, letterSpacing: 1.6, marginLeft: 10, marginTop: 14, marginBottom: 5 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, paddingHorizontal: 10, borderRadius: 10 },
  devRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 5, paddingHorizontal: 10 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  syncRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 6, paddingHorizontal: 10 },
  foot: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    borderTopWidth: 1, borderTopColor: colors.borderSubtle, paddingTop: 12, paddingHorizontal: 4,
  },
  avatar: {
    width: 32, height: 32, borderRadius: 16, backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center',
  },
});

export default SidePanel;
