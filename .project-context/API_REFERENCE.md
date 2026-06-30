# Verbal API Reference

**Purpose:** Complete API documentation for all internal modules and external integrations

---

## 📦 Desktop Application (Python)

### `app/config.py` - Configuration Management

#### Functions

##### `load_config() -> dict`
Loads user configuration from `~/.verbal/config.json`.

**Returns:**
```python
{
    "whisper_model": "base",
    "hotkey": "cmd_r",
    "hotkey_hold": 54,
    "hotkey_toggle": 54,
    "recording_mode": "toggle",
    "groq_api_keys": ["gsk_..."],
    "gemini_api_keys": ["AIza..."],
    "active_gemini_key_index": 0,
    "sync_enabled": True,
    "sync_user_id": "user-uuid",
    "sync_device_name": "MacBook Pro",
    "history": [...],
    "pinned": [...],
    "daily": {"date": "2026-06-30", "words": 1234},
    "auto_update": True
}
```

##### `save_config(config: dict) -> None`
Saves configuration atomically (writes to .tmp then renames).

##### `add_gemini_key(config: dict, key: str) -> dict`
Adds a new Gemini API key to the config.

##### `remove_gemini_key(config: dict, index: int) -> dict`
Removes a Gemini API key by index.

---

### `app/recorder.py` - Audio Recording

#### Class: `Recorder`

##### `__init__()`
Initializes the recorder with default settings.

**Attributes:**
- `sample_rate: int = 48000` - Native recording sample rate
- `channels: int = 1` - Mono recording
- `dtype: str = 'float32'` - Audio data type
- `_buffer: list = []` - Audio buffer
- `_recording: bool = False` - Recording state
- `_stream: sounddevice.InputStream` - Audio stream

##### `start_recording()`
Starts recording audio. Creates a new InputStream.

##### `stop_recording() -> np.ndarray`
Stops recording and returns the captured audio.

**Returns:**
- `np.ndarray` - Audio samples as float32 array

**Example:**
```python
recorder = Recorder()
recorder.start_recording()
# ... user speaks ...
audio = recorder.stop_recording()
```

##### `clear_buffer()`
Clears the audio buffer without stopping.

---

### `app/transcriber.py` - Speech-to-Text

#### Function: `transcribe(audio: np.ndarray, config: dict, sample_rate: int = 48000) -> str`

Transcribes audio using the fallback chain: Groq → Gemini → Local Whisper.

**Parameters:**
- `audio` - Audio samples as numpy array
- `config` - Configuration dict with API keys
- `sample_rate` - Audio sample rate (default: 48000)

**Returns:**
- `str` - Transcribed text

**Fallback Priority:**
1. **Groq API** (whisper-large-v3-turbo) - Best accuracy, free tier
2. **Gemini API** (gemini-2.0-flash) - User's existing keys
3. **Local Whisper** (faster-whisper) - Offline fallback

**Example:**
```python
text = transcribe(audio, config)
logger.info(f"Transcription: {text}")
```

#### Internal Functions

##### `_transcribe_groq(wav_path: str, api_key: str) -> str | None`
Calls Groq Whisper API.

**Parameters:**
- `wav_path` - Path to WAV file
- `api_key` - Groq API key

**Returns:**
- `str` - Transcription text, or `None` on failure

##### `_transcribe_gemini(wav_path: str, api_key: str) -> str | None`
Calls Gemini audio API.

**Parameters:**
- `wav_path` - Path to WAV file
- `api_key` - Gemini API key

**Returns:**
- `str` - Transcription text, or `None` on failure

##### `_transcribe_local(wav_path: str, model: str) -> str`
Runs local Whisper model.

**Parameters:**
- `wav_path` - Path to WAV file (must be 16kHz)
- `model` - Whisper model name (tiny/base/small/medium/large)

**Returns:**
- `str` - Transcription text

##### `_resample_to_16k(audio, orig_rate) -> str`
Resamples audio to 16kHz for local Whisper.

**Returns:**
- `str` - Path to temporary 16kHz WAV file

---

### `app/ai_cleanup.py` - Text Formatting

#### Function: `process_text(text: str, config: dict) -> str`

Applies AI formatting rules to transcribed text.

**Parameters:**
- `text` - Raw transcription output
- `config` - Configuration with command keywords

**Returns:**
- `str` - Formatted text

**Processing Steps:**
1. Check for command keywords (e.g., "make this formal")
2. Apply 17 formatting rules via Gemini
3. Remove hallucinations ("Thank you", etc.)
4. Convert file references to tags (@filename)

**Example:**
```python
raw = "um so like i think we should you know do the thing"
formatted = process_text(raw, config)
# Result: "So, I think we should do the thing."
```

#### Constants

##### `SYSTEM_PROMPT: str`
Complete prompt with all 17 formatting rules for Gemini.

##### `COMMAND_KEYWORDS: list`
Keywords that trigger AI processing:
```python
["make", "fix", "convert", "formal", "casual", "bullet",
 "summarize", "rephrase", "translate", "shorter", "longer"]
```

##### `FILE_TAG_PATTERNS: list`
Regex patterns for file reference conversion:
```python
[
    r'\bat file\s+(\S+)',
    r'\btag file\s+(\S+)',
    r'\btag\s+(\S+\.\S+)',
]
```

---

### `app/injector.py` - Text Injection

#### Function: `inject_text(text: str) -> None`

Pastes text into the focused application.

**Process:**
1. Save current focused app PID
2. Restore focus to saved app
3. Wait 200ms
4. Simulate Cmd+V via CGEvent
5. Clear clipboard

**Parameters:**
- `text` - Text to paste

##### `save_focused_app() -> int`
Saves the PID of the currently focused app.

**Returns:**
- `int` - App PID

##### `get_focused_app_name() -> str`
Gets the name of the currently focused app.

**Returns:**
- `str` - App name (e.g., "Visual Studio Code")

---

### `app/hotkey.py` - Hotkey Detection

#### Class: `HotkeyListener`

##### `__init__(on_start, on_stop, on_esc, config)`
Initializes hotkey listener.

**Parameters:**
- `on_start` - Callback when recording starts
- `on_stop` - Callback when recording stops
- `on_esc` - Callback when ESC pressed
- `config` - Configuration with hotkey settings

##### `start()`
Starts listening for hotkey events.

##### `stop()`
Stops listening.

##### `is_recording() -> bool`
Checks if currently recording.

**Implementation:**
```python
# Uses NSEvent.addGlobalMonitorForEventsMatchingMask_
# Monitors:
# - NSEventTypeFlagsChanged (type 12) for modifier keys
# - NSEventTypeKeyDown (type 10) for ESC
```

---

### `app/sync.py` - Cross-Device Sync

#### Class: `SyncClient`

##### `__init__(user_id: str, device_name: str, on_receive)`
Creates sync client and starts WebSocket connection.

**Parameters:**
- `user_id` - Unique user identifier
- `device_name` - Human-readable device name
- `on_receive` - Callback when transcription received from other device

**Attributes:**
- `user_id: str`
- `device_id: str` - platform.node()
- `device_name: str`
- `_ws: websocket.WebSocket`
- `_connected: bool`

##### `push(text: str, target_device_id: str | None = None)`
Pushes transcription to sync server.

**Parameters:**
- `text` - Transcription text
- `target_device_id` - Optional: send to specific device only (None = broadcast)

##### `_push_rest(text: str, target_device_id: str | None)`
Internal: REST API push implementation.

##### `_run()`
Internal: WebSocket listener thread.

##### `_register_device()`
Internal: Registers device in Supabase, updates every 60s.

---

### `app/dashboard.py` - Main Window

#### Class: `DashboardWindow`

##### `__init__(app: VerbalApp)`
Creates dashboard window.

**UI Components:**
- Daily word count
- Total transcriptions
- Total words
- History list
- Model selector
- API key management
- Sync settings

##### `update_stats()`
Refreshes statistics display.

##### `show_history()`
Opens history viewer.

##### `manage_api_keys()`
Opens API key management dialog.

---

## 📱 Mobile Application (React Native)

### `lib/supabase.ts` - Backend Client

#### Constant: `supabase`

Supabase client instance.

**Configuration:**
```typescript
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = 'https://ovpcthjingugwvpxlsna.supabase.co';
const supabaseKey = 'eyJhbG...';

export const supabase = createClient(supabaseUrl, supabaseKey);
```

**Usage:**
```typescript
// Query transcriptions
const { data } = await supabase
  .from('transcriptions')
  .select('*')
  .eq('user_id', userId)
  .order('created_at', { ascending: false });

// Subscribe to realtime
const channel = supabase
  .channel('transcriptions')
  .on('postgres_changes', 
    { event: 'INSERT', schema: 'public', table: 'transcriptions' },
    (payload) => {
      console.log('New transcription:', payload.new);
    }
  )
  .subscribe();
```

---

### `lib/groq.ts` - Groq API Client

#### Function: `transcribeAudio(audioUri: string): Promise<string>`

Transcribes audio file using Groq API.

**Parameters:**
- `audioUri` - Local file URI of audio recording

**Returns:**
- `Promise<string>` - Transcription text

**Example:**
```typescript
const audioUri = 'file:///path/to/recording.m4a';
const text = await transcribeAudio(audioUri);
console.log('Transcription:', text);
```

---

### `lib/storage.ts` - Local Storage

#### Functions

##### `saveTranscription(text: string, app: string): Promise<void>`
Saves transcription to local storage.

##### `getHistory(): Promise<Transcription[]>`
Gets all transcriptions from history.

##### `deleteTranscription(id: string): Promise<void>`
Deletes a transcription.

##### `getDailyWords(): Promise<number>`
Gets word count for today.

---

### `lib/theme.ts` - Design System

#### Constant: `colors`

Color palette for the app.

```typescript
export const colors = {
  heroBg: '#1A1917',
  heroMuted: '#7A7570',
  accent: '#E05A2B',
  text: '#F2EFE9',
  // ...
};
```

---

## 🔌 External APIs

### Groq API

**Endpoint:** `https://api.groq.com/openai/v1/audio/transcriptions`

**Model:** `whisper-large-v3-turbo`

**Request:**
```python
from groq import Groq

client = Groq(api_key="gsk_...")
result = client.audio.transcriptions.create(
    file=("audio.wav", open("audio.wav", "rb")),
    model="whisper-large-v3-turbo",
    language="en",
    temperature=0.0,
    prompt="Voice dictation of spoken English.",
)
```

**Response:**
```json
{
  "text": "Transcribed text here"
}
```

**Rate Limits:**
- Free tier: 8 hours/day
- RPM: 60 requests/minute
- TPM: 100,000 tokens/minute

---

### Google Gemini API

**Endpoint:** `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent`

**Request:**
```python
import google.generativeai as genai

genai.configure(api_key="AIza...")
model = genai.GenerativeModel("gemini-2.0-flash")

# For audio transcription
result = model.generate_content(
    contents=[audio_file],
    generation_config=genai.types.GenerationConfig(
        temperature=0.0,
    ),
)
```

**For text formatting:**
```python
response = model.generate_content([
    SYSTEM_PROMPT,
    raw_transcription_text
])
formatted_text = response.text
```

**Rate Limits:**
- Free tier: 1500 requests/day
- RPM: 15 requests/minute
- TPM: 1,000,000 tokens/minute

---

### Supabase API

**Base URL:** `https://ovpcthjingugwvpxlsna.supabase.co/rest/v1`

**Headers:**
```
apikey: eyJhbG...
Authorization: Bearer eyJhbG...
Content-Type: application/json
```

#### Insert Transcription

**Request:**
```http
POST /transcriptions
Content-Type: application/json

{
  "user_id": "user-uuid",
  "device_id": "device-id",
  "device_name": "MacBook Pro",
  "text": "Transcribed text",
  "target_device_id": null
}
```

#### Query Transcriptions

**Request:**
```http
GET /transcriptions?user_id=eq.user-uuid&order=created_at.desc
```

**Response:**
```json
[
  {
    "id": "uuid",
    "user_id": "user-uuid",
    "device_id": "device-id",
    "text": "Transcribed text",
    "created_at": "2026-06-30T12:00:00Z"
  }
]
```

#### Realtime Subscription

**WebSocket URL:**
```
wss://ovpcthjingugwvpxlsna.supabase.co/realtime/v1/websocket?apikey=KEY&vsn=1.0.0
```

**Join Message:**
```json
{
  "topic": "realtime:transcriptions",
  "event": "phx_join",
  "payload": {
    "config": {
      "broadcast": { "self": true },
      "presence": { "key": "user_id" }
    }
  },
  "ref": "1"
}
```

---

## 📊 Database Schema

### Tables

#### `transcriptions`

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid | Primary key |
| `user_id` | text | User identifier |
| `device_id` | text | Device identifier |
| `device_name` | text | Human-readable name |
| `target_device_id` | text | Optional target device |
| `text` | text | Transcription text |
| `created_at` | timestamptz | Creation timestamp |

**Indexes:**
```sql
CREATE INDEX idx_transcriptions_user ON transcriptions(user_id, created_at DESC);
```

#### `devices`

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | text | User identifier |
| `device_id` | text | Device identifier |
| `device_name` | text | Human-readable name |
| `device_type` | text | Platform (mac/win/ios/android) |
| `last_seen` | timestamptz | Last activity timestamp |

**Primary Key:** `(user_id, device_id)`

#### `app_versions`

| Column | Type | Description |
|--------|------|-------------|
| `id` | serial | Primary key |
| `platform` | text | Platform (mac/win/ios/android) |
| `version` | text | Version string (e.g., "1.0.10") |
| `release_notes` | text | Release notes markdown |
| `download_url` | text | Download link |
| `released_at` | timestamptz | Release timestamp |

---

## 🧪 Testing APIs

### Test Transcription

```python
import numpy as np
from app.transcriber import transcribe
from app.config import load_config

config = load_config()
# Generate test audio (1 second of silence)
audio = np.zeros(48000, dtype=np.float32)
result = transcribe(audio, config)
print(f"Result: '{result}'")
```

### Test Sync

```python
from app.sync import SyncClient

def on_receive(text):
    print(f"Received: {text}")

client = SyncClient(
    user_id="test-user",
    device_name="Test Device",
    on_receive=on_receive
)

client.push("Test transcription")
```

### Test Mobile Supabase

```typescript
import { supabase } from './lib/supabase';

async function testSync() {
  // Insert
  const { error: insertError } = await supabase
    .from('transcriptions')
    .insert({
      user_id: 'test-user',
      device_id: 'test-device',
      text: 'Test from mobile',
    });

  if (insertError) {
    console.error('Insert failed:', insertError);
  }

  // Query
  const { data, error } = await supabase
    .from('transcriptions')
    .select('*')
    .eq('user_id', 'test-user')
    .limit(5);

  console.log('Recent transcriptions:', data);
}
```

---

**End of API Reference**
