import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  TextInput, Switch, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, fonts, radius } from '../lib/theme';
import { flumeColors, flumeFonts, flumeSpacing, flumeRadius } from '../lib/flumeTheme';
import {
  getGroqKey, setGroqKey,
  getUserId, setUserId,
  getDeviceName, setDeviceName,
  getSyncEnabled, setSyncEnabled,
} from '../lib/storage';

export default function SettingsScreen() {
  const [groqKey,     setGroqKeyState]     = useState('');
  const [userId,      setUserIdState]      = useState('');
  const [deviceName,  setDeviceNameState]  = useState('');
  const [syncEnabled, setSyncEnabledState] = useState(false);
  const [saved,       setSaved]            = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setGroqKeyState(await getGroqKey());
      setUserIdState(await getUserId());
      setDeviceNameState(await getDeviceName());
      setSyncEnabledState(await getSyncEnabled());
    })();
  }, []);

  const save = async (key: string, value: string | boolean) => {
    if (key === 'groq')   await setGroqKey(value as string);
    if (key === 'userId') await setUserId(value as string);
    if (key === 'device') await setDeviceName(value as string);
    if (key === 'sync')   await setSyncEnabled(value as boolean);
    setSaved(key);
    setTimeout(() => setSaved(null), 1500);
  };

  const maskKey = (k: string) => k.length > 8 ? `...${k.slice(-8)}` : k;

  return (
    <View style={styles.root}>
      <View style={styles.hero}>
        <SafeAreaView edges={['top']}>
          <Text style={styles.headline}>Settings</Text>
          <Text style={styles.sub}>Keys & preferences</Text>
        </SafeAreaView>
      </View>

      <ScrollView style={styles.sheet} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>

        {/* ── API Keys ── */}
        <Text style={styles.sectionLabel}>API KEYS</Text>

        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <View style={styles.iconBox}>
              <Ionicons name="key-outline" size={18} color={colors.accent} />
            </View>
            <View style={styles.cardInfo}>
              <Text style={styles.cardTitle}>Groq API Key</Text>
              <Text style={styles.cardSub}>Transcription + formatting</Text>
            </View>
            {groqKey ? (
              <View style={styles.greenDot} />
            ) : (
              <View style={styles.redDot} />
            )}
          </View>
          <TextInput
            style={styles.input}
            value={groqKey}
            onChangeText={setGroqKeyState}
            placeholder="gsk_..."
            placeholderTextColor={colors.cardSub}
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
          />
          <TouchableOpacity
            style={styles.saveBtn}
            onPress={() => save('groq', groqKey)}
          >
            <Text style={styles.saveBtnText}>
              {saved === 'groq' ? '✓ Saved' : 'Save key'}
            </Text>
          </TouchableOpacity>
          <Text style={styles.hint}>Free at console.groq.com</Text>
        </View>

        {/* ── Sync ── */}
        <Text style={styles.sectionLabel}>CROSS-DEVICE SYNC</Text>

        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <View style={styles.iconBox}>
              <Ionicons name="sync-outline" size={18} color={colors.accent} />
            </View>
            <View style={styles.cardInfo}>
              <Text style={styles.cardTitle}>Enable sync</Text>
              <Text style={styles.cardSub}>Sync with Mac & other devices</Text>
            </View>
            <Switch
              value={syncEnabled}
              onValueChange={v => { setSyncEnabledState(v); save('sync', v); }}
              trackColor={{ false: colors.iconGray, true: colors.accent }}
              thumbColor="#fff"
            />
          </View>
        </View>

        {syncEnabled && (
          <>
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <View style={styles.iconBox}>
                  <Ionicons name="person-outline" size={18} color={colors.accent} />
                </View>
                <View style={styles.cardInfo}>
                  <Text style={styles.cardTitle}>User ID</Text>
                  <Text style={styles.cardSub}>Same on all your devices</Text>
                </View>
              </View>
              <TextInput
                style={styles.input}
                value={userId}
                onChangeText={setUserIdState}
                placeholder="your@email.com or any unique ID"
                placeholderTextColor={colors.cardSub}
                autoCapitalize="none"
                autoCorrect={false}
              />
              <TouchableOpacity
                style={styles.saveBtn}
                onPress={() => save('userId', userId)}
              >
                <Text style={styles.saveBtnText}>
                  {saved === 'userId' ? '✓ Saved' : 'Save ID'}
                </Text>
              </TouchableOpacity>
            </View>

            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <View style={styles.iconBox}>
                  <Ionicons name="phone-portrait-outline" size={18} color={colors.accent} />
                </View>
                <View style={styles.cardInfo}>
                  <Text style={styles.cardTitle}>Device name</Text>
                  <Text style={styles.cardSub}>Shown on other devices</Text>
                </View>
              </View>
              <TextInput
                style={styles.input}
                value={deviceName}
                onChangeText={setDeviceNameState}
                placeholder="iPhone"
                placeholderTextColor={colors.cardSub}
                autoCorrect={false}
              />
              <TouchableOpacity
                style={styles.saveBtn}
                onPress={() => save('device', deviceName)}
              >
                <Text style={styles.saveBtnText}>
                  {saved === 'device' ? '✓ Saved' : 'Save name'}
                </Text>
              </TouchableOpacity>
            </View>
          </>
        )}

        {/* ── About ── */}
        <Text style={styles.sectionLabel}>ABOUT</Text>
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <View style={styles.iconBox}>
              <Ionicons name="information-circle-outline" size={18} color={colors.accent} />
            </View>
            <View style={styles.cardInfo}>
              <Text style={styles.cardTitle}>Verbal</Text>
              <Text style={styles.cardSub}>v1.0  ·  Voice dictation</Text>
            </View>
          </View>
        </View>

        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root:     { flex: 1, backgroundColor: flumeColors.background },
  hero:     { backgroundColor: flumeColors.background, paddingHorizontal: flumeSpacing.xl, paddingBottom: flumeSpacing.xl },
  headline: { fontSize: flumeFonts.xxxl, fontWeight: flumeFonts.light, color: flumeColors.textPrimary, marginTop: flumeSpacing.md, letterSpacing: -0.5 },
  sub:      { fontSize: flumeFonts.md, color: flumeColors.textSecondary, marginTop: 4 },

  sheet:   {
    flex: 1,
    backgroundColor: flumeColors.surface,
    borderTopLeftRadius: flumeRadius.xxl,
    borderTopRightRadius: flumeRadius.xxl,
  },
  content: { paddingHorizontal: flumeSpacing.lg, paddingTop: flumeSpacing.xl },

  sectionLabel: {
    fontSize: flumeFonts.xs, fontWeight: flumeFonts.semibold,
    color: flumeColors.textTertiary, letterSpacing: 1.5,
    marginBottom: flumeSpacing.md, marginTop: flumeSpacing.sm, marginLeft: flumeSpacing.xs,
  },

  card: {
    backgroundColor: flumeColors.background,
    borderRadius: flumeRadius.lg,
    padding: flumeSpacing.lg,
    marginBottom: flumeSpacing.md,
    shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 10, shadowOffset: { width: 0, height: 3 },
    elevation: 2,
    borderWidth: 1, borderColor: flumeColors.border,
  },
  cardHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: flumeSpacing.md },
  iconBox:    {
    width: 36, height: 36, borderRadius: flumeRadius.md,
    backgroundColor: flumeColors.accentDim,
    alignItems: 'center', justifyContent: 'center', marginRight: flumeSpacing.md,
  },
  cardInfo:   { flex: 1 },
  cardTitle:  { fontSize: flumeFonts.md, fontWeight: flumeFonts.semibold, color: flumeColors.textPrimary },
  cardSub:    { fontSize: flumeFonts.xs, color: flumeColors.textSecondary, marginTop: 2 },
  greenDot:   { width: 8, height: 8, borderRadius: 4, backgroundColor: flumeColors.success },
  redDot:     { width: 8, height: 8, borderRadius: 4, backgroundColor: flumeColors.textTertiary },

  input: {
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderRadius: flumeRadius.md,
    paddingHorizontal: flumeSpacing.md, paddingVertical: flumeSpacing.sm,
    fontSize: flumeFonts.sm, color: flumeColors.textPrimary,
    marginTop: flumeSpacing.md,
    fontFamily: 'monospace',
  },
  saveBtn: {
    alignSelf: 'flex-end',
    marginTop: flumeSpacing.md,
    backgroundColor: flumeColors.buttonPrimary,
    paddingHorizontal: flumeSpacing.lg, paddingVertical: flumeSpacing.sm,
    borderRadius: flumeRadius.md,
  },
  saveBtnText: { fontSize: flumeFonts.sm, color: flumeColors.buttonPrimaryText, fontWeight: flumeFonts.semibold },
  hint:        { fontSize: flumeFonts.xs, color: flumeColors.textTertiary, marginTop: flumeSpacing.sm },
});
