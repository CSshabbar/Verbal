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
| **Windows desktop** | `whisperflow/app/win_*.py` | `pystray` tray + `pynput` + tkinter/pywebview, shares core modules | Secondary variant; fewer features wired |

All three share **one Supabase backend** (project `ovpcthjingugwvpxlsna`) — see `04-data-model.md`.

## Feature availability matrix

| Feature | macOS | iOS | Windows | Notes |
|---|:--:|:--:|:--:|---|
| Recording + transcription (Groq→Gemini→local) | ✅ | ✅ (Groq only) | ✅ | Fallback chain desktop; mobile = Groq `whisper-large-v3-turbo` |
| AI cleanup / formatting | ✅ | ✅ | ✅ | Desktop `process_text`; mobile `formatText`. Notes cleanup now wired on both (mobile `formatNotes`/`formatNoteWithTitle`) |
| Custom dictionary (vocab bias + replacement rules) | ✅ | ✅ | ✅ | Synced, one row/user |
| **Snippets** (spoken trigger → text expansion) | ✅ | ✅ | ⚠️ | On the `dictionary` row; longest-first, single-pass |
| **Auto-learn** dictionary from corrections | ✅ | ❌ | ❌ | Desktop-only (AX read-back + cream pill widget) |
| **File tagging** (`@name.ext` in IDEs) | ✅ | ❌ | ❌ | Desktop-only (macOS Accessibility) |
| Recordings save / playback / retry | ✅ | ✅ | ⚠️ partial | Local + cloud (`recordings` bucket) |
| Notes (voice-first, synced) | ✅ | ✅ | ⚠️ | Supabase `notes` table. **v2:** search, auto-title, structure/checklists, audio linkage, raw+formatted, conflict-pair sync; 4 flags (`notes_search/autotitle/structure_detection/audio_linkage_enabled`, default on) |
| Canvas (shared clipboard: text/link/image) | ✅ | ✅ | ⚠️ | Supabase `canvas` row + realtime |
| Cross-device sync (history/notes/canvas) | ✅ | ✅ | ✅ | Supabase realtime, keyed by `user_id` |
| Device pairing (QR) | ✅ | ✅ | ✅ | `pairings` table, single-use token |
| Google auth (Supabase) | ✅ | ✅ | ⚠️ | Desktop PKCE loopback; mobile deep link |
| Onboarding | ✅ | ✅ | — | |
| Recording overlay / floating HUD | ✅ | ❌ | ✅ | Desktop pill; iOS uses a modal screen |
| Menubar popover | ✅ | — | ⚠️ | macOS NSPopover |

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
