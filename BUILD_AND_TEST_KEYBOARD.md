# Flume Keyboard v2 — Build & Test Guide

Status snapshot for testing the redesigned keyboard on both platforms. Honest about
what's done, what needs a first-build fix pass, and what genuinely isn't finished.

## How to build & test

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
