# 01 — Product & Glossary

> Part of the `context/` knowledge set. See `context/README.md` for the maintenance rule.
> **Keep this current:** any new feature or platform-availability change must update the feature matrix below.

## What Verbal is

Verbal is a **voice-dictation product** in the style of Wispr Flow: press a hotkey, speak,
and cleaned-up text is transcribed and inserted wherever your cursor is — plus a set of
productivity surfaces (history, notes, a shared "canvas" clipboard) that **sync across your
devices**. The UI design system is called **Flume**; the shipping product / bundle is
**Verbal** (`com.verbal.app`).

Core loop (all platforms): **hotkey → record → transcribe → AI-clean → insert → (optionally) sync to other devices.**

## Platforms

| Platform | Where | Stack | Status |
|---|---|---|---|
| **macOS desktop** | `whisperflow/` | Python 3, PyObjC/AppKit, `rumps` menubar, WKWebView UIs, cloud + local Whisper | Primary, most complete (`APP_VERSION` 1.0.10) |
| **iOS + Android mobile** | `verbal-mobile/` | Expo SDK 55 / React Native 0.83, `flume-ui`, Supabase JS SDK — ONE codebase for both mobile OSes | Active; feature-parity for core, minus desktop-only features. Native code diverges only where it must: the custom keyboard ships as a real iOS keyboard extension (`targets/keyboard/KeyboardViewController.swift`, Swift) AND a real Android IME (`plugins/keyboard/FlumeInputMethodService.kt`, Kotlin) — see `05-conventions.md` Hard Rule #16 |
| **Windows desktop** | `whisperflow/app/win_*.py` | `pystray` tray + `pynput` + pywebview (WebView2), shares core modules **and now the same Flume UI** | Being brought to full parity — renders the identical Flume dashboard (`flume_html()`); auth/dictation-pipeline/sync/notes/canvas wired. Native-heavy features (meetings, auto-learn, file-tagging) specced for a Windows dev session — see `whisperflow/WINDOWS_PARITY_PLAN.md` |

All three share **one Supabase backend** (project `ovpcthjingugwvpxlsna`) — see `04-data-model.md`. The
feature matrix below still uses a single "iOS" column for mobile (both platforms are the same RN code
for anything not keyboard-extension-specific); where Android's *native* behavior genuinely differs, that's
called out in the Notes column rather than adding a 4th matrix column.

## Feature availability matrix

| Feature | macOS | iOS | Windows | Notes |
|---|:--:|:--:|:--:|---|
| Recording + transcription (Groq→Gemini→local) | ✅ | ✅ (Groq only) | ✅ | Fallback chain desktop; mobile = Groq `whisper-large-v3-turbo` |
| AI cleanup / formatting | ✅ | ✅ | ✅ | Desktop `process_text`; mobile `formatText` — both survive Groq's daily 429 via an Ollama Cloud fallback (desktop 4f08d1e; mobile IDI-180). Notes cleanup wired on both (mobile `formatNotes`/`formatNoteWithTitle`) |
| **Spoken language** (Whisper hint, 'auto' = detect) | ✅ | ✅ | ✅ | Desktop `config['spoken_language']`; mobile Settings picker (IDI-180) writing `flume_spoken_language`, shipped to BOTH native keyboards via the config bridge; drives meeting-notes output language too |
| Custom dictionary (vocab bias + replacement rules) | ✅ | ✅ | ✅ | Synced, one row/user |
| **Snippets** (spoken trigger → text expansion) | ✅ | ✅ | ✅ | On the `dictionary` row; longest-first, single-pass. Windows expands in-dictation via `dictionary.apply_snippets` |
| **Keyboard clipboard history** (quick-paste chip + overlay) | — | ✅ | — | Custom keyboard only (`targets/keyboard/KeyboardViewController.swift` + Android IME `plugins/keyboard/FlumeInputMethodService.kt` — same Expo codebase, this table just doesn't carry a separate Android column). Self-contained in each keyboard target, never synced to the app or cloud; gated by the on/off setting `clipboardHistoryEnabled` (Settings → Keyboard, default ON) |
| **Auto-learn** dictionary from corrections | ✅ | ❌ | ❌ | macOS AX read-back + cream pill widget. Windows port specced (UIA readback) — `windows_specs/W7-autolearn-uia.md` |
| **File tagging** (`@name.ext` in IDEs) | ✅ | ❌ | ❌ | macOS Accessibility. Windows port specced (UI Automation harvest) — `windows_specs/W8-filetags-uia.md` |
| Recordings save / playback / retry | ✅ | ✅ | ✅ | Local + cloud (`recordings` bucket). Windows `_process_audio` now saves WAV, uploads, and writes retryable `failed` entries |
| Notes (voice-first, synced) | ✅ | ✅ | ✅ | Supabase `notes` table. **v2:** search, auto-title, structure/checklists, audio linkage, raw+formatted, conflict-pair sync; 4 flags (`notes_search/autotitle/structure_detection/audio_linkage_enabled`, default on). **v3 (2026-08):** pinning, grouped list, one-click dictate-new-note, search highlight + create-from-query, Ask-your-notes, 3 named restyles (structure/prose/transcript), editable original + reformat-from-transcript, copy/export md·txt (desktop) / share sheet (mobile); **v3.1** desktop layout = NotebookLM-style floating panes (list · editor+dictate-FAB · pastel Studio); **v3.2** import from Meetings/Transcriptions (both platforms) + full dictation bar (pause/cancel/live waveform/timer) — see `03` §Notes. Windows uses the shared `DashboardApi` + Flume notes UI |
| Canvas (shared clipboard: text/link/image) | ✅ | ✅ | ✅ | Supabase `canvas` row + realtime |
| Cross-device sync (history/notes/canvas) | ✅ | ✅ | ✅ | Supabase realtime, keyed by `user_id` |
| Device pairing (QR) | ✅ | ✅ | ✅ | `pairings` table, single-use token |
| Google auth (Supabase) | ✅ | ✅ | ✅ | Desktop PKCE loopback (shared `auth.py`); mobile deep link. Windows wires `_sign_in`/`_sign_out` + tray item |
| **Account deletion** (in-app, App Store 5.1.1(v)) | ✅ | ✅ | ✅ | Server-side `delete-account` Edge Function purges every table + storage bucket + the auth user itself; both clients call it with the real session JWT then wipe local caches. Windows shares `DashboardApi.delete_account()` with macOS. Apple-token revocation deferred (Batch C) |
| Onboarding | ✅ | ✅ | ✅ | Windows now renders the same Flume onboarding/`#signin` screens |
| Recording overlay / floating HUD | ✅ | ❌ | ✅ | Desktop pill; iOS uses a modal screen. Windows currently a tkinter pill; webview parity (`overlay_html()`) specced — `windows_specs/W3-overlay.md` |
| **Meetings** (capture + live transcript + AI summary) | ✅ | 👁 read + edit | 👁 read-only | macOS captures system audio (ScreenCaptureKit) + mic, with **Granola-style auto-detection** (a "Meeting detected · <source>" pill offers one-click capture when a Zoom/Meet/Teams call is in progress — `meeting_detect.py`). Mobile has full read parity: list, detail (summary, decisions, action items w/ due + tappable done, marked moments w/ notes), the **full AI Notes page** (renders `notes_md`; can generate on-device if absent) — **and edits both the scratchpad and the AI notes themselves** (`MeetingNotesScreen.tsx`, raw-markdown edit mode, debounced sync via `updateNotesRemote`), plus tap-to-seek playback with continuous transcript highlighting (`MeetingPlaybackScreen.tsx`, reachable from both Detail and Notes). No capture on mobile. **Desktop UI v4 (2026-08-16):** Notes-language three-pane layout (compact grouped list · document + playback bar · Studio with speaker-filter and Send-to-Notes) — see `03` §Meetings. Windows: read-only cloud list + detail since Notes v3.2 (`DashboardApi.list_meetings`/`get_meeting` cloud fallback — feeds the Meetings screen and the Notes import picker); capture port still specced — `windows_specs/W6-meetings-wasapi.md` |
| **Transform — inline** (“…so Flume, make it formal”) | ✅ | ❌ (planned) | ❌ (TBD) | Trailing-instruction gate + LLM rewrite before paste; default OFF (`transform_enabled`) |
| **Transform — selection** (⌘⇧T / keyboard button → preview → replace) | ✅ | ✅ | ❌ (TBD) | Desktop: clipboard-captured selection, cream pill (Improvise / spoken / typed), preview + undo. Mobile (iOS + Android via the shared Expo codebase, same no-separate-Android-column caveat as the clipboard row): a dedicated Transform button on the custom keyboard reads the host field's selection (`selectedText`/`getSelectedText`), same Improvise/typed/spoken instruction paths and prompts, preview before replace; "undo" is a soft delete-and-reinsert (no OS-level undo API on mobile). Default OFF (`transformEnabled`, Settings → Keyboard), matching desktop's opt-in posture |
| **Insights** (words, WPM percentile, time saved, streak heatmap, per-app/device, rhythm) | ✅ | ✅ | ✅ | Dashboard sidebar destination (shared `flume_html()` → both desktops); mobile `InsightsScreen` is a bottom TAB since the V2 nav redesign (plus the Home strip). Local ledger + incremental cloud aggregate, no new Supabase columns — see `03-features.md` §Insights |
| Menubar / tray menu | ✅ | — | ⚠️ | **macOS: a real `NSMenu`** (`menubar_menu.py`) with one custom-drawn header row — the `NSPopover` mini-dashboard was retired in IDI-183. Windows still uses the tray-click pywebview popover (`popover_html()`) — `windows_specs/W4-popover.md`; a native Win32 tray menu is the open parity item |

Legend: ✅ present · ⚠️ partial/legacy · ❌ not present · — N/A.

## Glossary

- **Verbal** — the product (app name, bundle `com.verbal.app`).
- **Flume** — the UI/design system; on mobile the canonical UI lives in `verbal-mobile/flume-ui/`.
- **Dictation / transcription** — recording speech → text via Groq/Gemini/local Whisper.
- **Dictionary** — user's custom vocabulary (biases the model) + replacement rules (deterministic find/replace). Two separate mechanisms.
- **Auto-learn** — desktop feature: detects when you fix a mis-transcribed word in the target field and offers to add a replacement rule.
- **File tagging** — desktop feature: in a supported IDE, spoken filenames become real `@name.ext` editor references.
- **History / transcriptions** — the running log of dictations; the cross-device "shared clipboard" is the `transcriptions` table.
- **Canvas** — a shared staging board / clipboard (one row per user) for sending text/links/images between your devices.
- **Notes** — synced, voice-first notes.
- **Pairing** — linking a new device to your account by scanning a QR code (`flume://pair?t=…`).
- **Overlay / pill** — the desktop floating HUD shown while recording/transcribing.
- **Meeting** — a desktop-captured recording of a live call (system audio + mic, no bot), producing a live
  transcript, a user scratchpad, and a hybrid AI summary (summary + decisions + action items + the user's
  notes enhanced with transcript context). Mobile can't capture a meeting, but can edit both the scratchpad
  and the full AI notes, and play the recording back with the transcript synced to playback position.
- **Popover** — the **Windows** tray-click mini-dashboard (pywebview, `popover_html()`). macOS had the
  same thing as an `NSPopover` until IDI-183; its menubar surface is now a native `NSMenu` instead.

## Repo layout (top level)

```
Verbal/
├── whisperflow/         # macOS + Windows desktop app (Python).  app/*.py
├── verbal-mobile/       # Expo/React Native app.  flume-ui/ (canonical UI), lib/
├── context/             # THIS knowledge set (synced to the Claude project)
├── *.sql (in whisperflow/) # Supabase schema (partial — see 04-data-model.md)
└── many legacy *.md      # older design/impl docs; context/ supersedes these
```

For the "how it fits together" view see `02-architecture.md`; per-feature detail `03-features.md`;
backend/data `04-data-model.md`; conventions & gotchas `05-conventions.md`.

