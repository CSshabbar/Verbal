import React from 'react';
import { Pressable, View, StyleSheet, ViewStyle } from 'react-native';
import { Text } from './Text';
import { colors, radius } from '../theme';

export type ChipProps = {
  label: string;
  active?: boolean;
  leading?: React.ReactNode;     // dot, icon, etc.
  trailing?: React.ReactNode;
  onPress?: () => void;
  size?: 'sm' | 'md';            // sm = compact "DEFAULT" pill
  style?: ViewStyle;
};

/**
 * Compact pill. Used for device targets (3c, 3d), filters (3f, 4a),
 * "DEFAULT" tag (3i), and "Listening — sent to MacBook" indicators.
 */
export const Chip: React.FC<ChipProps> = ({
  label,
  active = false,
  leading,
  trailing,
  onPress,
  size = 'md',
  style,
}) => {
  const Wrap: any = onPress ? Pressable : View;
  return (
    <Wrap
      onPress={onPress}
      style={({ pressed }: { pressed?: boolean }) => [
        styles.base,
        size === 'sm' ? styles.sm : styles.md,
        active ? styles.active : styles.idle,
        pressed && { opacity: 0.7 },
        style,
      ]}
    >
      {leading ? <View style={{ marginRight: 6 }}>{leading}</View> : null}
      <Text
        variant={size === 'sm' ? 'metaSm' : 'label'}
        color={active ? colors.primaryAccent : colors.textSecondary}
        style={{ letterSpacing: size === 'sm' ? 0.6 : undefined }}
      >
        {label}
      </Text>
      {trailing ? <View style={{ marginLeft: 6 }}>{trailing}</View> : null}
    </Wrap>
  );
};

/** Solid colored 6×6 dot used inside an active Chip. */
export const ChipDot: React.FC<{ color?: string; size?: number }> = ({
  color = colors.primary,
  size = 6,
}) => (
  <View
    style={{
      width: size,
      height: size,
      borderRadius: size / 2,
      backgroundColor: color,
    }}
  />
);

const styles = StyleSheet.create({
  base: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  md: { paddingVertical: 8,  paddingHorizontal: 15 },
  sm: { paddingVertical: 4,  paddingHorizontal: 11 },
  idle:   { backgroundColor: colors.surface2, borderColor: colors.borderSubtle },
  active: { backgroundColor: colors.primarySoft, borderColor: colors.primaryBorder },
});

export default Chip;
