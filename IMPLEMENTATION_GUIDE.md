# Flume — Implementation Guide (React Native + Expo)

This guide walks you from "I have a fresh Expo app" or "I have an existing app" to a working Flume UI with your backend wired in. The UI itself is in `flume-ui/` and is design-complete — your job is wiring data and platform APIs into the **hooks**.

> If you're handing this to Claude Code / Cursor, the strict rule is: **never edit files in `flume-ui/screens/`, `flume-ui/components/`, or `flume-ui/theme/` to wire backend logic.** All wiring goes in `flume-ui/hooks/*.ts`. That keeps the design isolated from infrastructure changes.

---

## Table of contents

1. [How the pieces fit together](#1-how-the-pieces-fit-together)
2. [Installation](#2-installation)
3. [Mount the navigator](#3-mount-the-navigator)
4. [Wire each hook](#4-wire-each-hook)
   - 4.1 [Auth (Google sign-in)](#41-useauth-google-sign-in)
   - 4.2 [Recorder (mic + transcription)](#42-userecorder-mic--transcription)
   - 4.3 [Devices (pairing, default target)](#43-usedevices-pairing--default-target)
   - 4.4 [History (transcription store)](#44-usehistory)
   - 4.5 [Notes (CRUD)](#45-usenotes)
   - 4.6 [Canvas (push to clipboard)](#46-usecanvas-push-to-paired-clipboard)
5. [Where to add backend code (and where NOT to)](#5-where-to-add-backend-code)
6. [Customizing the design](#6-customizing-the-design)
7. [The "5-tab" navigation explained](#7-the-5-tab-navigation-explained)
8. [Light theme](#8-light-theme-not-shipped-yet)
9. [Common questions](#9-common-questions)
10. [File map](#10-file-map)

---

## 1. How the pieces fit together

```
┌──────────────────────────────────────────────────────────────┐
│  App.tsx                                                     │
│    └── SafeAreaProvider                                      │
│         └── RootNavigator         ← from flume-ui/navigation │
│              ├── Welcome  ─┐                                 │
│              ├── Onboarding┤ (Auth gate uses useAuth)        │
│              └── Main      ─┘                                │
│                   └── Tabs (5)                               │
│                        ├── Record    → HomeScreen (3c)       │
│                        ├── Notes     → Notes stack (4a/4b)   │
│                        ├── Canvas    → CanvasScreen (4c)     │
│                        ├── History   → History stack (3f/3g) │
│                        └── Settings  → Settings/Devices/Pair │
│                                                              │
│              + modals: Recording (3d), Confirmation (3e)     │
└──────────────────────────────────────────────────────────────┘
                          ▲
                          │ reads/writes via hooks
                          │
┌─────────────────────────┴────────────────────────────────────┐
│  flume-ui/hooks/*.ts      ← THE ONLY FILES YOU EDIT FOR WIRING│
│   useAuth      → your auth backend                           │
│   useRecorder  → expo-av + your transcription stream         │
│   useDevices   → your pairing + presence service             │
│   useHistory   → your transcription store                    │
│   useNotes     → your notes store                            │
│   useCanvas    → your clipboard-sync service                 │
└──────────────────────────────────────────────────────────────┘
```

**Rule of thumb:** if a change is about "what data shows up", it's a hook change. If it's about "how it looks", it's a component/theme change. They never mix.

---

## 2. Installation

### 2.1 Drop the folder in

```bash
# from your verbal-mobile/ repo root:
cp -r path/to/flume-ui src/flume-ui
```

### 2.2 Install dependencies

```bash
# core navigation
npx expo install \
  @react-navigation/native \
  @react-navigation/native-stack \
  @react-navigation/bottom-tabs \
  react-native-screens \
  react-native-safe-area-context

# fonts
npx expo install \
  expo-font \
  @expo-google-fonts/geist \
  @expo-google-fonts/jetbrains-mono

# native bits the screens use
npx expo install \
  expo-status-bar \
  expo-haptics \
  expo-av \
  expo-clipboard \
  expo-image-picker \
  expo-camera \
  expo-linear-gradient \
  react-native-reanimated \
  react-native-svg \
  @expo/vector-icons
```

### 2.3 Reanimated plugin

Reanimated needs its Babel plugin. In `babel.config.js`:

```js
module.exports = function(api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: ['react-native-reanimated/plugin'], // ← MUST be last
  };
};
```

### 2.4 Permissions

In `app.json`:

```json
{
  "expo": {
    "ios": {
      "infoPlist": {
        "NSMicrophoneUsageDescription": "Flume uses your mic to transcribe what you say.",
        "NSCameraUsageDescription": "Flume needs your camera to scan a pairing code on your computer.",
        "NSPhotoLibraryUsageDescription": "Flume needs photo access so you can send images to your computer."
      }
    },
    "android": {
      "permissions": ["RECORD_AUDIO", "CAMERA", "READ_MEDIA_IMAGES"]
    }
  }
}
```

---

## 3. Mount the navigator

Replace your `App.tsx`:

```tsx
import 'react-native-reanimated';
import { useFonts } from 'expo-font';
import {
  Geist_400Regular, Geist_500Medium, Geist_600SemiBold, Geist_700Bold,
} from '@expo-google-fonts/geist';
import {
  JetBrainsMono_500Medium, JetBrainsMono_600SemiBold,
} from '@expo-google-fonts/jetbrains-mono';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { RootNavigator } from './src/flume-ui';

export default function App() {
  const [fontsLoaded] = useFonts({
    Geist_400Regular, Geist_500Medium, Geist_600SemiBold, Geist_700Bold,
    JetBrainsMono_500Medium, JetBrainsMono_600SemiBold,
  });
  if (!fontsLoaded) return null;
  return (
    <SafeAreaProvider>
      <RootNavigator />
    </SafeAreaProvider>
  );
}
```

**At this point you should run the app and see the UI working with mock data.** Sign-in is bypassed (a mock user), recorder ticks duration but doesn't capture audio, devices come pre-paired, etc. Visual review the screens at this stage before any wiring.

---

## 4. Wire each hook

Each hook lives in `flume-ui/hooks/`. Open the file, search for `// TODO:` markers, and replace with your real code. Below is the recipe per hook.

### 4.1 `useAuth` — Google sign-in

Replace `signInWithGoogle` with `expo-auth-session`:

```ts
import * as Google from 'expo-auth-session/providers/google';
import * as SecureStore from 'expo-secure-store';

const [request, response, promptAsync] = Google.useAuthRequest({
  iosClientId:     'YOUR_IOS_CLIENT_ID.apps.googleusercontent.com',
  androidClientId: 'YOUR_ANDROID_CLIENT_ID.apps.googleusercontent.com',
  webClientId:     'YOUR_WEB_CLIENT_ID.apps.googleusercontent.com',
});

const signInWithGoogle = useCallback(async () => {
  const result = await promptAsync();
  if (result.type !== 'success') return;
  // Send result.authentication.idToken to your backend to exchange for a session
  const session = await yourBackend.post('/auth/google', {
    idToken: result.authentication!.idToken,
  });
  await SecureStore.setItemAsync('flumeSession', session.token);
  setUser(session.user);
}, [promptAsync]);
```

On mount, restore the session:

```ts
useEffect(() => {
  (async () => {
    const token = await SecureStore.getItemAsync('flumeSession');
    if (!token) { setUser(null); return; }
    const me = await yourBackend.get('/me', { token });
    setUser(me);
  })();
}, []);
```

Also start with `useState<User | null>(null)` (delete the mock).

### 4.2 `useRecorder` — mic + transcription

Use `expo-av` for capture. Choose ONE of two strategies for transcription:

**A) Cloud streaming (recommended).** Open a WebSocket to your backend the moment recording starts. Stream PCM chunks. Backend forwards to Deepgram / AssemblyAI / Whisper / your own model. Server emits partial transcripts; you setState `partialText`.

**B) Local capture, upload at stop.** Simpler. Record to file, then upload `.m4a` on stop, await final text.

Below is sketch for (A):

```ts
import { Audio } from 'expo-av';

const recRef = useRef<Audio.Recording | null>(null);
const wsRef  = useRef<WebSocket | null>(null);

const start = useCallback(async () => {
  const { status } = await Audio.requestPermissionsAsync();
  if (status !== 'granted') throw new Error('mic denied');

  await Audio.setAudioModeAsync({
    allowsRecordingIOS: true,
    playsInSilentModeIOS: true,
  });

  // open transcription stream
  wsRef.current = new WebSocket('wss://your-api.flume.app/transcribe');
  wsRef.current.onmessage = (evt) => {
    const { partial } = JSON.parse(evt.data);
    setPartialText(prev => prev + ' ' + partial);
  };

  // start recording
  const rec = new Audio.Recording();
  await rec.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
  await rec.startAsync();
  recRef.current = rec;

  // (advanced) tap audio buffers and forward to ws. expo-av doesn't expose
  // raw chunks directly — either use a dev-build with a custom audio module,
  // or fall back to strategy (B) for now.

  startedAtRef.current = Date.now();
  setStatus('recording');
}, []);

const stop = useCallback(async () => {
  const rec = recRef.current;
  if (!rec) return null;
  await rec.stopAndUnloadAsync();
  const uri = rec.getURI()!;
  wsRef.current?.close();

  // if you went with strategy (B): upload and await the final transcript
  const form = new FormData();
  form.append('audio', { uri, name: 'a.m4a', type: 'audio/m4a' } as any);
  const { text } = await yourBackend.uploadForm('/transcribe', form);

  return { uri, durationMs, text };
}, [durationMs]);
```

> **NoteEditorScreen also uses `useRecorder`** for in-note dictation. Same API — no per-screen changes needed.

### 4.3 `useDevices` — pairing + default target

Replace the `MOCK` array with a real fetch on mount, and call your sync service on actions:

```ts
useEffect(() => {
  (async () => {
    const devices = await yourBackend.get('/devices');
    setDevices(devices);
    setTarget(devices.find(d => d.isDefault) ?? null);
  })();
}, []);

const makeDefault = async (id: string) => {
  await yourBackend.post(`/devices/${id}/default`);
  setDevices(prev => prev.map(d => ({ ...d, isDefault: d.id === id })));
  setTarget(devices.find(d => d.id === id) ?? null);
};

const pair = async (payload: string) => {
  const d = await yourBackend.post('/devices/pair', { payload });
  setDevices(prev => [...prev, d]);
};
```

For online/offline presence, open a WebSocket and patch device entries as they go online/offline. **Don't poll.**

### 4.4 `useHistory`

Use your local store (SQLite via `expo-sqlite`, or WatermelonDB) for offline-first; sync up to your backend. Pseudocode:

```ts
const [items, setItems] = useState<HistoryItem[]>([]);

useEffect(() => {
  (async () => {
    const local = await db.history.list();
    setItems(local);
    // best-effort backfill from server
    const remote = await yourBackend.get('/history?since=' + lastSyncedAt);
    await db.history.upsertMany(remote);
    setItems(await db.history.list());
  })();
}, []);

const add = async (item: HistoryItem) => {
  await db.history.insert(item);
  yourBackend.post('/history', item).catch(() => {/* retry queue */});
  setItems(prev => [item, ...prev]);
};
```

The `dayLabel`, `timeOfDay`, etc. fields are pre-computed in this hook. Use `date-fns` to format consistently:

```ts
import { format, isToday, isYesterday, differenceInDays } from 'date-fns';

function dayLabelFor(d: Date) {
  if (isToday(d)) return 'Today';
  if (isYesterday(d)) return 'Yesterday';
  if (differenceInDays(new Date(), d) < 7) return format(d, 'EEEE');
  return format(d, 'MMM d');
}
```

### 4.5 `useNotes`

Same pattern as history. Add a debounce inside `updateNote` to coalesce rapid edits:

```ts
import debounce from 'lodash.debounce';

const persist = useMemo(() => debounce(async (note: Note) => {
  await db.notes.upsert(note);
  yourBackend.put(`/notes/${note.id}`, note).catch(() => {/* retry */});
}, 500), []);

const updateNote = (id: string, patch: Partial<Note>) => {
  setNotes(prev => {
    const next = prev.map(n => n.id === id ? { ...n, ...patch, updatedAt: Date.now() } : n);
    const updated = next.find(n => n.id === id);
    if (updated) persist(updated);
    return next;
  });
};
```

Mark a note as `isVoice: true` when it was created/extended via the dictate dock.

### 4.6 `useCanvas` — push to paired clipboard

This is the feature unique to Flume. Each canvas item, when "saved", needs to land in the paired computer's clipboard. Architecture:

```
[phone]                           [your backend]                       [computer]
useCanvas.save(itemId) ───POST──▶ /devices/:deviceId/clipboard ──WS──▶ Flume desktop app
                                                                       └─ writes via NSPasteboard / SetClipboardData
```

Hook side:

```ts
const save = useCallback(async (id: string) => {
  const item = items.find(i => i.id === id);
  if (!item || !target) return;

  let payload: { type: string; value: any };
  if (item.kind === 'text')  payload = { type: 'text/plain',          value: item.text };
  if (item.kind === 'link')  payload = { type: 'text/uri-list',       value: item.url  };
  if (item.kind === 'image') {
    // upload first, then send a signed URL OR the bytes
    const { url } = await yourBackend.upload(item.uri);
    payload = { type: 'image/url', value: url };
  }

  await yourBackend.post(`/devices/${target.id}/clipboard`, payload);

  setItems(prev => prev.map(i => i.id === id
    ? { ...i, state: 'sent', sentAt: nowHHmm() }
    : i));
}, [items, target]);
```

`addLink` should default-fill from system clipboard:

```ts
import * as Clipboard from 'expo-clipboard';

const addLink = async () => {
  const text = await Clipboard.getStringAsync();
  const url = /^https?:\/\//.test(text) ? text : '';
  // open your input modal / sheet pre-filled with `url`, then push as draft
};
```

`addPhoto` uses image picker:

```ts
import * as ImagePicker from 'expo-image-picker';

const addPhoto = async () => {
  const res = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ImagePicker.MediaTypeOptions.Images,
    quality: 0.8,
  });
  if (res.canceled) return;
  const asset = res.assets[0];
  setItems(prev => [{
    id: `c_${Date.now()}`, kind: 'image', state: 'draft',
    uri: asset.uri, filename: asset.fileName ?? 'photo.jpg',
    sizeLabel: humanFileSize(asset.fileSize),
    dimensions: `${asset.width}×${asset.height}`,
  }, ...prev]);
};
```

---

## 5. Where to add backend code

| You're adding...                                | Edit file                            |
|-------------------------------------------------|--------------------------------------|
| API calls, fetches, mutations                   | `flume-ui/hooks/*.ts`                |
| Real-time / WebSocket subscriptions             | `flume-ui/hooks/*.ts`                |
| Persistent storage (SQLite, SecureStore)        | `flume-ui/hooks/*.ts`                |
| Permissions prompts                             | `flume-ui/hooks/*.ts` (inside `start`) |
| Navigation between screens                      | `flume-ui/navigation/RootNavigator.tsx` |
| New screens                                     | `flume-ui/screens/`                  |
| New design tokens                               | `flume-ui/theme/*.ts`                |
| New components                                  | `flume-ui/components/`               |

**Forbidden mixes:**
- ❌ Don't `fetch()` inside a screen file.
- ❌ Don't import `expo-av` in a component file.
- ❌ Don't import an icon library inside a hook.
- ❌ Don't add colors as string literals in screens — go through `theme/colors.ts`.

---

## 6. Customizing the design

The whole visual system is **5 files in `flume-ui/theme/`**. Changing them propagates everywhere:

- `colors.ts` — switch the orange to a different brand color: change `primary`.
- `typography.ts` — switch fonts: change `fonts.*` and update the `useFonts` block in `App.tsx`.
- `spacing.ts` / `radius.ts` — tweak rhythm and softness.
- `shadow.ts` / `motion.ts` — feel of elevation and animation.

Per-screen tweaks live in the screen file itself, all in inline `StyleSheet.create` so they stay easy to grep.

---

## 7. The 5-tab navigation explained

| Tab        | Stack | Screens                                  |
|------------|-------|------------------------------------------|
| **Record** | none  | `HomeScreen` (3c) — modal Recording (3d) / Confirmation (3e) from root |
| **Notes**  | `NotesStack`    | `NotesListScreen` (4a) → `NoteEditorScreen` (4b) |
| **Canvas** | none  | `CanvasScreen` (4c)                      |
| **History**| `HistoryStack`  | `HistoryListScreen` (3f) → `HistoryDetailScreen` (3g) |
| **Settings** | `SettingsStack` | Settings placeholder → `DevicesScreen` (3i) → modal `PairDeviceScreen` (3h) |

**Recording is a root-level modal**, not inside the Record tab — pressing the mic anywhere in the app (e.g. from the Home tab) opens the same Recording screen on top.

**The Notes editor's own mic** uses the same `useRecorder` hook but doesn't open the modal; it transcribes inline into the note body via `partialText`.

---

## 8. Light theme (not shipped yet)

The design is dark-first. When you build the light theme:

1. Add `flume-ui/theme/colors.light.ts` with the same shape.
2. Make `flume-ui/theme/colors.ts` export a `useColors()` hook that picks between dark/light based on `Appearance.getColorScheme()` (or a user setting).
3. Migrate every `import { colors } from '../theme'` to `const colors = useColors()`.

Do NOT try to do this with `react-native`'s built-in `useColorScheme` alone — the colors object needs to flip atomically, not key-by-key.

---

## 9. Common questions

**"Where does the brand color come from?"**
`theme/colors.ts → primary = '#E0552C'`. Lifted from the orange in your logo.

**"The visualizer isn't moving."**
You probably forgot `react-native-reanimated/plugin` in `babel.config.js`, OR you didn't import `'react-native-reanimated'` somewhere top-level (App.tsx).

**"Mic press does nothing in dev."**
Either permissions aren't granted (run on a device, not simulator, for mic) or the hook is still on the mock body that doesn't actually start `expo-av`. Wire `useRecorder` per §4.2.

**"The Google button does nothing."**
You haven't filled in client IDs in `useAuth`. The stub returns without prompting.

**"How do I add a tab?"**
In `flume-ui/navigation/RootNavigator.tsx`, the `TabsNavigator` function has all 5 tabs. Add a `<Tabs.Screen>` entry between the others. Don't forget to add the route to `TabsParamList` in `navigation/types.ts`.

**"Can I use NativeWind / styled-components instead?"**
You can, but you'll rewrite every component. The current setup deliberately avoids style libraries to keep "what you see is in this one file" predictable for handoff.

**"The font isn't loading."**
You forgot to add the family name to `useFonts({ ... })` in `App.tsx`. The names must EXACTLY match `flume-ui/theme/typography.ts` (e.g. `Geist_600SemiBold`).

---

## 10. File map

```
verbal-mobile/
├── App.tsx                                     ← mount RootNavigator here
├── babel.config.js                             ← add reanimated plugin
├── app.json                                    ← add permissions
└── src/
    └── flume-ui/
        ├── README.md
        ├── index.ts                            ← barrel
        ├── theme/
        │   ├── index.ts
        │   ├── colors.ts                       ← all colors
        │   ├── typography.ts                   ← all type variants
        │   ├── spacing.ts                      ← space + radius scales
        │   ├── shadow.ts                       ← mic/toast/fab shadows
        │   └── motion.ts                       ← animation timing + stagger
        ├── components/
        │   ├── index.ts
        │   ├── Text.tsx
        │   ├── Button.tsx
        │   ├── Chip.tsx
        │   ├── Card.tsx
        │   ├── ListRow.tsx
        │   ├── IconButton.tsx
        │   ├── MicButton.tsx                   ← idle rings + recording shadow
        │   ├── Visualizer.tsx                  ← 10-bar Reanimated animation
        │   ├── PulseRing.tsx
        │   ├── PageDots.tsx
        │   ├── GoogleG.tsx
        │   ├── SuccessBadge.tsx
        │   └── LogoMark.tsx
        ├── screens/
        │   ├── index.ts
        │   ├── WelcomeScreen.tsx               ← 3a
        │   ├── OnboardingScreen.tsx            ← 3b (×3 internal steps)
        │   ├── HomeScreen.tsx                  ← 3c
        │   ├── RecordingScreen.tsx             ← 3d (modal)
        │   ├── ConfirmationScreen.tsx          ← 3e (modal, auto-dismiss)
        │   ├── HistoryListScreen.tsx           ← 3f
        │   ├── HistoryDetailScreen.tsx         ← 3g
        │   ├── PairDeviceScreen.tsx            ← 3h
        │   ├── DevicesScreen.tsx               ← 3i
        │   ├── NotesListScreen.tsx             ← 4a
        │   ├── NoteEditorScreen.tsx            ← 4b
        │   └── CanvasScreen.tsx                ← 4c
        ├── navigation/
        │   ├── index.ts
        │   ├── RootNavigator.tsx               ← root + tabs + sub-stacks
        │   └── types.ts                        ← param lists
        ├── hooks/
        │   ├── index.ts
        │   ├── useAuth.ts                      ← TODO: Google sign-in
        │   ├── useRecorder.ts                  ← TODO: expo-av + transcription
        │   ├── useDevices.ts                   ← TODO: pairing + presence
        │   ├── useHistory.ts                   ← TODO: store
        │   ├── useNotes.ts                     ← TODO: store
        │   └── useCanvas.ts                    ← TODO: clipboard sync
        └── assets/
            └── flume-mark.png                  ← logo (dark bg)
```

---

## 11. Order of work (recommended)

1. **Day 1** — drop in, install deps, run, see UI work end-to-end with mock data. Visual review against `Flume Wireframes.html` (3a–3i, 4a–4c).
2. **Day 2** — wire `useAuth` (real Google sign-in lands you on Home).
3. **Day 3** — wire `useRecorder` end-to-end (mic permission, capture, upload, transcription). Test on a device.
4. **Day 4** — wire `useDevices` (real list from your backend; default target persisted).
5. **Day 5** — wire `useHistory` (persist transcripts; show them in 3f/3g).
6. **Day 6** — wire `useNotes` (persistence + in-editor dictation).
7. **Day 7** — wire `useCanvas` (clipboard sync — the unique feature).
8. **Day 8** — design + ship Settings screens (audio, hotkeys, account, privacy).
9. **Day 9** — light theme + onboarding polish.
10. **Ship.**

Every step is one hook. Resist the urge to refactor components or theme along the way — the design is settled.
