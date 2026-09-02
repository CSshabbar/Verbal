# Flume — Product Requirements Document v2

**Status:** Ready for coding agents
**Version:** 2.0
**Last updated:** July 2026
**Companion:** `Flume_Competitive_Analysis.md` (rationale for every decision here)

---

## 0. How to Read This Document (Notes for Coding Agents)

- Each feature has: **ID**, **Priority (P0/P1/P2)**, **Platforms**, **User story**, **Acceptance criteria** (testable, boolean), **Technical notes / interfaces**, and **Analytics / telemetry**.
- **P0** items are the 60-day sprint. **P1** items are 60–180 days. **P2** items are 180–365 days.
- Feature IDs are stable — reference them in commits, PRs, and tickets (`F-01`, `F-02`, …).
- When in doubt about UX tone: **quiet, unobtrusive, never surprises the user, always undoable.** If a feature can't satisfy that, redesign it before shipping.
- All feature flags must be user-toggleable in Settings. No dark patterns.

---

## 1. Product Vision & Positioning

### 1.1 One-line vision
**Flume is the quiet voice tool: speak, and it's already written — safely, locally where possible, and never doing anything you didn't ask for.**

### 1.2 Positioning statement
For professionals and creators who talk faster than they type but don't trust AI to run wild in their apps, Flume is a voice-first productivity platform that transcribes accurately, formats intelligently, and — when given permission — acts on your behalf with visible, undoable confirmation. Unlike Wispr Flow, Willow, and Aqua, Flume is local-first, verbatim-capable, and consent-enforced by design.

### 1.3 Non-goals
- Not an ambient always-on wearable (see Anti-roadmap).
- Not a visible-bot meeting recorder.
- Not a general-purpose conversational assistant (that's ChatGPT / Siri / Copilot).
- Not a video-sentiment analyzer.
- Not a per-action credit-metered product.

### 1.4 Users & primary jobs-to-be-done
1. **The professional writer/PM/engineer** — dictates emails, Slack messages, PR descriptions, notes, docs across many apps daily. Wants speed + quality + trust.
2. **The developer** — dictates into IDEs, terminals, PR titles. Wants accurate technical vocabulary and code-aware context.
3. **The knowledge worker in meetings** — wants meeting notes without a bot joining, without their voice training a vendor's model, and without wading through raw transcripts.
4. **The accessibility user** — RSI, dyslexia, stutter, mobility limitations. Wants a tool that respects their voice patterns.
5. **The compliance-sensitive team** — legal, healthcare, finance, regulated enterprise. Needs SOC 2, HIPAA, on-device options, audit logs.

### 1.5 Five design commitments (used to reject bad ideas)
1. **Quiet by default** — never interrupts, no auto-actions without explicit prior consent.
2. **Local-first** — where inference can run on-device without meaningfully degrading quality, it does.
3. **Verbatim-capable** — the user can always see and get exactly what they said.
4. **Reversible** — every action Flume takes has an undo, and the undo works.
5. **Auditable** — every action Flume takes is logged, viewable, and exportable by the user.

---

## 2. Platforms & Availability Matrix

At v2.0 GA, Flume ships as one product across the following platforms with the following feature parity commitments:

| Platform | Status at v2.0 GA | Notes |
|---|---|---|
| macOS 13+ (Apple Silicon primary, Intel supported) | Full parity — reference platform | Local inference via WhisperKit + Apple Neural Engine |
| Windows 11 (x64 + ARM64) | Full parity | Local inference where hardware supports; Snapdragon-X / Copilot+ PCs get on-device path |
| iOS 17+ | Full parity minus meeting transcription (P1) | Voice keyboard + share-sheet + full app |
| Android 12+ | Full parity minus meeting transcription (P1) | Voice keyboard + full app |
| Linux (Fedora, Ubuntu, Pop!_OS) | **P2 target** — beta by day 365 | Aligns with power-user segment |

**No feature ships without at least Mac + Windows + one mobile OS unless explicitly noted per-feature.**

---

## 3. Existing Features — Consolidation & Hardening

The following features exist today and are **maintained and hardened** in v2. Any change to their behavior must be a deliberate spec change here.

### F-01 · Voice Dictation & Transcription (existing, hardened)
- **Priority:** P0 (already shipped — hardening only)
- **Platforms:** Mac ✅, Win 🟡→✅, iOS ✅, Android 🚧→✅
- **User story:** As a user, I press a hotkey (default `⌥Space` Mac / `Alt+Space` Win, tap-and-hold mic on mobile), speak, and my words appear at the cursor.
- **Acceptance criteria:**
  - Global system-wide hotkey works in any focused text-input surface on Mac and Windows.
  - Cold-start-to-first-word latency: ≤ 400ms on Mac (Apple Silicon), ≤ 600ms Windows.
  - **First-word capture fix (see F-08):** the first word must be captured 100% of the time across all supported platforms — verified by an automated test suite.
  - Offline Mac dictation continues to work with zero degradation vs. v1.
  - iOS voice keyboard installable and functional in any app that accepts the system keyboard.
- **Technical notes:**
  - Reference engine per platform documented in F-06 (Model Transparency).
  - VAD (Voice Activity Detection) buffer must start capturing 200ms *before* the hotkey down-event to prevent first-word truncation.

### F-02 · AI Cleanup & Formatting (existing, refactored)
- **Priority:** P0 (refactor to gate behind Mode Dial, F-09)
- **Platforms:** all
- **User story:** As a user, my filler words and false starts are removed by default, but I can turn cleanup off per-app or per-session.
- **Acceptance criteria:**
  - Existing behavior remains the default in the new "Polished" mode.
  - Verbatim mode (via F-09) produces literal transcription with no rewriting.
  - AI cleanup step is annotated in the activity log (F-15) — user can see what was changed.

### F-03 · Personal Dictionary (existing, extended)
- **Priority:** P0
- **Platforms:** all
- **Acceptance criteria:**
  - Existing manual add/edit continues to work.
  - **CSV import/export added (see F-20).**
  - **Dictionary size guardrails**: warn user at 500 entries that additional entries may reduce accuracy (learned from [Superwhisper community reports](https://www.reddit.com/r/superwhisper/comments/1max1yr/insane_they_block_you_if_you_mention_a_competitor/)).
  - Auto-suggest deduplication when adding entries similar to existing ones.

### F-04 · Auto-Learn from Corrections (existing, extended to Windows)
- **Priority:** P0 (existing on Mac; extend to Windows)
- **Platforms:** Mac ✅, Windows 🚧→✅
- **User story:** When I go back and edit a word Flume transcribed, Flume asks (once, unobtrusively) whether to remember the correction.
- **Acceptance criteria:**
  - Correction-detection heuristic works within 5 seconds of the original insertion.
  - Confirmation pop-up is dismissible with `Esc` and never blocks input.
  - Corrections are versioned — user can see and roll back learned corrections in Settings → Dictionary → Learned.
  - Auto-Learn ships on Windows with parity to Mac.

### F-05 · Smart File References for Developers (existing, extended)
- **Priority:** P0 → **P1 for expansion** to Windows + JetBrains/Neovim
- **Platforms:** Mac (VS Code, Cursor, Windsurf) ✅; Windows 🚧; JetBrains 🚧; Neovim 🚧
- **Acceptance criteria:**
  - Filename mentioned aloud is resolved to a workspace-relative reference in supported editors.
  - Supports camelCase / snake_case / kebab-case matching.
  - No cross-workspace leakage (only files in the currently open workspace are matched).

### F-05a · Recordings Library (existing, hardened)
- **Priority:** P0
- **Platforms:** Mac ✅, iOS ✅, Windows 🟡→✅
- **Acceptance criteria:**
  - Recordings are stored locally by default; sync is opt-in per recording.
  - **Meeting-length safety:** unlike [Superwhisper](https://www.reddit.com/r/superwhisper/comments/1oxjocz/good_bye_whisper/), recordings over 5 minutes must chunk to disk every 30 seconds so a crash cannot destroy a session.
  - Retry-transcription button re-runs the pipeline without re-recording.

### F-05b · Notes (existing, hardened + graph-integrated)
- **Priority:** P0 (integrated into the voice graph, F-18, in P1)
- **Platforms:** all
- **Acceptance criteria:**
  - Folder + pin behavior unchanged.
  - Notes become nodes in the personal voice graph (F-18) — indexed for voice search, retrieval preserves formatting.

### F-05c · Canvas — Shared Clipboard (existing, hardened)
- **Priority:** P0
- **Platforms:** all
- **Acceptance criteria:**
  - Existing send-text/image/link behavior unchanged.
  - **Windows parity to full ✅.**
  - Sensitive-context detection (F-10) applies: Flume will not auto-sync clipboard contents captured from password fields.

### F-05d · Cross-Device Sync + QR Pairing + Google SSO (existing, hardened)
- **Priority:** P0
- **Acceptance criteria:**
  - QR pairing: ≤ 15 seconds from scan to confirmed sync on both devices.
  - Add Apple Sign-In and Microsoft Entra Sign-In as additional identity providers for reach + enterprise readiness.
  - No behavior change to existing Google SSO users.

### F-05e · Guided First-Time Setup + On-Screen Recording Indicator + Menu-Bar (existing, extended)
- **Priority:** P0
- **Acceptance criteria:**
  - First-time setup ships on all platforms including Windows (currently missing).
  - Menu-bar mini-dashboard ships on Windows system tray at parity to Mac.
  - Recording indicator ships everywhere and never occludes user content.

---

## 4. P0 — 60-day Sprint (New Features)

### F-06 · Model Transparency & Engine Selection
- **Priority:** P0
- **Platforms:** all (Settings surface)
- **User story:** As a user, I want to know exactly which STT and LLM models Flume is using, and (on desktop) choose them.
- **Acceptance criteria:**
  - Settings → "Under the Hood" page lists the active STT model, active LLM (for cleanup), and where each runs (device vs. cloud), in plain English.
  - On Mac + Windows, users can select from ≥ 3 STT options (e.g., WhisperKit local, Groq Whisper large-v3-turbo cloud, ElevenLabs Scribe v2 cloud) and ≥ 3 LLM options for cleanup (local Gemma 3 4B via Ollama, GPT-4o-mini, Claude Haiku).
  - Model selection persists per device; sync of the *selection* across devices is opt-in.
  - BYOK (Bring Your Own Key) for OpenAI/Anthropic/Groq/OpenRouter available on Pro.
- **Technical notes:**
  - Default stack at GA: `WhisperKit + local Gemma 3 4B` on Mac Apple Silicon; `Groq Whisper large-v3-turbo + Claude Haiku` on Windows and Intel Mac; `WhisperKit + on-device Apple Foundation Model` on iOS 18+.
  - Each backend implements a common Rust/Swift interface: `transcribe(audio) -> transcript` + `clean(transcript, mode) -> text`.
  - Every request logged locally to the activity log (F-15) with model + latency.
- **Analytics:** model_used, latency_ms, backend (local|cloud), byok (true|false).

### F-07 · Sensitive-Context Auto-Suppression
- **Priority:** P0
- **Platforms:** Mac, Windows, iOS, Android
- **User story:** As a user, I do not want Flume auto-pasting into a password field, banking site, or incognito window without explicit permission.
- **Acceptance criteria:**
  - Detected sensitive contexts (see technical notes) trigger a **confirmation pill** — "Insert here? [Yes] [Cancel]" — instead of auto-paste.
  - User can whitelist a specific domain/app once ("always allow for this site").
  - Whitelist is per-device; Teams admins can enforce blocklist.
  - Zero false negatives on the following required cases: `input[type=password]`, `*.bank`, `*.chase.com`, `*.wellsfargo.com`, `/admin/*` paths, incognito/private browser windows.
- **Technical notes:**
  - Web contexts detected via accessibility APIs (macOS AXUIElement, Windows UIA) — no screenshots.
  - Ships with a built-in blocklist plus a user-editable list.
  - Direct remediation of the [Wispr Flow Business Insider incident](https://www.businessinsider.com/voice-to-text-wispr-flow-transcription-nearly-ruined-life-review-2026-5).

### F-08 · First-Word Capture Fix
- **Priority:** P0
- **Platforms:** all
- **User story:** As a user, when I press the hotkey and start speaking immediately, my first word is captured.
- **Acceptance criteria:**
  - Automated regression suite of ≥ 100 recorded "immediate-speech-on-hotkey" samples; ≥ 99% include the full first word in the transcript.
  - VAD circular buffer preloaded with 300ms of pre-roll audio before hotkey down-event.
  - Publish a blog post about this fix as a marketing story — the [15-app comparison thread](https://www.reddit.com/r/windowsapps/comments/1q7k1s8/i_tried_out_15_voice_dictation_apps_so_you_dont/) shows this is a category-wide bug.

### F-09 · Output Mode Dial (Verbatim / Polished / Rewrite / Custom)
- **Priority:** P0
- **Platforms:** all
- **User story:** As a user, I want to choose whether Flume gives me my words verbatim, cleaned up, rewritten for context, or transformed by a custom prompt.
- **Acceptance criteria:**
  - Four modes accessible via: (a) quick toggle in the recording indicator, (b) per-app persistent default in Settings, (c) voice command ("verbatim mode on").
  - **Verbatim**: raw STT output, no LLM step at all. Latency < Polished mode. Filler words + false starts preserved.
  - **Polished (default)**: current v1 behavior — filler removed, grammar fixed, no rewriting.
  - **Rewrite**: context-aware formatting (F-11) applied — tone matched to destination app.
  - **Custom**: user provides a system prompt applied to every transcript (Superwhisper parity).
  - Per-app defaults persist and sync.
- **Technical notes:**
  - Mode selection is a single enum passed to the cleanup pipeline.
  - Custom prompts limited to 2,000 chars; validated for injection attempts (basic prefix filtering).
- **Analytics:** mode_used, per_app_override (true|false).

### F-10 · Voice-Triggered Snippets (v1)
- **Priority:** P0
- **Platforms:** all
- **User story:** As a user, I define a trigger phrase once, and any time I say it mid-dictation, it expands into a longer block of text.
- **Acceptance criteria:**
  - Settings → Snippets → New Snippet: trigger phrase (2–6 words), expansion text (up to 4,000 chars).
  - Trigger phrases sync across devices.
  - Triggers work **mid-sentence** — "send them {my LinkedIn} and let's set up a call" expands only the trigger.
  - Variable support: `{date}`, `{time}`, `{clipboard}`, `{cursor}` — evaluated at expansion time.
  - Trigger table exposed as JSON export/import.
  - Trigger conflicts with the dictionary (F-03) are detected and surfaced to the user at snippet-creation time.
- **Technical notes:**
  - Snippet matching runs *after* cleanup (F-02) but *before* insertion.
  - Case-insensitive, punctuation-tolerant matching.
  - Longest-match-wins if two triggers overlap.
- **Analytics:** snippet_used, trigger_phrase_hash (never the phrase itself for privacy), expansion_length.

### F-11 · Context-Aware Formatting (v1)
- **Priority:** P0
- **Platforms:** Mac, Windows (P0); iOS/Android (P1)
- **User story:** As a user, dictating into Gmail produces a formatted email; the same words dictated into Slack produce a casual message; into Xcode produce code-compatible verbatim.
- **Acceptance criteria:**
  - Detects active app + (on browsers) active domain locally, using OS accessibility APIs — **never screenshots**.
  - Ships with sensible defaults for: Gmail, Outlook, Slack, Teams, Discord, iMessage, Messages, Notion, Google Docs, Microsoft Word, Xcode, VS Code, Cursor, JetBrains, terminal apps.
  - User can override per-app: choose mode (F-09) and format preset.
  - Rewrite mode transformations are captured in the activity log (F-15) so user can see exactly what was changed.
  - **No cross-app context leakage:** on-screen text from other windows is never read.
- **Technical notes:**
  - Uses `NSWorkspace.frontmostApplication` on Mac, `GetForegroundWindow` on Windows.
  - Browser URL detected via first-party browser extensions (Chrome/Safari/Edge/Firefox/Arc) — extension ships alongside desktop app.

### F-12 · Mid-Dictation Self-Correction
- **Priority:** P0
- **Platforms:** all
- **User story:** As a user, if I say "let's meet Tuesday — actually, Wednesday," the final output says "let's meet Wednesday" without me deleting anything.
- **Acceptance criteria:**
  - Post-STT LLM pass detects verbal-correction patterns: "actually," "I mean," "wait, make that," "sorry, [X]," "scratch that."
  - Correction rewrites the affected phrase in-place.
  - Runs only in Polished and Rewrite modes (never Verbatim).
  - False-positive rate ≤ 2% on a test set of 500 dictation samples containing no corrections.
- **Technical notes:**
  - Prompt template ships as part of the LLM cleanup pass; no extra round-trip.

### F-13 · Sensitive-Context & Privacy Dashboard
- **Priority:** P0
- **Platforms:** Mac, Windows, iOS, Android (Settings)
- **User story:** As a user, I want one screen that shows what data Flume has, where it lives, how long it's kept, and lets me delete it with one click.
- **Acceptance criteria:**
  - Settings → Privacy Dashboard displays:
    - Storage: total MB per data type (recordings, transcripts, notes, canvas, dictionary, snippets, activity log).
    - Location: device (local) vs. Flume Cloud vs. third-party provider (with sub-processor list linked).
    - Retention: current setting per data type, adjustable (7/30/90/365 days / forever / never store).
    - Actions: "Delete all my data" (with re-confirm), "Export all my data" (produces a ZIP of JSON + audio).
  - GDPR/CCPA data-subject rights (access, export, delete, rectify) fulfillable entirely from this screen.
  - Enterprise admin can enforce retention policies org-wide.

### F-14 · Windows Feature Parity Sprint
- **Priority:** P0
- **Platforms:** Windows (target)
- **User story:** As a Windows user, Flume works as fully as it does on Mac.
- **Acceptance criteria:**
  - Existing "Partial" features per current PRD achieve full ✅ status: Recordings, Notes, Canvas, Sign in with Google, Menu-bar (system tray) quick access.
  - Auto-Learn (F-04) parity to Mac.
  - Guided first-time setup on Windows (currently missing).
  - Windows on ARM (Snapdragon X / Copilot+ PCs) uses local WhisperKit-equivalent (via ONNX Runtime + DirectML) for on-device inference where hardware supports.

### F-15 · Activity Log & Universal Undo
- **Priority:** P0
- **Platforms:** all
- **User story:** As a user, I can see every action Flume has taken on my behalf and undo any of them.
- **Acceptance criteria:**
  - Every user-visible action Flume takes (transcription, cleanup, snippet expansion, dictionary learning, meeting capture, agentic action, sync event) writes a structured entry to a local activity log.
  - Log viewable in Settings → Activity, filterable by type, date, app.
  - Every entry has an "Undo" button — for text insertions, undo restores the prior state; for dictionary/snippet edits, undo restores prior values.
  - **30-second toast undo** for every text insertion — a small "Undo (30s)" pill appears near the cursor.
  - Log entries are versioned and locally encrypted at rest.
- **Technical notes:**
  - Undo is the foundation for the agentic system (F-24) — everything that can be done can be undone.

### F-16 · Android App
- **Priority:** P0 (parity target: 90 days post-v2 GA)
- **Platforms:** Android 12+
- **Status (2026-08-29):** 🚧 **built, not shipped.** Android is *not* a separate app — it is the same
  `verbal-mobile/` Expo codebase as iOS, with native divergence only at the keyboard: a from-scratch Kotlin
  IME (`plugins/keyboard/FlumeInputMethodService.kt`) injected at prebuild by the config plugin
  `plugins/withFlumeKeyboard.js`. The iOS keyboard extension was ported *from* it. Remaining launch work is
  tracked under Linear **IDI-269** (on-device validation, FCM, in-app keyboard-enable flow, Play listing, CI);
  the live platform matrix is `context/01-product.md`.
- **User story:** As an Android user, I have full parity with the iPhone app.
- **Acceptance criteria:**
  - Voice keyboard installable as IME. ✅ built — in-app enable/switch flow pending (IDI-272)
  - Full app: dictation, notes, canvas, dictionary, snippets, cross-device sync, QR pairing. ✅ shared RN code
  - Push notifications delivered on Android (FCM V1). ⏳ IDI-271
  - Ships to Google Play Store. ⏳ IDI-274 (build/submit) + IDI-275 (listing/policy)
- **Technical notes:**
  - *Superseded 2026-07-10:* the original plan called for a native **Kotlin + Jetpack Compose** app. It was
    replaced by the shared Expo codebase + Kotlin IME so every non-keyboard feature ships to both mobile OSes
    from one change; only the keyboard is native per platform (`context/05-conventions.md` Hard Rule #16
    covers the app→keyboard config bridge).
  - *F-Droid dropped:* F-Droid would carry the app only with the `NonFreeNet` anti-feature (hard dependence on
    hosted Supabase/Groq via `groq-proxy` and Google sign-in) and requires a FOSS licence plus a reproducible
    from-source build — none of which the project has or plans. Revisit only if a self-hosted / BYO-backend
    mode ships.

### F-17 · Compliance & Trust Foundations
- **Priority:** P0 (audit-work — not shippable code alone, but blocks Enterprise deals)
- **Deliverables:**
  - Publish `flume.app/security`: SOC 2 Type II audit engaged (with target date), HIPAA-ready posture, ISO 27001 roadmap, GDPR compliance statement, DPA available.
  - Publish sub-processor list.
  - Ship contractual guarantee: **no training on customer data, ever**, embedded in Terms of Service.
  - Ship EU AI Act Article 50 disclosure: any AI-rewritten output tagged in metadata; user can see when AI has touched their text.
  - Publish Trust Center with vulnerability disclosure program.

---

## 5. P1 — 60–180 days (Differentiators)

### F-18 · Personal Voice Graph
- **Priority:** P1
- **Platforms:** Mac, Windows (P1); iOS/Android search-only (P2)
- **User story:** As a user, all my transcripts, notes, snippets, corrections, and meeting summaries form one queryable graph I can search by voice.
- **Acceptance criteria:**
  - Every persisted content type is indexed into a local vector store (Chroma or SQLite-vec).
  - Vector embeddings computed locally (e.g., `nomic-embed-text` via Ollama, or Apple's built-in embeddings on Mac).
  - Text index stays on-device; opt-in cloud sync uses envelope encryption (user-side key).
  - Query API: `search(query, types=[transcript|note|snippet|meeting|canvas], limit, since, until) -> ranked results`.
  - Retention rules from Privacy Dashboard (F-13) automatically prune the index.

### F-19 · Voice Search Over History
- **Priority:** P1
- **Platforms:** all
- **User story:** As a user, I press hotkey + say "find that note about the Q3 numbers" and Flume shows me matches.
- **Acceptance criteria:**
  - Distinct voice-search hotkey (default `⌥⇧Space` Mac / `Alt+Shift+Space` Win).
  - Query intent classifier routes "find/search/where/what did I say about" phrases into search rather than dictation.
  - Results shown in a floating card near cursor: top 5 matches with preview + jump-to-source.
  - Never modifies content — pure read-only surface.
  - Powered by F-18.

### F-20 · Migration Toolkit — CSV Import/Export
- **Priority:** P1
- **Platforms:** Mac, Windows (Settings)
- **User story:** As a user switching from Wispr Flow, TextExpander, or Dragon, I can import my dictionary and snippets in one click.
- **Acceptance criteria:**
  - Import formats supported: Wispr Flow snippet export, TextExpander (`.textexpander`), Dragon `.dvc` custom vocabulary, generic CSV (columns: `trigger,expansion,notes`), JSON.
  - Export: Flume snippets + dictionary as CSV + JSON.
  - Conflict resolution UI: for each collision, choose keep-existing / replace / keep-both.
- **Technical notes:**
  - Ship this alongside a landing page: `flume.app/switch` with per-competitor migration guides.

### F-21 · Meeting Transcription (bot-free, local-first)
- **Priority:** P1 (target 120 days post-v2 GA)
- **Platforms:** Mac + Windows initially; iOS + Android P2
- **User story:** As a user, I can capture any meeting or in-person conversation without a bot joining and get structured post-meeting notes.
- **Acceptance criteria:**
  - Captures system audio + mic locally. No bot ever joins the call.
  - Works with Zoom, Meet, Teams, Webex, Slack huddles, FaceTime, WhatsApp, phone calls, in-person.
  - **Consent-mode reliability:** if user enables "Only capture when I've indicated consent for this session," Flume must gate recording on an explicit UI action for that session. This must have an automated test suite proving 100% enforcement — the Limitless failure mode is unacceptable.
  - Speaker diarization: at minimum "Speaker 1/2/3" labels; on iPhone/iOS in-person, true diarization via multi-channel mic where hardware supports.
  - Structured output produced post-meeting: **Topics · Decisions · Action Items · Open Questions**, each with linked transcript spans — never a wall of raw text.
  - User can regenerate summary with different templates.
  - Chunked disk writes every 30 seconds (see F-05a hardening).
  - Meeting summaries are nodes in the voice graph (F-18).
- **Technical notes:**
  - Reference architecture: [Granola](https://www.granola.ai) (bot-free + AI-enhanced notes) + [Meetily](https://meetily.ai) (100% local option) — Flume must ship both cloud and 100%-local paths.
  - LLM summary step: user-selectable per Model Transparency (F-06).
- **Analytics:** meeting_length_min, participant_count_est, template_used.

### F-22 · Voice Macros (unified with Snippets)
- **Priority:** P1
- **Platforms:** Mac, Windows (P1); mobile P2
- **User story:** As a user, my snippet system also supports templated expansion with LLM-filled variables.
- **Acceptance criteria:**
  - Snippet definition (F-10) extended: expansion can include `{{prompt: [description]}}` tokens filled by LLM at expansion time.
  - Example: trigger "meeting followup" → expansion `Hi {{prompt: recipient name from clipboard or last meeting}},\n\nThanks for the meeting today. Summary of what we discussed:\n\n{{prompt: bullet-point summary of the most recent meeting}}\n\n— {{userName}}`
  - Preview shown before insertion for macros that hit an LLM (confirm-first).
  - Macros can access voice graph (F-18) results as context.
- **Technical notes:**
  - Unifies snippets, macros, and (later) voice commands (F-24) into a single trigger table.

### F-23 · Whisper Mode / Silent Dictation
- **Priority:** P1
- **Platforms:** Mac, Windows, iOS
- **User story:** As a user in an open office, I can dictate at very low volume without accuracy dropping.
- **Acceptance criteria:**
  - Toggle in Settings + voice command "whisper mode on/off."
  - Accuracy on whisper-volume test set ≥ 85% of normal-volume accuracy on the same content.
- **Technical notes:**
  - Route to whisper-optimized model variant when enabled; on Mac Apple Silicon this can be a fine-tuned WhisperKit variant.

### F-24 · Command Palette — Confirm-First Agentic Voice
- **Priority:** P1
- **Platforms:** Mac, Windows (P1); mobile P2
- **User story:** As a user, I press a distinct hotkey, speak an instruction, see exactly what Flume will do, and confirm before it happens.
- **Acceptance criteria:**
  - Distinct agentic hotkey (default `⌥⇧A` Mac / `Alt+Shift+A` Win).
  - Speak instruction → Flume produces a **draft card** showing: action type, affected content, target app/destination.
  - User confirms (`Enter`), edits (`E`), or cancels (`Esc`). **No action ever executes without confirm.**
  - GA action set:
    1. **Create note** with title (routes to Notes)
    2. **Insert clipboard / from Canvas**
    3. **Translate selection** to specified language
    4. **Rewrite selection** with instruction ("make this more concise")
    5. **Summarize selection**
    6. **Search my history** (F-19 surface)
    7. **Send text to another device via Canvas**
  - Every action produces an activity-log entry (F-15) and is undoable.
- **Anti-goals:**
  - No sending emails, no calendar actions, no external HTTP calls at v2 GA. These require explicit OAuth consent flows added later (F-27).

### F-25 · Personal MCP Server
- **Priority:** P1
- **Platforms:** Mac, Windows (headless daemon)
- **User story:** As a developer, my own AI agents (Claude Code, Cursor, custom MCP clients) can query my Flume voice graph.
- **Acceptance criteria:**
  - Local MCP server auto-starts alongside desktop app on user opt-in.
  - Exposes read-only tools: `search_transcripts`, `search_notes`, `list_snippets`, `list_recent_meetings`, `get_meeting_summary`.
  - Runs on localhost only; no network exposure by default.
  - Auth: per-client token issued from Settings → Integrations → MCP.
  - Compatible with Anthropic MCP spec + Perplexity Computer MCP conventions.
- **Technical notes:**
  - Uniquely differentiating vs. Wispr / Willow / Aqua. Aligns with user's own AI agent orchestration stack.

### F-26 · Real-Time Translation Dictation
- **Priority:** P1
- **Platforms:** Mac, Windows, iOS, Android
- **User story:** As a user, I speak English and text appears in Spanish (or any of 40+ languages).
- **Acceptance criteria:**
  - Source language auto-detected or user-selected.
  - Target language selected per session or per-app (persists via context-aware defaults, F-11).
  - Translation quality on a test set of 500 sentences per language pair ≥ Google Translate quality (BLEU parity).
  - Available in Verbatim, Polished, and Rewrite modes.
- **Technical notes:**
  - Route via ElevenLabs Scribe v2 (multilingual STT native) OR Whisper-large-v3 STT + separate LLM translation step. A/B decide at implementation time based on cost/quality.

### F-27 · Personal Usage Analytics
- **Priority:** P1
- **Platforms:** all
- **User story:** As a user, I want a friendly weekly digest of my dictation habits.
- **Acceptance criteria:**
  - In-app dashboard: total words dictated (7d/30d/all-time), estimated time saved vs. typing, top apps, most-used snippets, dictionary growth curve.
  - Optional weekly email summary (opt-in).
  - All analytics computed locally from the activity log (F-15) — never uploaded except when user shares.
  - Streak indicator (soft — encouraging, not gamified into anxiety).

### F-28 · Accessibility / Stammer-Correction Mode
- **Priority:** P1
- **Platforms:** all
- **User story:** As a user with a stutter, RSI-limited typing, or dyslexia, Flume respects and adapts to my voice patterns.
- **Acceptance criteria:**
  - Stammer-correction toggle: detects and consolidates repeated word starts ("the-the-the meeting" → "the meeting").
  - Slow-speech mode: extends VAD trailing silence tolerance to 2.5 seconds (vs. default ~600ms) so users who pause more are not cut off.
  - Accessibility discount (50% off Pro) available via simple self-attestation — no gatekeeping.
- **Technical notes:**
  - Ship as a Settings → Accessibility surface, discoverable via macOS/Windows accessibility settings.

---

## 6. P2 — 180–365 days (Moat & TAM Expansion)

### F-29 · Teams Tier v1
- **Priority:** P2 (revenue-critical)
- **Platforms:** all (admin console: web)
- **User story:** As an admin, I can deploy Flume across my team with shared resources and controls.
- **Acceptance criteria:**
  - Shared dictionary + shared snippet library (team-scope).
  - Admin console (web): billing, seats, usage dashboards, retention policy enforcement, sub-processor visibility.
  - SSO/SAML (Okta, Azure AD, Google Workspace) + SCIM provisioning.
  - Audit log with export.
  - Enforced Privacy Mode option (Zero Data Retention org-wide).
  - Per-workspace voice graph (F-18) with explicit opt-in per user.

### F-30 · Longitudinal Commitment Tracking
- **Priority:** P2
- **Platforms:** Mac, Windows
- **User story:** As a user, Flume surfaces commitments I made or was asked to make across all my meetings/notes.
- **Acceptance criteria:**
  - Extraction step post-meeting: identifies "I will …," "you asked me to …," "let's [action] by [date]" patterns.
  - Personal "Commitments" surface: overdue, this-week, upcoming.
  - **Individual-first**, not sales-team-first (differentiates from [Sembly](https://www.sembly.ai/pricing/) and [Circleback](https://circleback.ai)).
  - Integrates with system Calendar/Reminders on opt-in.

### F-31 · Developer SDK (Voice-in-any-app)
- **Priority:** P2
- **Platforms:** Mac, Windows (SDK); iOS (as extension framework)
- **User story:** As a third-party developer, I can embed Flume dictation into my own app.
- **Acceptance criteria:**
  - Swift/AppKit SDK on Mac + WinRT SDK on Windows.
  - iOS Keyboard Extension API doc for third-party integrations.
  - Documented, versioned, semver-guaranteed API.
  - Reference implementation shipped in a public GitHub repo.
- **Technical notes:**
  - Distribution moat, not a revenue center. Following [SpeechOS](https://speechos.ai) pattern.

### F-32 · Voicemail & Call Transcription (Mobile)
- **Priority:** P2
- **Platforms:** iOS + Android
- **User story:** As a mobile user, I can transcribe my voicemails and (opt-in, jurisdiction-permitting) my phone calls.
- **Acceptance criteria:**
  - Voicemail transcription: reuse F-01 pipeline; ships in iOS + Android apps.
  - Call transcription: single-party consent jurisdictions only at GA; in-call recording opt-in with clear on-screen indicator to the user; all-party-consent jurisdictions get a "prompt to say the disclosure" flow.
  - Local-first processing where possible.

### F-33 · Voice-Driven Text Editing on Selection
- **Priority:** P2
- **Platforms:** Mac, Windows (P2); mobile P2+
- **User story:** As a user, I highlight text, hold a hotkey, say an instruction, preview the diff, and confirm.
- **Acceptance criteria:**
  - Uses Command Palette (F-24) infrastructure — same confirm-first UX.
  - Preview shows old text + new text as a diff card (not just the new version).
  - Instructions ≥ 90% success rate on a test set of common edits ("make this more concise," "add bullet points," "convert to formal tone," "translate to French," "fix grammar").

### F-34 · Linux Beta
- **Priority:** P2
- **Platforms:** Fedora, Ubuntu, Pop!_OS (X11 + Wayland)
- **User story:** As a Linux user, I can use Flume with feature parity to Windows minus platform-specific integrations.
- **Acceptance criteria:**
  - Tauri-based build (or native GTK) — evaluate at implementation.
  - System-wide hotkey via `evdev` on Wayland compatible with GNOME + KDE.
  - Local Whisper inference via `whisper.cpp` + Vulkan/CUDA acceleration where available.

---

## 7. Anti-Roadmap — Explicitly Not Building

- ❌ Wearable hardware (Limitless / Bee-style pendant).
- ❌ Visible bot for meeting join.
- ❌ Video-based sentiment / engagement scoring.
- ❌ Emotion recognition of any kind (EU AI Act Article 5(1)(f) violation).
- ❌ Credit-metered AI features layered on subscriptions ([Fireflies pattern](https://fireflies.ai/pricing)).
- ❌ Training AI models on customer data by default (Notta pattern).
- ❌ Agentic actions without confirmation UX.
- ❌ Windows-only or Mac-only features (parity is a hard rule except where documented).
- ❌ Screenshot-based context awareness ([Wispr's 2025 incident](https://efficient.app/apps/wispr-flow)).

---

## 8. Pricing (Ship at v2.0 GA)

| Tier | Price | Included |
|---|---|---|
| **Free** | $0 | 3,000 words/week (Mac/Win), 1,500/week (iOS/Android), **unlimited local Mac dictation**. Verbatim + Polished modes. Personal dictionary (50 entries). Snippets (10). Notes + Canvas (30-day history). |
| **Pro** | $10/mo billed annually ($120/yr) · $13/mo monthly | Unlimited words. All modes (Verbatim/Polished/Rewrite/Custom). Unlimited dictionary/snippets. Meeting transcription (up to 20 hrs/mo). Voice search. Translation. Command Palette. Voice Macros. Personal MCP server. Cross-device unlimited history. BYOK. |
| **Teams** | $15/user/mo (annual, min 3 seats) | Everything in Pro + shared dictionary/snippets, admin console, SSO/SAML, SCIM, audit log, admin-enforced Privacy Mode, per-workspace voice graph, priority support. |
| **Enterprise** | Custom | SOC 2 Type II, HIPAA BAA, ISO 27001, on-device model deployment, dedicated success manager, volume discounts. |
| **Student / Nonprofit / Accessibility** | 50% off Pro (annual only) | Self-attestation; no verification friction. |

**Regional pricing:** India ₹269/mo (~$3.20), Brazil R$19/mo, SEA localization at ~30% of USD price — matches [Wispr's India strategy](https://techcrunch.com/2026/05/09/voice-ai-in-india-is-hard-wispr-flow-is-betting-on-it-anyway/).

---

## 9. Compliance & Security Commitments (Public)

Publish `flume.app/security` and `flume.app/trust` at v2.0 GA covering:

- **No customer-data training** — contractual, ToS-embedded.
- **Sub-processor list** — public and current within 30 days of changes.
- **SOC 2 Type II** — audit engaged at GA; target completion within 9 months. Public quarterly milestones.
- **HIPAA BAA** — available on Enterprise from GA+90.
- **ISO 27001** — target GA+12 months.
- **GDPR "by default"** — local-first inference where possible; DSR portal in-app (F-13).
- **EU AI Act Article 50** — synthetic content tagged in metadata; users see when AI has touched their text.
- **No emotion recognition** — Article 5(1)(f) compliance by design.
- **Auditable activity log** — user-viewable, exportable (F-15).
- **Vulnerability disclosure program** — published, funded ($10K+ pool).

---

## 10. Technical Architecture Sketch

### 10.1 Stack (recommended defaults; teams may vary)

> *Note (2026-08-29): the shipped tree differs from these defaults — desktop is Python (`whisperflow/`), mobile is
> one Expo/React Native app for iOS + Android with Swift/Kotlin native keyboards (see `context/02-architecture.md`).
> This table remains the long-term recommendation, not a description of the current codebase.*

| Layer | Mac | Windows | iOS | Android | Cloud |
|---|---|---|---|---|---|
| UI | SwiftUI + AppKit | WinUI 3 / WPF | SwiftUI | Jetpack Compose | Next.js (admin console) |
| Language | Swift + Rust | C# + Rust | Swift | Kotlin | TypeScript |
| Local STT | WhisperKit (Apple Neural Engine) | ONNX Runtime + DirectML | WhisperKit | ONNX Runtime NNAPI | — |
| Cloud STT (opt-in) | Groq Whisper large-v3-turbo · ElevenLabs Scribe v2 · AssemblyAI Universal-3.5 (user choice) | same | same | same | Provider APIs |
| Local LLM cleanup | Gemma 3 4B via Ollama · Apple Foundation Model (iOS 18+) | Gemma 3 4B via ONNX + DirectML | Apple Foundation Model | Gemini Nano (where available) | — |
| Cloud LLM (opt-in) | GPT-4o-mini · Claude Haiku · Groq Llama · BYOK | same | same | same | Provider APIs |
| Cross-device sync | End-to-end encrypted via CRDT (Automerge) | same | same | same | Cloudflare Workers + R2 (encrypted at rest) |
| Vector store | SQLite-vec (local) | SQLite-vec | SQLite-vec | SQLite-vec | — |
| Embeddings | Apple built-in / `nomic-embed-text` | `nomic-embed-text` via ONNX | Apple built-in | `nomic-embed-text` via ONNX | — |
| MCP server | Rust binary, localhost | same | — | — | — |
| Analytics | Local-first, PostHog for opt-in aggregate | same | same | same | PostHog EU-hosted |

### 10.2 Cross-cutting requirements

- **All persisted data locally encrypted at rest** using platform-native APIs (Keychain / DPAPI / Keystore).
- **Cross-device sync encrypted end-to-end**, user key never leaves the device unencrypted (envelope encryption).
- **Activity log is append-only, tamper-evident** (hash-chained entries).
- **All feature flags user-toggleable** in Settings; no server-side kill switches for privacy-relevant features.
- **All cloud calls opt-in per feature** with a clear indicator that a network call happened.
- **No third-party SDKs with network access** except the ones required for chosen features (STT/LLM providers, sync, opt-in analytics).

### 10.3 Test / QA gates before v2.0 GA

- Automated regression suite for F-01 (first-word capture) covering 100+ samples.
- Automated regression suite for F-07 (sensitive-context detection) covering the required blocklist.
- Consent-mode enforcement test for F-21 with 100% pass rate.
- Model-transparency page copy reviewed by legal for accuracy.
- Full accessibility audit (WCAG 2.2 AA) for all Settings surfaces + Privacy Dashboard.
- Data-export ZIP round-trip test (F-13): export, delete all, re-import, verify byte-parity.
- Undo integration test for every action type in F-15.

---

## 11. Success Metrics (v2.0 GA + 6 months)

**Adoption / growth:**
- ≥ 500K free-tier active users (Wispr-comparable trajectory).
- ≥ 15% free → Pro conversion (category typical is 3–4%; Wispr reports ~19–20%).
- ≥ 70% 30-day retention on Pro cohort.
- ≥ 20% of Pro users on non-US pricing (regional expansion working).

**Engagement:**
- Median daily words dictated per active user: ≥ 800.
- ≥ 40% of Pro users have at least 3 snippets defined.
- ≥ 30% of Pro users have used Command Palette (F-24) in the last 30 days.

**Trust:**
- ≥ 4.5/5 App Store rating; ≥ 4.0/5 Trustpilot rating (Wispr's Trustpilot is 2.7/5 — deliberately avoid that pattern).
- Zero unresolved public trust incidents.
- SOC 2 Type II audit complete on schedule.
- Meeting transcription consent-mode test suite: 100% enforcement across every release.

**Business:**
- ≥ $10M ARR by GA+12 months.
- ≥ 50 Enterprise customers.
- ≥ 3 named endorsements from credible technical figures.

---

## 12. Feature Availability at v2.0 GA

Legend: ✅ = ships at v2.0 GA · 🟡 = ships within 90 days of GA · 🚧 = P1 (60–180) · ⏳ = P2 (180–365)

| Feature | Mac | Windows | iOS | Android | Web (admin) |
|---|---|---|---|---|---|
| F-01 Voice dictation (existing + fix) | ✅ | ✅ | ✅ | 🟡 | — |
| F-02 AI cleanup (refactored) | ✅ | ✅ | ✅ | 🟡 | — |
| F-03 Personal dictionary | ✅ | ✅ | ✅ | 🟡 | — |
| F-04 Auto-learn from corrections | ✅ | ✅ | 🚧 | 🚧 | — |
| F-05 Smart file references | ✅ | 🟡 | — | — | — |
| F-05a Recordings library | ✅ | ✅ | ✅ | 🟡 | — |
| F-05b Notes | ✅ | ✅ | ✅ | 🟡 | — |
| F-05c Canvas | ✅ | ✅ | ✅ | 🟡 | — |
| F-05d Sync + QR + SSO (Apple/MS added) | ✅ | ✅ | ✅ | 🟡 | — |
| F-06 Model transparency | ✅ | ✅ | ✅ | 🟡 | — |
| F-07 Sensitive-context suppression | ✅ | ✅ | ✅ | 🟡 | — |
| F-08 First-word capture fix | ✅ | ✅ | ✅ | 🟡 | — |
| F-09 Output mode dial | ✅ | ✅ | ✅ | 🟡 | — |
| F-10 Voice-triggered snippets | ✅ | ✅ | ✅ | 🟡 | — |
| F-11 Context-aware formatting v1 | ✅ | ✅ | 🚧 | 🚧 | — |
| F-12 Mid-dictation self-correction | ✅ | ✅ | ✅ | 🟡 | — |
| F-13 Privacy dashboard | ✅ | ✅ | ✅ | 🟡 | — |
| F-14 Windows parity | — | ✅ | — | — | — |
| F-15 Activity log + universal undo | ✅ | ✅ | ✅ | 🟡 | — |
| F-16 Android app | — | — | — | 🟡 (P0 target) | — |
| F-17 Compliance foundations | ✅ | ✅ | ✅ | ✅ | ✅ |
| F-18 Personal voice graph | 🚧 | 🚧 | ⏳ | ⏳ | — |
| F-19 Voice search over history | 🚧 | 🚧 | ⏳ | ⏳ | — |
| F-20 Migration toolkit | 🚧 | 🚧 | — | — | — |
| F-21 Meeting transcription | 🚧 | 🚧 | ⏳ | ⏳ | — |
| F-22 Voice macros | 🚧 | 🚧 | ⏳ | ⏳ | — |
| F-23 Whisper mode | 🚧 | 🚧 | 🚧 | ⏳ | — |
| F-24 Command Palette (agentic) | 🚧 | 🚧 | ⏳ | ⏳ | — |
| F-25 Personal MCP server | 🚧 | 🚧 | — | — | — |
| F-26 Real-time translation | 🚧 | 🚧 | 🚧 | 🚧 | — |
| F-27 Personal usage analytics | 🚧 | 🚧 | 🚧 | 🚧 | — |
| F-28 Accessibility mode | 🚧 | 🚧 | 🚧 | 🚧 | — |
| F-29 Teams tier | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| F-30 Commitment tracking | ⏳ | ⏳ | — | — | — |
| F-31 Developer SDK | ⏳ | ⏳ | ⏳ | — | — |
| F-32 Voicemail / call transcription | — | — | ⏳ | ⏳ | — |
| F-33 Voice-driven text editing | ⏳ | ⏳ | ⏳ | ⏳ | — |
| F-34 Linux beta | ⏳ | — | — | — | — |

---

## 13. Open Questions (Answer Before Coding)

1. **Build vs. buy on cloud STT default:** Groq Whisper large-v3-turbo (~9x cheaper) or ElevenLabs Scribe v2 (best independent WER, faster)? Recommend A/B on a controlled cohort in the first 30 days post-GA and settle on cost/quality Pareto winner.
2. **Sync backend:** managed Cloudflare Workers + R2 vs. self-hosted? Cost model changes significantly at 500K users. Recommend Cloudflare through 500K, revisit at scale.
3. **Team-tier admin console:** Retool + Next.js vs. custom Next.js? Suggest Next.js for brand control; Retool for internal-only ops.
4. **Personal MCP server auth:** localhost-only + token vs. OS keychain-signed? Recommend localhost + token at v2.0 GA, keychain-signed at v2.1.
5. **Analytics provider:** PostHog EU vs. self-hosted vs. no third-party (event schema in-house)? Recommend PostHog EU with strict opt-in.
6. **Regional pricing enforcement:** Payment-country vs. IP-country vs. self-attested? Recommend payment-country primary, IP as secondary signal, no self-attestation (fraud risk).

---

## 14. Change Log vs. v1

- Added: Model transparency, sensitive-context suppression, mode dial, snippets, context-aware formatting, mid-dictation correction, first-word fix, privacy dashboard, Windows parity, Android, activity log + universal undo, compliance foundations, personal voice graph, voice search, migration toolkit, bot-free meeting transcription, voice macros, Whisper mode, confirm-first Command Palette, personal MCP server, translation, personal analytics, accessibility mode, Teams tier, commitment tracking, developer SDK, voicemail transcription, voice text editing, Linux beta.
- Retained: All existing Flume v1 features, hardened.
- Removed/rejected: Video sentiment scoring, wearable hardware, visible-bot meeting capture, credit-metered pricing, opt-in-by-default customer data training, confirmation-free agentic actions.
- Positioning shifted: from "voice-first productivity app" to **"the quiet voice tool — local-first, verbatim-capable, confirm-first agentic, values-driven."**

---

## 15. Ready for Handoff

This PRD is designed to be sliceable — each feature block (F-01 through F-34) can be handed to a coding agent as an independent unit with sufficient context to implement, test, and ship. Acceptance criteria are boolean; technical notes cite specific defaults; open questions are called out separately from committed spec.

**Suggested sprint slicing:**
- **Sprint 1 (Weeks 1–2):** F-06, F-08, F-15, F-17 (foundations)
- **Sprint 2 (Weeks 3–4):** F-09, F-10, F-13, F-14 (mode dial, snippets, privacy dashboard, Windows parity begin)
- **Sprint 3 (Weeks 5–6):** F-11, F-12, F-07 (context-aware, self-correction, sensitive contexts)
- **Sprint 4 (Weeks 7–8):** F-16 Android + finish F-14 Windows
- **Sprint 5+ (Post-GA):** P1 items in order F-18 → F-19 → F-21 → F-22 → F-23 → F-24 → F-20 → F-25 → F-26 → F-27 → F-28
- **Beyond GA+180:** P2 items

Every feature must land with: user-visible behavior, activity-log integration, undo support (where applicable), privacy-dashboard exposure (where data is stored), and a test suite proving the acceptance criteria.

*End of PRD v2.*
