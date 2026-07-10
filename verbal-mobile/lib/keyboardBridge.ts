// Bridge that exposes the data the native Flume keyboard (Android IME) needs.
//
// The Kotlin IME cannot read AsyncStorage or call the TS pipeline, so we write a
// small JSON snapshot { groqKey, vocabulary, replacements, snippets } to the
// app's filesDir. The IME reads it (see plugins/keyboard/FlumeInputMethodService.kt)
// to bias transcription and apply replacements + snippet expansion — the same
// data the in-app dictation pipeline uses. Call syncKeyboardConfig() on app start
// and whenever the Groq key or dictionary changes.

import * as FileSystem from 'expo-file-system/legacy';
import { getGroqKey } from './storage';
import { getDictionary } from './dictionary';

// documentDirectory maps to the Android app filesDir (…/files/), which the IME
// reads via context.filesDir. Keep this filename in sync with the Kotlin service.
const CONFIG_FILE = 'flume_kbd_config.json';

export async function syncKeyboardConfig(): Promise<void> {
  try {
    const [groqKey, dict] = await Promise.all([getGroqKey(), getDictionary()]);
    const payload = JSON.stringify({
      groqKey: groqKey || '',
      vocabulary: dict.vocabulary || [],
      replacements: dict.replacements || [],
      snippets: dict.snippets || [],
    });
    const dir = FileSystem.documentDirectory;
    if (!dir) return; // web / unsupported — no keyboard there anyway
    await FileSystem.writeAsStringAsync(dir + CONFIG_FILE, payload);
  } catch {
    // best-effort — the keyboard simply falls back to "config not found" and
    // shows a retry message; never throw into the app.
  }
}
