/**
 * useRecorder — audio capture + transcription.
 * Wired to expo-audio (works in Expo Go; expo-av was removed in SDK 55) + Groq.
 */
import { useState, useRef, useCallback, useEffect } from 'react';
import {
  useAudioRecorder,
  RecordingPresets,
  AudioModule,
  setAudioModeAsync,
} from 'expo-audio';
import * as Haptics from 'expo-haptics';
import { transcribeAudio } from '../../lib/groq';
import { getGroqKey } from '../../lib/storage';
import * as recordings from '../../lib/recordings';

export type RecorderStatus = 'idle' | 'recording' | 'paused';

export type StopResult = {
  uri: string;
  durationMs: number;
  /** Final transcript (post-processed). Stream interim via `partialText`. */
  text: string;
  /** 'ok' = transcribed; 'failed' = transcription errored (audio still saved). */
  status: 'ok' | 'failed';
};

export type LastRecording = StopResult & { transcribeMs: number; recId: string };

/**
 * The most recent completed recording. `stop()` sets it so the navigator can
 * read the real transcript (the RecordingScreen's onComplete only forwards
 * uri + durationMs). Read-once — `consume` clears it.
 */
let lastRecording: LastRecording | null = null;
export function consumeLastRecording(): LastRecording | null {
  const r = lastRecording;
  lastRecording = null;
  return r;
}

export function useRecorder() {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [status, setStatus] = useState<RecorderStatus>('idle');
  const [durationMs, setDurationMs] = useState(0);
  const [partialText, setPartialText] = useState(''); // updates as transcription streams
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedAtRef = useRef<number>(0);
  const accumulatedRef = useRef<number>(0);

  useEffect(() => () => {
    if (tickRef.current) clearInterval(tickRef.current);
  }, []);

  const startTick = useCallback(() => {
    startedAtRef.current = Date.now();
    tickRef.current = setInterval(() => {
      setDurationMs(Date.now() - startedAtRef.current + accumulatedRef.current);
    }, 100);
  }, []);

  const start = useCallback(async () => {
    try {
      const perm = await AudioModule.requestRecordingPermissionsAsync();
      if (!perm.granted) {
        throw new Error('Microphone permission denied');
      }

      // Best-effort; option names vary across versions, don't block recording.
      try {
        await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      } catch {
        /* ignore */
      }

      await recorder.prepareToRecordAsync();
      recorder.record();

      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);

      accumulatedRef.current = 0;
      setDurationMs(0);
      setStatus('recording');
      startTick();
    } catch (err) {
      console.error('Failed to start recording:', err);
      throw err;
    }
  }, [recorder, startTick]);

  const pause = useCallback(async () => {
    if (tickRef.current) clearInterval(tickRef.current);
    accumulatedRef.current += Date.now() - startedAtRef.current;
    try {
      recorder.pause();
    } catch (err) {
      console.error('Failed to pause recording:', err);
    }
    setStatus('paused');
  }, [recorder]);

  const resume = useCallback(async () => {
    try {
      recorder.record();
    } catch (err) {
      console.error('Failed to resume recording:', err);
    }
    setStatus('recording');
    startTick();
  }, [recorder, startTick]);

  const stop = useCallback(async (): Promise<StopResult | null> => {
    if (tickRef.current) clearInterval(tickRef.current);
    if (status === 'idle') return null;

    try {
      const total = status === 'paused'
        ? accumulatedRef.current
        : Date.now() - startedAtRef.current + accumulatedRef.current;

      await recorder.stop();
      const rawUri = recorder.uri;
      if (!rawUri) {
        throw new Error('No recording URI');
      }

      // Persist the audio immediately — this is the playback backup + retry
      // cache, so a transcription failure never loses the recording.
      const recId = `rec_${Date.now()}`;
      const uri = (await recordings.persist(rawUri, recId)) ?? rawUri;

      // Transcribe. A network/API failure must NOT throw away the audio —
      // mark it 'failed' so it lands in History with a Retry button.
      let text = '';
      let txStatus: 'ok' | 'failed' = 'ok';
      let transcribeMs = 0;
      try {
        const apiKey = await getGroqKey();
        if (!apiKey) throw new Error('No Groq API key configured');
        const t0 = Date.now();
        text = await transcribeAudio(uri, apiKey);
        transcribeMs = Date.now() - t0;
      } catch (tErr) {
        console.warn('Transcription failed — saved for retry:', tErr);
        txStatus = 'failed';
      }

      await Haptics.notificationAsync(
        txStatus === 'ok'
          ? Haptics.NotificationFeedbackType.Success
          : Haptics.NotificationFeedbackType.Warning);

      setStatus('idle');
      setPartialText('');

      lastRecording = { uri, durationMs: total, text, transcribeMs, status: txStatus, recId };
      return { uri, durationMs: total, text, status: txStatus };
    } catch (err) {
      console.error('Failed to stop recording:', err);
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setStatus('idle');
      setPartialText('');
      throw err;
    }
  }, [status, recorder]);

  return {
    status,
    durationMs,
    partialText,
    uri: recorder.uri ?? '',
    start,
    pause,
    resume,
    stop,
  };
}
