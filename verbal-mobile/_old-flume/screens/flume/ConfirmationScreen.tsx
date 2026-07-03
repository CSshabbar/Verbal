import React, { useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, type, space, radius } from '../../lib/flumeTokens';

export default function ConfirmationScreen({ navigation }: { navigation: any }) {
  // Auto-dismiss after 3 seconds
  useEffect(() => {
    const timer = setTimeout(() => {
      navigation.navigate('FlumeHome');
    }, 3000);
    return () => clearTimeout(timer);
  }, []);

  const handleDone = () => {
    navigation.navigate('FlumeHome');
  };

  return (
    <View style={s.root}>
      <SafeAreaView style={s.safeArea} edges={['top']}>
        <ScrollView 
          contentContainerStyle={s.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Success Header */}
          <View style={s.successHeader}>
            <View style={s.successRing}>
              <Ionicons name="checkmark" size={26} color={colors.primary} />
            </View>
            <Text style={s.successTitle}>Pasted to MacBook</Text>
            <Text style={s.successMeta}>14 sec · 38 words · 1.8s to transcribe</Text>
          </View>

          {/* Transcript Label */}
          <Text style={s.transcriptLabel}>Transcript</Text>

          {/* Transcript Card */}
          <View style={s.transcriptCard}>
            <Text style={s.transcriptText}>
              Let's move the launch to next Tuesday and let the QA team know.
            </Text>
          </View>

          {/* Action Rows */}
          <View style={s.actionRows}>
            <TouchableOpacity style={s.actionRow} activeOpacity={0.7}>
              <Ionicons name="copy-outline" size={18} color={colors.textPrimary} />
              <Text style={s.actionText}>Copy again</Text>
            </TouchableOpacity>

            <TouchableOpacity 
              style={s.actionRow}
              activeOpacity={0.7}
              onPress={() => navigation.navigate('HistoryList')}
            >
              <Ionicons name="list-outline" size={18} color={colors.textPrimary} />
              <Text style={s.actionText}>Edit in History</Text>
            </TouchableOpacity>

            <TouchableOpacity style={s.actionRow} activeOpacity={0.7}>
              <Ionicons name="paper-plane-outline" size={18} color={colors.textPrimary} />
              <Text style={s.actionText}>Resend to another device</Text>
            </TouchableOpacity>
          </View>

          {/* Done Button */}
          <TouchableOpacity 
            style={s.doneBtn}
            onPress={handleDone}
            activeOpacity={0.7}
          >
            <Text style={s.doneBtnText}>Done</Text>
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
    paddingTop: space.l,
    paddingHorizontal: space.l,
    paddingBottom: space.xl,
  },
  successHeader: {
    alignItems: 'center',
    marginBottom: 22,
    gap: 10,
  },
  successRing: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.primarySoft,
    borderWidth: 1.5,
    borderColor: colors.primaryBorder,
    alignItems: 'center',
    justifyContent: 'center',
  },
  successTitle: {
    ...type.subtitle,
    color: colors.textPrimary,
  },
  successMeta: {
    ...type.bodyXs,
    color: colors.textMuted,
  },
  transcriptLabel: {
    ...type.meta,
    color: colors.textMuted,
    marginBottom: 8,
  },
  transcriptCard: {
    backgroundColor: colors.surface1,
    borderRadius: radius.lg,
    padding: 14,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    marginBottom: 20,
  },
  transcriptText: {
    ...type.bodySm,
    color: colors.textPrimary,
    lineHeight: 19,
  },
  actionRows: {
    gap: 8,
    marginBottom: 20,
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: colors.surface1,
    borderRadius: radius.lg,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  actionText: {
    ...type.body,
    color: colors.textPrimary,
  },
  doneBtn: {
    backgroundColor: colors.primary,
    borderRadius: radius.xl,
    paddingVertical: 13,
    paddingHorizontal: 18,
    alignItems: 'center',
  },
  doneBtnText: {
    ...type.buttonPrimary,
    color: colors.primaryInk,
  },
});
