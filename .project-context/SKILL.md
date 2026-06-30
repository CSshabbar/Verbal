# Verbal Project Context Skill

**Purpose:** Provide structured access to Verbal project context for debugging and feature development

**Scope:** This skill helps you navigate the Verbal codebase efficiently by using the project context index to locate relevant files, understand architecture, and apply appropriate patterns.

---

## 🎯 When to Use This Skill

### Debugging Scenarios
Use this skill when:
- User reports a bug or error in Verbal
- Logs show issues in transcription, recording, or sync
- Build fails with PyInstaller or Expo errors
- Hotkey detection not working
- Text injection fails
- Sync between devices broken
- API calls failing (Groq, Gemini, Supabase)

### Feature Development
Use this skill when:
- User wants to add new features to desktop or mobile apps
- Need to understand existing patterns for implementation
- Adding new API integrations
- Extending sync functionality
- Creating new UI components
- Modifying configuration options

### Code Understanding
Use this skill when:
- User asks how a specific component works
- Need to trace data flow through the system
- Understanding cross-platform differences
- Learning the architecture before making changes

---

## 📖 How to Use the Index

### Step 1: Identify the Context Domain

Based on the user's request, determine which domain they're asking about:

| Domain | Index Section | Key Files |
|--------|---------------|-----------|
| **Recording issues** | Component Map → Recorder | `app/recorder.py`, `app/hotkey.py` |
| **Transcription errors** | APIs & Integrations → Groq/Gemini | `app/transcriber.py`, `app/ai_cleanup.py` |
| **Sync problems** | APIs & Integrations → Supabase | `app/sync.py`, database schema |
| **UI/UX bugs** | Component Map → Dashboard/Overlay | `app/dashboard.py`, `app/overlay.py` |
| **Build failures** | Build & Deployment | `*.spec` files, `build.sh` |
| **Mobile issues** | Component Map → Mobile | `verbal-mobile/`, `App.tsx` |
| **Configuration** | Configuration Files | `app/config.py`, `~/.verbal/config.json` |

### Step 2: Retrieve Relevant Context

Use the index to locate specific files:

```markdown
1. Check "Component Map" for file location
2. Check "Key Files Reference" for file purpose
3. Check "Common Debugging Scenarios" for known issues
4. Check "Feature Development Guide" for implementation patterns
```

### Step 3: Apply Appropriate Patterns

#### For Desktop (Python) Features:
- Use `logging.getLogger("verbal.module_name")` for logging
- Follow the component pattern: create module → integrate in `main.py` → add config → update UI
- Use threading for background operations (sync, API calls)
- Store settings in `config.py` DEFAULT_CONFIG

#### For Mobile (React Native) Features:
- Create screen component in `screens/`
- Add to tab navigator in `App.tsx`
- Use lib utilities from `lib/` folder
- Follow theme from `lib/theme.ts`

---

## 🔍 Debugging Workflow

### 1. Recording/Audio Issues

**Check these files in order:**
1. `app/hotkey.py` - Key event detection
2. `app/recorder.py` - Audio capture
3. `app/main.py` - State management
4. `~/.verbal/logs/app.log` - Runtime logs

**Common patterns:**
```python
# In hotkey.py - add timestamp logging
logger.info(f"[HOTKEY] {time.time():.3f} - Key event: {keycode}")

# In recorder.py - check audio duration
duration = len(audio) / sample_rate
logger.info(f"Recorded {duration:.2f}s of audio (samples={len(audio)})")
```

### 2. Transcription Failures

**Check these files in order:**
1. `app/transcriber.py` - API fallback chain
2. `app/config.py` - API keys
3. `app/ai_cleanup.py` - Post-processing
4. Network connectivity

**Debug pattern:**
```python
# Add detailed logging for each tier
logger.info(f"[Groq] Attempting with key {api_key[:8]}...")
result = _transcribe_groq(...)
if result:
    logger.info(f"[Groq] Success: {result[:50]}...")
else:
    logger.warning("[Groq] Failed, trying Gemini...")
```

### 3. Sync Issues

**Check these files in order:**
1. `app/sync.py` - WebSocket connection
2. `app/config.py` - Sync credentials
3. Supabase dashboard - Realtime logs
4. `~/.verbal/logs/sync.log` - Sync-specific logs

**Debug pattern:**
```python
# In sync.py - log connection state
logger.info(f"SyncClient connecting to {WS_URL[:50]}...")
logger.debug(f"WebSocket state: connected={self._connected}, ref={self._ref}")

# Log push/pull operations
logger.info(f"Push: user={self.user_id[:8]}, text_len={len(text)}, target={target_device_id}")
```

### 4. Build Failures

**Common PyInstaller issues:**

**Missing data files:**
```python
# In .spec file
datas=[
    ('assets/icon.png', 'assets'),
    (fw_dir, 'faster_whisper'),  # Critical for Whisper
    (ct2_dir, 'ctranslate2'),     # Critical for inference
]
```

**Missing hidden imports:**
```python
hiddenimports=[
    'faster_whisper',
    'ctranslate2',
    'sounddevice',
    'soundfile',
    'numpy',
    # Platform-specific
    'AppKit', 'Foundation', 'Quartz',  # macOS
]
```

---

## 🚀 Feature Development Patterns

### Pattern 1: Adding a New API Integration

**Example: Adding DeepL translation**

1. **Create module** (`app/deepl_translator.py`):
```python
import logging
import httpx

logger = logging.getLogger("verbal.deepl")

class DeepLTranslator:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.deepl.com/v2/translate"
    
    def translate(self, text: str, target_lang: str) -> str:
        try:
            resp = httpx.post(
                self.base_url,
                headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
                params={"text": text, "target_lang": target_lang},
                timeout=10,
            )
            result = resp.json()["translations"][0]["text"]
            logger.info(f"Translated to {target_lang}: {result[:50]}...")
            return result
        except Exception as e:
            logger.error(f"DeepL translation failed: {e}")
            return text
```

2. **Add config** (`app/config.py`):
```python
DEFAULT_CONFIG = {
    # ...
    "deepl_api_key": "",
    "translation_target_lang": "EN-US",
}
```

3. **Integrate in main** (`app/main.py`):
```python
from app.deepl_translator import DeepLTranslator

class VerbalApp(rumps.App):
    def __init__(self):
        # ...
        self.translator = DeepLTranslator(self.config.get("deepl_api_key", ""))
```

4. **Add UI** (`app/dashboard.py`):
```python
@rumps.clicked("Translate to Spanish")
def translate_es(self, sender):
    # Get last transcription
    # Call self.translator.translate(text, "ES")
    # Update UI
    pass
```

### Pattern 2: Adding Mobile Screen

**Example: Analytics screen**

1. **Create screen** (`verbal-mobile/screens/AnalyticsScreen.tsx`):
```tsx
import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors } from '../lib/theme';
import { supabase } from '../lib/supabase';

export default function AnalyticsScreen() {
  const [stats, setStats] = useState({ totalWords: 0, totalTranscriptions: 0 });

  useEffect(() => {
    loadStats();
  }, []);

  async function loadStats() {
    const { data } = await supabase
      .from('transcriptions')
      .select('text')
      .eq('user_id', USER_ID);
    
    if (data) {
      setStats({
        totalTranscriptions: data.length,
        totalWords: data.reduce((acc, t) => acc + t.text.split(' ').length, 0),
      });
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Analytics</Text>
      <View style={styles.stat}>
        <Text style={styles.value}>{stats.totalTranscriptions}</Text>
        <Text style={styles.label}>Transcriptions</Text>
      </View>
      <View style={styles.stat}>
        <Text style={styles.value}>{stats.totalWords}</Text>
        <Text style={styles.label}>Words</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.heroBg, padding: 20 },
  title: { fontSize: 32, fontWeight: '700', color: colors.text, marginBottom: 24 },
  stat: { marginBottom: 16 },
  value: { fontSize: 48, fontWeight: '700', color: colors.accent },
  label: { fontSize: 14, color: colors.heroMuted },
});
```

2. **Add to navigation** (`verbal-mobile/App.tsx`):
```tsx
import AnalyticsScreen from './screens/AnalyticsScreen';

<Tab.Screen name="Analytics" component={AnalyticsScreen} />
```

3. **Add tab icon**:
```tsx
const icons: Record<string, [string, string]> = {
  // ...
  Analytics: ['analytics', 'analytics-outline'],
};
```

### Pattern 3: Adding Configuration Option

**Example: Add custom hotkey setting**

1. **Update DEFAULT_CONFIG** (`app/config.py`):
```python
DEFAULT_CONFIG = {
    # ...
    "custom_hotkey_enabled": False,
    "custom_hotkey_keycode": 54,  # Right Option
    "custom_hotkey_modifiers": ["cmd"],  # cmd, alt, ctrl, shift
}
```

2. **Update hotkey listener** (`app/hotkey.py`):
```python
class HotkeyListener:
    def __init__(self, config):
        self.config = config
        self.custom_enabled = config.get("custom_hotkey_enabled", False)
        self.keycode = config.get("custom_hotkey_keycode", 54)
    
    def _is_hotkey_pressed(self, event) -> bool:
        if self.custom_enabled:
            return self._check_custom_hotkey(event)
        return self._check_default_hotkey(event)
```

3. **Add UI** (`app/dashboard.py`):
```python
@rumps.clicked("Customize Hotkey")
def customize_hotkey(self, sender):
    # Open dialog to select key
    # Save to config
    # Restart hotkey listener
    pass
```

---

## 📋 Quick Reference

### File Locations

| Component | macOS | Windows | Mobile |
|-----------|-------|---------|--------|
| Entry point | `app/main.py` | `app/win_main.py` | `App.tsx` |
| Recording | `app/recorder.py` | `app/recorder.py` | `lib/audio.ts` |
| Transcription | `app/transcriber.py` | `app/transcriber.py` | `lib/groq.ts` |
| UI | `app/dashboard.py` | `app/win_dashboard.py` | `screens/*.tsx` |
| Config | `app/config.py` | `app/config.py` | `app.json` |
| Sync | `app/sync.py` | `app/sync.py` | `lib/supabase.ts` |

### Log Locations

- **Desktop:** `~/.verbal/logs/app.log`
- **Mobile:** Check via `npx expo start --clear`
- **Supabase:** Dashboard → Logs → Realtime

### Config Locations

- **Desktop:** `~/.verbal/config.json`
- **Mobile:** `verbal-mobile/app.json`, AsyncStorage
- **Environment:** `.env` file in project root

### Build Outputs

- **macOS:** `dist/Verbal.app`
- **Windows:** `dist-windows/Verbal.exe`
- **Mobile:** `dist/` (via EAS Build)

---

## 🎓 Best Practices

### Code Organization
- Keep components small and focused (<300 lines)
- Use logging for all async operations
- Separate concerns: UI, business logic, data access
- Follow existing patterns in the codebase

### Testing
- Test on actual devices (not just simulators)
- Verify API fallback chains work
- Check edge cases: no network, no permissions, empty audio
- Test cross-platform sync thoroughly

### Performance
- Use threading for background tasks
- Cache expensive operations (model loading)
- Minimize API calls (batch where possible)
- Clean up temp files promptly

### Security
- Never log API keys or tokens
- Use environment variables for secrets
- Validate user input before processing
- Handle errors gracefully (don't expose internals)

---

## 🆘 Troubleshooting Checklist

### Before Debugging
- [ ] Check logs: `tail -f ~/.verbal/logs/app.log`
- [ ] Verify API keys are valid
- [ ] Confirm network connectivity
- [ ] Check permissions (Microphone, Accessibility)
- [ ] Restart app completely

### Common Fixes
1. **Hotkey not working:** Reset permissions, check keycode
2. **Transcription slow:** Check API tier limits, switch to local
3. **Sync not updating:** Verify Supabase credentials, check Realtime
4. **Build fails:** Update `.spec` hiddenimports/datas
5. **Paste fails:** Re-enable Accessibility permissions

### When to Ask for Help
- After trying all checklist items
- When error is unclear from logs
- When feature requires architectural changes
- When cross-platform behavior differs significantly

---

**End of Skill Documentation**
