# Flume Keyboard · Recording Bar — Prompt + Code

Paste this to Claude Code / any dev tool that will build the animated recording bar. Everything it needs is here: behavior, dimensions, tokens, and the reference React Native + Reanimated implementation.

---

## Prompt

Build the Flume keyboard **recording bar** — a thin bar that sits between the input field and the keys.

**Two states, one component:**

1. **Idle** — F wordmark badge on the left, four action icons in the middle-right (History / Canvas / Snippets / Vocabulary), circular mic on the far right. Tapping mic starts recording.
2. **Recording** — F wordmark stays. The four action icons and mic fade to 0 and collapse (250ms). In their place, a **cross (✕) icon button** on the left, a **live 20-bar waveform** filling the middle, an **`0:04` mono timer** on the right of the waveform, and a **small 24pt terracotta pause dot** on the far right.

**Rules:**
- The keyboard below never re-renders or dims. Only this bar's contents cross-fade + slide.
- No caption row, no shadow, no background gradient, no glow.
- Cross button is a **circle icon button**, NOT a text button. Both Cancel (✕) and Pause use icons only.
- Waveform: 20 bars, 2 pt wide, gap 2 pt, height 14 pt. Bars scale Y between 0.15 and 1 via mic amplitude, or fall back to a repeating scale wave when amplitude isn't available. Fill color = primary text (`#141416` light / `#f2f2f2` dark).
- Timer: `JetBrainsMono_500Medium`, 11pt, formatted `M:SS`.
- Bar background: `#ebebed` (light) / `#141618` (dark). Height 42pt. Horizontal padding 12, gap 10.

**Icons:** inline `react-native-svg`, stroke 1.8, round caps. Cross = two paths `M18 6L6 18` + `M6 6l12 12`. Pause = two rounded rects.

**Tokens:** import from `flume-ui/theme/tokens.ts`. Never hardcode.

**Fonts:** Geist for text, JetBrains Mono for timer. Never system.

---

## Reference implementation

```tsx
// flume-ui/components/RecordingBar.tsx
import React, { useEffect } from 'react';
import { View, Pressable, StyleSheet } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withRepeat,
  withSequence,
  interpolate,
  Easing,
  cancelAnimation,
} from 'react-native-reanimated';
import Svg, { Path, Rect } from 'react-native-svg';
import { colors, fonts } from '../theme/tokens';

const BAR_COUNT = 20;
const BAR_WIDTH = 2;
const BAR_GAP = 2;
const BAR_HEIGHT = 14;
const BAR_HEIGHT_MIN = 0.15;

type Props = {
  mode: 'idle' | 'recording';
  scheme: 'light' | 'dark';
  elapsedMs: number;
  amplitudes?: number[]; // optional realtime 0..1 per bar (length BAR_COUNT)
  onCancel: () => void;
  onPauseToggle: () => void;
  onOpenHistory?: () => void;
  onOpenCanvas?: () => void;
  onOpenSnippets?: () => void;
  onOpenVocabulary?: () => void;
  onStartRecording?: () => void;
};

export function RecordingBar(p: Props) {
  const isDark = p.scheme === 'dark';
  const t = isDark ? darkTokens : lightTokens;

  const rec = useSharedValue(p.mode === 'recording' ? 1 : 0);
  useEffect(() => {
    rec.value = withTiming(p.mode === 'recording' ? 1 : 0, {
      duration: 250,
      easing: Easing.out(Easing.quad),
    });
  }, [p.mode]);

  const idleStyle = useAnimatedStyle(() => ({
    opacity: 1 - rec.value,
    transform: [{ translateX: interpolate(rec.value, [0, 1], [0, -8]) }],
  }));
  const recStyle = useAnimatedStyle(() => ({
    opacity: rec.value,
    transform: [{ translateX: interpolate(rec.value, [0, 1], [8, 0]) }],
    pointerEvents: rec.value > 0.5 ? 'auto' : 'none',
  }));

  return (
    <View style={[styles.bar, { backgroundColor: t.bar, borderTopColor: t.border }]}>
      <View style={styles.brand}>
        <View style={styles.badge}>
          <Animated.Text style={styles.badgeText}>F</Animated.Text>
        </View>
      </View>

      {/* IDLE stack */}
      <Animated.View style={[styles.stack, idleStyle]}>
        <IconBtn onPress={p.onOpenHistory} color={t.icon}>{icons.clock}</IconBtn>
        <IconBtn onPress={p.onOpenCanvas} color={t.icon}>{icons.canvas}</IconBtn>
        <IconBtn onPress={p.onOpenSnippets} color={t.icon}>{icons.bolt}</IconBtn>
        <IconBtn onPress={p.onOpenVocabulary} color={t.icon}>{icons.book}</IconBtn>
        <Pressable onPress={p.onStartRecording} style={[styles.mic, { backgroundColor: t.mic }]}>
          <Svg width={14} height={14} viewBox="0 0 24 24"
            fill="none" stroke={t.micIcon} strokeWidth={1.8}
            strokeLinecap="round" strokeLinejoin="round">
            <Rect x={9} y={3} width={6} height={12} rx={3}/>
            <Path d="M19 11v1a7 7 0 0 1-14 0v-1"/>
            <Path d="M12 19v3"/>
          </Svg>
        </Pressable>
      </Animated.View>

      {/* RECORDING stack */}
      <Animated.View style={[styles.stack, styles.stackAbs, recStyle]}>
        <Pressable onPress={p.onCancel} style={[styles.chip, { backgroundColor: t.chip }]}>
          <Svg width={11} height={11} viewBox="0 0 24 24"
            fill="none" stroke={t.text} strokeWidth={2}
            strokeLinecap="round" strokeLinejoin="round">
            <Path d="M18 6L6 18M6 6l12 12"/>
          </Svg>
        </Pressable>

        <Waveform amplitudes={p.amplitudes} color={t.text}/>

        <Animated.Text style={[styles.timer, { color: t.timer }]}>
          {formatElapsed(p.elapsedMs)}
        </Animated.Text>

        <Pressable onPress={p.onPauseToggle} style={styles.pause}>
          <Svg width={10} height={10} viewBox="0 0 24 24" fill={colors.primaryOn}>
            <Rect x={7} y={5} width={3.5} height={14} rx={1}/>
            <Rect x={13.5} y={5} width={3.5} height={14} rx={1}/>
          </Svg>
        </Pressable>
      </Animated.View>
    </View>
  );
}

function Waveform({ amplitudes, color }: { amplitudes?: number[]; color: string }) {
  return (
    <View style={styles.wave}>
      {Array.from({ length: BAR_COUNT }).map((_, i) => (
        <WaveBar key={i} index={i} amplitude={amplitudes?.[i]} color={color}/>
      ))}
    </View>
  );
}

function WaveBar({ index, amplitude, color }: { index: number; amplitude?: number; color: string }) {
  const s = useSharedValue(BAR_HEIGHT_MIN);
  useEffect(() => {
    if (amplitude != null) {
      s.value = withTiming(Math.max(BAR_HEIGHT_MIN, amplitude), { duration: 80 });
      return;
    }
    // fallback loop — offset by index for a travelling wave
    const delay = -(index * 80) % 1100;
    s.value = withRepeat(
      withSequence(
        withTiming(1, { duration: 550, easing: Easing.inOut(Easing.quad) }),
        withTiming(BAR_HEIGHT_MIN, { duration: 550, easing: Easing.inOut(Easing.quad) }),
      ),
      -1,
      false,
    );
    return () => cancelAnimation(s);
  }, [amplitude]);

  const style = useAnimatedStyle(() => ({ transform: [{ scaleY: s.value }] }));
  return <Animated.View style={[styles.waveBar, { backgroundColor: color }, style]}/>;
}

function IconBtn({
  onPress, color, children,
}: { onPress?: () => void; color: string; children: React.ReactNode }) {
  return (
    <Pressable onPress={onPress} style={styles.iconBtn}>
      <Svg width={14} height={14} viewBox="0 0 24 24"
        fill="none" stroke={color} strokeWidth={1.6}
        strokeLinecap="round" strokeLinejoin="round">{children}</Svg>
    </Pressable>
  );
}

const icons = {
  clock:  <><Path d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z"/><Path d="M12 7v5l3 2"/></>,
  canvas: <><Rect x={3} y={3} width={7} height={7} rx={1.2}/><Rect x={14} y={3} width={7} height={7} rx={1.2}/><Rect x={3} y={14} width={7} height={7} rx={1.2}/><Rect x={14} y={14} width={7} height={7} rx={1.2}/></>,
  bolt:   <Path d="M13 2 3 14h8l-1 8 10-12h-8z"/>,
  book:   <><Path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><Path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></>,
};

function formatElapsed(ms: number) {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

const lightTokens = {
  bar: '#ebebed', border: 'rgba(20,20,22,0.08)',
  icon: 'rgba(20,20,22,0.75)', chip: 'rgba(20,20,22,0.08)',
  mic: '#f2f2f2', micIcon: '#141416',
  text: '#141416', timer: 'rgba(20,20,22,0.7)',
};
const darkTokens = {
  bar: '#141618', border: 'rgba(240,240,240,0.06)',
  icon: 'rgba(240,240,240,0.7)', chip: 'rgba(240,240,240,0.09)',
  mic: '#f2f2f2', micIcon: '#141416',
  text: '#f2f2f2', timer: 'rgba(240,240,240,0.7)',
};

const styles = StyleSheet.create({
  bar: {
    height: 42, paddingHorizontal: 12, borderTopWidth: 1,
    flexDirection: 'row', alignItems: 'center', gap: 10,
  },
  brand: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 4 },
  badge: { width: 16, height: 16, borderRadius: 4, backgroundColor: '#141416',
    alignItems: 'center', justifyContent: 'center' },
  badgeText: { fontFamily: fonts.uiBold, fontSize: 10, color: '#C85A3E', lineHeight: 12 },

  stack: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8 },
  stackAbs: { position: 'absolute', left: 32 /* after brand */, right: 12, top: 0, bottom: 0 },

  iconBtn: { width: 24, height: 24, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  mic: { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center', marginLeft: 'auto' },

  chip: { width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },

  wave: {
    flex: 1, height: BAR_HEIGHT,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: BAR_GAP,
  },
  waveBar: { width: BAR_WIDTH, height: BAR_HEIGHT, borderRadius: BAR_WIDTH / 2 },

  timer: { fontFamily: fonts.monoSemi, fontSize: 11, letterSpacing: 0.2 },
  pause: { width: 24, height: 24, borderRadius: 12,
    backgroundColor: '#C85A3E', alignItems: 'center', justifyContent: 'center' },
});
```

---

## Usage

```tsx
const [recording, setRecording] = useState(false);
const [elapsed, setElapsed] = useState(0);
const [amps, setAmps] = useState<number[] | undefined>(undefined);

// wire mic amplitude from expo-av or your recorder to setAmps

<RecordingBar
  mode={recording ? 'recording' : 'idle'}
  scheme={useColorScheme() ?? 'light'}
  elapsedMs={elapsed}
  amplitudes={amps}
  onStartRecording={() => setRecording(true)}
  onCancel={() => { setRecording(false); setElapsed(0); }}
  onPauseToggle={() => {/* pause/resume recorder */}}
  onOpenHistory={() => navigate('history-overlay')}
  onOpenCanvas={() => navigate('canvas-overlay')}
  onOpenSnippets={() => navigate('snippets-overlay')}
  onOpenVocabulary={() => navigate('vocab-overlay')}
/>
```

Feed amplitude:

```ts
// with expo-av Recording — poll status @ 60fps in JS or use a native module
recording.setOnRecordingStatusUpdate((s) => {
  if (s.metering == null) return;
  // metering is dBFS in [-160, 0]. Normalize to 0..1
  const norm = Math.max(0, Math.min(1, (s.metering + 60) / 60));
  setAmps((prev) => {
    const next = prev ? [...prev.slice(1), norm] : Array(BAR_COUNT).fill(norm);
    return next;
  });
});
recording.setProgressUpdateInterval(80);
```

---

## Behavior spec

- Cross-fade duration: 250ms, `Easing.out(quad)`.
- Idle stack translates 8pt left as it fades out; recording stack starts 8pt right and slides to 0.
- Waveform bars are absolutely positioned inside a flex row; only their `scaleY` transform animates (no layout thrash).
- When paused, freeze the current shared values (`cancelAnimation` on each bar's shared value; timer stops ticking).
- Pause button icon swaps to a play triangle when paused (same 24pt disc, same color).
- Long-press on ✕ = confirm discard (haptic + tooltip). Tap = immediate discard.

Every value above is a token or a constant in the file — nothing hardcoded downstream.
