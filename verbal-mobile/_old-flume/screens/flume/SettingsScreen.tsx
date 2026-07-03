import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, type, space, radius } from '../../lib/flumeTokens';

export default function SettingsScreen({ navigation }: { navigation: any }) {
  return (
    <View style={s.root}>
      <SafeAreaView style={s.safeArea} edges={['top']}>
        <ScrollView 
          contentContainerStyle={s.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Header */}
          <Text style={s.headline}>Settings</Text>
          <Text style={s.sub}>Keys & preferences</Text>

          {/* API Keys Section */}
          <Text style={s.sectionLabel}>API KEYS</Text>

          {/* Groq Key Card */}
          <TouchableOpacity style={s.card} activeOpacity={0.7}>
            <View style={s.cardHeader}>
              <View style={s.iconBox}>
                <Ionicons name="key-outline" size={18} color={colors.primary} />
              </View>
              <View style={s.cardInfo}>
                <Text style={s.cardTitle}>Groq API Key</Text>
                <Text style={s.cardSub}>Transcription + formatting</Text>
              </View>
              <View style={s.greenDot} />
            </View>
            <Text style={s.input}>••••••••••••gk2X</Text>
            <TouchableOpacity style={s.saveBtn}>
              <Text style={s.saveBtnText}>Save</Text>
            </TouchableOpacity>
          </TouchableOpacity>

          {/* Devices Section */}
          <Text style={s.sectionLabel}>DEVICES</Text>

          {/* Devices Card */}
          <TouchableOpacity 
            style={s.card}
            onPress={() => navigation.navigate('YourDevices')}
            activeOpacity={0.7}
          >
            <View style={s.cardHeader}>
              <View style={s.iconBox}>
                <Ionicons name="laptop-outline" size={18} color={colors.primary} />
              </View>
              <View style={s.cardInfo}>
                <Text style={s.cardTitle}>Your Devices</Text>
                <Text style={s.cardSub}>3 paired devices</Text>
              </View>
              <Ionicons name="chevron-forward" size={16} color={colors.textSubtle} />
            </View>
          </TouchableOpacity>
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
        <TouchableOpacity 
          style={s.tab} 
          activeOpacity={0.7}
          onPress={() => navigation.navigate('HistoryList')}
        >
          <Ionicons name="time-outline" size={14} color={colors.textDisabled} />
          <Text style={s.tabLabel}>History</Text>
        </TouchableOpacity>
        <TouchableOpacity style={s.tab} activeOpacity={0.7}>
          <Ionicons name="settings" size={14} color={colors.primary} />
          <Text style={[s.tabLabel, { color: colors.primary }]}>Settings</Text>
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
    paddingTop: space.l,
    paddingHorizontal: space.l,
    paddingBottom: space.base,
  },
  headline: {
    ...type.titleSm,
    color: colors.textPrimary,
    marginBottom: 4,
  },
  sub: {
    ...type.body,
    color: colors.textMuted,
    marginBottom: space.xl,
  },
  sectionLabel: {
    ...type.meta,
    color: colors.textMuted,
    marginBottom: 10,
    marginTop: 4,
    marginLeft: 2,
  },
  card: {
    backgroundColor: colors.surface1,
    borderRadius: radius.lg,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  iconBox: {
    width: 34,
    height: 34,
    borderRadius: radius.md,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  cardInfo: {
    flex: 1,
  },
  cardTitle: {
    ...type.button,
    color: colors.textPrimary,
  },
  cardSub: {
    ...type.caption,
    color: colors.textMuted,
    marginTop: 1,
  },
  greenDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.online,
  },
  input: {
    backgroundColor: colors.surface2,
    borderRadius: radius.sm,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    color: colors.textPrimary,
    marginTop: 10,
    fontFamily: 'monospace',
  },
  saveBtn: {
    alignSelf: 'flex-end',
    marginTop: 8,
    backgroundColor: colors.surface3,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: radius.sm,
  },
  saveBtnText: {
    ...type.buttonSm,
    color: colors.textPrimary,
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
