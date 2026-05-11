import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Animated,
  ScrollView, Alert, Platform, Easing, Vibration,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAudioRecorder, RecordingPresets, AudioModule, useAudioPlayer } from 'expo-audio';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import { Ionicons } from '@expo/vector-icons';
import { colors, fonts, radius } from '../lib/theme';
import { transcribeAudio, formatText } from '../lib/groq';
import {
  addToHistory, getGroqKey, getUserId,
  getDeviceName, getDeviceId, getSyncEnabled,
} from '../lib/storage';
import { supabase } from '../lib/supabase';
import { useDeviceSelector, TARGET_NONE } from '../lib/useDeviceSelector';
import DeviceSelector from '../components/DeviceSelector';

type State = 'idle' | 'recording' | 'processing' | 'done' | 'error';

// Vibration patterns (ms: wait, vibrate, wait, vibrate...)
const VIB_START = [0, 40, 60, 40];          // double tap — start
const VIB_STOP  = [0, 80];                  // single firm — stop
const VIB_DONE  = [0, 30, 40, 30, 40, 60]; // triple light — done

export default function HomeScreen({ navigation }: { navigation?: any }) {
  const [state, setState]           = useState<State>('idle');
  const [result, setResult]         = useState('');
  const [errorMsg, setErrorMsg]     = useState('');
  const [dailyWords, setDailyWords] = useState(0);
  const [totalClips, setTotalClips] = useState(0);

  const { devices, targetDeviceId, setTargetDeviceId } = useDeviceSelector();

  const audioRecorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const pulseAnim     = useRef(new Animated.Value(1)).current;
  const waveAnim      = useRef(new Animated.Value(0)).current;
  const fadeAnim      = useRef(new Animated.Value(0)).current;
  const wavePhase     = useRef(new Animated.Value(0)).current;

  // Continuous pulse while recording
  useEffect(() => {
    if (state === 'recording') {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1.14, duration: 600, useNativeDriver: true, easing: Easing.inOut(Easing.sin) }),
          Animated.timing(pulseAnim, { toValue: 1.0,  duration: 600, useNativeDriver: true, easing: Easing.inOut(Easing.sin) }),
        ])
      ).start();
      Animated.loop(
        Animated.timing(wavePhase, { toValue: 1, duration: 1400, useNativeDriver: false, easing: Easing.linear })
      ).start();
    } else {
      pulseAnim.stopAnimation(); pulseAnim.setValue(1);
      wavePhase.stopAnimation(); wavePhase.setValue(0);
    }
  }, [state]);

  useEffect(() => {
    if (state === 'done') {
      Animated.spring(fadeAnim, { toValue: 1, useNativeDriver: true, tension: 80, friction: 8 }).start();
    } else {
      fadeAnim.setValue(0);
    }
  }, [state]);

  const startRecording = useCallback(async () => {
    try {
      const status = await AudioModule.requestRecordingPermissionsAsync();
      if (!status.granted) {
        Alert.alert('Permission needed', 'Microphone access is required.');
        return;
      }
      await audioRecorder.prepareToRecordAsync();
      audioRecorder.record();
      setState('recording');
      setResult('');

      // Vibration: double tap pattern = "recording started"
      Vibration.vibrate(VIB_START);
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch (e) {
      setErrorMsg('Could not start recording');
      setState('error');
    }
  }, [audioRecorder]);

  const stopRecording = useCallback(async () => {
    // Vibration: single firm = "recording stopped"
    Vibration.vibrate(VIB_STOP);
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
    setState('processing');

    try {
      await audioRecorder.stop();
      const uri = audioRecorder.uri;
      if (!uri) throw new Error('No audio file');

      const apiKey = await getGroqKey();
      if (!apiKey) {
        Alert.alert('No API Key', 'Add your Groq API key in Settings.');
        setState('idle');
        return;
      }

      let text = await transcribeAudio(uri, apiKey);
      if (!text) { setState('idle'); return; }
      text = await formatText(text, apiKey);

      await Clipboard.setStringAsync(text);

      const deviceName = await getDeviceName();
      const deviceId   = await getDeviceId();
      const history    = await addToHistory(text, deviceName, deviceId);
      setTotalClips(history.length);
      setDailyWords(w => w + text.split(' ').length);
      setResult(text);
      setState('done');

      // Vibration: triple light = "done, pasted"
      Vibration.vibrate(VIB_DONE);
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);

      // Sync to other devices
      const syncOn = await getSyncEnabled();
      if (syncOn && targetDeviceId !== TARGET_NONE) {
        const userId     = await getUserId();
        const deviceId   = await getDeviceId();
        const deviceName = await getDeviceName();
        await supabase.from('transcriptions').insert({
          user_id:          userId,
          device_id:        deviceId,
          device_name:      deviceName,
          text,
          target_device_id: targetDeviceId ?? null,
        });
      }
    } catch (e: any) {
      setErrorMsg(e.message ?? 'Transcription failed');
      setState('error');
      Vibration.vibrate([0, 100, 50, 100]);
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    }
  }, [audioRecorder]);

  const handlePress = () => {
    if (state === 'recording') stopRecording();
    else if (state !== 'processing') startRecording();
  };

  const copyResult = async () => {
    if (!result) return;
    await Clipboard.setStringAsync(result);
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  };

  const label = {
    idle:       'Tap to record',
    recording:  'Tap to stop',
    processing: 'Transcribing…',
    done:       'Copied to clipboard ✓',
    error:      errorMsg || 'Error — tap to retry',
  }[state];

  const btnBg = state === 'recording' ? colors.accent : colors.heroBg;

  return (
    <View style={s.root}>
      {/* Hero */}
      <View style={s.hero}>
        <SafeAreaView edges={['top']}>
          <View style={s.heroTop}>
            <Text style={s.logo}>✳</Text>
            <View style={[s.dot, {
              backgroundColor:
                state === 'recording'  ? colors.accent :
                state === 'processing' ? '#4A90E2' :
                state === 'done'       ? colors.green : colors.heroMuted,
            }]} />
            {/* Canvas shortcut */}
            <TouchableOpacity
              style={s.canvasBtn}
              onPress={() => (navigation as any)?.navigate?.('Canvas')}
            >
              <Ionicons name="albums-outline" size={18} color={colors.heroText} />
            </TouchableOpacity>
          </View>

          <Text style={s.headline}>
            {state === 'idle'       ? 'Ready to\ndictate.' :
             state === 'recording'  ? 'Listening…' :
             state === 'processing' ? 'Transcribing…' :
             state === 'done'       ? 'Done.' : 'Oops.'}
          </Text>

          {/* Device selector */}
          <View style={s.selectorRow}>
            <Text style={s.selectorLabel}>
              {targetDeviceId === TARGET_NONE ? 'Local only ·' : 'Send to'}
            </Text>
            <DeviceSelector
              devices={devices}
              targetDeviceId={targetDeviceId}
              onSelect={setTargetDeviceId}
            />
          </View>
        </SafeAreaView>
      </View>

      {/* Sheet */}
      <View style={s.sheet}>
        {/* Record button */}
        <View style={s.btnWrap}>
          <Animated.View style={{ transform: [{ scale: pulseAnim }] }}>
            <TouchableOpacity
              style={[s.btn, { backgroundColor: btnBg }]}
              onPress={handlePress}
              activeOpacity={0.85}
              disabled={state === 'processing'}
            >
              {state === 'processing' ? (
                <Ionicons name="hourglass-outline" size={30} color={colors.heroText} />
              ) : (
                <Ionicons
                  name={state === 'recording' ? 'stop' : 'mic'}
                  size={32}
                  color={colors.heroText}
                />
              )}
            </TouchableOpacity>
          </Animated.View>
          <Text style={s.label}>{label}</Text>
        </View>

        {/* Waveform */}
        {state === 'recording' && (
          <View style={s.wave}>
            {Array.from({ length: 22 }).map((_, i) => {
              const base = 4 + Math.abs(Math.sin(i * 0.75)) * 22;
              return (
                <Animated.View
                  key={i}
                  style={[s.bar, {
                    height: base,
                    opacity: wavePhase.interpolate({
                      inputRange: [0, 1],
                      outputRange: [0.25 + (i % 4) * 0.15, 0.9],
                    }),
                  }]}
                />
              );
            })}
          </View>
        )}

        {/* Cancel button — only while recording, pushed lower */}
        {state === 'recording' && (
          <TouchableOpacity
            style={s.cancelBtn}
            onPress={async () => {
              await audioRecorder.stop();
              setState('idle');
              Vibration.vibrate([0, 60]);
              await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
            }}
            activeOpacity={0.7}
          >
            <Ionicons name="close" size={16} color={colors.cardSub} />
            <Text style={s.cancelTxt}>Cancel recording</Text>
          </TouchableOpacity>
        )}

        {/* Result card */}
        {state === 'done' && result ? (
          <Animated.View style={[s.card, { opacity: fadeAnim }]}>
            <ScrollView style={s.cardScroll} showsVerticalScrollIndicator={false}>
              <Text style={s.cardText}>{result}</Text>
            </ScrollView>
            <TouchableOpacity style={s.copyRow} onPress={copyResult}>
              <Ionicons name="copy-outline" size={15} color={colors.accent} />
              <Text style={s.copyTxt}>Copy again</Text>
            </TouchableOpacity>
          </Animated.View>
        ) : null}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root:     { flex: 1, backgroundColor: colors.heroBg },
  hero:     { backgroundColor: colors.heroBg, paddingHorizontal: 24, paddingBottom: 20 },
  heroTop:  { flexDirection: 'row', alignItems: 'center', marginBottom: 18, marginTop: 8, gap: 8, flex: 1 },
  logo:     { fontSize: 26, color: colors.heroText, fontWeight: fonts.thin },
  dot:      { width: 8, height: 8, borderRadius: 4 },
  canvasBtn:{ marginLeft: 'auto' as any, width: 34, height: 34, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.08)', alignItems: 'center', justifyContent: 'center' },
  headline: { fontSize: 34, fontWeight: fonts.bold, color: colors.heroText, lineHeight: 40, marginBottom: 14 },

  selectorRow:  { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 4 },
  selectorLabel:{ fontSize: 11, color: 'rgba(255,255,255,0.35)', fontWeight: fonts.medium },

  sheet: {
    flex: 1, backgroundColor: colors.sheetBg,
    borderTopLeftRadius: 28, borderTopRightRadius: 28,
    paddingTop: 32, paddingHorizontal: 24,
  },

  btnWrap: { alignItems: 'center', marginBottom: 24 },
  btn: {
    width: 80, height: 80, borderRadius: 40,
    alignItems: 'center', justifyContent: 'center',
    shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 14, shadowOffset: { width: 0, height: 5 },
    elevation: 8,
  },
  label: { marginTop: 14, fontSize: 13, color: colors.cardSub, fontWeight: fonts.medium },

  wave:  { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 3, marginBottom: 20 },
  bar:   { width: 3, backgroundColor: colors.accent, borderRadius: 2 },

  cancelBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    alignSelf: 'center',
    marginTop: 32,        // pushed lower — more breathing room from waveform
    paddingHorizontal: 20, paddingVertical: 10,
    borderRadius: 20, backgroundColor: colors.iconGray,
  },
  cancelTxt: { fontSize: 13, color: colors.cardSub, fontWeight: fonts.medium },

  card: {
    backgroundColor: colors.cardBg, borderRadius: radius.lg,
    padding: 16, maxHeight: 230,
    shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 8, shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  cardScroll: { maxHeight: 170 },
  cardText:   { fontSize: 15, color: colors.cardText, lineHeight: 22, fontWeight: fonts.light },
  copyRow:    { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 10, alignSelf: 'flex-end' },
  copyTxt:    { fontSize: 12, color: colors.accent, fontWeight: fonts.medium },
});
