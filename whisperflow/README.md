# Verbal

Local-first voice dictation for macOS. Hold Right Option key to record, release to transcribe and paste.

## Features

- Local Whisper transcription (no cloud for basic dictation)
- Gemini AI cleanup for commands like "make this formal", "fix grammar"
- Multiple Gemini API keys with automatic fallback
- Menu bar app with model selection and history

## Setup

### Quick Start (Development)

```bash
cd whisperflow
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m app.main
```

### Build .app

```bash
chmod +x build.sh
./build.sh
# Output: dist/Verbal.app
```

### Gemini API Keys (Free)

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Create a free API key
3. In the app menu bar, click Verbal > "Manage Gemini API Keys..."
4. Paste your key(s) - add multiple for automatic failover

### Permissions

On first launch, macOS will ask for:
- **Microphone** - for voice recording
- **Accessibility** - for pasting text into apps

Grant both in System Settings > Privacy & Security.

## Usage

1. Hold **Right Option** key to record
2. Release to transcribe
3. Text is automatically pasted into the focused app

### Voice Commands

Include these in your dictation for AI processing:
- "make this formal"
- "fix grammar"
- "convert to bullet points"
- "summarize this"
- "translate to Spanish"

Without a command keyword, raw Whisper output is used directly (faster).

## Configuration

Settings stored in `~/.verbal/config.json`. Change Whisper model from the menu bar (tiny/base/small/medium).
