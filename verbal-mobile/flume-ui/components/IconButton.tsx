import React from 'react';
import { Pressable, View, StyleSheet, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Text } from './Text';
import { colors, radius, PRESSED_OPACITY } from '../theme';

export type IconButtonProps = {
  icon: keyof typeof Ionicons.glyphMap;
  onPress?: () => void;
  /** Diameter in px. Defaults to 64 (matches Recording cancel/pause). */
  size?: number;
  variant?: 'surface' | 'primary' | 'primarySoft';
  /** Optional label rendered under the button (used in Recording controls). */
  label?: string;
  style?: ViewStyle;
};

/**
 * Round icon button. Variants:
 *  - surface     → bg surface1, border, used as cancel/pause in 3d
 *  - primary     → bg primary, used as stop in 3d
 *  - primarySoft → bg primarySoft, used as "+" on 3i header
 */
export const IconButton: React.FC<IconButtonProps> = ({
  icon,
  onPress,
  size = 64,
  variant = 'surface',
  label,
  style,
}) => {
  const bg =
    variant === 'primary' ? colors.primary :
    variant === 'primarySoft' ? colors.primarySoft :
    colors.surface1;
  const ink =
    variant === 'primary' ? colors.primaryInk :
    variant === 'primarySoft' ? colors.primary :
    colors.textSecondary;
  const border =
    variant === 'surface' ? colors.borderDefault : 'transparent';

  return (
    <View style={[{ alignItems: 'center', gap: 6 }, style]}>
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [
          styles.btn,
          {
            width: size,
            height: size,
            borderRadius: size / 2,
            backgroundColor: bg,
            borderWidth: border === 'transparent' ? 0 : 1,
            borderColor: border,
            opacity: pressed ? PRESSED_OPACITY : 1,
          },
        ]}
      >
        <Ionicons name={icon} size={Math.max(14, size * 0.36)} color={ink} />
      </Pressable>
      {label ? (
        <Text variant="caption" color={colors.textMuted}>
          {label}
        </Text>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  btn: { alignItems: 'center', justifyContent: 'center' },
});

export default IconButton;
