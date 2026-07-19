/**
 * sounds — tiny recording cue player (start / stop / done).
 *
 * Mirrors the desktop app's start/stop/done sound effects for the in-app
 * recorder. Fully fail-closed: a missing asset, audio-session conflict, or any
 * expo-audio error must NEVER throw or break the recording→transcribe→inject
 * path. All calls are fire-and-forget.
 */
import { createAudioPlayer, setAudioModeAsync } from 'expo-audio';

export type Cue = 'start' | 'stop' | 'done';

// require() the bundled assets so Metro resolves them at build time.
const SOURCES: Record<Cue, number> = {
  start: require('../assets/sounds/start.wav'),
  stop: require('../assets/sounds/stop.wav'),
  done: require('../assets/sounds/done.wav'),
};

// Lazily-created, reused players. Keyed by cue so we only construct each once.
const players: Partial<Record<Cue, ReturnType<typeof createAudioPlayer>>> = {};

/**
 * Play a recording cue. Never throws — swallows all errors so it can be called
 * fire-and-forget from the recorder without risk to the capture flow.
 */
export async function playCue(name: Cue, volume = 0.4): Promise<void> {
  try {
    // Ensure our cue is audible even while the recorder holds the audio session
    // (and in silent mode). Best-effort — don't block the cue if this fails.
    try {
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
    } catch {
      /* ignore audio-mode failures */
    }

    let p = players[name];
    if (!p) {
      p = createAudioPlayer(SOURCES[name]);
      players[name] = p;
    }
    p.volume = volume;
    // Rewind so a rapid re-trigger replays from the start.
    try {
      await p.seekTo(0);
    } catch {
      /* ignore */
    }
    p.play();
  } catch {
    /* never break the recording flow */
  }
}
