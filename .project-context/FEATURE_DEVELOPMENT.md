# Verbal Feature Development Guide

**Purpose:** Systematic approach to adding new features to Verbal

---

## 📋 Feature Development Process

### Phase 1: Planning

1. **Define the feature scope**
   - What problem does it solve?
   - Which platforms? (Desktop, Mobile, or both)
   - User stories and acceptance criteria

2. **Identify affected components**
   - Use [INDEX.md](./INDEX.md) to locate relevant files
   - Check for existing similar features
   - Plan integration points

3. **Design the implementation**
   - Data model changes (if any)
   - API integrations (if any)
   - UI/UX changes
   - Configuration options

### Phase 2: Implementation

1. **Create new modules** (if needed)
2. **Update configuration**
3. **Integrate into main app**
4. **Add UI components**
5. **Write tests**

### Phase 3: Testing

1. **Unit tests** for new logic
2. **Integration tests** with existing features
3. **Cross-platform testing** (macOS, Windows, iOS, Android)
4. **User acceptance testing**

### Phase 4: Deployment

1. **Update version** in config
2. **Document changes** in release notes
3. **Build and distribute**

---

## 🎨 Feature Templates

### Template 1: New API Integration

**Example:** Adding DeepL translation

#### Step 1: Create Module

```python
# app/deepl_translator.py
"""
DeepL translation integration for Verbal.

Usage:
    translator = DeepLTranslator(api_key="...")
    translated = translator.translate("Hello", "ES")
    print(translated)  # "Hola"
"""

import logging
import httpx
from typing import Optional

logger = logging.getLogger("verbal.deepl")

class DeepLTranslator:
    """DeepL API translation client."""
    
    BASE_URL = "https://api.deepl.com/v2/translate"
    SUPPORTED_LANGUAGES = {
        "EN": "English",
        "ES": "Spanish",
        "FR": "French",
        "DE": "German",
        "IT": "Italian",
        "PT": "Portuguese",
        "NL": "Dutch",
        "JA": "Japanese",
        "ZH": "Chinese",
    }
    
    def __init__(self, api_key: str):
        """Initialize with DeepL API key."""
        self.api_key = api_key
        self.session = httpx.Client(
            base_url=self.BASE_URL,
            headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
            timeout=10.0,
        )
    
    def translate(self, text: str, target_lang: str) -> Optional[str]:
        """
        Translate text to target language.
        
        Args:
            text: Text to translate
            target_lang: Target language code (e.g., "ES", "FR")
        
        Returns:
            Translated text, or None on failure
        """
        try:
            logger.info(f"Translating to {target_lang}: {text[:50]}...")
            
            response = self.session.post(
                "/translate",
                params={
                    "text": text,
                    "target_lang": target_lang.upper(),
                    "formality": "default",
                },
            )
            response.raise_for_status()
            
            result = response.json()
            translated = result["translations"][0]["text"]
            
            logger.info(f"Translation complete: {translated[:50]}...")
            return translated
            
        except httpx.HTTPError as e:
            logger.error(f"DeepL API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return None
    
    def get_supported_languages(self) -> dict:
        """Return dict of supported language codes and names."""
        return self.SUPPORTED_LANGUAGES.copy()
```

#### Step 2: Add Configuration

```python
# app/config.py
DEFAULT_CONFIG = {
    # ... existing config ...
    
    # DeepL translation
    "deepl_api_key": "",
    "translation_target_lang": "EN-US",
    "auto_translate": False,
}
```

#### Step 3: Integrate into Main App

```python
# app/main.py
from app.deepl_translator import DeepLTranslator

class VerbalApp(rumps.App):
    def __init__(self):
        super().__init__("Verbal", icon=ICON_PATH, template=True)
        
        # ... existing initialization ...
        
        # Initialize DeepL translator
        deepl_key = self.config.get("deepl_api_key", "")
        self.translator = DeepLTranslator(deepl_key) if deepl_key else None
        
        # Add translation menu
        if self.translator:
            self.translate_menu = rumps.MenuItem("Translate")
            for lang_code, lang_name in self.translator.get_supported_languages().items():
                item = rumps.MenuItem(
                    f"Translate to {lang_name}",
                    self._translate_to_lang
                )
                item.target_lang = lang_code
                self.translate_menu.add(item)
            self.menu.add(self.translate_menu)
```

#### Step 4: Add UI Controls

```python
# app/dashboard.py
from app.deepl_translator import DeepLTranslator

class DashboardWindow:
    def __init__(self, app: VerbalApp):
        self.app = app
        
        # Add DeepL settings section
        self.deepl_section = self._create_deepl_section()
        
    def _create_deepl_section(self):
        """Create DeepL translation settings UI."""
        section = tk.LabelFrame(self.window, text="Translation")
        
        # API Key input
        tk.Label(section, text="DeepL API Key:").grid(row=0, column=0, sticky="w")
        self.deepl_key_var = tk.StringVar()
        tk.Entry(section, textvariable=self.deepl_key_var, width=40, show="*").grid(
            row=0, column=1, padx=5, pady=5
        )
        
        # Target language
        tk.Label(section, text="Target Language:").grid(row=1, column=0, sticky="w")
        self.target_lang_var = tk.StringVar(value="ES")
        lang_combo = ttk.Combobox(
            section,
            textvariable=self.target_lang_var,
            values=list(DeepLTranslator.SUPPORTED_LANGUAGES.keys()),
        )
        lang_combo.grid(row=1, column=1, padx=5, pady=5)
        
        # Auto-translate checkbox
        self.auto_translate_var = tk.BooleanVar()
        tk.Checkbutton(
            section,
            text="Auto-translate after transcription",
            variable=self.auto_translate_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w")
        
        # Save button
        tk.Button(
            section,
            text="Save Translation Settings",
            command=self._save_deepl_settings,
        ).grid(row=3, column=1, sticky="e", pady=10)
        
        return section
    
    def _save_deepl_settings(self):
        """Save DeepL settings to config."""
        self.app.config["deepl_api_key"] = self.deepl_key_var.get()
        self.app.config["translation_target_lang"] = self.target_lang_var.get()
        self.app.config["auto_translate"] = self.auto_translate_var.get()
        save_config(self.app.config)
        
        # Reinitialize translator
        if self.deepl_key_var.get():
            self.app.translator = DeepLTranslator(self.deepl_key_var.get())
            tk.messagebox.showinfo("Success", "DeepL settings saved!")
        else:
            self.app.translator = None
            tk.messagebox.showinfo("Success", "DeepL disabled")
```

#### Step 5: Auto-Translation Hook

```python
# app/main.py
class VerbalApp(rumps.App):
    def _process_transcription(self, audio):
        # ... existing transcription logic ...
        
        text = transcribe(audio, self.config)
        
        # Auto-translate if enabled
        if self.config.get("auto_translate") and self.translator:
            target_lang = self.config.get("translation_target_lang", "EN-US")
            translated = self.translator.translate(text, target_lang)
            if translated:
                text = translated
                logger.info(f"Auto-translated to {target_lang}")
        
        # ... rest of processing ...
```

---

### Template 2: New Mobile Screen

**Example:** Analytics dashboard

#### Step 1: Create Screen Component

```tsx
// verbal-mobile/screens/AnalyticsScreen.tsx
import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { colors } from '../lib/theme';
import { supabase } from '../lib/supabase';
import { Ionicons } from '@expo/vector-icons';

interface AnalyticsData {
  totalTranscriptions: number;
  totalWords: number;
  todayWords: number;
  weekWords: number;
  topHour: string;
  avgTranscriptionLength: number;
}

export default function AnalyticsScreen() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadAnalytics();
  }, []);

  async function loadAnalytics() {
    try {
      setError(null);
      
      // Fetch all transcriptions for user
      const { data: transcriptions, error } = await supabase
        .from('transcriptions')
        .select('text, created_at')
        .eq('user_id', USER_ID)
        .order('created_at', { ascending: false });

      if (error) throw error;

      // Calculate analytics
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

      const stats = {
        totalTranscriptions: transcriptions.length,
        totalWords: transcriptions.reduce(
          (acc, t) => acc + (t.text?.split(' ').length || 0),
          0
        ),
        todayWords: transcriptions
          .filter((t) => new Date(t.created_at) >= today)
          .reduce((acc, t) => acc + (t.text?.split(' ').length || 0), 0),
        weekWords: transcriptions
          .filter((t) => new Date(t.created_at) >= weekAgo)
          .reduce((acc, t) => acc + (t.text?.split(' ').length || 0), 0),
        topHour: calculateTopHour(transcriptions),
        avgTranscriptionLength:
          transcriptions.length > 0
            ? stats.totalWords / stats.totalTranscriptions
            : 0,
      };

      setData(stats);
    } catch (err: any) {
      setError(err.message || 'Failed to load analytics');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  function calculateTopHour(transcriptions: any[]): string {
    const hourCounts = new Array(24).fill(0);
    transcriptions.forEach((t) => {
      const hour = new Date(t.created_at).getHours();
      hourCounts[hour]++;
    });
    const topHour = hourCounts.indexOf(Math.max(...hourCounts));
    return `${topHour}:00`;
  }

  async function onRefresh() {
    setRefreshing(true);
    await loadAnalytics();
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.accent} />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.center}>
        <Ionicons name="warning" size={48} color={colors.error} />
        <Text style={styles.errorText}>{error}</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      <Text style={styles.title}>Analytics</Text>

      {/* Summary Cards */}
      <View style={styles.cards}>
        <View style={styles.card}>
          <Ionicons name="document-text" size={32} color={colors.accent} />
          <Text style={styles.cardValue}>{data?.totalTranscriptions}</Text>
          <Text style={styles.cardLabel}>Total Transcriptions</Text>
        </View>

        <View style={styles.card}>
          <Ionicons name="text" size={32} color={colors.accent} />
          <Text style={styles.cardValue}>{data?.totalWords.toLocaleString()}</Text>
          <Text style={styles.cardLabel}>Total Words</Text>
        </View>
      </View>

      {/* Today's Activity */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Today</Text>
        <View style={styles.stat}>
          <Text style={styles.statValue}>{data?.todayWords.toLocaleString()}</Text>
          <Text style={styles.statLabel}>Words Today</Text>
        </View>
      </View>

      {/* Weekly Activity */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>This Week</Text>
        <View style={styles.stat}>
          <Text style={styles.statValue}>{data?.weekWords.toLocaleString()}</Text>
          <Text style={styles.statLabel}>Words This Week</Text>
        </View>
      </View>

      {/* Insights */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Insights</Text>
        <View style={styles.insight}>
          <Ionicons name="time" size={24} color={colors.accent} />
          <Text style={styles.insightText}>
            Most productive hour: {data?.topHour}
          </Text>
        </View>
        <View style={styles.insight}>
          <Ionicons name="analytics" size={24} color={colors.accent} />
          <Text style={styles.insightText}>
            Average transcription: {Math.round(data?.avgTranscriptionLength || 0)} words
          </Text>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.heroBg,
    padding: 20,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  title: {
    fontSize: 32,
    fontWeight: '700',
    color: colors.text,
    marginBottom: 24,
  },
  cards: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  card: {
    flex: 1,
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 4,
    alignItems: 'center',
  },
  cardValue: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.accent,
    marginTop: 8,
  },
  cardLabel: {
    fontSize: 12,
    color: colors.heroMuted,
    marginTop: 4,
    textAlign: 'center',
  },
  section: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: colors.text,
    marginBottom: 12,
  },
  stat: {
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 36,
    fontWeight: '700',
    color: colors.text,
  },
  statLabel: {
    fontSize: 14,
    color: colors.heroMuted,
    marginTop: 4,
  },
  insight: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
  },
  insightText: {
    fontSize: 16,
    color: colors.text,
    marginLeft: 12,
    flex: 1,
  },
  errorText: {
    fontSize: 16,
    color: colors.error,
    marginTop: 16,
    textAlign: 'center',
  },
});
```

#### Step 2: Add to Navigation

```tsx
// verbal-mobile/App.tsx
import AnalyticsScreen from './screens/AnalyticsScreen';

export default function App() {
  return (
    <Tab.Navigator ...>
      {/* ... existing screens ... */}
      <Tab.Screen name="Analytics" component={AnalyticsScreen} />
    </Tab.Navigator>
  );
}
```

#### Step 3: Add Tab Icon

```tsx
// verbal-mobile/App.tsx
const icons: Record<string, [string, string]> = {
  Home: ['mic', 'mic-outline'],
  Canvas: ['albums', 'albums-outline'],
  Notes: ['document-text', 'document-text-outline'],
  History: ['time', 'time-outline'],
  Settings: ['settings', 'settings-outline'],
  Analytics: ['analytics', 'analytics-outline'], // Add this
};
```

---

### Template 3: New Configuration Option

**Example:** Add custom sound effects

#### Step 1: Update Config Schema

```python
# app/config.py
DEFAULT_CONFIG = {
    # ... existing config ...
    
    # Sound effects
    "sound_enabled": True,
    "sound_start": "start.aiff",
    "sound_stop": "stop.aiff",
    "sound_done": "done.aiff",
    "sound_volume": 0.7,  # 0.0 to 1.0
    "custom_sound_dir": "",  # Empty = use default sounds
}
```

#### Step 2: Update Sound Module

```python
# app/sounds.py
import os
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger("verbal.sounds")

def _play_sound(filename: str, volume: float = 0.7):
    """Play a sound file with volume control."""
    if not filename:
        return
    
    # Find sound file
    sound_path = None
    
    # Check custom sound directory
    custom_dir = Path.home() / ".verbal" / "sounds"
    if custom_dir.exists():
        custom_path = custom_dir / filename
        if custom_path.exists():
            sound_path = str(custom_path)
            logger.info(f"Using custom sound: {sound_path}")
    
    # Fallback to bundled sounds
    if not sound_path:
        sound_path = _asset_path(f"sounds/{filename}")
        if not os.path.exists(sound_path):
            logger.warning(f"Sound file not found: {sound_path}")
            return
    
    # Play with volume control
    try:
        # macOS: use afplay with volume
        if PLATFORM == "mac":
            subprocess.run([
                "afplay",
                sound_path,
                "-v", str(volume),
            ], check=False)
        # Windows: use winsound
        elif PLATFORM == "win":
            import winsound
            winsound.PlaySound(sound_path, winsound.SND_FILENAME)
    except Exception as e:
        logger.error(f"Failed to play sound: {e}")

def play_start(volume_override=None):
    """Play recording start sound."""
    from app.config import load_config
    config = load_config()
    
    if not config.get("sound_enabled", True):
        return
    
    volume = volume_override or config.get("sound_volume", 0.7)
    sound_file = config.get("sound_start", "start.aiff")
    _play_sound(sound_file, volume)

def play_stop(volume_override=None):
    """Play recording stop sound."""
    from app.config import load_config
    config = load_config()
    
    if not config.get("sound_enabled", True):
        return
    
    volume = volume_override or config.get("sound_volume", 0.7)
    sound_file = config.get("sound_stop", "stop.aiff")
    _play_sound(sound_file, volume)

def play_done(volume_override=None):
    """Play transcription complete sound."""
    from app.config import load_config
    config = load_config()
    
    if not config.get("sound_enabled", True):
        return
    
    volume = volume_override or config.get("sound_volume", 0.7)
    sound_file = config.get("sound_done", "done.aiff")
    _play_sound(sound_file, volume)
```

#### Step 3: Add UI Controls

```python
# app/dashboard.py
class DashboardWindow:
    def _create_sound_section(self):
        """Create sound effects settings UI."""
        section = tk.LabelFrame(self.window, text="Sound Effects")
        
        # Enable/disable
        self.sound_enabled_var = tk.BooleanVar(
            value=self.app.config.get("sound_enabled", True)
        )
        tk.Checkbutton(
            section,
            text="Enable sound effects",
            variable=self.sound_enabled_var,
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        
        # Volume slider
        tk.Label(section, text="Volume:").grid(row=1, column=0, sticky="w")
        self.volume_var = tk.DoubleVar(
            value=self.app.config.get("sound_volume", 0.7)
        )
        volume_slider = tk.Scale(
            section,
            variable=self.volume_var,
            from_=0.0,
            to=1.0,
            resolution=0.1,
            orient="horizontal",
            length=200,
        )
        volume_slider.grid(row=1, column=1, sticky="w", padx=5)
        
        # Sound file selectors
        for i, sound_type in enumerate(["start", "stop", "done"]):
            row = i + 2
            tk.Label(section, text=f"{sound_type.title()} Sound:").grid(
                row=row, column=0, sticky="w"
            )
            
            sound_var = tk.StringVar(
                value=self.app.config.get(f"sound_{sound_type}", f"{sound_type}.aiff")
            )
            sound_entry = tk.Entry(section, textvariable=sound_var, width=20)
            sound_entry.grid(row=row, column=1, sticky="w", padx=5)
            
            # Test button
            def test_sound(sound=sound_type, var=sound_var):
                from app.sounds import _play_sound
                _play_sound(var.get(), self.volume_var.get())
            
            tk.Button(
                section,
                text="Test",
                command=test_sound,
            ).grid(row=row, column=2, padx=5)
        
        # Save button
        def save_sound_settings():
            self.app.config["sound_enabled"] = self.sound_enabled_var.get()
            self.app.config["sound_volume"] = self.volume_var.get()
            save_config(self.app.config)
            tk.messagebox.showinfo("Success", "Sound settings saved!")
        
        tk.Button(
            section,
            text="Save Sound Settings",
            command=save_sound_settings,
        ).grid(row=5, column=1, sticky="e", pady=10)
        
        return section
```

---

### Template 4: New Sync Feature

**Example:** Add transcription sharing to specific device

#### Step 1: Extend Database Schema

```sql
-- Add target_device_id column to transcriptions table
ALTER TABLE transcriptions 
ADD COLUMN target_device_id text;

-- Add index for targeted queries
CREATE INDEX idx_transcriptions_target 
ON transcriptions(target_device_id) 
WHERE target_device_id IS NOT NULL;
```

#### Step 2: Update Sync Client

```python
# app/sync.py
class SyncClient:
    def push(self, text: str, target_device_id: str | None = None):
        """
        Push transcription to sync server.
        
        Args:
            text: Transcription text
            target_device_id: If set, only this device receives it.
                             If None, broadcast to all devices.
        """
        logger.info(f"Sync push request: target={target_device_id}")
        threading.Thread(
            target=self._push_rest,
            args=(text, target_device_id),
            daemon=True,
        ).start()
    
    def _push_rest(self, text: str, target_device_id: str | None):
        try:
            payload = {
                "user_id": self.user_id,
                "device_id": self.device_id,
                "device_name": self.device_name,
                "text": text,
            }
            
            # Only include target_device_id if specified
            if target_device_id:
                payload["target_device_id"] = target_device_id
                logger.debug(f"Targeting specific device: {target_device_id}")
            else:
                logger.debug("Broadcasting to all devices")
            
            resp = httpx.post(
                f"{REST_URL}/transcriptions",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=5,
            )
            resp.raise_for_status()
            logger.info(f"Sync push successful: {len(text)} chars")
            
        except Exception as e:
            logger.error(f"Sync push failed: {e}")
```

#### Step 3: Add UI for Device Selection

```python
# app/dashboard.py
class DashboardWindow:
    def _create_sync_section(self):
        """Create sync settings UI with device targeting."""
        section = tk.LabelFrame(self.window, text="Device Sync")
        
        # Sync toggle
        self.sync_enabled_var = tk.BooleanVar(
            value=self.app.config.get("sync_enabled", False)
        )
        tk.Checkbutton(
            section,
            text="Enable cross-device sync",
            variable=self.sync_enabled_var,
            command=self._toggle_sync,
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        
        # Device list
        tk.Label(section, text="Share to:").grid(row=1, column=0, sticky="w")
        
        self.target_device_var = tk.StringVar(value="all")
        device_combo = ttk.Combobox(
            section,
            textvariable=self.target_device_var,
            values=["all"],
            state="readonly",
            width=20,
        )
        device_combo.grid(row=1, column=1, sticky="w", padx=5)
        
        # Populate with registered devices
        self._load_registered_devices(device_combo)
        
        # Help text
        tk.Label(
            section,
            text="Select 'all' to broadcast, or choose a specific device",
            font=("Helvetica", 9),
            fg="gray",
        ).grid(row=2, column=0, columnspan=2, sticky="w")
        
        return section
    
    def _load_registered_devices(self, combo):
        """Load registered devices from Supabase."""
        try:
            from app.sync import SyncClient, SUPABASE_KEY, SUPABASE_URL
            import httpx
            
            user_id = self.app.config.get("sync_user_id", "")
            if not user_id:
                return
            
            resp = httpx.get(
                f"{SUPABASE_URL}/rest/v1/devices",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                },
                params={"user_id": "eq." + user_id},
                timeout=5,
            )
            
            if resp.status_code == 200:
                devices = resp.json()
                device_names = [d["device_name"] for d in devices]
                combo["values"] = ["all"] + device_names
        except Exception as e:
            logger.error(f"Failed to load devices: {e}")
```

---

## 🧪 Testing Guidelines

### Unit Tests

```python
# tests/test_transcriber.py
import pytest
import numpy as np
from app.transcriber import transcribe

def test_transcribe_silent_audio():
    """Test that silent audio returns empty string."""
    audio = np.zeros(48000, dtype=np.float32)
    config = {"groq_api_keys": [], "gemini_api_keys": []}
    
    result = transcribe(audio, config)
    assert result == ""

def test_transcribe_with_mock_groq(monkeypatch):
    """Test transcription with mocked Groq API."""
    def mock_groq(*args, **kwargs):
        return "Mock transcription"
    
    monkeypatch.setattr("app.transcriber._transcribe_groq", mock_groq)
    
    audio = np.random.randn(48000).astype(np.float32)
    config = {"groq_api_keys": ["test_key"]}
    
    result = transcribe(audio, config)
    assert result == "Mock transcription"
```

### Integration Tests

```python
# tests/test_integration.py
import pytest
from app.main import VerbalApp

def test_full_workflow():
    """Test complete transcription workflow."""
    app = VerbalApp()
    
    # Simulate recording
    app._start_recording()
    # ... wait for audio ...
    app._stop_recording()
    
    # Verify transcription appeared
    assert app._total_transcriptions > 0
    assert len(app.config["history"]) > 0
```

### Manual Testing Checklist

For each feature, test:

- [ ] **Happy path** - Normal usage works
- [ ] **Edge cases** - Empty input, network errors, etc.
- [ ] **Error handling** - Graceful failures
- [ ] **Cross-platform** - macOS, Windows, iOS, Android
- [ ] **Performance** - No significant slowdown
- [ ] **Backwards compatibility** - Existing features still work
- [ ] **Configuration** - Settings save/load correctly
- [ ] **Documentation** - Updated README and help text

---

## 📝 Code Review Checklist

Before merging any feature:

- [ ] Code follows existing patterns
- [ ] Proper logging added
- [ ] Error handling implemented
- [ ] Configuration options documented
- [ ] UI consistent with existing design
- [ ] Tests written and passing
- [ ] No sensitive data in logs
- [ ] Performance impact acceptable
- [ ] Cross-platform compatibility verified
- [ ] Release notes updated

---

## 🎓 Best Practices

### Code Organization
- Keep modules focused (<500 lines)
- Use type hints for function signatures
- Add docstrings to all public APIs
- Follow existing naming conventions

### Logging
- Use `logging.getLogger("verbal.module")`
- Log at appropriate levels: INFO, WARNING, ERROR
- Include context in log messages
- Never log sensitive data (API keys, tokens)

### Error Handling
- Catch specific exceptions, not bare `Exception`
- Log errors with full stack traces
- Provide user-friendly error messages
- Implement fallback mechanisms

### Performance
- Use threading for I/O operations
- Cache expensive operations
- Clean up resources (temp files, connections)
- Profile before optimizing

### Security
- Validate all user input
- Sanitize data before logging
- Use environment variables for secrets
- Implement rate limiting for APIs

---

**End of Feature Development Guide**
