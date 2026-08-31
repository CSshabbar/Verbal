/**
 * MenuButton — the ☰ that opens the SidePanel (the app's navigation hub).
 *
 * Every tab's root screen (Home, Notes, History, Insights) shows one in its
 * header so the hub is reachable from wherever you are, not just Home
 * (user request, 2026-08-30). The opener is delivered through `MenuContext`
 * (provided by `MainWithPanel` in RootNavigator) so screens nested inside the
 * tab stacks don't need it plumbed through props. Outside the provider the
 * button renders nothing — a styled-but-inert circle would read as a blank
 * button (rule #44).
 */
import React, { createContext, useContext } from 'react';
import { Pressable, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, pressedStyle } from '../theme';

export const MenuContext = createContext<(() => void) | null>(null);

export const useOpenMenu = () => useContext(MenuContext);

export const MenuButton: React.FC = () => {
  const openMenu = useOpenMenu();
  if (!openMenu) return null;
  return (
    <Pressable
      onPress={openMenu}
      style={({ pressed }) => [styles.iconCircle, pressed && pressedStyle]}
      accessibilityRole="button"
      accessibilityLabel="Open menu"
      hitSlop={8}
    >
      <Ionicons name="menu" size={18} color={colors.textSecondary} />
    </Pressable>
  );
};

const styles = StyleSheet.create({
  iconCircle: { width: 34, height: 34, borderRadius: 17, backgroundColor: colors.surface2, alignItems: 'center', justifyContent: 'center' },
});

export default MenuButton;
