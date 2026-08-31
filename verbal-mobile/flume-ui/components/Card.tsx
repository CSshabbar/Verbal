import React from 'react';
import { Pressable, View, StyleSheet, ViewStyle } from 'react-native';
import { colors, radius, space, PRESSED_OPACITY } from '../theme';

export type CardProps = {
  children: React.ReactNode;
  onPress?: () => void;
  padding?: keyof typeof space | number;
  style?: ViewStyle;
  emphasis?: 'default' | 'draft';   // draft uses dashed primary border (Canvas + Pair empty)
};

/**
 * Surface1 card. Backbone of history (3f), note list (4a), canvas items (4c),
 * transcript display (3e/3g), device rows (3i).
 */
export const Card: React.FC<CardProps> = ({
  children,
  onPress,
  padding = 'm',
  style,
  emphasis = 'default',
}) => {
  const pad = typeof padding === 'number' ? padding : space[padding];

  const base = [styles.base, emphasis === 'draft' ? styles.draft : styles.default, { padding: pad }, style];

  // A plain View silently IGNORES a function-valued `style` — only Pressable
  // resolves it. Passing the callback form unconditionally meant every Card
  // without onPress rendered unstyled: no surface, no padding, and no `flex: 1`,
  // which is how History detail's transcript card collapsed to zero height
  // (found on the simulator, 2026-08-27).
  if (!onPress) {
    return <View style={base}>{children}</View>;
  }
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [...base, pressed && { opacity: PRESSED_OPACITY }]}
    >
      {children}
    </Pressable>
  );
};

const styles = StyleSheet.create({
  base: {
    borderRadius: radius.lg,
    borderWidth: 1,
  },
  default: {
    backgroundColor: colors.surface1,
    borderColor: colors.borderSubtle,
  },
  draft: {
    backgroundColor: colors.primarySofter,
    borderColor: colors.primaryDashed,
    borderStyle: 'dashed',
  },
});

export default Card;
