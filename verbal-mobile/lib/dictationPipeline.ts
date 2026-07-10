// Shared dictation pipeline (FLUME_KEYBOARD_SWARM.md — Agent D, "Shared Pipeline
// Adapter"). One interface that wraps the existing transcription + AI-cleanup +
// dictionary-replacement + snippet-expansion logic, so every front door (the
// existing in-app recorder, the iOS keyboard-extension → main-app handoff, and
// any RN-hosted path) runs the exact same pipeline instead of re-implementing it.
//
// NOTE (scope, per the spec's iOS/Android split):
//   • iOS: the keyboard extension cannot run JS. It hands off to the main Flume
//     app, which calls runDictation() here. This adapter IS that shared entry point.
//   • Android: a native InputMethodService (Kotlin) cannot call this TS directly —
//     it must either mirror this sequence natively or host an RN runtime. This
//     module is the reference contract that mirror must match.
//
// Fails closed (project Hard Rule #1): any post-transcription step that throws
// returns the best text obtained so far rather than losing the dictation.

import { getGroqKey } from './storage';
import { transcribeAudio, formatText } from './groq';
import { getSnippets, applySnippets } from './dictionary';

export type DictationOptions = {
  /** Run the LLM cleanup pass (formatText). Default false — matches the mobile
   *  recorder, which copies raw and only cleans on retry. */
  cleanup?: boolean;
  /** Expand snippet triggers into their saved text. Default true. */
  expandSnippets?: boolean;
};

export type DictationResult = {
  /** Final text to insert into the field. */
  text: string;
  /** Transcript before snippet expansion / cleanup (for history/debugging). */
  raw: string;
};

/**
 * Full dictation front-door: audio file → text ready to insert.
 * `transcribeAudio` already applies the user's dictionary replacement rules and
 * vocabulary bias, so this layer adds optional cleanup + snippet expansion on top.
 */
export async function runDictation(
  audioUri: string,
  opts: DictationOptions = {}
): Promise<DictationResult> {
  const { cleanup = false, expandSnippets = true } = opts;

  const apiKey = await getGroqKey();
  // transcribeAudio bakes in vocabulary bias + replacement rules already.
  const raw = await transcribeAudio(audioUri, apiKey);

  let text = raw;

  if (cleanup) {
    try {
      text = await formatText(text, apiKey);
    } catch {
      // fail closed — keep the un-cleaned transcript
    }
  }

  if (expandSnippets) {
    try {
      const snippets = await getSnippets();
      if (snippets.length) text = applySnippets(text, snippets);
    } catch {
      // fail closed — keep the text as-is
    }
  }

  return { text, raw };
}
