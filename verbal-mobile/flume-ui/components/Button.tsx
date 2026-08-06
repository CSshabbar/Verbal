import React from 'react';
import {
  Pressable, PressableProps, StyleSheet, View, ViewStyle, ActivityIndicator,
} from 'react-native';
import { Text } from './Text';
import { colors, radius, space, type, PRESSED_OPACITY } from '../theme';

type Variant = 'primary' | 'primaryLight' | 'ghost' | 'text';

export type ButtonProps = Omit<PressableProps, 'style'> & {
  label: string;
  variant?: Variant;
  loading?: boolean;
  icon?: React.ReactNode;
  trailing?: React.ReactNode;
  fullWidth?: boolean;
  style?: ViewStyle;
};

/**
 * Primary CTA button. Used in:
 *  - 3a "Continue with Google" (variant primaryLight + icon)
 *  - 3a "Continue with Apple" (variant ghost + icon)
 *  - Onboarding "Begin →" / "Next" (variant primary)
 *  - 3e "Done" / 3g "Resend" (variant primary)
 *  - 3g "Edit" / "Copy" (variant ghost)
 */
export const Button: React.FC<ButtonProps> = ({
  label,
  variant = 'primary',
  loading = false,
  icon,
  trailing,
  fullWidth = true,
  style,
  disabled,
  ...rest
}) => {
  const isPrimary = variant === 'primary';
  const isPrimaryLight = variant === 'primaryLight';
  const isGhost = variant === 'ghost';
  const isText = variant === 'text';

  // Minimalist-dark: primary CTAs are near-white with dark ink (not orange).
  const bg =
    isPrimary ? colors.inkLight :
    isPrimaryLight ? colors.inkLight :
    isGhost ? 'transparent' :
    'transparent';

  const ink =
    isPrimary || isPrimaryLight ? colors.primaryInk :
    colors.textPrimary;

  return (
    <Pressable
      {...rest}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.base,
        fullWidth && { alignSelf: 'stretch' },
        {
          backgroundColor: bg,
          borderWidth: isGhost ? 1 : 0,
          borderColor: colors.borderStrong,
          opacity: pressed ? PRESSED_OPACITY : disabled ? 0.5 : 1,
          paddingVertical: isText ? 12 : 13,
          paddingHorizontal: isText ? 16 : 18,
        },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={ink} />
      ) : (
        <>
          {icon ? <View style={{ marginRight: 10 }}>{icon}</View> : null}
          <Text
            variant={isPrimary || isPrimaryLight ? 'buttonPrimary' : 'button'}
            color={isText ? colors.textSecondary : ink}
          >
            {label}
          </Text>
          {trailing ? <View style={{ marginLeft: 10 }}>{trailing}</View> : null}
        </>
      )}
    </Pressable>
  );
};

const styles = StyleSheet.create({
  base: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.xl,
  },
});

export default Button;
