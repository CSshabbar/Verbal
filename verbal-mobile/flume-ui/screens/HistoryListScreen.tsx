import React, { useMemo, useState } from 'react';
import { View, StyleSheet, FlatList, Pressable, TextInput } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text, Chip, Card } from '../components';
import { colors, radius } from '../theme';
import { useHistory, HistoryItem } from '../hooks/useHistory';

type Props = {
  onOpen: (item: HistoryItem) => void;
};

/** Colored device tag badge (turn 8: Mac terracotta, PC blue, else neutral). */
export const DeviceTag: React.FC<{ tag: string }> = ({ tag }) => {
  const t = tag.toLowerCase();
  const [bg, ink] =
    t.includes('mac') || t.includes('imac') ? [colors.tagMac, colors.tagMacInk] :
    t.includes('pc') || t.includes('windows') || t.includes('work') ? [colors.tagPC, colors.tagPCInk] :
    [colors.surface3, colors.textSecondary];
  return (
    <View style={[styles.tag, { backgroundColor: bg }]}>
      <Text variant="buttonSm" color={ink} style={{ fontSize: 10.5 }}>{tag}</Text>
    </View>
  );
};

/**
 * Screen 3f / 8e — History list. Day-grouped cards, colored device tag,
 * word + duration meta.
 */
export const HistoryListScreen: React.FC<Props> = ({ onOpen }) => {
  const insets = useSafeAreaInsets();
  const { items } = useHistory();
  const [filter, setFilter] = useState<'all' | string>('all');
  const [searching, setSearching] = useState(false);
  const [query, setQuery] = useState('');

  const todayCount = useMemo(() => items.filter(i => i.dayLabel === 'Today').length, [items]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter(i =>
      (filter === 'all' || i.deviceTag === filter) &&
      (!q || i.text.toLowerCase().includes(q)),
    );
  }, [items, filter, query]);
  const grouped = useMemo(() => groupByDay(filtered), [filtered]);

  return (
    <View style={[styles.root, { paddingTop: insets.top + 10 }]}>
      <View style={styles.header}>
        <View>
          <Text variant="caption" color={colors.textSubtle} style={{ marginBottom: 2 }}>
            {items.length} total · {todayCount} today
          </Text>
          <Text variant="titleSm">History</Text>
        </View>
        <Pressable
          style={styles.iconBtn}
          onPress={() => { setSearching(s => !s); if (searching) setQuery(''); }}
          accessibilityRole="button"
          accessibilityLabel={searching ? 'Close search' : 'Search history'}
        >
          <Ionicons name={searching ? 'close' : 'search-outline'} size={17} color={colors.textSecondary} />
        </Pressable>
      </View>

      {searching && (
        <View style={styles.searchBox}>
          <Ionicons name="search-outline" size={16} color={colors.textSubtle} />
          <TextInput
            style={styles.searchInput}
            value={query}
            onChangeText={setQuery}
            placeholder="Search transcriptions…"
            placeholderTextColor={colors.textDisabled}
            autoFocus
            returnKeyType="search"
          />
        </View>
      )}

      <View style={styles.filters}>
        <Chip label="All" active={filter === 'all'} onPress={() => setFilter('all')} />
        <Chip label="MacBook" active={filter === 'MacBook'} onPress={() => setFilter('MacBook')} />
        <Chip label="Work PC" active={filter === 'Work PC'} onPress={() => setFilter('Work PC')} />
      </View>

      <FlatList
        data={grouped}
        keyExtractor={g => g.label}
        renderItem={({ item: group }) => (
          <View>
            <Text variant="meta" color={colors.textSubtle} style={{ marginBottom: 10, marginTop: 6 }}>
              {group.label}
            </Text>
            <View style={{ gap: 10, marginBottom: 16 }}>
              {group.items.map(item => (
                <Card key={item.id} padding={14} onPress={() => onOpen(item)}>
                  <View style={styles.cardHeader}>
                    <Text variant="caption" color={colors.textSubtle}>{item.timeOfDay}</Text>
                    <Text variant="metaSm" color={colors.primary}>
                      {item.wordCount}w · {item.durationLabel}
                    </Text>
                  </View>
                  <Text variant="bodySm" numberOfLines={2} style={{ marginBottom: 10 }}>
                    {item.text}
                  </Text>
                  <DeviceTag tag={item.deviceTag} />
                </Card>
              ))}
            </View>
          </View>
        )}
        contentContainerStyle={{ paddingBottom: insets.bottom + 80 }}
        showsVerticalScrollIndicator={false}
      />
    </View>
  );
};

function groupByDay(items: HistoryItem[]) {
  const map = new Map<string, HistoryItem[]>();
  items.forEach(i => {
    const key = i.dayLabel ?? 'Earlier';
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(i);
  });
  return Array.from(map.entries()).map(([label, items]) => ({ label, items }));
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 18,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 18,
  },
  iconBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: colors.surface1,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    paddingHorizontal: 12,
    paddingVertical: 9,
    marginTop: 12,
  },
  searchInput: {
    flex: 1,
    color: colors.textPrimary,
    fontFamily: 'Geist_400Regular',
    fontSize: 14,
    padding: 0,
  },
  filters: {
    flexDirection: 'row',
    gap: 7,
    marginBottom: 18,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 6,
  },
  tag: {
    alignSelf: 'flex-start',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 7,
  },
});

export default HistoryListScreen;
