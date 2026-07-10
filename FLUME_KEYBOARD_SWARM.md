# Flume Keyboard — Feature Spec & Swarm Plan

> Status: **Proposed — not yet built.** This is the full implementation plan: architecture, test matrix,
> and how the work splits across subagents. Once built, fold a summary into `03-features.md` and the
> `01-product.md` matrix, record any new shared-container data shapes in `04-data-model.md`, and add any
> new hard rules discovered along the way to `05-conventions.md`, per the project's maintenance contract.

## Mission

Right now, dictating into a third-party app on mobile means leaving it: open Flume, dictate, copy, switch
back, paste. This spec builds **Flume as an installable keyboard** on both iOS and Android, so dictation
happens inline, in whatever app the person is already in — matching the frictionless feel of the desktop
overlay as closely as each platform allows.

## Scope for v1

**In scope:**
- iOS custom keyboard extension + the main-app session/handoff logic it depends on
- Android custom IME (input method) with direct microphone access
- Shared use of the existing dictionary/snippets/cleanup pipeline already built for mobile
- First-run setup flow (enabling the keyboard, granting permissions)
- Graceful fallback in fields that block third-party keyboards or require the system keyboard

**Explicitly out of scope for v1** (see "Deferred" section for detail):
- The Android Accessibility Service floating-bubble approach discussed as a possible v2 enhancement
- Any Command-Mode / agentic voice-action behavior
- Team/shared settings across the keyboard

## Architecture

### iOS

**Two new pieces, tightly coupled:**

1. **Keyboard Extension target** (`FlumeKeyboard`) — the actual `UIInputViewController` subclass users
   select in Settings → Keyboards. Its UI is deliberately simple: a mic button, a small waveform/level
   indicator, and the system-provided globe key (switching keyboards is a platform behavior, not
   something Flume builds). Text lands in the focused field via `UITextDocumentProxy.insertText()` —
   this is the one part of the whole feature that's genuinely simple, since Apple explicitly supports it.

2. **Main-app session/handoff bridge** — because keyboard extensions cannot access the microphone or
   trigger a permission dialog themselves, the first tap on the mic button hands off to the main Flume
   app just long enough to (a) prompt for microphone permission if not already granted, and (b) start a
   background-capable recording session. The app then returns focus to whatever app the person was
   typing in. For the remainder of that session (configurable: 5 min / 15 min / 1 hour / until manually
   ended — mirrors the pattern competitors already ship), taps on the extension's mic button start/stop
   against that already-authorized recording without another handoff.

**⚠️ Key technical risk — flag before committing to the full build:** the mechanism by which the
extension (one process) tells the main app (a different process) to start/stop recording, and gets
transcribed text back fast enough to feel instant, is the hardest and least certain part of this entire
feature. Likely candidates: an App Group shared container plus Darwin notifications (`CFNotificationCenter`)
for low-latency signaling, or a small local IPC mechanism. **Recommend a one-week engineering spike
specifically on this bridge, with a working "tap mic → hear it start recording" prototype, before
committing to the full build timeline below.** Everything else in this spec is comparatively
well-understood; this part isn't, and estimates should reflect that honestly.

**What "Full Access" actually grants:** just network access and read/write to a shared App Group
container — not microphone access. Full Access is still required (so the extension can read synced
dictionary/snippets data and, depending on the spike's outcome, possibly call the transcription API
directly rather than routing everything through the main app).

### Android

**One piece, much simpler:** a `FlumeInputMethodService` (Android's `InputMethodService` subclass) that
requests `RECORD_AUDIO` directly and can hold it — no handoff dance required. The IME's own process can
capture audio, call the existing transcription pipeline, and insert the result via
`InputConnection.commitText()` in one continuous flow. This is architecturally much closer to what
desktop Flume already does, and should ship a noticeably smoother v1 than iOS is capable of.

### Shared pipeline (both platforms)

Neither platform should duplicate transcription, cleanup, or dictionary/snippet-expansion logic. Both
the iOS main app and the Android IME should call the same underlying module the mobile app already uses
(`lib/groq.ts`-equivalent transcription + cleanup, plus `lib/dictionary.ts`'s replacement and — once
built — snippet expansion). This is a wrapper/adapter task, not new pipeline logic.

## Data & permissions model

- **iOS:** dictionary, snippets, and auth state live in the App Group shared container so the extension
  can read them without its own network round-trip for settings. Actual audio/transcription network
  calls route through whichever side the spike determines is faster and more reliable.
- **Android:** no shared-container problem — the IME service runs inside the same app process space and
  can call existing mobile lib functions directly.
- **Both:** never store audio or transcripts in a location outside the app's existing sync path. No new
  backend tables are needed for this feature — it's a new *front door* to the existing pipeline, not new
  data.

## Failure handling (fail-closed, per the project's Hard Rule #1)

- **Secure fields:** the keyboard must detect secure text entry (password fields) and refuse to activate
  the mic — never record audio in a password field, full stop.
- **Network loss mid-dictation:** show a clear, dismissible error in the keyboard UI; never leave the
  field in an ambiguous or partially-inserted state.
- **Permission revoked mid-session:** detect this and fall back to prompting re-authorization rather than
  silently failing or crashing.
- **Session expiry mid-recording:** treat as an incomplete dictation, not a crash — save what was
  captured if possible, otherwise fail visibly and let the person retry.
- **Extension crash:** iOS should never leave someone stuck — a crashed extension must fall back to the
  system keyboard automatically, not a blank input area (this exact failure mode is a documented
  competitor bug, worth explicitly testing against).
- **Unsupported field type (number pad, decimal pad, secure fields):** automatically defer to the system
  keyboard, matching platform convention.

## Testing plan

### Functional coverage

| Scenario | Platform |
|---|---|
| First-time keyboard setup + permission grant walkthrough | Both |
| Tap mic, speak, text inserted correctly | Both |
| Tap globe, switch away mid-recording, switch back | Both |
| Dictation across a session-expiry boundary | iOS |
| Rapid start/stop tapping (race condition check) | Both |
| Dictionary replacements and snippet expansion apply correctly through the keyboard | Both |
| Falls back to system keyboard on number/decimal/secure fields | Both |
| Long dictation (several minutes continuous) | Both |

### Cross-app compatibility checklist

Test in at minimum: WhatsApp, Messages/iMessage, Gmail, Slack, native Notes app, Safari/Chrome address
bar and web forms, Twitter/X, Instagram DMs, and one banking-style app known to block third-party
keyboards (expected result: graceful fallback, not a crash).

### Platform/OS version matrix

- iOS: current major version and the previous major version, on at least one small-screen device (globe
  key placement differs on iPhone SE-class screens) and one large-screen device.
- Android: current major version and previous major version, tested with each of Gboard and Samsung
  Keyboard installed as the "other" keyboard, since manufacturer keyboards vary in globe-key behavior.

### Edge cases

- Airplane mode / connection loss mid-recording
- Microphone permission revoked in system settings mid-session
- App force-quit while the extension is still selected as active keyboard
- Low Power Mode (iOS) suspending the background session unexpectedly
- Device rotation mid-recording
- Three or more keyboards installed, cycling through the globe key lands back on the expected one
- VoiceOver / TalkBack screen-reader compatibility with the mic button and state changes

### Performance

- Tap-to-first-partial-result latency
- Extension memory footprint against each platform's extension memory ceiling
- Battery drain from a long-running background recording session (iOS)

### Automated vs. manual coverage — be honest about the split

- Shared transcription/cleanup/dictionary logic: unit-testable, should have real automated coverage,
  same as the existing mobile lib tests.
- Text-insertion correctness, UI state: automatable via XCTest UI testing (iOS) / Espresso (Android).
- Cross-app compatibility, permission-revocation edge cases, and multi-keyboard cycling: **largely manual
  QA territory.** IME/keyboard-extension testing doesn't automate well across third-party host apps —
  budget real device time for this rather than assuming CI coverage will catch it.

## Swarm plan — multi-agent build breakdown

The work splits along genuinely separate boundaries, so most of it can run in parallel rather than as one
long sequential build.

| Agent | Owns | Depends on |
|---|---|---|
| **A — iOS Extension** | The `FlumeKeyboard` extension target: UI, text insertion, App Group reads | Contract from Agent B (spike output) |
| **B — iOS Session Bridge** | Main-app recording session, permission flow, the extension↔app IPC bridge (the spike) | Nothing — this is the critical path, start first |
| **C — Android IME** | `FlumeInputMethodService`: mic capture, UI, text insertion | Adapter interface from Agent D |
| **D — Shared Pipeline Adapter** | Wraps existing transcription/cleanup/dictionary/snippet logic behind one common interface both platforms call | Nothing — can start immediately, in parallel with B |
| **E — Test & QA** | Builds the automated test suites and the manual cross-app checklist/tooling from the plan above | Testable builds from A, B, C (can build harness/checklist in parallel before that) |
| **F — Docs & Maintenance** | Updates `03-features.md`, `01-product.md` matrix, `04-data-model.md`, `05-conventions.md` per the project's maintenance contract | Everything else landing |

**Sequencing:**
1. **B runs first, alone, as a spike.** Nothing else about iOS can be finalized until the extension↔app
   bridge mechanism is proven. Budget this as its own milestone with a go/no-go checkpoint, not a task
   folded into a bigger sprint.
2. **D runs in parallel with B**, since it doesn't depend on either platform's UI — it's wrapping logic
   that already exists.
3. **A starts once B's spike produces a stable contract** (the interface the extension calls to
   start/stop recording and get text back) — A doesn't need the bridge finished, just its contract
   defined.
4. **C starts immediately and independently** — Android has no equivalent blocking risk, so it doesn't
   need to wait on anything from the iOS side. If sequencing resources tightly, C is the safest place to
   start work on day one.
5. **E starts building its harness and checklist as soon as the plan is agreed** (doesn't need working
   code yet), then executes against A/B/C as each reaches a testable state.
6. **F runs last**, once everything else has landed and passed E's test matrix.

**The orchestration loop — this is not a single build-and-done pass:**

```
1. Agree interfaces/contracts up front (B's bridge contract, D's adapter interface)
2. Each agent implements against its contract independently
3. Integration pass — wire A+B together, C+D together
4. Run the full testing plan above
5. Route any failures back to the responsible agent, not a generic "fix bugs" catch-all
6. Re-run the test matrix
7. Repeat steps 4–6 until the full matrix passes — "done" is defined by the test matrix passing,
   not by the first integration successfully compiling
```

Treat step 7 as the real definition of "implemented" — a keyboard extension that builds and runs once on
a developer's phone is not the bar; one that survives the cross-app checklist, the edge cases, and a
second OS version is.

## Definition of done

- Full functional + cross-app + edge-case matrix above passes on both platforms
- The iOS bridge spike's chosen mechanism is documented (not just working — documented, since this is
  the part most likely to need future maintenance)
- Fallback-to-system-keyboard behavior verified on secure fields and unsupported field types
- `03-features.md`, `01-product.md`, and any schema notes in `04-data-model.md` updated per the
  maintenance contract

## Deferred (explicitly out of scope for this build)

- **Android Accessibility Service overlay bubble** — a persistent floating button working across any
  keyboard, not just when Flume is the active one. Bigger permission ask, bigger engineering lift; a
  strong v2 candidate once the core keyboard ships and is stable.
- **Command Mode / voice actions inside the keyboard** — agentic territory per the earlier tiering
  discussion; not part of this build.
- **Shared/team keyboard settings** — depends on the org/workspace layer that doesn't exist yet.
