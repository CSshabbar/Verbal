# flume-ui

The Flume UI module. Drop this whole folder into your Expo app at `src/flume-ui/` and you have all 12 screens with theme, components, navigation, and hooks.

```
flume-ui/
├── theme/             ← design tokens (colors, type, spacing, radius, shadow, motion)
├── components/        ← Text, Button, Chip, Card, MicButton, Visualizer, etc.
├── screens/           ← all 12 screens
├── navigation/        ← root stack + bottom tabs + sub-stacks
├── hooks/             ← useAuth, useRecorder, useDevices, useHistory, useNotes, useCanvas
└── assets/
    └── flume-mark.png ← logo
```

## Usage

In your app's `App.tsx`:

```tsx
import { useFonts } from 'expo-font';
import { Geist_400Regular, Geist_500Medium, Geist_600SemiBold, Geist_700Bold } from '@expo-google-fonts/geist';
import { JetBrainsMono_500Medium, JetBrainsMono_600SemiBold } from '@expo-google-fonts/jetbrains-mono';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { RootNavigator } from './src/flume-ui';

export default function App() {
  const [fontsLoaded] = useFonts({
    Geist_400Regular,
    Geist_500Medium,
    Geist_600SemiBold,
    Geist_700Bold,
    JetBrainsMono_500Medium,
    JetBrainsMono_600SemiBold,
  });
  if (!fontsLoaded) return null;
  return (
    <SafeAreaProvider>
      <RootNavigator />
    </SafeAreaProvider>
  );
}
```

See `IMPLEMENTATION_GUIDE.md` (one folder up) for the full step-by-step.

## Wiring your backend

All backend touch points live in `hooks/`. Each hook has `// TODO:` markers showing where to drop your API calls. The screens never reach the network directly — replace the hook bodies and the UI is done.

| Hook            | What to wire                                                       |
| --------------- | ------------------------------------------------------------------ |
| `useAuth`       | `expo-auth-session` Google provider → your `/exchange` endpoint    |
| `useRecorder`   | `expo-av` recording + WS/SSE to your transcription service         |
| `useDevices`    | Your device pairing + presence service                             |
| `useHistory`    | Your transcription store (SQLite or backend)                       |
| `useNotes`      | Your notes store                                                   |
| `useCanvas`     | Your sync service that pushes payloads to a paired device's clipboard |

## Conventions

- **Inline styles or `StyleSheet.create`** — no Tailwind, no styled-components.
- **All sizes from `theme/spacing.ts` and `theme/radius.ts`**. Don't hardcode.
- **All colors from `theme/colors.ts`**. Don't hardcode.
- **All text through `<Text variant="...">`**. Don't use raw `<RNText>`.
- **Animations via Reanimated shared values**, never state-driven.
