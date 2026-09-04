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
  Image,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import { Text, Button } from '../components';
import { colors, fonts, radius, pressedStyle } from '../theme';
import {
  reportIssue,
  REPORT_MESSAGE_MAX,
  REPORT_IMAGE_MAX_BYTES,
  type ReportImage,
} from '../../lib/reportIssue';
import { supabase } from '../../lib/supabase';

type Shot = ReportImage & { uri: string };

type Props = { onBack: () => void };

export const ReportIssueScreen: React.FC<Props> = ({ onBack }) => {
  const insets = useSafeAreaInsets();
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [shot, setShot] = useState<Shot | null>(null);
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

  const attachScreenshot = async () => {
    if (sending) return;
    try {
      // Same picker flow as Canvas's sendPhoto (useCanvas.ts) — permission,
      // library, images only — plus base64 so the bytes ride the report JSON.
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('Photos permission needed', 'Allow photo access to attach a screenshot.');
        return;
      }
      const res = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.7,
        base64: true,
      });
      if (res.canceled || !res.assets?.length) return;
      const a = res.assets[0];
      if (!a.base64) {
        Alert.alert('Could not read that image', 'Try a different one.');
        return;
      }
      if (a.base64.length * 0.75 > REPORT_IMAGE_MAX_BYTES) {
        Alert.alert('Image is too large', 'Screenshots up to 5 MB can be attached.');
        return;
      }
      const mime = (a.mimeType ?? '').toLowerCase();
      let ext = mime.startsWith('image/') ? mime.slice(6) : '';
      if (ext === 'jpeg') ext = 'jpg';
      if (!['png', 'jpg', 'webp', 'gif'].includes(ext)) {
        const m = /\.(png|jpe?g|webp|gif)(\?|$)/i.exec(a.uri ?? '');
        ext = m ? m[1].toLowerCase().replace('jpeg', 'jpg') : 'jpg';
      }
      setShot({ base64: a.base64, ext, uri: a.uri });
    } catch {
      Alert.alert('Could not open the photo library', 'Please try again.');
    }
  };

  const send = async () => {
    if (sending) return;
    setSending(true);
    const result = await reportIssue(message, shot);
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

          {shot ? (
            <View style={styles.shotRow}>
              <Image source={{ uri: shot.uri }} style={styles.shotThumb} />
              <Text variant="bodyXs" color={colors.textSecondary} style={{ flex: 1 }}>
                Screenshot attached
              </Text>
              <Pressable
                onPress={() => setShot(null)}
                hitSlop={8}
                accessibilityRole="button"
                accessibilityLabel="Remove screenshot"
                style={({ pressed }) => pressed && pressedStyle}
              >
                <Ionicons name="close-circle" size={22} color={colors.textSubtle} />
              </Pressable>
            </View>
          ) : (
            <Pressable
              onPress={attachScreenshot}
              accessibilityRole="button"
              style={({ pressed }) => [styles.attachBtn, pressed && pressedStyle]}
            >
              <Ionicons name="image-outline" size={18} color={colors.textSecondary} />
              <Text variant="bodyXs" color={colors.textSecondary}>Attach screenshot</Text>
            </Pressable>
          )}

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
  attachBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    alignSelf: 'flex-start',
    marginTop: 12,
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surface2,
  },
  shotRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginTop: 12,
    padding: 8,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    backgroundColor: colors.surface2,
  },
  shotThumb: {
    width: 44,
    height: 44,
    borderRadius: 8,
    backgroundColor: colors.borderSubtle,
  },
});
