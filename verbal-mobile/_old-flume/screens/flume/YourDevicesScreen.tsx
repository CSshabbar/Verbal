import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, type, space, radius } from '../../lib/flumeTokens';

const devices = [
  { id: '1', name: 'MacBook Pro', type: 'laptop', online: true, isDefault: true },
  { id: '2', name: 'Work PC', type: 'desktop', online: true, isDefault: false },
  { id: '3', name: 'Home Desktop', type: 'desktop', online: false, isDefault: false },
];

export default function YourDevicesScreen({ navigation }: { navigation: any }) {
  return (
    <View style={s.root}>
      <SafeAreaView style={s.safeArea} edges={['top']}>
        <ScrollView 
          contentContainerStyle={s.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Top Bar */}
          <View style={s.topBar}>
            <TouchableOpacity 
              style={s.backBtn}
              onPress={() => navigation.goBack()}
              activeOpacity={0.7}
            >
              <Ionicons name="chevron-back" size={18} color={colors.textPrimary} />
              <Text style={s.backText}>Your devices</Text>
            </TouchableOpacity>
            <TouchableOpacity 
              style={s.addBtn}
              onPress={() => navigation.navigate('PairDevice')}
              activeOpacity={0.7}
            >
              <Ionicons name="add" size={16} color={colors.primary} />
            </TouchableOpacity>
          </View>

          {/* Section Label */}
          <Text style={s.sectionLabel}>Paired · {devices.length}</Text>

          {/* Device List */}
          {devices.map(device => (
            <TouchableOpacity
              key={device.id}
              style={[
                s.deviceRow,
                !device.online && s.deviceOffline,
              ]}
              onPress={() => {}}
              activeOpacity={0.7}
            >
              <View style={s.deviceIcon}>
                <Ionicons 
                  name={device.type === 'laptop' ? 'laptop-outline' : 'desktop-outline'} 
                  size={14} 
                  color={colors.textPrimary} 
                />
              </View>
              <View style={s.deviceInfo}>
                <Text style={s.deviceName}>{device.name}</Text>
                <View style={s.deviceMeta}>
                  <View 
                    style={[
                      s.statusDot, 
                      { backgroundColor: device.online ? colors.online : colors.offline }
                    ]} 
                  />
                  <Text 
                    style={[
                      s.statusText,
                      { color: device.online ? colors.textSubtle : colors.textDisabled }
                    ]}
                  >
                    {device.online ? 'online' : 'offline'}
                  </Text>
                </View>
              </View>
              {device.isDefault ? (
                <View style={s.defaultChip}>
                  <Text style={s.defaultChipText}>DEFAULT</Text>
                </View>
              ) : (
                <Ionicons 
                  name="chevron-forward" 
                  size={16} 
                  color={device.online ? colors.textSubtle : colors.textDisabled} 
                />
              )}
            </TouchableOpacity>
          ))}

          {/* Spacer */}
          <View style={s.spacer} />

          {/* Add Device CTA */}
          <TouchableOpacity 
            style={s.addDeviceCta}
            onPress={() => navigation.navigate('PairDevice')}
            activeOpacity={0.7}
          >
            <View style={s.addIcon}>
              <Ionicons name="add" size={14} color={colors.primary} />
            </View>
            <Text style={s.addDeviceText}>Pair another device</Text>
          </TouchableOpacity>
        </ScrollView>
      </SafeAreaView>
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
    paddingBottom: space.xl,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.l,
  },
  backBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  backText: {
    ...type.button,
    color: colors.textPrimary,
  },
  addBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sectionLabel: {
    ...type.meta,
    color: colors.textMuted,
    marginBottom: 8,
  },
  deviceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.l,
    backgroundColor: colors.surface1,
    borderRadius: radius.lg,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    marginBottom: 8,
  },
  deviceOffline: {
    opacity: 0.75,
  },
  deviceIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.sm,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  deviceInfo: {
    flex: 1,
  },
  deviceName: {
    ...type.button,
    color: colors.textPrimary,
    marginBottom: 4,
  },
  deviceMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  statusDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
  },
  statusText: {
    ...type.caption,
  },
  defaultChip: {
    backgroundColor: colors.primarySoft,
    borderRadius: radius.pill,
    paddingVertical: 3,
    paddingHorizontal: 8,
    borderWidth: 1,
    borderColor: colors.primaryBorder,
  },
  defaultChipText: {
    ...type.metaSm,
    color: colors.primaryAccent,
    fontSize: 9.5,
  },
  spacer: {
    flex: 1,
  },
  addDeviceCta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.l,
    backgroundColor: colors.primarySofter,
    borderRadius: radius.lg,
    padding: 14,
    borderWidth: 1,
    borderColor: colors.primaryDashed,
    borderStyle: 'dashed',
  },
  addIcon: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  addDeviceText: {
    flex: 1,
    ...type.buttonSm,
    color: colors.primary,
  },
});
