# WhisperFlow — Full Agentic Build Prompt
# Run this inside Claude Code with --dangerously-skip-permissions on your Mac

---

You are building a complete, production-ready macOS menu bar application called **WhisperFlow** — a free, local-first voice dictation tool similar to AquaVoice. You will build, test, and package this entirely end-to-end with zero human intervention required. Do not stop and ask questions. Make all decisions yourself. If something fails, debug and fix it before moving on.

---

## What You Are Building

A macOS menu bar app that:
1. Sits silently in the menu bar with a microphone icon
2. User holds **Right Option (⌥)** key → recording starts
3. User releases the key → recording stops
4. Audio is transcribed locally using OpenAI Whisper (small model, runs on CPU/GPU)
5. If the transcript contains an inline command (e.g. "make this formal", "fix grammar", "bullet points"), it is sent to **Gemini 2.0 Flash API** for cleanup
6. Otherwise, raw Whisper output is used directly (for speed)
7. Result is copied to clipboard and **pasted into the currently focused app** via Cmd+V simulation
8. The entire flow from key release to text injection must complete in under 2 seconds for plain dictation

---

## Tech Stack

- **Language**: Python 3.11
- **Menu bar**: `rumps` (macOS menu bar framework)
- **Global hotkey**: `pynput`
- **Audio capture**: `sounddevice` + `numpy`
- **Transcription**: `openai-whisper` (Python package, runs locally)
- **AI cleanup**: `google-generativeai` (Gemini 2.0 Flash, free tier)
- **Text injection**: `pyperclip` + `pyautogui`
- **Packaging**: `PyInstaller` → `.app` bundle
- **Config**: `.env` file for GEMINI_API_KEY

---

## Project Structure to Create

```
whisperflow/
├── app/
│   ├── __init__.py
│   ├── main.py              # Entry point, rumps app
│   ├── recorder.py          # Mic capture using sounddevice
│   ├── transcriber.py       # Whisper transcription
│   ├── ai_cleanup.py        # Gemini API integration
│   ├── injector.py          # Clipboard + text injection
│   ├── hotkey.py            # pynput global hotkey listener
│   └── config.py            # Settings, env loading
├── assets/
│   ├── icon.png             # Menu bar icon (mic icon, 22x22 template image)
│   └── icon_active.png      # Recording state icon (red)
├── whisperflow.spec         # PyInstaller spec file
├── build.sh                 # One-command build script
├── requirements.txt
├── .env.example
└── README.md
```

---

## Detailed Implementation Requirements

### `config.py`
- Load `GEMINI_API_KEY` from `.env` file using `python-dotenv`
- Configurable: whisper model size (default: `small`), hotkey key (default: right alt), command detection keywords list
- Store config in `~/.whisperflow/config.json` (create on first run with defaults)

### `recorder.py`
- Use `sounddevice` to record from default input device
- Sample rate: 16000 Hz (Whisper native)
- Record into a buffer while hotkey is held
- Return raw numpy float32 array when stopped
- Handle device errors gracefully with fallback

### `transcriber.py`
- Load Whisper `small` model on startup (cache it, do not reload on each transcription)
- Accept numpy audio array, return string transcript
- Run in a way that does not block the main thread (use threading)
- Log transcription time to console for debugging

### `ai_cleanup.py`
- Use `google-generativeai` SDK with `gemini-2.0-flash` model
- System prompt:
  ```
  You are a voice dictation assistant. The user has dictated text.
  If they included an instruction (e.g. "make this formal", "fix grammar", 
  "convert to bullet points", "summarize this"), follow it and return only 
  the final processed text. If there is no instruction, lightly clean up 
  punctuation and capitalization only. Never add commentary. Return only 
  the final text.
  ```
- Detect if cleanup is needed by checking for command keywords: `["make", "fix", "convert", "formal", "casual", "bullet", "summarize", "rephrase", "translate", "shorter", "longer"]`
- If no command keyword detected → skip Gemini, return transcript directly
- Timeout: 5 seconds max, fall back to raw transcript if exceeded

### `hotkey.py`
- Use `pynput.keyboard` listener
- Listen for `Key.alt_r` (right option key on Mac)
- On press → emit `on_record_start` event
- On release → emit `on_record_stop` event
- Run listener in a daemon thread so it doesn't block the app

### `injector.py`
- Copy text to clipboard using `pyperclip`
- Simulate Cmd+V using `pyautogui` with a 100ms delay after clipboard set
- Add accessibility permission check — if `pyautogui` fails, show a rumps alert telling user to grant Accessibility permissions in System Settings

### `main.py`
- `rumps.App` subclass named `WhisperFlowApp`
- Menu bar items:
  - Status indicator (disabled label): "WhisperFlow — Ready"
  - Separator
  - "Set Gemini API Key…" → opens input dialog
  - "Whisper Model" submenu → tiny / base / small / medium (checkmark active)
  - "History" → shows last 10 transcriptions in a scrollable window
  - Separator
  - "About" → version info
  - "Quit"
- On record start: change menu bar icon to `icon_active.png`, update status to "🔴 Recording…"
- On record stop: update status to "⚙️ Transcribing…", run transcription + optional Gemini in background thread, then inject text and reset to "✅ Done — [first 30 chars of text]"
- Show macOS notification on completion with the injected text preview
- Handle all errors with rumps alerts (never crash silently)

### `assets/`
- Generate both icons programmatically using `Pillow`:
  - `icon.png`: white microphone on transparent background, 22x22px (macOS template image style)
  - `icon_active.png`: red filled circle with white mic, 22x22px
- Generate these icons as part of the build process if they don't exist

### `whisperflow.spec` (PyInstaller)
- Bundle the app as a proper `.app` with:
  - App name: WhisperFlow
  - Bundle identifier: `com.whisperflow.app`
  - Include all whisper model files
  - Include `ffmpeg` binary (required by whisper) — download it if not present
  - Icon: use a proper `.icns` file (convert from `icon.png`)
  - Code sign: ad-hoc signing (`codesign --sign -`)
  - `NSMicrophoneUsageDescription` in Info.plist: "WhisperFlow needs microphone access for voice dictation"
  - `NSAccessibilityUsageDescription` in Info.plist: "WhisperFlow needs accessibility access to inject text into apps"

### `build.sh`
```bash
#!/bin/bash
set -e
echo "🔨 Building WhisperFlow..."

# 1. Create venv
python3 -m venv .venv
source .venv/bin/activate

# 2. Install deps
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# 3. Download whisper small model if not cached
python3 -c "import whisper; whisper.load_model('small')"

# 4. Generate icons
python3 scripts/generate_icons.py

# 5. Convert icon.png to .icns
mkdir -p assets/icon.iconset
sips -z 16 16 assets/icon.png --out assets/icon.iconset/icon_16x16.png
sips -z 32 32 assets/icon.png --out assets/icon.iconset/icon_32x32.png
sips -z 128 128 assets/icon.png --out assets/icon.iconset/icon_128x128.png
sips -z 256 256 assets/icon.png --out assets/icon.iconset/icon_256x256.png
iconutil -c icns assets/icon.iconset -o assets/WhisperFlow.icns

# 6. Build .app
pyinstaller whisperflow.spec --clean

# 7. Ad-hoc code sign
codesign --sign - --force --deep dist/WhisperFlow.app

echo "✅ Build complete: dist/WhisperFlow.app"
echo "👉 Drag to /Applications and launch"
```

### `requirements.txt`
```
rumps>=0.4.0
pynput>=1.7.6
sounddevice>=0.4.6
numpy>=1.24.0
openai-whisper>=20231117
google-generativeai>=0.7.0
pyperclip>=1.8.2
pyautogui>=0.9.54
python-dotenv>=1.0.0
Pillow>=10.0.0
```

### `.env.example`
```
GEMINI_API_KEY=your_key_here
```

---

## Build & Validation Steps You Must Complete

After writing all code, do the following in sequence:

1. **Create all files** in the project structure above
2. **Run `pip install -r requirements.txt`** in a venv and fix any dependency conflicts
3. **Run `python3 -c "import whisper; whisper.load_model('small')"`** to pre-download the model
4. **Run the app in development mode** (`python3 app/main.py`) and verify it launches without errors — fix any import or runtime errors
5. **Test the hotkey** — verify right option key triggers recording
6. **Test transcription** — record a short clip, verify Whisper returns a transcript
7. **Test injection** — verify text lands in a text field
8. **Run `build.sh`** — fix any PyInstaller errors until `dist/WhisperFlow.app` is produced
9. **Verify the .app launches** and the menu bar icon appears
10. **Write a `README.md`** with: setup steps, how to get free Gemini API key (Google AI Studio), first-run accessibility permission instructions, and hotkey usage

---

## Error Handling Rules

- If microphone permission is denied → show rumps alert with instructions to enable in System Settings > Privacy > Microphone
- If Accessibility permission is denied → show rumps alert with instructions
- If Gemini API key is missing → skip AI cleanup silently, use raw Whisper output
- If Gemini call fails or times out → fall back to raw Whisper output, never crash
- If Whisper model not found → show alert prompting user to run `python3 -c "import whisper; whisper.load_model('small')"`
- All background threads must have try/except with error logging to `~/.whisperflow/logs/app.log`

---

## Final Deliverable

The completed project directory + `dist/WhisperFlow.app` ready to drag into /Applications.
The user only needs to:
1. Copy `.env.example` to `.env` and add their free Gemini API key from Google AI Studio
2. Drag `WhisperFlow.app` to `/Applications`
3. Launch it and grant mic + accessibility permissions when prompted

Everything else is handled by the app itself.
