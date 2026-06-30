# Verbal Debugging Guide

**Purpose:** Systematic approach to debugging common issues in Verbal

---

## 🔍 Debugging Philosophy

1. **Start with logs** - Always check `~/.verbal/logs/app.log` first
2. **Reproduce consistently** - Document exact steps to trigger the issue
3. **Isolate the component** - Determine which module is failing
4. **Check the simple stuff** - Permissions, network, API keys
5. **Add targeted logging** - Don't guess, instrument the code

---

## 📋 Debugging Checklist

### Before You Start

- [ ] Check logs: `tail -f ~/.verbal/logs/app.log`
- [ ] Verify API keys are valid and not rate-limited
- [ ] Confirm network connectivity: `ping api.groq.com`
- [ ] Check permissions (macOS): System Settings → Privacy & Security
- [ ] Restart app completely (quit from menu bar, relaunch)
- [ ] Test with different audio (rule out mic issues)
- [ ] Try different hotkey mode (hold vs toggle)

---

## 🐛 Common Issues & Solutions

### 1. Recording Cuts Short (Toggle Mode Bug)

**Symptoms:**
- First recording: works perfectly (8-10 seconds)
- Second/third recording: only 1-2 seconds captured
- Wrong transcription as a result

**Root Cause:**
Toggle mode double-trigger - NSEvent fires multiple events for a single keypress.

**Debug Steps:**

1. **Add timestamp logging** in `app/hotkey.py`:
```python
import time
logger = logging.getLogger("verbal.hotkey")

def _handle_key_event(self, event):
    timestamp = time.time()
    logger.info(f"[{timestamp:.6f}] Key event: keycode={event.keyCode}, flags={event.modifierFlags}")
```

2. **Add duration check** in `app/main.py`:
```python
def _stop_recording(self):
    duration = time.time() - self._recording_start_time
    logger.info(f"Stopping recording after {duration:.2f}s")
    if duration < 2.0:
        logger.warning("Recording stopped too early (<2s), ignoring")
        return
```

3. **Add minimum duration** in `app/recorder.py`:
```python
MIN_RECORDING_DURATION = 3.0  # seconds

def stop_recording(self):
    duration = time.time() - self._start_time
    if duration < MIN_RECORDING_DURATION:
        logger.warning(f"Enforcing minimum duration: {duration:.2f}s < {MIN_RECORDING_DURATION}s")
        time.sleep(MIN_RECORDING_DURATION - duration)
```

**Solution:**
- Switch to hold mode as default
- Add debounce logic to hotkey listener
- Use key release event instead of press

---

### 2. Transcription Fails Silently

**Symptoms:**
- Recording completes successfully
- No text appears
- No error message shown

**Debug Steps:**

1. **Check transcription logs** in `app.log`:
```bash
grep -i "transcribe" ~/.verbal/logs/app.log | tail -20
```

2. **Test each API tier manually**:
```python
# Test Groq
from groq import Groq
client = Groq(api_key="gsk_...")
with open("test.wav", "rb") as f:
    result = client.audio.transcriptions.create(
        file=("test.wav", f),
        model="whisper-large-v3-turbo"
    )
print(f"Groq result: {result.text}")

# Test Gemini
import google.generativeai as genai
genai.configure(api_key="AIza...")
model = genai.GenerativeModel("gemini-2.0-flash")
# Upload audio file and test
```

3. **Add detailed logging** in `app/transcriber.py`:
```python
def transcribe(audio, config, sample_rate=48000):
    logger.info(f"Transcription started - audio shape: {audio.shape}, sample_rate: {sample_rate}")
    
    # Check for silent audio
    peak = np.max(np.abs(audio))
    logger.info(f"Audio peak amplitude: {peak:.4f}")
    if peak < 0.01:
        logger.warning("Audio is nearly silent!")
    
    # Log each API attempt
    for i, key in enumerate(config.get("groq_api_keys", [])):
        logger.info(f"Trying Groq API key {i+1}/{len(config['groq_api_keys'])}")
        result = _transcribe_groq(tmp.name, key)
        if result:
            logger.info(f"Groq succeeded: {result[:50]}...")
            return result
        logger.warning(f"Groq key {i+1} failed")
```

**Common Causes:**
- API key expired or rate-limited
- Network connectivity issue
- Audio file format problem
- Empty/silent audio

**Solution:**
- Add retry logic with exponential backoff
- Show user-friendly error messages
- Implement proper fallback chain
- Add network connectivity check

---

### 3. Text Injection/Paste Fails

**Symptoms:**
- Transcription completes
- Text appears in dashboard
- Doesn't paste into target app

**Debug Steps:**

1. **Check Accessibility permissions** (macOS):
```bash
# Reset permissions
tccutil reset All com.verbal.app

# Check current permissions
sqlite3 ~/Library/Application\ Support/com.apple.TCC/TCC.db \
  "SELECT * FROM access WHERE client = 'com.verbal.app';"
```

2. **Add logging** in `app/injector.py`:
```python
def inject_text(text):
    logger.info(f"Injecting text ({len(text)} chars)")
    
    # Save focused app
    app_pid = save_focused_app()
    logger.info(f"Saved focused app PID: {app_pid}")
    
    # Set clipboard
    pyperclip.copy(text)
    logger.info("Text copied to clipboard")
    
    # Restore focus
    restore_focus(app_pid)
    logger.info("Focus restored")
    
    # Wait for focus
    time.sleep(0.2)
    
    # Simulate Cmd+V
    logger.info("Simulating Cmd+V")
    # ... CGEvent code ...
```

3. **Test manually**:
```python
import pyperclip
pyperclip.copy("Test text")
# Manually press Cmd+V to verify clipboard works
```

**Common Causes:**
- Accessibility permission denied
- App lost focus during transcription
- Timing issue (paste before app focused)
- CGEvent blocked by security software

**Solution:**
- Re-enable Accessibility permissions
- Increase focus restore delay (200ms → 500ms)
- Add visual indicator when pasting
- Fallback to manual copy (show notification)

---

### 4. Sync Not Working

**Symptoms:**
- Transcription appears on Device A
- Doesn't appear on Device B
- No error messages

**Debug Steps:**

1. **Check sync configuration**:
```bash
cat ~/.verbal/config.json | grep -A5 "sync"
```

Expected:
```json
{
  "sync_enabled": true,
  "sync_user_id": "user-uuid",
  "sync_device_name": "MacBook Pro"
}
```

2. **Test Supabase connection**:
```bash
curl -H "apikey: YOUR_KEY" \
  "https://ovpcthjingugwvpxlsna.supabase.co/rest/v1/transcriptions?limit=1"
```

3. **Check WebSocket connection** in `app/sync.py`:
```python
class SyncClient:
    def _run(self):
        logger.info(f"Connecting to {WS_URL[:50]}...")
        try:
            self._ws = websocket.create_connection(WS_URL)
            self._connected = True
            logger.info("WebSocket connected")
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            self._connected = False
```

4. **Monitor Supabase dashboard**:
- Go to Supabase project → Logs → Realtime
- Check for connection events
- Look for INSERT events

5. **Add push/pull logging**:
```python
def push(self, text, target_device_id=None):
    logger.info(f"Push request: text_len={len(text)}, target={target_device_id}")
    threading.Thread(
        target=self._push_rest,
        args=(text, target_device_id),
        daemon=True
    ).start()

def _push_rest(self, text, target_device_id):
    try:
        logger.debug(f"POST to {REST_URL}/transcriptions")
        resp = httpx.post(...)
        logger.info(f"Push response: {resp.status_code}")
    except Exception as e:
        logger.error(f"Push failed: {e}")
```

**Common Causes:**
- Sync disabled in config
- Wrong Supabase credentials
- WebSocket connection blocked by firewall
- Different user_id on devices
- Realtime subscription not active

**Solution:**
- Verify same `sync_user_id` on all devices
- Check Supabase Realtime is enabled
- Add connection retry logic
- Show sync status in UI

---

### 5. Build Fails (PyInstaller)

**Symptoms:**
- Build script runs but app crashes on launch
- Missing module errors
- Data files not found

**Debug Steps:**

1. **Check build output**:
```bash
./build.sh 2>&1 | grep -i "error\|warning\|missing"
```

2. **Add all hidden imports** in `.spec` file:
```python
hiddenimports=[
    'faster_whisper',
    'ctranslate2',
    'sounddevice',
    'soundfile',
    'numpy',
    'rumps',
    'pyperclip',
    'pyautogui',
    'google.generativeai',
    'huggingface_hub',
    # macOS frameworks
    'objc',
    'Foundation',
    'AppKit',
    'Quartz',
]
```

3. **Include data files**:
```python
datas=[
    ('assets/icon.png', 'assets'),
    ('assets/icon_active.png', 'assets'),
    ('assets/sounds/start.aiff', 'assets/sounds'),
    ('assets/sounds/stop.aiff', 'assets/sounds'),
    # Critical: Whisper model data
    (fw_dir, 'faster_whisper'),
    (ct2_dir, 'ctranslate2'),
]
```

4. **Test built app with console output**:
```bash
# Run from terminal to see errors
./dist/Verbal.app/Contents/MacOS/Verbal

# Or check system logs
log show --predicate 'process == "Verbal"' --last 5m
```

5. **Clean build**:
```bash
rm -rf build/ dist/ __pycache__/
./build.sh
```

**Common Causes:**
- Missing hidden imports
- Data files not bundled
- Binary dependencies (faster_whisper, ctranslate2)
- Framework imports not included

**Solution:**
- Add all imports to `.spec` file
- Include data directories
- Test on clean machine
- Use `--onefile` vs `--onedir` appropriately

---

### 6. Hotkey Not Detected

**Symptoms:**
- Press hotkey (Right Option/Right Cmd)
- No response from app
- Recording doesn't start

**Debug Steps:**

1. **Check keycode mapping**:
```python
# Test keycode detection
from AppKit import NSEvent
import logging

def test_hotkey():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("hotkey_test")
    
    def handle_event(event):
        if event.type() == 12:  # FlagsChanged
            logger.info(f"FlagsChanged: keyCode={event.keyCode()}, flags={event.modifierFlags()}")
        elif event.type() == 10:  # KeyDown
            logger.info(f"KeyDown: keyCode={event.keyCode()}, flags={event.modifierFlags()}")
    
    NSEvent.addGlobalMonitorForEventsMatchingMask_mask_callback_(
        0xFFFFFFFFFFFFFFFF,  # All events
        handle_event
    )
    
    # Run for 30 seconds
    from time import sleep
    sleep(30)

test_hotkey()
```

2. **Check permissions** (macOS):
```bash
# Accessibility permission required for global hotkeys
# System Settings → Privacy & Security → Accessibility
```

3. **Add logging** in `app/hotkey.py`:
```python
class HotkeyListener:
    def _handle_event(self, event):
        keycode = event.keyCode()
        flags = event.modifierFlags()
        logger.info(f"Event: type={event.type()}, keycode={keycode}, flags={flags}")
        
        if keycode == 0x36:  # Right Command
            logger.info("Right Command detected!")
```

**Common Causes:**
- Wrong keycode in config
- Accessibility permission denied
- Event monitor not started
- Conflicting app using same hotkey

**Solution:**
- Verify keycode (Right Option = 54, Right Cmd = 0x36)
- Re-enable Accessibility permissions
- Check for hotkey conflicts
- Use different hotkey if needed

---

### 7. API Rate Limit Errors

**Symptoms:**
- Transcription fails after several uses
- Error: "Rate limit exceeded"
- Fallback to next tier works

**Debug Steps:**

1. **Check API usage**:
```python
# Groq dashboard: https://console.groq.com/usage
# Gemini dashboard: https://console.cloud.google.com/apis/credentials

# Add usage tracking in config
{
  "groq_usage_today": 2.5,  # hours
  "gemini_requests_today": 1200,
}
```

2. **Add rate limit handling**:
```python
from groq import RateLimitError

def _transcribe_groq(wav_path, api_key):
    try:
        client = Groq(api_key=api_key)
        result = client.audio.transcriptions.create(...)
        return result.text
    except RateLimitError as e:
        logger.warning(f"Groq rate limited: {e}")
        return None  # Trigger fallback
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return None
```

3. **Implement rotation**:
```python
def get_next_groq_key(config):
    keys = config.get("groq_api_keys", [])
    if not keys:
        return None
    
    # Rotate through keys
    current = config.get("current_groq_key_index", 0)
    next_index = (current + 1) % len(keys)
    config["current_groq_key_index"] = next_index
    save_config(config)
    
    return keys[current]
```

**Common Causes:**
- Free tier limits (Groq: 8hrs/day, Gemini: 1500 req/day)
- Burst limits (RPM, TPM)
- Single key shared across devices

**Solution:**
- Add multiple API keys with rotation
- Show usage in dashboard
- Implement exponential backoff
- Cache transcriptions to reduce API calls

---

## 🛠️ Debugging Tools

### Log Analysis

```bash
# Real-time monitoring
tail -f ~/.verbal/logs/app.log

# Search for errors
grep -i "error\|fail\|exception" ~/.verbal/logs/app.log

# Count transcriptions per hour
grep "Transcription:" ~/.verbal/logs/app.log | cut -d' ' -f1 | cut -d':' -f1 | uniq -c

# Find slow transcriptions
grep "transcribe.*s:" ~/.verbal/logs/app.log | awk '{print $NF}' | sort -n | tail -10
```

### Network Debugging

```bash
# Test Groq API
curl -X POST https://api.groq.com/openai/v1/audio/transcriptions \
  -H "Authorization: Bearer $GROQ_API_KEY" \
  -F "file=@test.wav" \
  -F "model=whisper-large-v3-turbo"

# Test Gemini API
curl -X POST "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @request.json

# Test Supabase
curl -H "apikey: $SUPABASE_KEY" \
  "https://YOUR_PROJECT.supabase.co/rest/v1/transcriptions?limit=5"

# Check WebSocket
wscat -c "wss://YOUR_PROJECT.supabase.co/realtime/v1/websocket?apikey=KEY"
```

### Permission Debugging (macOS)

```bash
# Reset all permissions for app
tccutil reset All com.verbal.app

# Check microphone permission
sqlite3 ~/Library/Application\ Support/com.apple.TCC/TCC.db \
  "SELECT * FROM access WHERE client = 'com.verbal.app' AND service = 'kTCCServiceMicrophone';"

# Check accessibility permission
sqlite3 ~/Library/Application\ Support/com.apple.TCC/TCC.db \
  "SELECT * FROM access WHERE client = 'com.verbal.app' AND service = 'kTCCServiceAccessibility';"

# Grant permissions manually
# System Settings → Privacy & Security → Microphone → Verbal
# System Settings → Privacy & Security → Accessibility → Verbal
```

### Memory/Performance Profiling

```python
# Add to app/main.py
import tracemalloc
import linecache

tracemalloc.start()

def print_memory_usage():
    current, peak = tracemalloc.get_traced_memory()
    print(f"Current: {current / 10**6:.2f} MB; Peak: {peak / 10**6:.2f} MB")
    
    # Top 10 memory allocations
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')
    print("\nTop 10 memory allocations:")
    for stat in top_stats[:10]:
        print(stat)

# Call periodically
# print_memory_usage()
```

---

## 📊 Debugging Checklist by Component

### Audio Recording
- [ ] Microphone permission granted
- [ ] Audio device selected correctly
- [ ] Sample rate set to 48000
- [ ] Buffer not overflowing
- [ ] Recording state managed correctly
- [ ] Audio not silent (check peak amplitude)

### Transcription
- [ ] API keys configured
- [ ] Network connectivity OK
- [ ] Not rate-limited
- [ ] Audio file saved correctly
- [ ] Fallback chain working
- [ ] Resampling to 16kHz for local Whisper

### Text Injection
- [ ] Accessibility permission granted
- [ ] Focused app saved before recording
- [ ] Focus restored correctly
- [ ] Clipboard set with text
- [ ] Cmd+V simulated
- [ ] Timing delays sufficient

### Sync
- [ ] Sync enabled in config
- [ ] Supabase credentials valid
- [ ] WebSocket connected
- [ ] Realtime subscription active
- [ ] Device registered
- [ ] Heartbeat updating last_seen

### UI/UX
- [ ] Menu bar icon visible
- [ ] Dashboard opens correctly
- [ ] History displays properly
- [ ] Settings save/load correctly
- [ ] Overlay shows during recording
- [ ] Sounds play at correct times

---

## 🎯 Debugging Workflow Template

When debugging any issue, follow this template:

### 1. Reproduce the Issue
```
Steps to reproduce:
1. Open Verbal from menu bar
2. Press Right Option key
3. Speak for 5 seconds
4. Release key
5. Observe: [what happens vs what should happen]
```

### 2. Collect Logs
```bash
# Enable debug logging
# In app/config.py, add:
# "debug_mode": true

# Collect logs
tail -f ~/.verbal/logs/app.log > /tmp/verbal-debug.log
# ... reproduce issue ...
# Press Ctrl+C to stop
cat /tmp/verbal-debug.log
```

### 3. Isolate Component
```
Based on logs, the issue appears to be in:
- [ ] Audio recording (recorder.py)
- [ ] Transcription (transcriber.py)
- [ ] AI processing (ai_cleanup.py)
- [ ] Text injection (injector.py)
- [ ] Hotkey detection (hotkey.py)
- [ ] Sync (sync.py)
- [ ] UI (dashboard.py, overlay.py)
```

### 4. Add Targeted Logging
```python
# In the suspected module, add:
logger.info(f"DEBUG: [timestamp] state={state}, input={input}, output={output}")
```

### 5. Test Hypothesis
```
Hypothesis: The issue is caused by [specific cause]
Test: [specific test to verify]
Result: [pass/fail]
```

### 6. Implement Fix
```python
# Code change here
```

### 7. Verify Fix
```
- [ ] Issue no longer occurs
- [ ] No regressions in other features
- [ ] Logs show expected behavior
- [ ] Tested on clean environment
```

---

**End of Debugging Guide**
