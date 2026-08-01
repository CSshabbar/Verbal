# Verbal

Local-first voice dictation for **macOS, Windows and Linux**. Hold the hotkey to record, release to
transcribe and paste. macOS is the most complete; Windows and Linux share the same pipeline core behind
their own tray/overlay shells (`app/win_*.py`, `app/linux_*.py`).

## Features

- Local Whisper transcription (no cloud for basic dictation)
- Gemini AI cleanup for commands like "make this formal", "fix grammar"
- Multiple Gemini API keys with automatic fallback
- Menu bar app with model selection and history

## Setup

### Quick Start — macOS

```bash
cd whisperflow
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m app.main
```

### Quick Start — Linux

Linux needs system packages first. PyGObject is **not** pip-installable into a plain venv, and without it
the tray icon won't dock (pystray silently falls back to a backend with no menu at all) and the dashboard
won't open.

```bash
sudo apt install -y \
    python3-gi gir1.2-ayatanaappindicator3-0.1 gir1.2-webkit2-4.1 \
    python3-tk libportaudio2 xdotool xclip wl-clipboard

cd whisperflow
python3 -m venv --system-site-packages .venv     # --system-site-packages is REQUIRED
.venv/bin/python -m pip install -r requirements-linux.txt
.venv/bin/python -m app.linux_main
```

**Wayland users read this.** Wayland forbids an app from seeing global keys while another window is
focused, so the built-in hotkey does nothing there. Let the desktop own the key instead:

```bash
.venv/bin/python -m app.linux_main --install-hotkey        # default <Control><Alt>space
```

That registers a GNOME custom shortcut which runs `--toggle` against Verbal's IPC socket. Other commands:
`--start`, `--stop`, `--cancel`, `--show`, `--quit`, `--ping`, `--uninstall-hotkey`. GNOME shortcuts are
press-only, so this gives toggle mode, not hold-to-talk.

Optional desktop integration (`.desktop` entry, icon, a `verbal` launcher on PATH, autostart):

```bash
./packaging/install-desktop.sh --autostart
```

### Build

```bash
./build.sh          # macOS  → dist/Verbal.app
./build-win.sh      # Windows → dist/Verbal.exe
./build-linux.sh    # Linux   → dist/Verbal
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

Windows and Linux have no equivalent prompt. On Linux, note that target-app attribution (which app you
dictated into) is unavailable on Wayland — there's no supported API for it — so history entries there have
no app name.

## Usage

1. Hold the hotkey to record — **Right Option** on macOS, **Right Alt** on Windows, and on Linux whatever
   you bound with `--install-hotkey` (default `Ctrl+Alt+Space`, tap to toggle)
2. Release (or tap again) to transcribe
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
