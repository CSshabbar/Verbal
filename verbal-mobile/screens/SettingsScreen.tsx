import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  TextInput, Switch, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, fonts, radius } from '../lib/theme';
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
  root:     { flex: 1, backgroundColor: colors.heroBg },
  hero:     { backgroundColor: colors.heroBg, paddingHorizontal: 24, paddingBottom: 28 },
  headline: { fontSize: 30, fontWeight: fonts.bold, color: colors.heroText, marginTop: 8 },
  sub:      { fontSize: 13, color: colors.heroMuted, marginTop: 4 },

  sheet:   {
    flex: 1,
    backgroundColor: colors.sheetBg,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
  },
  content: { paddingHorizontal: 16, paddingTop: 24 },

  sectionLabel: {
    fontSize: 10, fontWeight: fonts.bold,
    color: colors.cardSub, letterSpacing: 1,
    marginBottom: 10, marginTop: 4, marginLeft: 2,
  },

  card: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: 14,
    marginBottom: 10,
    shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 6, shadowOffset: { width: 0, height: 2 },
    elevation: 1,
  },
  cardHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  iconBox:    {
    width: 34, height: 34, borderRadius: 10,
    backgroundColor: colors.accentDim,
    alignItems: 'center', justifyContent: 'center', marginRight: 12,
  },
  cardInfo:   { flex: 1 },
  cardTitle:  { fontSize: 14, fontWeight: fonts.semibold, color: colors.cardText },
  cardSub:    { fontSize: 11, color: colors.cardSub, marginTop: 1 },
  greenDot:   { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.green },
  redDot:     { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.cardSub },

  input: {
    backgroundColor: colors.sheetBg,
    borderRadius: radius.sm,
    paddingHorizontal: 12, paddingVertical: 10,
    fontSize: 13, color: colors.cardText,
    marginTop: 10,
    fontFamily: 'monospace',
  },
  saveBtn: {
    alignSelf: 'flex-end',
    marginTop: 8,
    backgroundColor: colors.heroBg,
    paddingHorizontal: 16, paddingVertical: 8,
    borderRadius: radius.sm,
  },
  saveBtnText: { fontSize: 12, color: colors.heroText, fontWeight: fonts.semibold },
  hint:        { fontSize: 10, color: colors.cardSub, marginTop: 6 },
});
