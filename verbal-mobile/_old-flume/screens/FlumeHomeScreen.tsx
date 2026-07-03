import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Animated,
  Dimensions, Vibration,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAudioRecorder, RecordingPresets, AudioModule } from 'expo-audio';
import * as Haptics from 'expo-haptics';
import { Ionicons } from '@expo/vector-icons';
import { colors, fonts } from '../lib/theme';
import { transcribeAudio } from '../lib/groq';
import { getGroqKey, getDeviceName, getDeviceId, addToHistory } from '../lib/storage';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

export default function FlumeHomeScreen({ navigation }: { navigation?: any }) {
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState('');
  const [waveformValues, setWaveformValues] = useState<number[]>([]);

  const audioRecorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const waveAnim = useRef(new Animated.Value(0)).current;

  // Generate waveform bars
  const bars = Array.from({ length: 40 }, (_, i) => i);

  // Animate waveform while recording
  useEffect(() => {
    if (isRecording) {
      const interval = setInterval(() => {
        const newValues = bars.map(() => Math.random() * 40 + 10);
        setWaveformValues(newValues);
      }, 100);
      return () => clearInterval(interval);
    } else {
      setWaveformValues([]);
    }
  }, [isRecording]);

  const startRecording = useCallback(async () => {
    try {
      const status = await AudioModule.requestRecordingPermissionsAsync();
      if (!status.granted) {
        alert('Microphone permission needed');
        return;
      }
      await audioRecorder.prepareToRecordAsync();
      audioRecorder.record();
      setIsRecording(true);
      setResult('');
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      Vibration.vibrate([0, 50]);
    } catch (e) {
      console.error(e);
    }
  }, [audioRecorder]);

  const stopRecording = useCallback(async () => {
    setIsRecording(false);
    setIsProcessing(true);
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
    Vibration.vibrate([0, 100]);

    try {
      await audioRecorder.stop();
      const uri = audioRecorder.uri;
      if (!uri) throw new Error('No audio file');

      const apiKey = await getGroqKey();
      if (!apiKey) {
        alert('Add Groq API key in settings');
        setIsProcessing(false);
        return;
      }

      const text = await transcribeAudio(uri, apiKey);
      if (text) {
        setResult(text);
        const deviceName = await getDeviceName();
        const deviceId = await getDeviceId();
        await addToHistory(text, deviceName, deviceId);
      }
    } catch (e: any) {
      console.error(e);
    } finally {
      setIsProcessing(false);
    }
  }, [audioRecorder]);

  const handlePress = () => {
    if (isRecording) stopRecording();
    else if (!isProcessing) startRecording();
  };

  return (
    <SafeAreaView style={s.container} edges={['top']}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => navigation?.navigate('Settings')}>
          <Ionicons name="settings-outline" size={24} color={colors.heroText} />
        </TouchableOpacity>
        <Text style={s.logo}>FLUME</Text>
        <TouchableOpacity onPress={() => navigation?.navigate('History')}>
          <Ionicons name="time-outline" size={24} color={colors.heroText} />
        </TouchableOpacity>
      </View>

      {/* Main Content */}
      <View style={s.main}>
        {result ? (
          // Result View
          <View style={s.resultContainer}>
            <View style={s.resultCard}>
              <Text style={s.resultText}>{result}</Text>
            </View>
            <TouchableOpacity
              style={s.copyButton}
              onPress={() => {
                // Copy to clipboard logic here
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
              }}
            >
              <Ionicons name="copy-outline" size={20} color={colors.accent} />
              <Text style={s.copyText}>Copy to clipboard</Text>
            </TouchableOpacity>
          </View>
        ) : (
          // Recording View
          <View style={s.recordingContainer}>
            <Text style={s.status}>
              {isRecording ? 'Listening…' : isProcessing ? 'Transcribing…' : 'Ready to dictate'}
            </Text>

            {/* Waveform */}
            <View style={s.waveform}>
              {bars.map((_, i) => (
                <Animated.View
                  key={i}
                  style={[
                    s.bar,
                    {
                      height: waveformValues[i] || 4,
                      opacity: isRecording ? 1 : 0.3,
                    },
                  ]}
                />
              ))}
            </View>

            {/* Device Selector */}
            <TouchableOpacity style={s.deviceSelector}>
              <Ionicons name="phone-portrait-outline" size={18} color={colors.heroMuted} />
              <Text style={s.deviceText}>MacBook Pro · Sync enabled</Text>
              <Ionicons name="chevron-down" size={18} color={colors.heroMuted} />
            </TouchableOpacity>
          </View>
        )}
      </View>

      {/* Record Button */}
      <View style={s.footer}>
        <TouchableOpacity
          style={[
            s.recordButton,
            {
              backgroundColor: isRecording ? colors.accent : colors.heroBg,
              transform: [{ scale: isRecording ? 1.1 : 1 }],
            },
          ]}
          onPress={handlePress}
          disabled={isProcessing}
        >
          <Ionicons
            name={isRecording ? 'stop' : 'mic'}
            size={32}
            color={isRecording ? '#fff' : colors.accent}
          />
        </TouchableOpacity>
        <Text style={s.buttonLabel}>
          {isRecording ? 'Tap to stop' : isProcessing ? 'Processing…' : 'Tap to record'}
        </Text>
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.heroBg,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 24,
    paddingVertical: 20,
  },
  logo: {
    fontSize: 20,
    fontWeight: fonts.bold,
    color: colors.heroText,
    letterSpacing: 3,
  },
  main: {
    flex: 1,
    paddingHorizontal: 24,
  },
  resultContainer: {
    flex: 1,
    justifyContent: 'center',
  },
  resultCard: {
    backgroundColor: colors.cardBg,
    borderRadius: 16,
    padding: 20,
    marginBottom: 20,
  },
  resultText: {
    fontSize: 18,
    lineHeight: 24,
    color: colors.cardText,
  },
  copyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 12,
  },
  copyText: {
    fontSize: 16,
    fontWeight: fonts.medium,
    color: colors.accent,
  },
  recordingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  status: {
    fontSize: 28,
    fontWeight: fonts.light,
    color: colors.heroText,
    marginBottom: 60,
    textAlign: 'center',
  },
  waveform: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
    height: 100,
    marginBottom: 60,
  },
  bar: {
    width: 3,
    backgroundColor: colors.accent,
    borderRadius: 2,
  },
  deviceSelector: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 12,
    paddingHorizontal: 20,
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderRadius: 20,
  },
  deviceText: {
    fontSize: 16,
    color: colors.heroMuted,
    fontWeight: fonts.medium,
  },
  footer: {
    alignItems: 'center',
    paddingBottom: 60,
  },
  recordButton: {
    width: 88,
    height: 88,
    borderRadius: 44,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: colors.accent,
    shadowOpacity: 0.3,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 10 },
    elevation: 10,
  },
  buttonLabel: {
    fontSize: 16,
    color: colors.heroMuted,
    fontWeight: fonts.medium,
    marginTop: 16,
  },
});
