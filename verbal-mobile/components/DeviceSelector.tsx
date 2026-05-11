import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, fonts } from '../lib/theme';
import { Device } from '../lib/useDeviceSelector';

// Special sentinel values — must match useDeviceSelector.ts
export const TARGET_NONE = '__none__';
export const TARGET_ALL  = null;

interface Props {
  devices:        Device[];
  targetDeviceId: string | null;
  onSelect:       (id: string | null) => void;
}

type Segment = {
  id:    string | null;
  icon:  string;           // Ionicons name
  label: string;
  tint?: string;           // override active color
};

function iconFor(dtype: string): string {
  if (dtype === 'iphone' || dtype === 'ios') return 'phone-portrait-outline';
  if (dtype === 'android')                   return 'phone-portrait-outline';
  if (dtype === 'mac')                       return 'laptop-outline';
  return 'desktop-outline';
}

export default function DeviceSelector({ devices, targetDeviceId, onSelect }: Props) {
  // Build segments
  const typeCounts: Record<string, number> = {};
  const deviceSegs: Segment[] = devices.map(d => {
    typeCounts[d.device_type] = (typeCounts[d.device_type] ?? 0) + 1;
    const n = typeCounts[d.device_type];
    return {
      id:    d.device_id,
      icon:  iconFor(d.device_type),
      label: n > 1 ? String(n) : '',
    };
  });

  const segments: Segment[] = [
    { id: TARGET_NONE, icon: 'ban-outline',        label: 'None' },
    { id: TARGET_ALL,  icon: 'radio-button-on-outline', label: 'All' },
    ...deviceSegs,
  ];

  return (
    <View style={s.container}>
      {segments.map((seg, i) => {
        const isActive = seg.id === targetDeviceId;
        const isNone   = seg.id === TARGET_NONE;
        const isAll    = seg.id === TARGET_ALL;

        const activeBg = isNone
          ? 'rgba(255,255,255,0.12)'
          : isAll
          ? colors.accent
          : colors.accent;

        return (
          <TouchableOpacity
            key={seg.id ?? 'all'}
            style={[s.seg, isActive && { backgroundColor: activeBg }]}
            onPress={() => onSelect(seg.id)}
            activeOpacity={0.7}
          >
            <Ionicons
              name={seg.icon as any}
              size={14}
              color={isActive ? '#fff' : 'rgba(255,255,255,0.35)'}
            />
            {seg.label ? (
              <Text style={[s.segTxt, isActive && s.segTxtActive]}>
                {seg.label}
              </Text>
            ) : null}
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const s = StyleSheet.create({
  container: {
    flexDirection: 'row',
    backgroundColor: 'rgba(255,255,255,0.07)',
    borderRadius: 12,
    padding: 3,
    gap: 2,
  },
  seg: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 9,
  },
  segTxt:       { fontSize: 11, color: 'rgba(255,255,255,0.35)', fontWeight: fonts.medium },
  segTxtActive: { color: '#fff' },
});
