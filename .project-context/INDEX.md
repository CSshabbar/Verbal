# Verbal Project Context Index

**Generated:** 2026-06-30  
**Last Updated:** 2026-06-30  
**Project Type:** Cross-platform voice-to-text dictation application  
**Platforms:** macOS, Windows, iOS, Android (React Native)

---

## 📋 Quick Navigation

- [Architecture Overview](#architecture-overview)
- [Component Map](#component-map)
- [Key Files Reference](#key-files-reference)
- [Configuration Files](#configuration-files)
- [Build & Deployment](#build--deployment)
- [APIs & Integrations](#apis--integrations)
- [Common Debugging Scenarios](#common-debugging-scenarios)
- [Feature Development Guide](#feature-development-guide)

---

## 🏗️ Architecture Overview

### System Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                     VERBAL ECOSYSTEM                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Desktop Apps (Python)          Mobile Apps (React Native)  │
│  ┌─────────────┐ ┌───────────┐  ┌─────────────────────────┐ │
│  │   macOS     │ │  Windows  │  │  iOS / Android          │ │
│  │  (rumps)    │ │ (pystray) │  │  (Expo)                 │ │
│  └──────┬──────┘ └─────┬─────┘  └───────────┬─────────────┘ │
│         │              │                     │               │
│         └──────────────┴─────────────────────┘               │
│                        │                                      │
│                        ▼                                      │
│              ┌──────────────────┐                            │
│              │  Supabase Sync   │                            │
│              │  - Realtime DB   │                            │
│              │  - Auth          │                            │
│              │  - Storage       │                            │
│              └──────────────────┘                            │
│                        │                                      │
│         ┌──────────────┴──────────────┐                      │
│         ▼                             ▼                      │
│  ┌─────────────┐             ┌──────────────┐               │
│  │ Groq API    │             │ Gemini API   │               │
│  │ Whisper LV3 │             │ 2.0 Flash    │               │
│  └─────────────┘             └──────────────┘               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow
```
User Input → Audio Recording → Transcription → AI Processing → Output
     │            │                │              │              │
  Hotkey      48kHz WAV       Groq/Gemini/   Formatting     Clipboard
  Press     Capture          Local Whisper   + Cleanup      + Paste
```

---

## 🧩 Component Map

### Desktop Application (`whisperflow/`)

| Component | File | Purpose | Key Functions |
|-----------|------|---------|---------------|
| **Main App** | `app/main.py` | macOS menu bar app, event loop | `VerbalApp`, state management |
| **Windows App** | `app/win_main.py` | Windows system tray app | `VerbalWindowsApp` |
| **Recorder** | `app/recorder.py` | Audio capture at 48kHz | `Recorder`, `start_recording()`, `stop_recording()` |
| **Transcriber** | `app/transcriber.py` | Speech-to-text pipeline | `transcribe()`, `_transcribe_groq()`, `_transcribe_gemini()` |
| **AI Cleanup** | `app/ai_cleanup.py` | Text formatting & enhancement | `process_text()`, 17 formatting rules |
| **Injector** | `app/injector.py` | Text injection into apps | `inject_text()`, `save_focused_app()` |
| **Hotkey** | `app/hotkey.py` | Global hotkey detection | `HotkeyListener`, NSEvent monitoring |
| **Overlay** | `app/overlay.py` | Recording status UI | `OverlayBar`, floating pill |
| **Dashboard** | `app/dashboard.py` | Main settings window | `DashboardWindow`, history view |
| **Sync** | `app/sync.py` | Cross-device sync | `SyncClient`, Supabase Realtime |
| **Config** | `app/config.py` | Settings management | `load_config()`, `save_config()` |
| **Sounds** | `app/sounds.py` | Audio feedback | `play_start()`, `play_stop()` |

### Mobile Application (`verbal-mobile/`)

| Component | File | Purpose | Key Functions |
|-----------|------|---------|---------------|
| **App Root** | `App.tsx` | Navigation, error boundary | Tab navigator, ErrorBoundary |
| **Home Screen** | `screens/HomeScreen.tsx` | Recording interface | Audio capture, transcription |
| **Canvas Screen** | `screens/CanvasScreen.tsx` | Text editing workspace | Rich text editing |
| **Notes Screen** | `screens/NotesScreen.tsx` | Notes management | CRUD operations |
| **History Screen** | `screens/HistoryScreen.tsx` | Transcription history | List view, search |
| **Settings Screen** | `screens/SettingsScreen.tsx` | App configuration | API keys, preferences |
| **Supabase Client** | `lib/supabase.ts` | Backend connectivity | `supabase` instance |
| **Storage** | `lib/storage.ts` | Local persistence | AsyncStorage wrappers |
| **Groq Client** | `lib/groq.ts` | Transcription API | `transcribeAudio()` |
| **Theme** | `lib/theme.ts` | Design system | `colors`, typography |

### Build System

| File | Purpose | Platform |
|------|---------|----------|
| `whisperflow.spec` | PyInstaller spec for macOS | macOS |
| `verbal-win.spec` | PyInstaller spec for Windows | Windows |
| `build.sh` | macOS build script | macOS |
| `build-win.sh` | Windows build script | Windows |
| `build_exe.sh` | Windows EXE build (root) | Windows |
| `eas.json` | Expo EAS Build config | Mobile |
| `app.json` | Expo app configuration | Mobile |

---

## 📁 Key Files Reference

### Core Application Files

```
whisperflow/
├── app/
│   ├── main.py              # Entry point, menu bar app
│   ├── win_main.py          # Windows entry point
│   ├── recorder.py          # Audio recording (48kHz)
│   ├── transcriber.py       # Transcription pipeline
│   ├── ai_cleanup.py        # AI text formatting (17 rules)
│   ├── injector.py          # Text injection (Cmd+V)
│   ├── hotkey.py            # Global hotkey listener
│   ├── overlay.py           # Recording overlay UI
│   ├── dashboard.py         # Main window UI
│   ├── canvas_window.py     # Canvas editing window
│   ├── history_window.py    # History viewer
│   ├── sync.py              # Supabase sync client
│   ├── config.py            # Configuration management
│   ├── sounds.py            # Sound effects
│   ├── updater.py           # Auto-update mechanism
│   └── shared_dashboard.py  # Shared dashboard components
```

### Configuration Files

```
~/.verbal/
├── config.json              # User settings
└── logs/
    ├── app.log              # Application logs
    └── sync.log             # Sync operation logs
```

### Mobile Files

```
verbal-mobile/
├── App.tsx                  # Root component
├── app.json                 # Expo config
├── eas.json                 # EAS Build config
├── package.json             # Dependencies
├── screens/                 # Screen components
├── lib/                     # Utilities & clients
└── assets/                  # Images, sounds
```

---

## ⚙️ Configuration Files

### Desktop Config (`~/.verbal/config.json`)

```json
{
  "whisper_model": "base",
  "hotkey": "cmd_r",
  "hotkey_hold": 54,           // macOS: Right Option keycode
  "hotkey_toggle": 54,
  "recording_mode": "toggle",  // "hold" or "toggle"
  "groq_api_keys": [],
  "gemini_api_keys": [],
  "active_gemini_key_index": 0,
  "sync_enabled": true,
  "sync_user_id": "user-uuid",
  "sync_device_name": "MacBook Pro",
  "history": [...],
  "pinned": [...],
  "daily": {"date": "2026-06-30", "words": 1234},
  "auto_update": true
}
```

### Environment Variables (`.env`)

```bash
GEMINI_API_KEY=AIzaSy...
GROQ_API_KEY=gsk_...
SUPABASE_URL=https://...
SUPABASE_KEY=eyJhbG...
```

### Mobile Config (`verbal-mobile/app.json`)

```json
{
  "expo": {
    "name": "Verbal",
    "slug": "verbal-mobile",
    "version": "1.0.0",
    "orientation": "portrait",
    "platforms": ["ios", "android"],
    "ios": { "bundleIdentifier": "com.verbal.app" },
    "android": { "package": "com.verbal.app" }
  }
}
```

---

## 🔨 Build & Deployment

### macOS Build

```bash
cd whisperflow
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./build.sh
# Output: dist/Verbal.app
```

### Windows Build

```bash
cd whisperflow
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-win.txt
./build-win.sh
# Output: dist-windows/Verbal.exe
```

### Mobile Build

```bash
cd verbal-mobile
npm install
npx expo start
# Build with EAS
eas build --platform ios
eas build --platform android
```

### PyInstaller Packaging

Key dependencies in `.spec` files:
- `faster_whisper` + data files
- `ctranslate2` + data files
- `sounddevice`, `soundfile`
- Platform-specific: `rumps` (macOS), `pystray` (Windows)
- Hidden imports for AppKit, Foundation (macOS)

---

## 🔌 APIs & Integrations

### Groq API (Primary Transcription)
- **Model:** `whisper-large-v3-turbo`
- **Free Tier:** 8 hours/day
- **Latency:** ~0.3s
- **Endpoint:** `client.audio.transcriptions.create()`
- **File:** `app/transcriber.py:_transcribe_groq()`

### Google Gemini API (Fallback + Formatting)
- **Models:** `gemini-2.0-flash` (transcription), `gemini-pro` (formatting)
- **Free Tier:** 1500 requests/day
- **Features:** 17 formatting rules, voice commands
- **File:** `app/ai_cleanup.py`, `app/transcriber.py:_transcribe_gemini()`

### Supabase (Sync Backend)
- **URL:** `https://ovpcthjingugwvpxlsna.supabase.co`
- **Tables:** `transcriptions`, `devices`, `app_versions`
- **Features:** Realtime subscriptions, REST API
- **File:** `app/sync.py`

### Database Schema

```sql
-- Transcriptions table
CREATE TABLE transcriptions (
  id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id         text NOT NULL,
  device_id       text NOT NULL,
  device_name     text,
  target_device_id text,  -- For targeted sync
  text            text NOT NULL,
  created_at      timestamptz DEFAULT now()
);

-- Devices table
CREATE TABLE devices (
  user_id       text NOT NULL,
  device_id     text NOT NULL,
  device_name   text,
  device_type   text,  -- 'mac', 'win', 'ios', 'android'
  last_seen     timestamptz,
  PRIMARY KEY (user_id, device_id)
);

-- App versions table
CREATE TABLE app_versions (
  id            serial PRIMARY KEY,
  platform      text NOT NULL,  -- 'mac', 'win', 'ios', 'android'
  version       text NOT NULL,
  release_notes text,
  download_url  text,
  released_at   timestamptz DEFAULT now()
);
```

---

## 🐛 Common Debugging Scenarios

### 1. Recording Cuts Short (Toggle Mode Bug)

**Symptoms:** 2nd/3rd recording only captures 1-2 seconds

**Files to Check:**
- `app/hotkey.py` - Key event handling
- `app/recorder.py` - Recording state management
- `app/main.py` - Toggle mode logic

**Debug Steps:**
1. Enable verbose logging in `app/main.py`
2. Add timestamps to hotkey events in `app/hotkey.py`
3. Check for double-trigger in NSEvent
4. Add minimum recording duration (3s)

**Related Issue:** Documented in `PICO_TECHNICAL_DOCS.md`

### 2. Transcription Fails Silently

**Files to Check:**
- `app/transcriber.py` - API fallback chain
- `app/config.py` - API key configuration
- `~/.verbal/logs/app.log` - Error logs

**Debug Steps:**
1. Check API key validity
2. Verify network connectivity
3. Inspect transcription logs for API errors
4. Test each tier: Groq → Gemini → Local

### 3. Sync Not Working

**Files to Check:**
- `app/sync.py` - Supabase client
- `app/config.py` - Sync configuration
- Supabase dashboard - Realtime subscriptions

**Debug Steps:**
1. Verify `sync_enabled` in config
2. Check Supabase credentials
3. Test Realtime WebSocket connection
4. Inspect `transcriptions` table for new rows

### 4. Text Injection Fails

**Files to Check:**
- `app/injector.py` - Paste mechanism
- Accessibility permissions (macOS)

**Debug Steps:**
1. Check Accessibility permissions
2. Verify focused app PID saved correctly
3. Test CGEvent simulation manually
4. Check timing (200ms delay after focus restore)

### 5. Build Fails (PyInstaller)

**Common Issues:**
- Missing hidden imports
- Data files not bundled
- Binary dependencies (faster_whisper, ctranslate2)

**Solution:** Update `.spec` file with:
```python
datas=[
    ('assets/icon.png', 'assets'),
    (fw_dir, 'faster_whisper'),
    (ct2_dir, 'ctranslate2'),
]
hiddenimports=[...]
```

---

## 🚀 Feature Development Guide

### Adding a New Feature

#### 1. Desktop (Python)

**Step 1:** Create new module in `app/`
```python
# app/new_feature.py
import logging
logger = logging.getLogger("verbal.new_feature")

class NewFeature:
    def __init__(self, config):
        self.config = config
    
    def process(self):
        pass
```

**Step 2:** Integrate into `main.py`
```python
from app.new_feature import NewFeature

class VerbalApp(rumps.App):
    def __init__(self):
        # ...
        self.new_feature = NewFeature(self.config)
```

**Step 3:** Add config options in `config.py`
```python
DEFAULT_CONFIG = {
    # ...
    "new_feature_enabled": True,
}
```

**Step 4:** Update UI in `dashboard.py`

#### 2. Mobile (React Native)

**Step 1:** Create screen component
```tsx
// screens/NewScreen.tsx
import React from 'react';
import { View, Text } from 'react-native';

export default function NewScreen() {
  return (
    <View>
      <Text>New Feature</Text>
    </View>
  );
}
```

**Step 2:** Add to navigation in `App.tsx`
```tsx
import NewScreen from './screens/NewScreen';

<Tab.Screen name="New" component={NewScreen} />
```

**Step 3:** Add lib utilities if needed
```ts
// lib/new-feature.ts
export async function doSomething() {
  // Implementation
}
```

### Testing Guidelines

#### Desktop Tests
```bash
# Test dependencies
python test_dependencies.py

# Build and test
./build.sh
./dist/Verbal.app/Contents/MacOS/Verbal
```

#### Mobile Tests
```bash
cd verbal-mobile
npm test
# Run on device
npx expo start --ios
```

### Code Style

#### Python
- Follow PEP 8
- Type hints for function signatures
- Docstrings for public APIs
- Logging via `logging.getLogger("verbal.module")`

#### TypeScript/React
- Functional components with hooks
- TypeScript strict mode
- Error boundaries for all screens
- Consistent styling via `lib/theme.ts`

---

## 📊 Project Metrics

### Codebase Size
- **Desktop (Python):** ~15 files, ~3000 lines
- **Mobile (React Native):** ~10 files, ~2000 lines
- **Build Scripts:** ~5 files

### Dependencies

#### Desktop (Python)
- Core: `rumps`, `pynput`, `sounddevice`
- AI: `faster-whisper`, `groq`, `google-generativeai`
- Sync: `httpx`, `websocket-client`
- UI: `pystray`, `pywebview`

#### Mobile (React Native)
- Navigation: `@react-navigation/*`
- Backend: `@supabase/supabase-js`
- Media: `expo-audio`, `expo-av`
- Storage: `@react-native-async-storage/async-storage`

---

## 🔐 Security Considerations

### API Key Management
- Keys stored in `~/.verbal/config.json` (600 permissions)
- Multiple keys with automatic failover
- Environment variable override via `.env`

### Data Privacy
- Local-first transcription (optional cloud)
- No audio stored permanently
- Sync encrypted via Supabase

### Permissions
- **macOS:** Microphone, Accessibility
- **Windows:** Microphone
- **Mobile:** Microphone, Storage

---

## 📚 Related Documentation

- `README.md` - Product overview
- `PICO_TECHNICAL_DOCS.md` - macOS technical details
- `CROSSPLATFORM_SYNC_PLAN.md` - Sync architecture
- `VERBAL_V1.0.8_FIXES_SUMMARY.md` - Bug fix history
- `RELEASE_NOTES_v*.md` - Version history

---

## 🆘 Quick Reference Commands

### Development
```bash
# Run desktop app (macOS)
cd whisperflow && python3 -m app.main

# Run mobile app
cd verbal-mobile && npx expo start

# View logs
tail -f ~/.verbal/logs/app.log

# Clean build
rm -rf build/ dist/
```

### Build
```bash
# macOS
./build.sh

# Windows
./build-win.sh

# Mobile
eas build --platform ios
```

### Debugging
```bash
# Test API keys
python -c "from groq import Groq; print(Groq(api_key='...').audio.transcriptions.create(...))"

# Check Supabase connection
curl -H "apikey: YOUR_KEY" https://YOUR_PROJECT.supabase.co/rest/v1/transcriptions

# Verify permissions (macOS)
tccutil reset All com.verbal.app
```

---

**End of Index**
