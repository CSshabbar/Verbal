import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../theme';

/**
 * Success badge — 56×56 ring around a check mark.
 * Used on the Confirmation screen (3e).
 */
export const SuccessBadge: React.FC<{ size?: number }> = ({ size = 56 }) => (
  <View
    style={[
      styles.outer,
      {
        width: size,
        height: size,
        borderRadius: size / 2,
        borderColor: colors.primaryBorder,
      },
    ]}
  >
    <Ionicons name="checkmark" size={size * 0.46} color={colors.primary} />
  </View>
);

const styles = StyleSheet.create({
  outer: {
    backgroundColor: colors.primarySoft,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default SuccessBadge;
