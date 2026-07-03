import React from 'react';
import { View, StyleSheet } from 'react-native';
import { colors } from '../theme';

export type PageDotsProps = {
  count: number;
  active: number; // 0-indexed
};

/** Onboarding step indicator. Active pip is wider + primary color. */
export const PageDots: React.FC<PageDotsProps> = ({ count, active }) => {
  return (
    <View style={styles.row}>
      {Array.from({ length: count }).map((_, i) => {
        const isOn = i === active;
        return (
          <View
            key={i}
            style={[
              styles.pip,
              isOn ? styles.on : styles.off,
            ]}
          />
        );
      })}
    </View>
  );
};

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 8, justifyContent: 'center' },
  pip: { height: 4, borderRadius: 2 },
  on:  { width: 34, backgroundColor: colors.primary },
  off: { width: 24, backgroundColor: 'rgba(240, 240, 240, 0.18)' },
});

export default PageDots;
