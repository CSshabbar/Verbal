/**
 * useRecorder — audio capture + transcription.
 * Wired to expo-audio (works in Expo Go; expo-av was removed in SDK 55) + Groq.
 *
 * The post-capture text work is NOT done here (IDI-179): stop() persists the
 * audio and then hands the file to `lib/dictationPipeline.runDictation`, the one
 * shared transcribe → AI-cleanup → snippet-expansion sequence (the same one
 * historyStore.retryEntry uses, so a retry of the same audio produces the same
 * text). This hook keeps ownership of everything AROUND that: the audio is
 * persisted BEFORE transcription so a failure never loses it, the result is
 * classified 'ok' | 'failed', and the cues/haptics/`lastRecording` bookkeeping
 * stays local.
 */
import { useState, useRef, useCallback, useEffect } from 'react';
import {
  useAudioRecorder,
  RecordingPresets,
  AudioModule,
  setAudioModeAsync,
} from 'expo-audio';
import * as Haptics from 'expo-haptics';
import { runDictation } from '../../lib/dictationPipeline';
import * as recordings from '../../lib/recordings';
import { playCue } from '../../lib/sounds';

export type RecorderStatus = 'idle' | 'recording' | 'paused';

export type StopResult = {
  uri: string;
  durationMs: number;
  /** Final transcript (post AI-cleanup + snippets). Stream interim via `partialText`. */
  text: string;
  /** Transcript BEFORE cleanup/snippets. The note editor feeds this to the
   *  separate note formatter (formatNoteWithTitle) so a dictated note is
   *  cleaned once, not twice — see NoteEditorScreen / Hard Rule #12. */
  raw: string;
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

      void playCue('start'); // fire-and-forget; never blocks recording
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

  // Discard the in-progress recording without transcribing or saving anything.
  // Releases the mic and resets to idle. Never sets `lastRecording`.
  const cancel = useCallback(async () => {
    if (tickRef.current) clearInterval(tickRef.current);
    try {
      await recorder.stop();
    } catch (err) {
      console.warn('Failed to stop recorder on cancel:', err);
    }
    accumulatedRef.current = 0;
    setDurationMs(0);
    setStatus('idle');
    setPartialText('');
    try { await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); } catch { /* ignore */ }
  }, [recorder]);

  const stop = useCallback(async (): Promise<StopResult | null> => {
    if (tickRef.current) clearInterval(tickRef.current);
    if (status === 'idle') return null;

    try {
      const total = status === 'paused'
        ? accumulatedRef.current
        : Date.now() - startedAtRef.current + accumulatedRef.current;

      await recorder.stop();
      void playCue('stop'); // fire-and-forget; user stopped recording
      const rawUri = recorder.uri;
      if (!rawUri) {
        throw new Error('No recording URI');
      }

      // Persist the audio immediately — this is the playback backup + retry
      // cache, so a transcription failure never loses the recording.
      const recId = `rec_${Date.now()}`;
      const uri = (await recordings.persist(rawUri, recId)) ?? rawUri;

      // Run the ONE shared dictation pipeline: transcribe → AI cleanup →
      // snippet expansion (lib/dictationPipeline). `cleanup: true` — the
      // feature matrix documents mobile dictation as having AI cleanup, and
      // formatText is timeout-bounded with an Ollama fallback (IDI-180), so a
      // slow/failed model keeps the raw transcript instead of blocking. Cleanup
      // and snippet expansion fail closed INSIDE runDictation; only a failed
      // transcription rejects, and that must NOT throw away the audio — mark it
      // 'failed' so it lands in History with a Retry button (which re-runs this
      // exact pipeline over the saved file).
      // Auth is handled by the groq-proxy Edge Function (session JWT or anon
      // key) — no client-side key exists or is required.
      let text = '';
      let raw = '';
      let txStatus: 'ok' | 'failed' = 'ok';
      let transcribeMs = 0;
      try {
        const t0 = Date.now();
        const result = await runDictation(uri, { cleanup: true });
        text = result.text;
        raw = result.raw;
        transcribeMs = Date.now() - t0;
      } catch (tErr) {
        console.warn('Transcription failed — saved for retry:', tErr);
        txStatus = 'failed';
      }

      // Transcription finished — chime only on a successful transcript.
      if (txStatus === 'ok' && text) void playCue('done');

      await Haptics.notificationAsync(
        txStatus === 'ok'
          ? Haptics.NotificationFeedbackType.Success
          : Haptics.NotificationFeedbackType.Warning);

      setStatus('idle');
      setPartialText('');

      lastRecording = { uri, durationMs: total, text, raw, transcribeMs, status: txStatus, recId };
      return { uri, durationMs: total, text, raw, status: txStatus };
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
    cancel,
    stop,
  };
}
