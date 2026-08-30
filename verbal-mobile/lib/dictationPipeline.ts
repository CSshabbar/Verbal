// Shared dictation pipeline — the SINGLE in-app dictation sequence
// (transcribe → AI-cleanup → dictionary-replacement → snippet-expansion).
//
// WHY THIS IS THE CONTRACT (IDI-179). This module used to have zero callers,
// which is precisely how iOS drifted (IDI-161): every front door re-implemented
// the sequence and they disagreed. It now has exactly TWO app callers and they
// are the only places in the RN app allowed to run this chain:
//   • flume-ui/hooks/useRecorder.ts   — stop() (first pass)
//   • flume-ui/hooks/historyStore.ts  — retryEntry() (retry of a failed pass)
// Both pass `cleanup: true`. Before IDI-179 the first pass skipped `formatText`
// while retry ran it, so retrying the SAME audio produced different text; the
// feature matrix has always documented mobile dictation as having AI cleanup.
// formatText carries its own timeouts + Ollama fallback (IDI-180), so latency is
// bounded and a failure keeps the raw transcript.
//
// NOTE (scope, per the iOS/Android split): neither keyboard can run this TS —
// an iOS keyboard extension and an Android InputMethodService are separate
// native sandboxes, and there is **no main-app handoff** (the old claim of one
// was never true — IDI-161). BOTH natives MIRROR this sequence natively
// (`targets/keyboard/KeyboardViewController.swift`,
// `plugins/keyboard/FlumeInputMethodService.kt`): vocab-bias prompt →
// transcribe via groq-proxy → replacements → snippets, with NO LLM cleanup pass
// — i.e. they implement the `cleanup: false` shape of this contract. This file
// is the reference both mirrors must match; change the sequence here and the
// two natives must be updated in the same change.
//
// Fails closed (project Hard Rule #1): any post-transcription step that throws
// returns the best text obtained so far rather than losing the dictation. Only
// `transcribeAudio` is allowed to reject — the caller decides what a failed
// transcription means (mobile marks the entry 'failed' and keeps the audio).

import { transcribeAudio, formatText } from './groq';
import { getEffectiveSnippets, applySnippets } from './dictionary';

export type DictationOptions = {
  /** Run the LLM cleanup pass (formatText). Default false — the shape the two
   *  native keyboard mirrors implement. Both IN-APP callers pass `true`. */
  cleanup?: boolean;
  /** Expand snippet triggers into their saved text. Default true. */
  expandSnippets?: boolean;
};

export type DictationResult = {
  /** Final text to insert into the field (post cleanup + snippet expansion). */
  text: string;
  /** Raw transcript, before cleanup/snippets. Callers use it to tell "the model
   *  heard nothing" (empty) apart from "cleanup changed the words". */
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

  // transcribeAudio bakes in vocabulary bias + replacement rules already.
  // Auth is handled by the groq-proxy (session JWT or anon key) — no client key.
  const raw = await transcribeAudio(audioUri);

  let text = raw;

  // Nothing was heard — don't spend an LLM call (or a dictionary read) on "".
  // The caller distinguishes this case via `raw`.
  if (!text.trim()) return { text, raw };

  if (cleanup) {
    try {
      text = await formatText(text);
    } catch {
      // fail closed — keep the un-cleaned transcript
    }
  }

  if (expandSnippets) {
    try {
      // Personal ∪ team (IDI-216 Phase 4) — a shared snippet expands for every
      // member, while a personal trigger of the same name still wins.
      const snippets = await getEffectiveSnippets();
      if (snippets.length) text = applySnippets(text, snippets);
    } catch {
      // fail closed — keep the text as-is
    }
  }

  return { text, raw };
}
