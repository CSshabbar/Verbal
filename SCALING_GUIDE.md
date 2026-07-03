# Flume — Scaling Guide

The Flume wireframes were drawn inside a 280 pt phone frame. Real iPhones are 390–430 pt wide, and real Androids sit 360–412 pt. When we copied pixel values 1:1 from the wireframes into `flume-ui/`, every size stayed the same in absolute pt — so on a real device everything reads about **35% smaller** than in the mock.

The mock was already visually correct. The code needs to scale UP to match.

This guide is the fix — a single theme-level scale, plus a handful of intentional overrides in specific screens.

---

## 1. The multiplier

```
Real iPhone width (14/15):  390 pt
Wireframe frame width:      280 pt
Scale:                      390 / 280 ≈ 1.39
```

Round to **1.35** for a comfortable, not-oversized feel. Larger devices (iPhone Pro Max, Android XL) get the same scale — density scaling handles the rest.

You have two paths. Pick ONE — do not mix.

- **Path A (recommended):** rescale the theme once, everything else follows. 30 minutes of work.
- **Path B:** leave the theme alone, override the ~15 hardcoded values inside screens. Faster to try, harder to maintain.

I strongly recommend Path A. Instructions below cover both.

---

## 2. Path A — one-time theme rescale (recommended)

### 2.1 Replace `flume-ui/theme/typography.ts`

Multiply every `fontSize` and matching `lineHeight` by 1.35. Round to the nearest .5. Letter-spacing scales too (multiply by 1.35).

```ts
// flume-ui/theme/typography.ts — SCALED
import { TextStyle } from 'react-native';

export const fonts = {
  regular:  'Geist_400Regular',
  medium:   'Geist_500Medium',
  semibold: 'Geist_600SemiBold',
  bold:     'Geist_700Bold',
  mono:     'JetBrainsMono_500Medium',
  monoBold: 'JetBrainsMono_600SemiBold',
} as const;

type Variant = Required<Pick<TextStyle, 'fontFamily' | 'fontSize' | 'lineHeight'>>
  & Pick<TextStyle, 'letterSpacing' | 'textTransform'>;

export const type: Record<string, Variant> = {
  // Display
  displayXL:     { fontFamily: fonts.bold,     fontSize: 60, lineHeight: 57, letterSpacing: -1.8 },
  display:       { fontFamily: fonts.bold,     fontSize: 49, lineHeight: 49, letterSpacing: -1.5 },
  displaySm:     { fontFamily: fonts.semibold, fontSize: 35, lineHeight: 39, letterSpacing: -0.7 },
  title:         { fontFamily: fonts.semibold, fontSize: 30, lineHeight: 34 },
  titleSm:       { fontFamily: fonts.semibold, fontSize: 27, lineHeight: 32 },
  subtitle:      { fontFamily: fonts.semibold, fontSize: 24, lineHeight: 30 },
  bodyLg:        { fontFamily: fonts.medium,   fontSize: 19, lineHeight: 27 },
  body:          { fontFamily: fonts.regular,  fontSize: 17, lineHeight: 25 },
  bodySm:        { fontFamily: fonts.regular,  fontSize: 17, lineHeight: 25 },  // bumped to 17 (iOS body size)
  bodyXs:        { fontFamily: fonts.regular,  fontSize: 15, lineHeight: 21 },
  buttonPrimary: { fontFamily: fonts.semibold, fontSize: 18, lineHeight: 22 },
  button:        { fontFamily: fonts.semibold, fontSize: 17, lineHeight: 21 },
  buttonSm:      { fontFamily: fonts.medium,   fontSize: 16, lineHeight: 19 },
  label:         { fontFamily: fonts.medium,   fontSize: 15, lineHeight: 19 },
  caption:       { fontFamily: fonts.regular,  fontSize: 14, lineHeight: 18 },
  tabLabel:      { fontFamily: fonts.medium,   fontSize: 12, lineHeight: 14 },

  // Mono
  timer:         { fontFamily: fonts.monoBold, fontSize: 56, lineHeight: 58, letterSpacing: -1 },
  timerXL:       { fontFamily: fonts.mono,     fontSize: 76, lineHeight: 76, letterSpacing: -3 },
  code:          { fontFamily: fonts.mono,     fontSize: 27, lineHeight: 30 },
  meta:          { fontFamily: fonts.mono,     fontSize: 13, lineHeight: 15, letterSpacing: 1.4, textTransform: 'uppercase' },
  metaSm:        { fontFamily: fonts.mono,     fontSize: 12, lineHeight: 14, letterSpacing: 0.6, textTransform: 'uppercase' },

  wordmark:      { fontFamily: fonts.semibold, fontSize: 17, lineHeight: 19, letterSpacing: 0.7 },
};

export type TypeVariant = keyof typeof type;
```

> Body copy jumped to **17 pt** (`body` and `bodySm` alike). That matches iOS's default body size and is where most native apps live. Anything smaller feels squinty on real devices.

### 2.2 Replace `flume-ui/theme/spacing.ts`

Same 1.35× multiplier, round to whole numbers.

```ts
// flume-ui/theme/spacing.ts — SCALED
export const space = {
  px:   1,
  xs:   6,     // 4  → 6
  s:    11,    // 8  → 11
  m:    16,    // 12 → 16
  base: 22,    // 16 → 22
  l:    24,    // 18 → 24
  lg:   30,    // 22 → 30
  xl:   38,    // 28 → 38
  xxl:  48,    // 36 → 48
  xxxl: 64,    // 48 → 64
} as const;

export const radius = {
  xs:    8,    // 6  → 8
  sm:    11,   // 8  → 11
  md:    14,   // 10 → 14
  lg:    16,   // 12 → 16   (cards look right at 16 on-device)
  xl:    18,   // 14 → 18
  xxl:   24,   // 18 → 24
  pill:  999,
} as const;
```

### 2.3 Bump component-internal sizes

Some hardcoded numbers live in components rather than the theme (mic diameters, icon-button size, status dots, chip padding, etc.). Change these:

**`flume-ui/components/MicButton.tsx`** — bigger mic feels right at ~120 pt idle:
```ts
// change the default size argument
size = state === 'idle' ? 120 : 92,   //  was 92 / 70
```

**`flume-ui/components/IconButton.tsx`** — recording cancel/pause:
```ts
// change the default
size = 64,   // was 48
```

**`flume-ui/components/Chip.tsx`** — bump padding:
```ts
md: { paddingVertical: 8,  paddingHorizontal: 15 },   // was 6 / 11
sm: { paddingVertical: 4,  paddingHorizontal: 11 },   // was 3 / 8
```

**`flume-ui/components/ListRow.tsx`** — bigger tap targets:
```ts
row: {
  ...,
  gap: 15,      // was 11
  padding: 16,  // was 12
},
iconBox: {
  width: 42, height: 42,           // was 32
  borderRadius: radius.md,
  ...
},
dot: {
  width: 7, height: 7,             // was 5
  borderRadius: 3.5,
},
```

**`flume-ui/components/PageDots.tsx`** — bigger dots:
```ts
pip: { height: 4, borderRadius: 2 },          // was 3
on:  { width: 34, ... },                       // was 26
off: { width: 24, ... },                       // was 18
```

**`flume-ui/components/Visualizer.tsx`** — bump bar width + gap **inside the recording screen call site** (do NOT change the component default, since the dictation strip in NoteEditor uses smaller bars). In `RecordingScreen.tsx`:

```tsx
<Visualizer active={...} barWidth={6} gap={7} />
```

Reanimated will scale the bar heights via the transform correctly — but we also want to bump their base heights. Do it locally on the recording screen:

```tsx
import { visualizerHeights } from '../theme'; // remove this
// replace with:
const bigHeights = [38, 76, 120, 94, 148, 108, 134, 80, 120, 54];
<Visualizer active={...} heights={bigHeights} barWidth={6} gap={7} />
```

### 2.4 Screen-level overrides

A few individual numbers are baked directly into screens. Change these:

**`WelcomeScreen.tsx`** — bigger logo, more air:
```tsx
<LogoMark size={128} />                  // was 96
// paddingTop: insets.top + 30           unchanged
// paddingBottom: insets.bottom + 30     was + 26 — a hair more
```

**`OnboardingScreen.tsx` — Slide1 brand row**:
```tsx
<LogoMark size={38} />                   // was 28
```
**Slide2 step number tile**:
```ts
stepNum: {
  width: 52, height: 52,                 // was 38
  ...
},
```

**`HomeScreen.tsx`**:
```tsx
<LogoMark size={48} />                   // was 36
```

**`ConfirmationScreen.tsx`**:
```tsx
<SuccessBadge size={76} />               // was 56
```

**`HistoryDetailScreen.tsx`** — playback bar dimensions:
```ts
playBtn:  { width: 40, height: 40, borderRadius: 20, ... },  // was 30
deviceIcon: { width: 28, height: 28, borderRadius: 8, ... }, // was 20/6
// waveRow height:
waveRow: { ..., height: 30 },   // was 22
// bar widths (inside the map)
{ width: 3, height: h * 1.35, borderRadius: 1.5, ... }
```

**`NotesListScreen.tsx`** — FAB:
```ts
fab: { width: 68, height: 68, borderRadius: 34, ... },      // was 52
// bottom offset gets bumped too since tab bar is taller:
bottom: insets.bottom + 96,   // was + 78
```

**`DevicesScreen.tsx`** — header + button:
```ts
addBtn: { width: 40, height: 40, borderRadius: 20, ... },   // was 32
plusDisc: { width: 34, height: 34, borderRadius: 17, ... }, // was 26
```

**`PairDeviceScreen.tsx`** — viewfinder corners:
```ts
corner: { width: 32, height: 32, ... },   // was 24
// border widths for the L shapes stay at 3px
```

**Tab bar** — in `flume-ui/navigation/RootNavigator.tsx` inside `TabsNavigator`:
```ts
tabBarStyle: {
  ...,
  height: 78 + insets.bottom,   // was 60
  paddingTop: 12,               // was 10
  paddingBottom: insets.bottom + 18,  // was + 14
},
tabBarLabelStyle: type.tabLabel,   // now 12pt from the scaled type
// AND the icon:
tabBarIcon: ({ color }) => <Ionicons name="mic-outline" size={26} color={color} />,
// bump every icon in the file: 20 → 26
```

### 2.5 Ionicon sizes across the app

The Ionicons calls in components use hardcoded sizes. Update these defaults:

| File                | Old | New |
| ------------------- | --- | --- |
| `ListRow` leading icon                       | 16 | 22 |
| `IconButton` (formula `size * 0.36`)         | keeps working ✓ | ✓ |
| `ConfirmationScreen` action-row icons        | 16 | 22 |
| `HistoryListScreen` search button icon       | 14 | 18 |
| `HistoryDetailScreen` chevron-back           | 18 | 22 |
| `HistoryDetailScreen` overflow ellipsis      | 14 | 18 |
| `DevicesScreen` chevron/back/add             | 18 | 22 |
| `NotesListScreen` search icon                | 14 | 18 |
| `NotesListScreen` FAB `+`                    | 26 | 34 |
| `NoteEditorScreen` mic/keyboard/back         | 18 | 24 |
| `NoteEditorScreen` mic-dock icon             | 24 | 30 |
| `CanvasScreen` action icons                  | 16 | 22 |
| `PairDeviceScreen` chevron-back              | 18 | 22 |

Do a search across `flume-ui/` for `Ionicons` and bump each `size=` in one pass — takes a couple minutes.

### 2.6 Done — you're back to wireframe proportions

Run the app. It should now match the wireframes visually on a real device.

---

## 3. Path B — target overrides without touching theme

Only recommended if you can't rebuild your bundle right now and need to patch specific screens. Follow §2.3–2.5 above but SKIP §2.1 and §2.2. Result: type still looks a bit small, but layout, icons, and controls will feel right.

Not sustainable long-term — everything you build after this stays small.

---

## 4. Rule for future components

Any time you write `fontSize: N`, `size={N}`, `width: N`, `height: N`, `padding: N` — ask: **did I copy this from a 280 pt wireframe?** If yes, multiply by 1.35 before writing it.

Or better: only use `space.*`, `radius.*`, and `<Text variant="...">` — never a raw number for spacing or sizing. Then this problem never comes back.

---

## 5. Density note (bonus)

React Native's default sizes ALREADY scale to device density via pt. You do NOT need to multiply by `PixelRatio.get()` or anything — a 22 pt icon is 22 pt everywhere. The 1.35 multiplier here is because the *design* was drawn small, not because the code needs density math.

---

## 6. TL;DR checklist

- [ ] Replace `flume-ui/theme/typography.ts` with §2.1
- [ ] Replace `flume-ui/theme/spacing.ts` with §2.2
- [ ] Bump `MicButton`, `IconButton`, `Chip`, `ListRow`, `PageDots` defaults (§2.3)
- [ ] Update Visualizer sizing at the RecordingScreen call site (§2.3)
- [ ] Bump logo sizes on Welcome, Onboarding, Home (§2.4)
- [ ] Bump success badge, FAB, viewfinder corners (§2.4)
- [ ] Bump tab bar height + icon size (§2.4)
- [ ] Sweep Ionicons `size=` values (§2.5)
- [ ] Test on device (simulators lie about size a bit)

If anything still feels off after this, the fix is almost always a specific number — send me a screenshot and I'll call out exactly which line.
