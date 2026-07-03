import React from 'react';
import { Text as RNText, TextProps as RNTextProps, StyleSheet } from 'react-native';
import { type, TypeVariant, colors } from '../theme';

export type TextProps = RNTextProps & {
  variant?: TypeVariant;
  color?: string;
  align?: 'left' | 'center' | 'right';
};

/**
 * Themed Text. Defaults to body + primary color.
 * Pass `variant` for a sized + weighted style from theme/typography.
 *
 *   <Text variant="title">Hi</Text>
 *   <Text variant="meta" color={colors.textSubtle}>TODAY</Text>
 */
export const Text: React.FC<TextProps> = ({
  variant = 'body',
  color = colors.textPrimary,
  align,
  style,
  ...rest
}) => {
  return (
    <RNText
      {...rest}
      style={[
        type[variant],
        { color },
        align && { textAlign: align },
        style,
      ]}
    />
  );
};

export default Text;
