import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, type, space, radius } from '../../lib/flumeTokens';

const historyGroups = [
  {
    label: 'Today',
    items: [
      { id: '1', text: 'Reschedule the design review to Thursday afternoon…', time: '9:24 AM', device: 'MacBook', words: 38 },
      { id: '2', text: 'Let\'s move the launch to next Tuesday and let the QA team know.', time: '8:15 AM', device: 'MacBook', words: 14 },
    ],
  },
  {
    label: 'Yesterday',
    items: [
      { id: '3', text: 'Can you send me the updated proposal by end of day?', time: '4:30 PM', device: 'Work PC', words: 12 },
    ],
  },
  {
    label: 'Monday',
    items: [
      { id: '4', text: 'Team standup notes: Sprint progress is on track. Blockers identified.', time: '10:00 AM', device: 'MacBook', words: 45 },
    ],
  },
];

const filters = ['All', 'MacBook', 'Work PC'];

export default function HistoryListScreen({ navigation }: { navigation: any }) {
  const [activeFilter, setActiveFilter] = useState('All');

  return (
    <View style={s.root}>
      <SafeAreaView style={s.safeArea} edges={['top']}>
        <ScrollView 
          contentContainerStyle={s.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Header */}
          <View style={s.header}>
            <Text style={s.headline}>History</Text>
            <TouchableOpacity style={s.searchBtn} activeOpacity={0.7}>
              <Ionicons name="search" size={16} color={colors.textPrimary} />
            </TouchableOpacity>
          </View>

          {/* Filter Chips */}
          <View style={s.filterChips}>
            {filters.map(filter => (
              <TouchableOpacity
                key={filter}
                style={[
                  s.filterChip,
                  activeFilter === filter && s.filterChipActive,
                ]}
                onPress={() => setActiveFilter(filter)}
                activeOpacity={0.7}
              >
                <Text 
                  style={[
                    s.filterChipText,
                    activeFilter === filter && s.filterChipTextActive,
                  ]}
                >
                  {filter}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* History Groups */}
          {historyGroups.map(group => (
            <View key={group.label} style={s.group}>
              <Text style={s.groupLabel}>{group.label}</Text>
              {group.items.map(item => (
                <TouchableOpacity
                  key={item.id}
                  style={s.historyCard}
                  onPress={() => navigation.navigate('HistoryDetail', { item })}
                  activeOpacity={0.7}
                >
                  <View style={s.cardHeader}>
                    <Text style={s.cardMeta}>{item.time} · {item.device}</Text>
                    <Text style={s.wordCount}>{item.words}w</Text>
                  </View>
                  <Text style={s.cardText} numberOfLines={2}>
                    "{item.text}"
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          ))}
        </ScrollView>
      </SafeAreaView>

      {/* Tab Bar */}
      <View style={s.tabBar}>
        <TouchableOpacity 
          style={s.tab} 
          activeOpacity={0.7}
          onPress={() => navigation.navigate('FlumeHome')}
        >
          <Ionicons name="mic-outline" size={14} color={colors.textDisabled} />
          <Text style={s.tabLabel}>Record</Text>
        </TouchableOpacity>
        <TouchableOpacity style={s.tab} activeOpacity={0.7}>
          <Ionicons name="time" size={14} color={colors.primary} />
          <Text style={[s.tabLabel, { color: colors.primary }]}>History</Text>
        </TouchableOpacity>
        <TouchableOpacity 
          style={s.tab} 
          activeOpacity={0.7}
          onPress={() => navigation.navigate('Settings')}
        >
          <Ionicons name="settings-outline" size={14} color={colors.textDisabled} />
          <Text style={s.tabLabel}>Settings</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
  },
  safeArea: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    paddingTop: space.s,
    paddingHorizontal: space.l,
    paddingBottom: space.base,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.l,
  },
  headline: {
    ...type.titleSm,
    color: colors.textPrimary,
  },
  searchBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  filterChips: {
    flexDirection: 'row',
    gap: 6,
    marginBottom: 18,
  },
  filterChip: {
    backgroundColor: colors.surface2,
    borderRadius: radius.pill,
    paddingVertical: 6,
    paddingHorizontal: 11,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  filterChipActive: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primaryBorder,
  },
  filterChipText: {
    ...type.label,
    color: colors.textPrimary,
    opacity: 0.85,
  },
  filterChipTextActive: {
    color: colors.primaryAccent,
  },
  group: {
    marginBottom: 14,
  },
  groupLabel: {
    ...type.meta,
    color: colors.textMuted,
    marginBottom: 8,
  },
  historyCard: {
    backgroundColor: colors.surface1,
    borderRadius: radius.lg,
    padding: 12,
    borderWidth: 1,
    borderColor: 'rgba(245,237,228,0.05)',
    marginBottom: 8,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  cardMeta: {
    ...type.metaSm,
    color: colors.textSubtle,
  },
  wordCount: {
    ...type.metaSm,
    color: colors.primary,
    opacity: 0.7,
  },
  cardText: {
    ...type.bodySm,
    color: colors.textPrimary,
    opacity: 0.9,
  },
  tabBar: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingTop: 10,
    paddingBottom: 26,
    paddingHorizontal: 16,
    borderTopWidth: 1,
    borderTopColor: colors.borderSubtle,
    backgroundColor: colors.bgScreen,
  },
  tab: {
    alignItems: 'center',
    gap: 4,
  },
  tabLabel: {
    ...type.tabLabel,
    color: colors.textDisabled,
  },
});
