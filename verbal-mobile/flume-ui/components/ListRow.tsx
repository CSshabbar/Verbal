import React from 'react';
import { Pressable, View, StyleSheet, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Text } from './Text';
import { colors, radius } from '../theme';

export type ListRowProps = {
  icon?: keyof typeof Ionicons.glyphMap;
  iconElement?: React.ReactNode;
  title: string;
  subtitle?: string;
  /** Trailing UI: chevron by default, set to null to omit, or pass any node. */
  trailing?: React.ReactNode | null;
  onPress?: () => void;
  /** Online status dot color. Set to undefined to hide. */
  statusColor?: string;
  /** Dim the row (offline). */
  dimmed?: boolean;
  style?: ViewStyle;
};

/**
 * Standard list item. Used for device rows (3i),
 * onboarding download tiles (3b/3), settings rows, etc.
 */
export const ListRow: React.FC<ListRowProps> = ({
  icon,
  iconElement,
  title,
  subtitle,
  trailing = undefined,
  onPress,
  statusColor,
  dimmed = false,
  style,
}) => {
  const showChevron = trailing === undefined;
  const Wrap: any = onPress ? Pressable : View;
  return (
    <Wrap
      onPress={onPress}
      style={({ pressed }: { pressed?: boolean }) => [
        styles.row,
        { opacity: dimmed ? 0.75 : pressed ? 0.85 : 1 },
        style,
      ]}
    >
      <View style={styles.iconBox}>
        {iconElement ?? (icon ? (
          <Ionicons name={icon} size={22} color={dimmed ? colors.textSubtle : colors.textPrimary} />
        ) : null)}
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text variant="button" color={dimmed ? colors.textMuted : colors.textPrimary}>
          {title}
        </Text>
        {subtitle ? (
          <View style={styles.subRow}>
            {statusColor ? (
              <View style={[styles.dot, { backgroundColor: statusColor }]} />
            ) : null}
            <Text variant="caption" color={dimmed ? colors.textSubtle : colors.textMuted}>
              {subtitle}
            </Text>
          </View>
        ) : null}
      </View>
      {showChevron ? (
        <Ionicons
          name="chevron-forward"
          size={22}
          color={dimmed ? colors.textDisabled : colors.textSubtle}
        />
      ) : (
        trailing
      )}
    </Wrap>
  );
};

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 15,
    padding: 16,
    borderRadius: radius.lg,
    backgroundColor: colors.surface1,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  iconBox: {
    width: 42,
    height: 42,
    borderRadius: radius.md,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  subRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    marginTop: 3,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
  },
});

export default ListRow;
