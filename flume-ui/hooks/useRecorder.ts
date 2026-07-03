/**
 * useRecorder — audio capture + live transcription.
 * Wired to expo-av + Groq transcription API.
 */
import { useState, useRef, useCallback } from 'react';
import { Audio } from 'expo-av';
import * as Haptics from 'expo-haptics';
import { transcribeAudio } from '../../lib/groq';
import { getGroqKey } from '../../lib/storage';

export type RecorderStatus = 'idle' | 'recording' | 'paused';

export type StopResult = {
  uri: string;
  durationMs: number;
  /** Final transcript (post-processed). Stream interim via `partialText`. */
  text: string;
};

export function useRecorder() {
  const [status, setStatus] = useState<RecorderStatus>('idle');
  const [durationMs, setDurationMs] = useState(0);
  const [partialText, setPartialText] = useState(''); // updates as transcription streams
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedAtRef = useRef<number>(0);
  const accumulatedRef = useRef<number>(0);

  useEffect(() => () => {
    if (tickRef.current) clearInterval(tickRef.current);
  }, []);

  const start = useCallback(async () => {
    try {
      const { status } = await Audio.requestPermissionsAsync();
      if (status !== 'granted') {
        throw new Error('Microphone permission denied');
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const recording = new Audio.Recording();
      await recording.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      await recording.startAsync();
      recRef.current = recording;

      // Haptic feedback on start
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);

      startedAtRef.current = Date.now();
      accumulatedRef.current = 0;
      setDurationMs(0);
      setStatus('recording');
      tickRef.current = setInterval(() => {
        setDurationMs(Date.now() - startedAtRef.current + accumulatedRef.current);
      }, 100);
    } catch (err) {
      console.error('Failed to start recording:', err);
      throw err;
    }
  }, []);

  const pause = useCallback(async () => {
    // TODO: rec.pauseAsync();
    if (tickRef.current) clearInterval(tickRef.current);
    accumulatedRef.current += Date.now() - startedAtRef.current;
    setStatus('paused');
  }, []);

  const resume = useCallback(async () => {
    // TODO: rec.startAsync();
    startedAtRef.current = Date.now();
    tickRef.current = setInterval(() => {
      setDurationMs(Date.now() - startedAtRef.current + accumulatedRef.current);
    }, 100);
    setStatus('recording');
  }, []);

  const stop = useCallback(async (): Promise<StopResult | null> => {
    if (tickRef.current) clearInterval(tickRef.current);
    if (status === 'idle') return null;
    
    try {
      const total = status === 'paused'
        ? accumulatedRef.current
        : Date.now() - startedAtRef.current + accumulatedRef.current;
      
      // Stop the recording
      if (recRef.current) {
        await recRef.current.stopAndUnloadAsync();
        const uri = recRef.current.getURI();
        
        if (!uri) {
          throw new Error('No recording URI');
        }

        // Get Groq API key and transcribe
        const apiKey = await getGroqKey();
        if (!apiKey) {
          throw new Error('No Groq API key configured');
        }

        // Transcribe the audio
        const text = await transcribeAudio(uri, apiKey);
        
        // Haptic feedback on success
        await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);

        setStatus('idle');
        setPartialText('');
        recRef.current = null;
        
        return { uri, durationMs: total, text };
      }
      
      return null;
    } catch (err) {
      console.error('Failed to stop recording:', err);
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setStatus('idle');
      setPartialText('');
      recRef.current = null;
      throw err;
    }
  }, [status]);

  return {
    status,
    durationMs,
    partialText,
    uri: '', // populated post-stop
    start,
    pause,
    resume,
    stop,
  };
}
