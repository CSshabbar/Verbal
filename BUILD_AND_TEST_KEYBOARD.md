# Flume Keyboard v2 — Build & Test Guide

Status snapshot for testing the redesigned keyboard on both platforms. Honest about
what's done, what needs a first-build fix pass, and what genuinely isn't finished.

## How to build & test

### Prebuild-only smoke check (no JDK, no Android SDK, no device)

The cheapest guard that the config plugin still injects the IME. Node is the only
requirement, so it runs on any machine and belongs in CI (IDI-274).

```
cd verbal-mobile
npx expo prebuild -p android --clean --no-install
```

Then assert all five:

| # | Assertion | Where |
| -- | -- | -- |
| 1 | `<service android:name=".keyboard.FlumeInputMethodService" …>` | `android/app/src/main/AndroidManifest.xml` |
| 2 | that service carries `android:permission="android.permission.BIND_INPUT_METHOD"` | same |
| 3 | `method.xml` exists | `android/app/src/main/res/xml/method.xml` |
| 4 | `FlumeInputMethodService.kt` exists (~128 KB) | `android/app/src/main/java/com/verbal/app/keyboard/` |
| 5 | **11** asset files copied | `android/app/src/main/assets/` |

The 11 assets are the list in `plugins/withFlumeKeyboard.js` — four TTFs (`ionicons`,
`geist_regular`, `geist_medium`, `jetbrains_mono`), three WAV cues (`flume_start`,
`flume_stop`, `flume_done`) and four tables (`flume_words`, `flume_bigrams`,
`flume_emoji`, `flume_emoji_kw`). IDI-270 says "12 assets" — that miscounts; `method.xml`
goes to `res/xml`, not `assets`.

**Verified 2026-08-31** on Windows 11, Node 24.19.0, Expo SDK 55.0.31 — all five pass.
This proves generation only. It does **not** prove the Kotlin compiles, links, or runs;
that still needs the Gradle build and the on-device matrix in IDI-270.

Two warnings prebuild emits today, both known and neither fatal here:
- `ios.appleTeamId` missing from the Expo config — iOS signing only (IDI-247).
- `userInterfaceStyle: Install expo-system-ui …` — `app.json` sets `"dark"` but the
  package that applies it on Android is not installed, so the setting is inert. Decide
  under IDI-270 whether to install it or drop the key.

### Android (no account needed — VERIFIED: full APK builds locally)
```
cd verbal-mobile
npx expo prebuild -p android --clean   # REQUIRED — copies the v2 keyboard in (the plugin's
                                       # file-copy only runs on a full prebuild; plain
                                       # run:android skips it and builds the OLD keyboard)
npx expo run:android                   # builds + installs on a running emulator/device
```
> This was the cause of the earlier `assembleDebug` failure: `android/` held the stale
> pre-v2 keyboard. With `--clean`, the v2 file is copied in and the whole APK compiles
> (confirmed here: `:app:assembleDebug BUILD SUCCESSFUL`).
Then: Settings → System → Languages & input → On-screen keyboard → Manage keyboards →
enable **Flume** → switch to it with the keyboard-switch button. Test in any app.

### Release APK for testers (no Metro, no laptop)
The debug APK is a dev shell: without Metro it shows the dev-client URL screen, so never hand it to a
tester (nor tell them to use Expo Go — the custom keyboard rules that out). Build the JS in instead:
```
cd verbal-mobile/android && ./gradlew assembleRelease   # → app/build/outputs/apk/release/app-release.apk
```
Signed with the debug keystore (sideload only; real signing is IDI-269). The easiest repeatable path is
`eas build -p android --profile preview`. On Windows, a deep OneDrive checkout can hit Ninja's 260-character
path limit; map the repository root to a short drive before running Gradle (`context/05-conventions.md` #90).

### iOS (Simulator — no paid account needed; device/App Store needs the account)
```
cd verbal-mobile
npx expo run:ios            # if the keyboard doesn't update: npx expo prebuild -p ios --clean && npx expo run:ios
```
Then in the simulator: **Settings → General → Keyboard → Keyboards → Add New Keyboard →
Flume**, enable **Allow Full Access** (for overlays/dictation network), and turn on the
software keyboard (⌘K; ⌘⇧K disconnects the hardware keyboard). Test in Notes.

> First native build almost always surfaces a Swift/Kotlin error or two — that's
> expected. Paste the build output and we fix-iterate. The two-supervisor review
> (`KEYBOARD_V2_REVIEW.md`) front-runs most of these.

## What's complete (both platforms unless noted)
- Full **QWERTY**, **?123 numbers**, **=\< symbols** layers; shift / caps-lock; backspace; space; comma/period; contextual return.
- **Flume bar**: F · ⚡ snippets · ▦ canvas · 🕐 history · 📖 vocabulary · ● mic, with the active-overlay highlight.
- **Emoji picker** (curated grid + category tabs + recents) — long-press the comma key.
- **Light + dark theming** following the system appearance.
- **Overlays** (History / Snippets / Vocabulary): **Android populated** from the config bridge; **iOS UI renders but is empty** until the App Group data module (below).
- **Dictation** via the `groq-proxy` Edge Function (key server-side).

## Needs a first-build fix pass (I can't compile here)
- Native compile of both files — the review pre-fixes most; the rest we catch on your first `run:*`.

## Genuinely not finished (need input / a device / a dedicated effort)
1. **iOS overlay data** — needs a tiny native module to write the config into the App Group container `group.com.verbal.app` (RN's `expo-file-system` can't reach it). UI is done; data path pending.
2. **GIF** — needs a **Tenor API key** from you, plus `commitContent` (Android) / pasteboard (iOS) wiring. Deferred until you provide a key.
3. **Glide / swipe typing** — a genuine ML/geometry effort (library or model); not deliverable to Gboard parity solo. Deferred.
4. **ML autocorrect / next-word prediction** — currently only a basic vocabulary-prefix suggestion strip; real autocorrect (UITextChecker on iOS, a dictionary/n-gram on Android) is a follow-on, not Gboard-grade.
5. **iOS device + App Store** — gated on the Apple Developer account (App Group entitlement provisioning, Full Access, `PrivacyInfo.xcprivacy`, TestFlight/review). The **Simulator** works without it.

## Nothing has been pushed
Per instruction — no `eas update`, no store submission. Everything is local for build + test.
