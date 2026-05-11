# Pico — Complete Technical Documentation

## Overview
Pico is a macOS voice dictation app. Press Right Command to record, release/press again to stop, and transcribed text is pasted into the focused app.

## Architecture

```
User speaks → Recorder (48kHz) → WAV file → Groq API (Whisper Large V3) → Text → Paste into focused app
                                           → Gemini (fallback)
                                           → Local Whisper base (last resort)
```

## Current Bug: Recordings Cut Short After First Transcription

### Symptoms
- First recording: works perfectly (8-10 seconds captured)
- Second recording: only 1.8-2.2 seconds captured → wrong transcription
- Third recording: same problem

### Evidence from logs
```
Recording 1: Captured 8.7s → [Groq] "Today I am going to eat ice cream before I am going to bed." ✓
Recording 2: Captured 1.8s → [Groq] "Today I'm going to be asking for a better." ✗ (cut off)
Recording 3: Captured 2.2s → [Local] "I think we need to be blind with that." ✗ (cut off)
```

### Root Cause Analysis
The transcription itself is CORRECT for the audio it receives. Groq Whisper Large V3 works perfectly. The problem is the **recording is being stopped prematurely** on 2nd/3rd attempts.

Possible causes:
1. **Toggle mode double-trigger**: Right Cmd key fires press+release. In toggle mode, a second press stops recording. If the key bounces or the event fires twice, recording stops almost immediately.
2. **Hotkey listener re-entry**: The NSEvent global monitor may be firing multiple events for a single keypress.
3. **Thread timing**: The UI queue processes the stop before the user finishes speaking.

### Suggested fixes to investigate
1. Add extensive logging to `hotkey.py` to see EVERY key event with timestamps
2. Add a minimum recording duration (e.g., don't allow stop within 3 seconds of start)
3. Switch from toggle mode to hold mode as default
4. Use a different key detection method

---

## File Structure

```
whisperflow/
├── app/
│   ├── __init__.py           # Empty
│   ├── main.py               # PicoApp (rumps.App) — main app, menu bar, event loop
│   ├── recorder.py           # Audio capture using sounddevice at 48kHz native rate
│   ├── transcriber.py        # Groq → Gemini → Local Whisper transcription chain
│   ├── ai_cleanup.py         # Post-processing: filler removal, file tagging, Gemini cleanup
│   ├── injector.py           # Clipboard + CGEvent Cmd+V paste + focus restore
│   ├── hotkey.py             # NSEvent global monitor for Right Cmd + ESC
│   ├── overlay.py            # Floating pill overlay (NSPanel, above fullscreen)
│   ├── dashboard.py          # Main window with history, stats, controls
│   ├── sounds.py             # afplay system sounds (start/stop/done)
│   └── config.py             # ~/.pico/config.json management
├── assets/
│   ├── icon.png              # Menu bar icon (44x44 template)
│   ├── icon_active.png       # Recording state icon
│   ├── app_icon_512.png      # Dock icon
│   └── Pico.icns             # macOS app icon
├── scripts/
│   └── generate_icons.py     # Icon generation with Pillow
├── pico.spec                 # PyInstaller spec
├── build.sh                  # Build script
├── requirements.txt          # Python dependencies
└── .env.example              # GEMINI_API_KEY template
```

---

## Key Components

### recorder.py
- Records at mic's native sample rate (48kHz for MacBook Pro)
- NO resampling before sending to cloud APIs (Groq handles it server-side)
- Only resamples to 16kHz for local Whisper fallback (using scipy.signal.resample_poly)
- No audio normalization — raw audio as captured
- Uses sounddevice.InputStream with callback buffer

### transcriber.py
- **Priority chain**: Groq → Gemini → Local Whisper
- **Groq**: whisper-large-v3-turbo, free (8hrs/day), ~0.3s latency, best accuracy
- **Gemini**: gemini-2.0-flash, free tier (user's existing keys), audio-capable
- **Local**: faster-whisper base model, int8 quantization, beam_size=1
- Saves audio as WAV temp file, sends to API, deletes after

### hotkey.py
- Uses NSEvent.addGlobalMonitorForEventsMatchingMask_ (AppKit)
- Monitors NSEventTypeFlagsChanged (type 12) for Right Command (keycode 0x36)
- Monitors NSEventTypeKeyDown (type 10) for ESC (keycode 0x35)
- Calls on_start/on_stop/on_esc callbacks
- **BUG**: In toggle mode, may fire multiple events causing premature stop

### injector.py
- Saves the focused app PID before recording starts (save_focused_app)
- After transcription: restores focus to original app, waits 200ms, simulates Cmd+V via CGEvent
- Uses Quartz.CGEventCreateKeyboardEvent for paste simulation
- Requires Accessibility permission in System Settings
- Prompts for permission on first launch via AXIsProcessTrustedWithOptions

### overlay.py
- NSPanel (not NSWindow) with NSWindowStyleMaskNonactivatingPanel
- Level: NSScreenSaverWindowLevel (shows above fullscreen apps)
- Collection behavior: CanJoinAllSpaces + Stationary + FullScreenAuxiliary
- Animated pill with Google-colored waveform bars
- Auto-hides after showing "Done" message

### dashboard.py
- Main window with animated wave header
- Stats bar (transcription count, word count)
- Transcription history cards with Copy buttons
- Start/Stop Recording button
- Clear All history button
- Accessibility permission warning

### ai_cleanup.py
- Removes filler words (um, uh, erm)
- Removes repeated words
- Strips Whisper hallucinations
- Applies file tagging (@mentions)
- Sends to Gemini for advanced cleanup when command keywords detected

### config.py
- Config stored at ~/.pico/config.json
- Supports multiple Groq API keys and Gemini API keys
- Default whisper model: base
- Default recording mode: toggle

---

## Configuration (~/.pico/config.json)

```json
{
  "whisper_model": "base",
  "hotkey": "cmd_r",
  "groq_api_keys": ["gsk_..."],
  "gemini_api_keys": ["AIza..."],
  "active_gemini_key_index": 0,
  "recording_mode": "toggle",
  "command_keywords": ["make", "fix", "convert", "formal", ...],
  "history": ["transcription 1", "transcription 2", ...]
}
```

---

## Dependencies

```
rumps>=0.4.0          # macOS menu bar framework
sounddevice>=0.4.6    # Audio recording
soundfile>=0.12.0     # WAV file I/O
numpy>=1.24.0         # Audio arrays
scipy                 # High-quality resampling
faster-whisper>=1.0.0 # Local Whisper (fallback)
groq>=0.9.0           # Groq cloud Whisper API
google-generativeai   # Gemini API
pyperclip>=1.8.2      # Clipboard
python-dotenv>=1.0.0  # .env loading
Pillow>=10.0.0        # Icon generation
```

PyObjC (included with macOS Python): AppKit, Foundation, Quartz, ApplicationServices

---

## Build

```bash
cd whisperflow
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller scipy

# Run in dev mode
python3 -m app.main

# Build .app
pyinstaller pico.spec --clean --noconfirm
codesign --sign - --force --deep dist/Pico.app

# Build DMG
mkdir -p /tmp/pico_dmg
cp -R dist/Pico.app /tmp/pico_dmg/
ln -s /Applications /tmp/pico_dmg/Applications
hdiutil create -volname "Pico" -srcfolder /tmp/pico_dmg -ov -format UDZO dist/Pico.dmg
```

---

## How Wispr Flow Works (for reference)
- Cloud-only transcription (no local Whisper)
- Sends audio to their servers via API
- Uses CrisperWhisper (fine-tuned Whisper Large V3) + LLaMA for cleanup
- Captures screenshots of active window for context
- Sub-700ms end-to-end latency
- $8-10/month subscription

## How AquaVoice Works (for reference)
- Cloud-only via their Avalon model
- 97.4% accuracy on technical terms
- Outperforms Whisper Large V3 on OpenASR benchmarks
- $8/month subscription
