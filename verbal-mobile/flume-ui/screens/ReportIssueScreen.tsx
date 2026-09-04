/**
 * ReportIssueScreen — in-app "Report an issue" (beta launch, 2026-09).
 * A message box and a Send button; the report goes to the `report-issue`
 * Edge Function via lib/reportIssue (saved to `issue_reports`, best-effort
 * emailed to the founder). Hosted in the Menu modal stack, reached from
 * Settings → About → Report an issue.
 */
import React, { useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  TextInput,
  Pressable,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { Text, Button } from '../components';
import { colors, fonts, radius, pressedStyle } from '../theme';
import { reportIssue, REPORT_MESSAGE_MAX } from '../../lib/reportIssue';
import { supabase } from '../../lib/supabase';

type Props = { onBack: () => void };

export const ReportIssueScreen: React.FC<Props> = ({ onBack }) => {
  const insets = useSafeAreaInsets();
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  // Optimistically assume signed-in so the anonymity warning never flashes for
  // the common case; corrected once the session read resolves (desktop parity —
  // the Support pane shows the same two lines).
  const [signedIn, setSignedIn] = useState(true);

  useEffect(() => {
    let alive = true;
    supabase.auth.getSession()
      .then(({ data }) => { if (alive) setSignedIn(!!data.session); })
      .catch(() => { /* leave optimistic */ });
    return () => { alive = false; };
  }, []);

  const send = async () => {
    if (sending) return;
    setSending(true);
    const result = await reportIssue(message);
    setSending(false);
    if (!result.ok) {
      // Native Alert, not the custom confirm modal — this screen lives in the
      // native-stack MODAL, where a JS <Modal> doesn't reliably receive
      // touches on iOS (the SettingsScreen sign-out lesson).
      Alert.alert('Could not send the report', result.error || 'Please try again.');
      return;
    }
    try {
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch { /* haptics are garnish */ }
    Alert.alert('Report sent', 'Thank you — it goes straight to the team.', [
      { text: 'Done', onPress: onBack },
    ]);
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={[styles.root, { paddingTop: insets.top + 12 }]}>
        <View style={styles.topBar}>
          <Pressable
            onPress={onBack}
            style={({ pressed }) => pressed && pressedStyle}
            accessibilityRole="button"
            accessibilityLabel="Back"
            hitSlop={8}
          >
            <Ionicons name="chevron-back" size={24} color={colors.textSecondary} />
          </Pressable>
          <Text variant="titleSm">Report an issue</Text>
          <View style={{ width: 24 }} />
        </View>

        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingBottom: 24 }}>
          <Text variant="bodyXs" color={colors.textSecondary} style={{ marginTop: 8, marginBottom: 6 }}>
            Something broken or confusing? Describe it below — reports go straight to the team.
          </Text>
          <Text variant="bodyXs" color={colors.textSubtle} style={{ marginBottom: 14 }}>
            {signedIn
              ? 'Sent with your account email so we can follow up.'
              : "You're signed out, so the report is anonymous — include an email in the text if you want a reply."}
          </Text>

          <View style={styles.fieldHead}>
            <Text variant="meta" color={colors.textSubtle}>WHAT HAPPENED</Text>
            <Text variant="meta" color={colors.textSubtle}>
              {message.length}/{REPORT_MESSAGE_MAX}
            </Text>
          </View>
          <TextInput
            value={message}
            onChangeText={t => setMessage(t.slice(0, REPORT_MESSAGE_MAX))}
            placeholder="What were you doing, and what did Flume do instead?"
            placeholderTextColor={colors.textSubtle}
            maxLength={REPORT_MESSAGE_MAX}
            multiline
            style={styles.input}
          />

          <Button
            label={sending ? 'Sending…' : 'Send report'}
            loading={sending}
            disabled={!message.trim() || sending}
            onPress={send}
            fullWidth
            style={{ marginTop: 16 }}
          />
        </ScrollView>
      </View>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bgScreen, paddingHorizontal: 18 },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  fieldHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  input: {
    backgroundColor: colors.surface2,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: colors.textPrimary,
    fontFamily: fonts.regular,
    fontSize: 16,
    minHeight: 160,
    textAlignVertical: 'top',
  },
});
