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
| **iOS mobile** | `verbal-mobile/` | Expo SDK 55 / React Native 0.83, `flume-ui`, Supabase JS SDK | Active; feature-parity for core, minus desktop-only features |
| **Windows desktop** | `whisperflow/app/win_*.py` | `pystray` tray + `pynput` + pywebview (WebView2), shares core modules **and now the same Flume UI** | Being brought to full parity — renders the identical Flume dashboard (`flume_html()`); auth/dictation-pipeline/sync/notes/canvas wired. Native-heavy features (meetings, auto-learn, file-tagging) specced for a Windows dev session — see `whisperflow/WINDOWS_PARITY_PLAN.md` |

All three share **one Supabase backend** (project `ovpcthjingugwvpxlsna`) — see `04-data-model.md`.

## Feature availability matrix

| Feature | macOS | iOS | Windows | Notes |
|---|:--:|:--:|:--:|---|
| Recording + transcription (Groq→Gemini→local) | ✅ | ✅ (Groq only) | ✅ | Fallback chain desktop; mobile = Groq `whisper-large-v3-turbo` |
| AI cleanup / formatting | ✅ | ✅ | ✅ | Desktop `process_text`; mobile `formatText`. Notes cleanup now wired on both (mobile `formatNotes`/`formatNoteWithTitle`) |
| Custom dictionary (vocab bias + replacement rules) | ✅ | ✅ | ✅ | Synced, one row/user |
| **Snippets** (spoken trigger → text expansion) | ✅ | ✅ | ✅ | On the `dictionary` row; longest-first, single-pass. Windows expands in-dictation via `dictionary.apply_snippets` |
| **Auto-learn** dictionary from corrections | ✅ | ❌ | ❌ | macOS AX read-back + cream pill widget. Windows port specced (UIA readback) — `windows_specs/W7-autolearn-uia.md` |
| **File tagging** (`@name.ext` in IDEs) | ✅ | ❌ | ❌ | macOS Accessibility. Windows port specced (UI Automation harvest) — `windows_specs/W8-filetags-uia.md` |
| Recordings save / playback / retry | ✅ | ✅ | ✅ | Local + cloud (`recordings` bucket). Windows `_process_audio` now saves WAV, uploads, and writes retryable `failed` entries |
| Notes (voice-first, synced) | ✅ | ✅ | ✅ | Supabase `notes` table. **v2:** search, auto-title, structure/checklists, audio linkage, raw+formatted, conflict-pair sync; 4 flags (`notes_search/autotitle/structure_detection/audio_linkage_enabled`, default on). Windows uses the shared `DashboardApi` + Flume notes UI |
| Canvas (shared clipboard: text/link/image) | ✅ | ✅ | ✅ | Supabase `canvas` row + realtime |
| Cross-device sync (history/notes/canvas) | ✅ | ✅ | ✅ | Supabase realtime, keyed by `user_id` |
| Device pairing (QR) | ✅ | ✅ | ✅ | `pairings` table, single-use token |
| Google auth (Supabase) | ✅ | ✅ | ✅ | Desktop PKCE loopback (shared `auth.py`); mobile deep link. Windows wires `_sign_in`/`_sign_out` + tray item |
| Onboarding | ✅ | ✅ | ✅ | Windows now renders the same Flume onboarding/`#signin` screens |
| Recording overlay / floating HUD | ✅ | ❌ | ✅ | Desktop pill; iOS uses a modal screen. Windows currently a tkinter pill; webview parity (`overlay_html()`) specced — `windows_specs/W3-overlay.md` |
| **Meetings** (capture + live transcript + AI summary) | ✅ | 👁 full read | ❌ | macOS captures system audio (ScreenCaptureKit) + mic, with **Granola-style auto-detection** (a "Meeting detected · <source>" pill offers one-click capture when a Zoom/Meet/Teams call is in progress — `meeting_detect.py`). iOS is full READ parity: list, detail (summary, decisions, action items w/ due + tappable done, marked moments w/ notes), the **full AI Notes page** (renders `notes_md`; can generate on-device if absent), playback+transcript, and edits the scratchpad. No capture on mobile. Windows port specced — `windows_specs/W6-meetings-wasapi.md` |
| **Transform — inline** (“…so Flume, make it formal”) | ✅ | ❌ (planned) | ❌ (TBD) | Trailing-instruction gate + LLM rewrite before paste; default OFF (`transform_enabled`) |
| **Transform — selection** (⌘⇧T → preview → replace) | ✅ | ❌ | ❌ (TBD) | Clipboard-captured selection, cream pill (Improvise / spoken / typed), preview + undo |
| Menubar popover | ✅ | — | ⚠️ | macOS NSPopover. Windows equivalent (tray-click pywebview `popover_html()`) specced — `windows_specs/W4-popover.md` |

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
  notes enhanced with transcript context). Mobile views are read-only except the scratchpad.
- **Popover** — the macOS menubar dropdown (NSPopover) mini-dashboard.

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

