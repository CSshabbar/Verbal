// Bridge that exposes the data the native Flume keyboard (Android IME) needs.
//
// The Kotlin IME cannot read AsyncStorage or call the TS pipeline, so we write a
// small JSON snapshot to the app's filesDir. The IME reads it (see
// plugins/keyboard/FlumeInputMethodService.kt) to bias transcription, apply
// replacements + snippet expansion, and populate its Snippets / History panels.
//
// Call syncKeyboardConfig() on app start and whenever the Groq key, dictionary,
// or (implicitly) history changes.

import * as FileSystem from 'expo-file-system/legacy';
import { getGroqKey, getHistory } from './storage';
import { fetchRemote, getDictionary } from './dictionary';

// documentDirectory maps to the Android app filesDir (…/files/), which the IME
// reads via context.filesDir. Keep this filename in sync with the Kotlin service.
const CONFIG_FILE = 'flume_kbd_config.json';

export async function syncKeyboardConfig(): Promise<void> {
  try {
    // fetchRemote pulls the LATEST cloud dictionary (incl. snippets) and refreshes
    // the local cache; it falls back to local when offline / not signed in. Using
    // it (rather than getDictionary, which only reads the local cache) is what
    // makes freshly-synced snippets actually reach the keyboard.
    let dict;
    try {
      dict = await fetchRemote();
    } catch {
      dict = await getDictionary();
    }
    const [groqKey, history] = await Promise.all([getGroqKey(), getHistory()]);
    const payload = JSON.stringify({
      groqKey: groqKey || '',
      vocabulary: dict.vocabulary || [],
      replacements: dict.replacements || [],
      snippets: dict.snippets || [],
      // Recent dictations for the keyboard's History panel (text only, capped).
      history: (history || []).slice(0, 15).map((h) => h.text).filter(Boolean),
    });
    const dir = FileSystem.documentDirectory;
    if (!dir) return; // web / unsupported — no keyboard there anyway
    await FileSystem.writeAsStringAsync(dir + CONFIG_FILE, payload);
  } catch {
    // best-effort — the keyboard falls back to "config not found" and shows a
    // retry message; never throw into the app.
  }
}
