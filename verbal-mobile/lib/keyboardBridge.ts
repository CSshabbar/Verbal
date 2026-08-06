// Bridge that exposes the data the native Flume keyboard (Android IME) needs.
//
// The Kotlin IME cannot read AsyncStorage or call the TS pipeline, so we write a
// small JSON snapshot to the app's filesDir. The IME reads it (see
// plugins/keyboard/FlumeInputMethodService.kt) to bias transcription, apply
// replacements + snippet expansion, and populate its Snippets / History panels.
//
// Call syncKeyboardConfig() on app start and whenever the dictionary or
// (implicitly) history changes.

import { Platform } from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import { getHistory, getDeviceId, getDeviceName, getClipboardHistoryEnabled, getTransformEnabled } from './storage';
import { getSpokenLanguage } from './groq';
import { fetchRemote, getDictionary } from './dictionary';
import { KEYBOARD_THEME } from './keyboardTokens';
import { writeToGroup } from '../modules/flume-shared-store';

// documentDirectory maps to the Android app filesDir (…/files/), which the IME
// reads via context.filesDir. Keep this filename in sync with the Kotlin service.
const CONFIG_FILE = 'flume_kbd_config.json';
// iOS keyboard extensions are a SEPARATE sandbox — they can only read the shared
// App Group container, never the app's documentDirectory. Must match the group id
// in app.json ios.entitlements and the Swift extension's readConfig().
const APP_GROUP = 'group.com.verbal.app';

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
    const [history, deviceId, deviceName, clipboardHistoryEnabled, transformEnabled, spokenLanguage] = await Promise.all([
      getHistory(), getDeviceId(), getDeviceName(), getClipboardHistoryEnabled(), getTransformEnabled(),
      getSpokenLanguage(),
    ]);
    const payload = JSON.stringify({
      // v2: theme tokens + richer overlay shapes (see FLUME_KEYBOARD_V2_DESIGN.md).
      // Native parsers (Android Kotlin, iOS Swift) read these exact shapes.
      schemaVersion: 2,
      // No Groq key on disk — the keyboard transcribes via the groq-proxy Edge
      // Function; deviceId is the proxy's per-device rate-limit identity.
      deviceId: deviceId || 'android-keyboard',
      deviceName: deviceName || 'your computer',   // Canvas overlay header ("→ …")
      theme: KEYBOARD_THEME,
      // Vocabulary as objects so a phonetic can ride along (design shows "Idiaz  i-DEE-uhz").
      // No phonetic is stored yet → `phonetic` is absent; native renders it only if present.
      vocabulary: (dict.vocabulary || []).map((w) => ({ word: w })),
      replacements: dict.replacements || [],
      snippets: dict.snippets || [],
      // Recent dictations with timestamps → the History panel's time pills.
      history: (history || []).slice(0, 15)
        .map((h) => ({ text: h.text, at: h.created_at }))
        .filter((x) => x.text),
      // Gates the native clipboard-history feature (flume_kbd_clipboard.json is a
      // SEPARATE, extension/IME-authored file — clipboard content itself never
      // passes through this bridge, only this on/off preference does).
      clipboardHistoryEnabled,
      // Gates the Transform button (select text elsewhere → instruction → LLM rewrite →
      // replace) — an opt-in, LLM-driven feature, default OFF to match desktop's posture.
      transformEnabled,
      // Whisper language hint for keyboard dictation. Both natives read this
      // (IDI-161/162); 'auto' → the natives omit the param. Until IDI-180 adds
      // a picker, getSpokenLanguage() returns its 'en' default.
      spokenLanguage,
    });
    if (Platform.OS === 'ios') {
      // Write into the App Group container the keyboard extension reads from.
      const ok = await writeToGroup(APP_GROUP, CONFIG_FILE, payload);
      if (ok) return;
      // Fall through to the sandbox write (dev client without the native module).
    }
    const dir = FileSystem.documentDirectory;
    if (!dir) return; // web / unsupported — no keyboard there anyway
    await FileSystem.writeAsStringAsync(dir + CONFIG_FILE, payload);
  } catch {
    // best-effort — the keyboard falls back to "config not found" and shows a
    // retry message; never throw into the app.
  }
}
