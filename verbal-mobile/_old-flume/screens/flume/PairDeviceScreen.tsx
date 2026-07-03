import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, type, space, radius } from '../../lib/flumeTokens';

export default function PairDeviceScreen({ navigation }: { navigation: any }) {
  return (
    <View style={s.root}>
      <SafeAreaView style={s.safeArea} edges={['top']}>
        <ScrollView 
          contentContainerStyle={s.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Back Row */}
          <TouchableOpacity 
            style={s.backRow}
            onPress={() => navigation.goBack()}
            activeOpacity={0.7}
          >
            <Ionicons name="chevron-back" size={18} color={colors.textPrimary} />
            <Text style={s.backText}>Pair a computer</Text>
          </TouchableOpacity>

          {/* Instruction */}
          <Text style={s.instruction}>
            Open Flume on your computer and point your camera at the code shown.
          </Text>

          {/* Viewfinder */}
          <View style={s.viewfinder}>
            <View style={s.innerFrame} />
            {/* Corner markers */}
            <View style={[s.corner, s.cornerTL]} />
            <View style={[s.corner, s.cornerTR]} />
            <View style={[s.corner, s.cornerBL]} />
            <View style={[s.corner, s.cornerBR]} />
            {/* Scan line */}
            <View style={s.scanLine} />
          </View>

          {/* Helper Text */}
          <Text style={s.helperText}>
            No computer?{' '}
            <Text style={s.helperLink}>Get the app</Text>
          </Text>

          {/* Spacer */}
          <View style={s.spacer} />

          {/* Ghost Button */}
          <TouchableOpacity 
            style={s.ghostBtn}
            onPress={() => {}}
            activeOpacity={0.7}
          >
            <Text style={s.ghostBtnText}>Enter code instead</Text>
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
  backRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginBottom: space.l,
  },
  backText: {
    ...type.button,
    color: colors.textPrimary,
  },
  instruction: {
    ...type.bodySm,
    color: colors.textSecondary,
    marginBottom: space.l,
    textAlign: 'center',
  },
  viewfinder: {
    aspectRatio: 1,
    borderRadius: radius.xxl,
    backgroundColor: '#14110f',
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: space.l,
  },
  innerFrame: {
    position: 'absolute',
    top: 18,
    left: 18,
    right: 18,
    bottom: 18,
    borderWidth: 2,
    borderColor: colors.primary,
    borderRadius: radius.lg,
  },
  corner: {
    position: 'absolute',
    width: 24,
    height: 24,
    borderColor: colors.primary,
    borderWidth: 3,
  },
  cornerTL: {
    top: 24,
    left: 24,
    borderBottomWidth: 0,
    borderRightWidth: 0,
    borderTopLeftRadius: 14,
  },
  cornerTR: {
    top: 24,
    right: 24,
    borderBottomWidth: 0,
    borderLeftWidth: 0,
    borderTopRightRadius: 14,
  },
  cornerBL: {
    bottom: 24,
    left: 24,
    borderTopWidth: 0,
    borderRightWidth: 0,
    borderBottomLeftRadius: 14,
  },
  cornerBR: {
    bottom: 24,
    right: 24,
    borderTopWidth: 0,
    borderLeftWidth: 0,
    borderBottomRightRadius: 14,
  },
  scanLine: {
    position: 'absolute',
    width: '100%',
    height: 2,
    backgroundColor: colors.primary,
    opacity: 0.5,
    top: '50%',
  },
  helperText: {
    ...type.bodyXs,
    color: colors.textMuted,
    textAlign: 'center',
    marginBottom: space.xl,
  },
  helperLink: {
    color: colors.primary,
  },
  spacer: {
    flex: 1,
  },
  ghostBtn: {
    backgroundColor: 'transparent',
    borderRadius: radius.lg,
    paddingVertical: 13,
    paddingHorizontal: 18,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    alignItems: 'center',
  },
  ghostBtnText: {
    ...type.button,
    color: colors.textPrimary,
  },
});
