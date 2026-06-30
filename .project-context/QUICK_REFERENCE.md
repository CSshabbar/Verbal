# Verbal Quick Reference Card

**One-page cheat sheet for common tasks**

---

## 🚀 Quick Start Commands

```bash
# Run desktop app (development)
cd whisperflow && python3 -m app.main

# Run mobile app
cd verbal-mobile && npx expo start

# View logs (real-time)
tail -f ~/.verbal/logs/app.log

# Clean build
rm -rf build/ dist/ && ./build.sh
```

---

## 📁 File Locations

| What | Location |
|------|----------|
| **Desktop Code** | `whisperflow/app/` |
| **Mobile Code** | `verbal-mobile/` |
| **Config (Desktop)** | `~/.verbal/config.json` |
| **Logs** | `~/.verbal/logs/app.log` |
| **Build Scripts** | `build.sh`, `build-win.sh` |
| **Spec Files** | `*.spec` (PyInstaller config) |

---

## 🧩 Core Components

| Component | File | Purpose |
|-----------|------|---------|
| **Main App** | `app/main.py` | Menu bar app, event loop |
| **Recorder** | `app/recorder.py` | Audio capture (48kHz) |
| **Transcriber** | `app/transcriber.py` | Groq → Gemini → Whisper |
| **AI Cleanup** | `app/ai_cleanup.py` | 17 formatting rules |
| **Injector** | `app/injector.py` | Paste text (Cmd+V) |
| **Hotkey** | `app/hotkey.py` | Global key listener |
| **Sync** | `app/sync.py` | Supabase Realtime |
| **Config** | `app/config.py` | Settings management |

---

## 🔌 APIs & Keys

### Groq (Primary Transcription)
- **Model:** `whisper-large-v3-turbo`
- **Free Tier:** 8 hours/day
- **Config:** `groq_api_keys` array

### Gemini (Fallback + Formatting)
- **Model:** `gemini-2.0-flash`
- **Free Tier:** 1500 requests/day
- **Config:** `gemini_api_keys` array

### Supabase (Sync)
- **URL:** `https://ovpcthjingugwvpxlsna.supabase.co`
- **Tables:** `transcriptions`, `devices`
- **Config:** Built-in (no user config needed)

---

## 🐛 Common Issues

| Issue | Fix |
|-------|-----|
| Recording Cuts Short | Switch to hold mode or add min duration |
| Transcription Fails | Check API keys, network, rate limits |
| Paste Fails | Re-enable Accessibility permissions |
| Sync Not Working | Verify same `sync_user_id` on devices |
| Build Fails | Update `.spec` hiddenimports |
| **Local Whisper Missing** | **Use Groq only - it's optional!** |

---

## 🔧 Configuration Options

```json
{
  "whisper_model": "base",
  "hotkey_hold": 54,
  "recording_mode": "toggle",
  "groq_api_keys": ["gsk_..."],
  "gemini_api_keys": ["AIza..."],
  "sync_enabled": true,
  "sync_user_id": "user-uuid",
  "auto_update": true
}
```

---

## 📊 Database Schema

### transcriptions
```sql
id (uuid) | user_id (text) | device_id (text) | text (text) | created_at (timestamptz)
```

### devices
```sql
user_id (text) | device_id (text) | device_name (text) | device_type (text) | last_seen (timestamptz)
```

---

## 🛠️ Debugging Commands

```bash
# Test Groq API
curl -X POST https://api.groq.com/openai/v1/audio/transcriptions \
  -H "Authorization: Bearer $GROQ_API_KEY" \
  -F "file=@test.wav" \
  -F "model=whisper-large-v3-turbo"

# Test Supabase
curl -H "apikey: $SUPABASE_KEY" \
  "https://YOUR_PROJECT.supabase.co/rest/v1/transcriptions?limit=5"

# Reset macOS permissions
tccutil reset All com.verbal.app

# Check errors in logs
grep -i "error\|fail" ~/.verbal/logs/app.log | tail -20
```

---

## 📱 Mobile Navigation

| Screen | File | Tab Icon |
|--------|------|----------|
| Home | `screens/HomeScreen.tsx` | mic |
| Canvas | `screens/CanvasScreen.tsx` | albums |
| Notes | `screens/NotesScreen.tsx` | document-text |
| History | `screens/HistoryScreen.tsx` | time |
| Settings | `screens/SettingsScreen.tsx` | settings |

---

## 🏗️ Build Outputs

| Platform | Command | Output |
|----------|---------|--------|
| **macOS** | `./build.sh` | `dist/Verbal.app` |
| **Windows** | `./build-win.sh` | `dist-windows/Verbal.exe` |
| **iOS** | `eas build --platform ios` | `.ipa` file |
| **Android** | `eas build --platform android` | `.apk` file |

---

## 📝 Code Patterns

### Add Logging
```python
logger = logging.getLogger("verbal.module_name")
logger.info(f"Operation completed: {result}")
```

### Add Config Option
```python
# In app/config.py DEFAULT_CONFIG
"new_feature_enabled": True,
```

### Add Mobile Screen
```tsx
// 1. Create screens/NewScreen.tsx
// 2. Add to App.tsx navigation
// 3. Add tab icon
```

---

## 🔐 Security

- **Never log** API keys or tokens
- **Use .env** for secrets in development
- **Config file** permissions: `chmod 600 ~/.verbal/config.json`
- **Permissions required:** Microphone, Accessibility (macOS)

---

## 📚 Full Documentation

- **INDEX.md** - Complete project overview
- **SKILL.md** - How to use this context
- **API_REFERENCE.md** - Function signatures
- **DEBUGGING_GUIDE.md** - Troubleshooting
- **FEATURE_DEVELOPMENT.md** - Implementation patterns

---

**Print this page for quick reference!**
