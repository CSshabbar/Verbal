# Flume Keyboard — iOS Bridge Spike Assessment & Build Feasibility

> Companion to `FLUME_KEYBOARD_SWARM.md`. This is the **go/no-go analysis the spec calls for**
> (§Architecture "Key technical risk", §Definition of Done). Written after surveying the actual repo.
> **No native keyboard/IME code has been built** — see "Why not built here" below. What *is* built:
> the shared pipeline adapter (`verbal-mobile/lib/dictationPipeline.ts`), Agent D, tsc-verified.

## Repo reality (grounds every estimate below)

- `verbal-mobile/` is an **Expo prebuild** project. **`ios/` exists; `android/` does NOT** (never
  prebuilt) — and this environment has **no Android SDK** (`ANDROID_HOME` unset). So the Android IME
  cannot even be compiled here without `expo prebuild --platform android` + a full Android toolchain.
- The iOS project has **no keyboard-extension target** and **no App Group entitlements** yet.
- Adding a keyboard extension = a new Xcode target (editing `project.pbxproj`), a Swift
  `UIInputViewController`, an App Group entitlement on *both* app and extension, `NSExtension` Info.plist
  keys, and provisioning for two bundle ids. None of that is verifiable without Xcode + signing + a device.

## The core iOS problem

A keyboard extension is a **separate, sandboxed process** that **cannot access the microphone** and
**cannot show a permission prompt**. The main app can. So "tap mic in the keyboard → record → get text
back → insert" requires cross-process coordination. This is the spec's flagged high-risk spike.

### Bridge options considered

| Option | How | Verdict |
|---|---|---|
| **App Group container + Darwin notifications** (`CFNotificationCenterGetDarwinNotifyCenter`) | Extension posts a Darwin notification ("start"/"stop"); main app (or a background audio session it owns) listens, records, transcribes, writes the transcript to the shared App Group container; extension observes a "result-ready" Darwin notification and reads the text, then `insertText()`. | **Recommended.** Darwin notifications are the standard low-latency cross-process signal on iOS; the App Group container is the sanctioned shared storage. Full Access grants exactly this (App Group + network) — **not** mic. |
| Deep-link handoff (extension opens the main app via URL each time) | Extension triggers `openURL` to foreground the app to record. | **Only for the first-run authorization handoff**, not per-utterance — it yanks the user out of their app every time. Matches the spec's "hand off once to authorize, then stay in the extension" design. |
| Local socket / loopback IPC | Extension ↔ app over a local port. | Fragile under iOS process suspension; not worth it over Darwin notifications. |

### The genuinely uncertain parts (what the on-device prototype must prove)

1. **Latency**: tap → Darwin signal → app records → transcribes (network) → writes container → Darwin
   signal → extension reads → `insertText`. Does the round trip feel instant enough? Unknown until measured.
2. **Background session survival**: can the main app hold a background-capable `AVAudioSession` long enough
   for the configurable session window (5/15/60 min) without iOS suspending it (esp. Low Power Mode)?
3. **Who calls the API**: with Full Access, the extension *can* hit the transcription API directly
   (bypassing the app for the network leg) — the spike should measure whether extension-direct or
   app-mediated is faster/more reliable, then the shared `dictationPipeline` contract is called from
   whichever side wins.

**Recommendation: build a throwaway "tap mic → hear it start recording → text appears in the field"
prototype on a real device first, measure the three unknowns, and make an explicit go/no-go before
committing to the full target build.** This is the spec's own guidance and the repo confirms nothing
downstream can be finalized until it's proven.

## Android (much simpler — but not buildable here)

`FlumeInputMethodService` gets `RECORD_AUDIO` directly and records/transcribes/inserts in one process —
no bridge. Architecturally close to desktop. **But:** it's native Kotlin, `android/` isn't prebuilt, and
there's no Android SDK in this environment. And a Kotlin IME **cannot call `lib/dictationPipeline.ts`
directly** — it must mirror that sequence natively (or host an RN runtime, which is heavy). The TS
adapter is the reference contract that native mirror follows.

## Why the rest wasn't built in this session (honest scope)

The JS features shipped so far (file-tagging, auto-learn, snippets) were **swarm-buildable because they're
JS/Python, verifiable via `py_compile`/`tsc`/fixtures/logs**. This feature is **~90% native** (Swift
extension + Kotlin IME + Xcode target/entitlement surgery) and, per the spec, **"largely manual QA on
real devices"** for the cross-app matrix. Producing that native code here would be **unverifiable** — it
couldn't be built or tested in this environment — so it was deliberately not fabricated. What was done is
the slice that is real and verifiable today (the adapter) plus this assessment.

## What's ready now vs. what needs your environment

**Done & verified (this session):**
- `verbal-mobile/lib/dictationPipeline.ts` — the shared adapter (`runDictation(audioUri, {cleanup?,
  expandSnippets?})`), wrapping transcribe → optional cleanup → dictionary replacements → snippet
  expansion, fail-closed. `tsc` clean. This is the single front-door both platforms' recording paths call.

**Needs Xcode / Android Studio / real devices (your side):**
1. **iOS bridge spike prototype** (recommended first, go/no-go).
2. iOS: `expo prebuild`, add the `FlumeKeyboard` extension target + App Group entitlement, Swift
   `UIInputViewController`, wire to the bridge.
3. Android: `expo prebuild --platform android`, `FlumeInputMethodService` in Kotlin.
4. The full functional + cross-app + edge-case + OS-matrix testing (manual device QA).

## Recommended next step

Approve the **iOS bridge spike** as its own milestone. If you have a Mac with Xcode + a device and want to
proceed, I can (a) scaffold the extension target and Swift `UIInputViewController` + App Group config as a
starting point for you to build/run in Xcode (clearly marked unverified-here), and (b) hand you the exact
`expo prebuild` + target-creation steps. But building/verifying the native keyboard and running the QA
matrix has to happen in your native toolchain on real devices — it can't be done or truthfully verified
from here.
