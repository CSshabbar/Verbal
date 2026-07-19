import React, { useEffect, useState } from 'react';
import { View, StyleSheet, ScrollView, Switch, Pressable, Alert } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text, ListRow } from '../components';
import { colors } from '../theme';
import { useAuth } from '../hooks/useAuth';
import { getSyncEnabled, setSyncEnabled } from '../../lib/storage';

type Props = {
  onClose: () => void;
  onOpenSettings: () => void;
  onOpenSnippets: () => void;
  onOpenDictionary: () => void;
  onOpenDevices: () => void;
};

/**
 * Menu — the app's navigation hub (opened from the Home ☰). Consolidates the
 * secondary destinations that used to be buried inside Settings: account,
 * snippets, dictionary, device pairing, the sync toggle, and sign out.
 */
export const MenuScreen: React.FC<Props> = ({
  onClose, onOpenSettings, onOpenSnippets, onOpenDictionary, onOpenDevices,
}) => {
  const insets = useSafeAreaInsets();
  const { user, signOut } = useAuth();
  const [sync, setSync] = useState(false);

  useEffect(() => { (async () => setSync(await getSyncEnabled()))(); }, []);

  const toggleSync = async (v: boolean) => { setSync(v); await setSyncEnabled(v); };

  const confirmSignOut = () => {
    // Native Alert: Menu is a native-stack modal, and a JS <Modal> over it doesn't
    // reliably receive touches on iOS (same reason the old sign-out looked dead).
    Alert.alert(
      'Sign out?',
      'You can sign back in with Google any time.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Sign out', style: 'destructive', onPress: () => { signOut(); onClose(); } },
      ],
      { cancelable: true },
    );
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 12 }]}>
      <View style={styles.topBar}>
        <Text variant="titleSm">Menu</Text>
        <Pressable onPress={onClose} style={styles.iconCircle} accessibilityRole="button" accessibilityLabel="Close menu" hitSlop={8}>
          <Ionicons name="close" size={18} color={colors.textSecondary} />
        </Pressable>
      </View>

      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingTop: 16, paddingBottom: insets.bottom + 28, gap: 24 }}
      >
        <Section label="ACCOUNT">
          <ListRow
            icon="person-circle-outline"
            title={user?.firstName || user?.email || 'Signed in'}
            subtitle={user?.email}
            trailing={null}
          />
          <ListRow icon="settings-outline" title="Settings" subtitle="Keys & preferences" onPress={onOpenSettings} />
          <ListRow icon="log-out-outline" title="Sign out" subtitle="End this session on this device" onPress={confirmSignOut} trailing={null} />
        </Section>

        <Section label="TOOLS">
          <ListRow icon="flash-outline" title="Snippets" subtitle="Say a phrase, get the full text" onPress={onOpenSnippets} />
          <ListRow icon="book-outline" title="Dictionary" subtitle="Vocabulary & replacement rules" onPress={onOpenDictionary} />
        </Section>

        <Section label="DEVICES">
          <ListRow
            icon="sync-outline"
            title="Sync"
            subtitle="Sync history, notes & clipboard across devices"
            trailing={
              <Switch
                value={sync}
                onValueChange={toggleSync}
                trackColor={{ false: colors.surface3, true: colors.primary }}
                thumbColor="#fff"
                accessibilityLabel="Enable sync"
              />
            }
          />
          <ListRow icon="laptop-outline" title="Device pairing" subtitle="Manage & pair your computers" onPress={onOpenDevices} />
        </Section>
      </ScrollView>
    </View>
  );
};

const Section: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <View style={{ gap: 8 }}>
    <Text variant="meta" color={colors.textSubtle} style={{ marginLeft: 2 }}>{label}</Text>
    {children}
  </View>
);

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bgScreen, paddingHorizontal: 18 },
  topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
  iconCircle: { width: 34, height: 34, borderRadius: 17, backgroundColor: colors.surface2, alignItems: 'center', justifyContent: 'center' },
});

export default MenuScreen;
