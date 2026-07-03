import React from 'react';
import { Pressable, View, StyleSheet, ViewStyle } from 'react-native';
import { colors, radius, space } from '../theme';

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
  const Wrap: any = onPress ? Pressable : View;

  return (
    <Wrap
      onPress={onPress}
      style={({ pressed }: { pressed?: boolean }) => [
        styles.base,
        emphasis === 'draft' ? styles.draft : styles.default,
        { padding: pad },
        pressed && { opacity: 0.85 },
        style,
      ]}
    >
      {children}
    </Wrap>
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
