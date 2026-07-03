# Flume — Design Handoff (React Native + Expo)

**Source of truth:** `Flume Wireframes.dc.html`, turn 3 (screens `3a`–`3i`).
**Theme:** Dark only (light theme to be added later).
**Stack target:** React Native + Expo, plain `StyleSheet` (no Tailwind/NativeWind assumed). Swap to your in-house theming layer if you have one — the token names below map cleanly to any system.

This doc covers ONLY what was designed. No phantom screens, no invented components.

---

## 1. Design tokens

### 1.1 Color

All values pulled directly from the wireframes. Naming is semantic, not literal.

```ts
// theme/colors.ts
export const colors = {
  // Surfaces
  bgCanvas:        '#14110f',  // outermost page background (used in nav containers, edge of safe area)
  bgScreen:        '#0b0908',  // the phone screen background — primary screen bg
  surface1:        'rgba(245, 237, 228, 0.04)', // resting card/tile
  surface2:        'rgba(245, 237, 228, 0.06)', // chip, icon button bg, hovered/pressed tile
  surface3:        'rgba(245, 237, 228, 0.08)', // emphasized/elevated
  scrim:           'rgba(0, 0, 0, 0.55)',       // bottom-sheet/modal scrim

  // Lines
  borderSubtle:    'rgba(245, 237, 228, 0.06)',
  borderDefault:   'rgba(245, 237, 228, 0.08)',
  borderStrong:    'rgba(245, 237, 228, 0.12)',
  borderDashed:    'rgba(245, 237, 228, 0.16)', // pair-empty placeholder

  // Text
  textPrimary:     '#f5ede4',                       // headings, primary copy
  textSecondary:   'rgba(245, 237, 228, 0.65)',     // body
  textMuted:       'rgba(245, 237, 228, 0.55)',     // helper
  textSubtle:      'rgba(245, 237, 228, 0.45)',     // metadata
  textDisabled:    'rgba(245, 237, 228, 0.30)',

  // Brand (orange)
  primary:         '#E0552C',
  primaryInk:      '#14110f',                       // text/icon ON primary
  primarySoft:     'rgba(224, 85, 44, 0.14)',       // tinted bg
  primarySofter:   'rgba(224, 85, 44, 0.08)',
  primaryBorder:   'rgba(224, 85, 44, 0.35)',
  primaryDashed:   'rgba(224, 85, 44, 0.30)',
  primaryGlow:     'rgba(224, 85, 44, 0.35)',       // mic shadow
  primaryAccent:   '#ffb593',                       // text on primarySoft chip

  // Status
  online:          '#4ad15a',
  recording:       '#E0552C',
  offline:         'rgba(245, 237, 228, 0.30)',
} as const;
```

### 1.2 Typography

Two families. **Geist** for everything UI (headings + body). **JetBrains Mono** for numerals, codes, and meta labels.

```ts
// theme/typography.ts
export const fonts = {
  sans: 'Geist',               // expo-google-fonts/geist
  mono: 'JetBrainsMono',       // expo-google-fonts/jetbrains-mono
} as const;

export const type = {
  // Display
  displayXL:    { family: 'sans', size: 44, weight: '700', lineHeight: 42, letterSpacing: -1.3 }, // onboarding hero (3b screen 1)
  display:      { family: 'sans', size: 36, weight: '700', lineHeight: 36, letterSpacing: -1.1 }, // login minimal (2b)
  displaySm:    { family: 'sans', size: 26, weight: '600', lineHeight: 29, letterSpacing: -0.5 }, // welcome title (3a)
  title:        { family: 'sans', size: 22, weight: '600', lineHeight: 25 },                      // onboarding screen-3 title
  titleSm:      { family: 'sans', size: 20, weight: '600', lineHeight: 24 },                      // section title (History)
  subtitle:     { family: 'sans', size: 18, weight: '600', lineHeight: 22 },                      // "Pasted to MacBook"
  bodyLg:       { family: 'sans', size: 14, weight: '500', lineHeight: 20 },
  body:         { family: 'sans', size: 13, weight: '400', lineHeight: 19 },                      // welcome subhead
  bodySm:       { family: 'sans', size: 12.5, weight: '400', lineHeight: 19 },                    // transcript copy
  bodyXs:       { family: 'sans', size: 11.5, weight: '400', lineHeight: 16 },
  buttonPrimary:{ family: 'sans', size: 13.5, weight: '600' },
  button:       { family: 'sans', size: 13, weight: '600' },
  buttonSm:     { family: 'sans', size: 12, weight: '500' },
  label:        { family: 'sans', size: 11, weight: '500' },
  caption:      { family: 'sans', size: 11, weight: '400', lineHeight: 14 },
  tabLabel:     { family: 'sans', size: 10, weight: '500' },

  // Mono
  timer:        { family: 'mono', size: 36, weight: '600', letterSpacing: -0.7 },                 // recording 00:23
  timerXL:      { family: 'mono', size: 56, weight: '300', letterSpacing: -2.2 },                 // (kept for future minimal recording)
  code:         { family: 'mono', size: 20, weight: '500' },                                      // pairing-code cell
  meta:         { family: 'mono', size: 10, weight: '500', letterSpacing: 1.4, textTransform: 'uppercase' }, // labels like "Today", "Recent"
  metaSm:       { family: 'mono', size: 9.5, weight: '500', letterSpacing: 0.6 },                 // device tag in dense list
} as const;
```

> **Brand wordmark "FLUME"**: Geist 600, 13 px, letter-spacing 0.5 px (≈ 0.04 em). Used in headers (3b screen 1, 2b).

### 1.3 Spacing

Loose 4-pt scale. Not strict 8-pt — the design uses interstitial values where they help.

```ts
export const space = {
  px:   1,
  xs:   4,
  s:    8,
  m:    12,
  base: 16,
  l:    18,
  lg:   22,
  xl:   28,
  xxl:  36,
  xxxl: 48,
} as const;
```

### 1.4 Radius

```ts
export const radius = {
  xs:    6,    // pip, mini swatch
  sm:    8,    // small tile icon (device row icon)
  md:    10,   // numpad cell, input
  lg:    12,   // card, list row
  xl:    14,   // primary button, large input
  xxl:   18,   // viewfinder
  pill:  999,  // chip
  phone: 38,   // (wireframe-only) phone bezel
} as const;
```

### 1.5 Shadow / elevation

Used sparingly. Only two real cases.

```ts
export const shadow = {
  mic: {
    // Resting (idle) — soft halo around the orange mic
    // box-shadow: 0 0 0 8px rgba(224,85,44,.08), 0 0 0 18px rgba(224,85,44,.04)
    // In RN: rendered with two transparent ring Views since native shadow doesn't do double-rings cleanly
    rings: [
      { size: 8,  color: 'rgba(224, 85, 44, 0.08)' },
      { size: 18, color: 'rgba(224, 85, 44, 0.04)' },
    ],
  },
  micActive: {
    // Recording — drop shadow
    // box-shadow: 0 12px 28px rgba(224,85,44,.35)
    color: 'rgba(224, 85, 44, 0.35)',
    offset: { width: 0, height: 12 },
    radius: 28,
    elevation: 12, // Android
  },
  toast: {
    // 0 14px 40px rgba(0,0,0,.55)
    color: 'rgba(0, 0, 0, 0.55)',
    offset: { width: 0, height: 14 },
    radius: 40,
    elevation: 16,
  },
} as const;
```

### 1.6 Motion / animation

```ts
export const motion = {
  // Visualizer bars — the only continuous animation
  visualizer: {
    duration: 1100,             // ms
    easing: 'easeInOut',
    keyframes: { from: 0.18, to: 1.0 }, // scaleY
    // Each bar gets a deterministic staggered delay; we use phase offsets in seconds:
    // 0, -0.12, -0.24, -0.36, -0.48, -0.60, -0.72, -0.84, -0.96, -0.10  (10 bars, 3d)
  },
  // Pulse rings (idle/listening — pair search 3i+, bird-listening variant)
  pulse: {
    duration: 1600,
    easing: 'easeInOut',
    keyframes: { from: 0.18, to: 1.0 }, // scale + opacity
  },
  // UI transitions
  micPress:        { duration: 120, easing: 'easeOut',   scale: 0.94 },
  cardPress:       { duration: 100, easing: 'easeOut',   scale: 0.98 },
  screenTransition:{ duration: 280, easing: 'easeInOut' },
  toastIn:         { duration: 240, easing: 'easeOut' },
  toastOut:        { duration: 180, easing: 'easeIn' },
} as const;
```

---

## 2. Components

Only what's actually in the picked screens (3a–3i). Sizes are exact.

### 2.1 Buttons

| Variant         | Where                      | Spec                                                                                         |
|-----------------|----------------------------|----------------------------------------------------------------------------------------------|
| **Primary**     | "Begin", "Done", "Resend"  | `bg: primary` · `text: primaryInk` · `padY: 13` · `padX: 18` · `radius: 14` · `type.buttonPrimary` |
| **Primary on light** (Google) | 3a, 3b, 2a, 2b  | `bg: #f5ede4` · `text: primaryInk` · same padding · same radius · 16px Google G icon on left |
| **Ghost**       | "Edit", "Copy", "Skip"     | `bg: transparent` · `text: textPrimary` · `border: 1px borderStrong` · `padY: 13` · `radius: 14` |
| **Mic (idle)**  | 3c                         | `92×92` · `radius: 50%` · `bg: primary` · `text: primaryInk` · two outer pulse rings (see `shadow.mic`) |
| **Mic (recording)** | 3d (Stop)             | `70×70` · `radius: 50%` · `bg: primary` · `text: primaryInk` · `shadow.micActive` · Stop icon ■ |
| **Icon (round)**| 3d cancel/pause            | `48×48` · `radius: 50%` · `bg: surface1` · `text: textSecondary` · `border: 1px borderDefault` |
| **Floating add**| 3i header (+)              | `32×32` · `radius: 50%` · `bg: primarySoft` · `icon: primary` · font 16                        |

### 2.2 Chips

| Variant        | Spec                                                                                       |
|----------------|--------------------------------------------------------------------------------------------|
| **Resting**    | `bg: surface2` · `text: textPrimary` (.85) · `border: 1px borderSubtle` · `padY: 6` `padX: 11` · `radius: pill` · font `500 10.5` |
| **Active (on)**| `bg: primarySoft` · `text: primaryAccent` · `border: 1px primaryBorder` · leading 6×6 `primary` dot |

Used in 3c device chips, 3d recording target chip, 3f filter chips, 3i "DEFAULT" pill (use a compact variant: `padY: 3` `padX: 8` font `9.5`).

### 2.3 List rows (device tile)

Used in 3i, 3b screen 3 (download), Settings → Devices.

```
container: bg surface1 · radius lg (12) · border 1px borderSubtle · padding 12
icon-square: 32×32 · radius sm (8) · bg surface2 · centered icon · fontSize 14
title: type.button (13 → 12.5 in dense)
sub: type.caption · textMuted · row with 5×5 dot indicator
trailing: chevron › textSubtle  OR  "DEFAULT" chip  OR  action label primary
```

### 2.4 History card

Used in 3c "Last sent" and 3f list items.

```
padding: 12 × 13            // smaller (12) in 3f items
radius: lg (12)
bg: surface1
border: 1px rgba(245,237,228,0.05)
header row: meta-label left, meta-label right (word count)
body: bodySm color textPrimary (.9), max 2 lines truncated
```

### 2.5 Transcript card

Used in 3e and 3g.

```
padding: 14
radius: lg (12)
bg: surface1
border: 1px borderSubtle
optional meta-label header
body: bodySm line-height 19
```

### 2.6 Playback bar (3g)

```
container: surface1 · border 1px borderSubtle · radius lg · padding 12 × 13
left: 30×30 play button · radius 50% · bg primary · ▶ icon primaryInk fontSize 11
right (waveform strip):
  - 20 vertical lines, width 2px each, gap 2px
  - played portion (≈5 bars from left): bg primary
  - unplayed: bg textDisabled
  - heights: deterministic per index (6, 12, 18, 10, 20, 8, 14, 18, 6, 12, 16, 8, 14, 20, 8, 18, 10, 14, 6, 12) px
  - below: mono caption 9.5 — "0:04" left, "0:14" right
```

### 2.7 Recording visualizer (3d)

```
container: row, gap 5, height 110, center-aligned
bars: 10 × { width 4, radius 2, bg primary, transform-origin: center }
animation: scaleY 0.18 ↔ 1.0, duration 1100ms, easeInOut, infinite reverse
stagger (per bar, in ms): 0, 120, 240, 360, 480, 600, 720, 840, 960, 100
base heights (px): 28, 56, 90, 70, 110, 80, 100, 60, 90, 40
```

> In RN: use **Reanimated** shared values + `withRepeat(withTiming(...), -1, true)`. One shared value per bar with its own delay. Don't drive 10 React state updates per frame.

### 2.8 Pulse rings (e.g. mic idle, pair search)

Two concentric `View`s positioned absolutely outside the central element, animating `opacity` (0.4 → 0) and `scale` (1.0 → 1.4) with the outer ring delayed by ~600 ms.

### 2.9 Bottom tab bar

Used in 3c, 3f, and Settings root. **Three tabs only**.

```
container: row · justify space-around · paddingTop 10 · paddingBottom (16 + safe-area) · paddingX 16
            · borderTop 1px borderSubtle · bg bgScreen
tab: column · gap 4 · align center
  icon: fontSize 14 (or 18 from Ionicons)
  label: type.tabLabel
inactive color: textDisabled (.4)
active color: primary
```

Order: **Record** (mic) · **History** (list) · **Settings** (gear).

### 2.10 Status bar / header row

Each screen begins with a 32-px-tall row: time "9:41" left, status glyph right.
On 3d recording: right side is `● REC` in `primary` color.

For production this is the real `expo-status-bar` — use `style="light"` and let it overlay the screen bg.

### 2.11 Page indicator (onboarding dots)

```
row, gap 6, justify center
each pip: width 18, height 3, radius 2, bg textDisabled (.18)
active: width 26, bg primary
```

### 2.12 QR viewfinder (3h)

```
container: aspect-ratio 1 · radius xxl (18) · bg #14110f · border 1px borderSubtle · overflow hidden
inner frame: absolute inset 18 · border 2px primary · radius 14
4 L-shaped corners: 24×24 thick (3px) primary in each corner, radii pointing inward
scan line: full-width 2px gradient (transparent → primary → transparent) at y=50%, blurred glow
            (animate: top 18 → bottom 18 → top, loop 2.4s)
```

### 2.13 Pairing code input (1q reference; not in turn 3 but useful)

If you ship code-entry as fallback to QR: 6 cells, each 34×46, radius 10, bg surface1, border 1.5 borderStrong; focused cell border `primary` and bg `primarySofter`; digit font `type.code`.

### 2.14 Numpad (for code entry)

3-col grid, gap 6, each cell `paddingY 10`, radius md (10), `bg surface1`, font `500 16`.

---

## 3. Navigation

```
RootStack (createNativeStackNavigator)
├─ Auth (when !isSignedIn)
│   └─ Welcome              → screen 3a
└─ App (when isSignedIn && needsOnboarding)
│   ├─ OnboardingWelcome    → screen 3b/1
│   ├─ OnboardingHow        → screen 3b/2
│   └─ OnboardingPair       → screen 3b/3
└─ Main (when fully set up)
    └─ Tabs (createBottomTabNavigator)
        ├─ RecordStack
        │   ├─ Home          → 3c
        │   ├─ Recording     → 3d  (presentation: 'modal', gestureEnabled: false)
        │   └─ Confirmation  → 3e  (presentation: 'modal', auto-dismiss after timeout)
        ├─ HistoryStack
        │   ├─ HistoryList   → 3f
        │   └─ HistoryDetail → 3g
        └─ SettingsStack
            ├─ Settings      → (root settings — to design)
            ├─ Devices       → 3i
            └─ PairDevice    → 3h  (presentation: 'modal')
```

### 3.1 Navigator theming

```ts
const navTheme: Theme = {
  dark: true,
  colors: {
    primary: colors.primary,
    background: colors.bgScreen,
    card: colors.bgScreen,
    text: colors.textPrimary,
    border: colors.borderSubtle,
    notification: colors.primary,
  },
};
```

Tab bar styling:
```ts
tabBarStyle: {
  backgroundColor: colors.bgScreen,
  borderTopColor: colors.borderSubtle,
  borderTopWidth: StyleSheet.hairlineWidth,
  height: 60 + insets.bottom,
  paddingTop: 10,
  paddingBottom: insets.bottom + 16,
},
tabBarActiveTintColor: colors.primary,
tabBarInactiveTintColor: colors.textDisabled,
tabBarLabelStyle: type.tabLabel,
```

---

## 4. Per-screen specs

> **Screen body padding:** every screen uses **18 px** left/right on its content (the `.ph-body` inner padding). Top padding varies by screen — values noted per screen.

### 4.1 Welcome / Sign in (3a)

- Background: `bgScreen` (solid, no gradient — per your spec)
- Padding: top 30, bottom 26, x 22
- Top group (centered, gap 22, marginTop 12)
  - Logo circle 96×96 (the `.bird-circle`; `bg: #000`, image cropped to circle, overflow hidden)
  - Title `displaySm` "Welcome to Flume" · 8 px below
  - Sub `body` `textMuted` "Voice typing that lands in your computer's clipboard." · max width ≈ 240, center
- Bottom group (column, gap 10)
  - Google button (light bg, see 2.1)
  - Apple button (`surface2` bg, sparkle glyph or `apple` Ionicon)
  - "Use email instead" text button (no bg)
  - Terms + Privacy caption: `bodyXs` `textDisabled`, center, Terms + Privacy in `textPrimary` (.7)

### 4.2 Onboarding (3b, three screens)

**Common:**
- Background `bgScreen`
- Three screens share the page-indicator at bottom.

**Screen 1 — "Voice to text, anywhere."**
- Brand row (top, gap 10): 28×28 logo circle + "FLUME" wordmark
- Heading `displayXL` — three lines, second word "anywhere." in `primary`. Letter-spacing −1.3.
- Sub `body` `textMuted` below.
- Primary button "Begin →".

**Screen 2 — "How it works"**
- Three steps, column gap 22.
- Each step: 38×38 numbered tile (`radius md` 10, `primarySoft` bg, primary text, `JetBrains Mono 600 14`), + title (`button` 13) + sub (`bodyXs` `textMuted`).
- Primary button "Next".

**Screen 3 — "Connect a computer"**
- "Step 3 of 3" `meta` label
- Title `displaySm` (700, 26)
- Sub `body`
- Two list rows (mac + windows) — `radius lg`, `border 1px borderStrong`, padding 14, leading 18px glyph, trailing "↓" subtle
- Primary "I'm ready to pair" + ghost "Skip for now"

### 4.3 Home / mic idle (3c)

Body padding-top 8.

- **Greeting row** (between status bar and content): "Good morning" caption + "Aman" 600/18 left · 36×36 logo circle right
- **Device chip row** (gap 6): one active chip "MacBook Pro", one resting chip "Desktop"
- **"Last sent" section**: `meta` label "Last sent" · history card (padded 14) containing quote + footer row (time/duration left, "Resend" `primary` right)
- **Flex spacer**
- **Mic group**: "Hold to speak" caption · Mic button (idle, rings)
- **Tab bar** (Record active)

### 4.4 Recording (3d)

Background: radial gradient. Reproduce in RN with **`expo-linear-gradient`** plus a translucent orange-tinted view, OR a single full-screen `LinearGradient` with center stop:

```tsx
<LinearGradient
  colors={['rgba(224,85,44,0.12)', '#0b0908']}
  locations={[0, 0.6]}
  style={StyleSheet.absoluteFill}
  // For radial-ish: use a centered RadialGradient via 'react-native-linear-gradient' or a simulated view
/>
```

A cheap approximation that looks right: one full-bleed gradient (top→bottom 12% orange → bgScreen at 60%), plus an absolute centered 240×240 circular view with `bg: primarySoft` and high `blur` (Skia or just opacity).

Layout (body padding-top 14):
- Status row: time + `● REC` (primary)
- Target chip row — centered, single active chip "→ MacBook Pro" — margin-bottom 30
- **Center column** (flex 1, center, gap 26):
  - Visualizer bars (see 2.7)
  - Timer `type.timer` "00:23"
  - Hint `bodySm` `textSubtle` "Listening — tap stop when done"
- **Controls** (row, justify space-around, padY 16):
  - Cancel (48 round + label below)
  - Stop (70 round, primary, centered/larger + label "Stop")
  - Pause (48 round + label)

Disable swipe-back; this is a modal.

### 4.5 Pasted confirmation (3e)

Body padding-top 16. Modal presentation.

- **Success header** (column, center, gap 10, marginBottom 22):
  - 56×56 success ring (`radius 50%`, `bg primarySoft`, `border 1.5px primaryBorder`, ✓ glyph primary 26 px)
  - Subtitle 18 "Pasted to MacBook"
  - `bodyXs` `textMuted` "14 sec · 38 words · 1.8s to transcribe"
- **Transcript card** (see 2.5) with `meta` "Transcript" label
- **Action rows** (column, gap 8) — three full-width tiles, each: `padY 12 padX 14 radius lg bg surface1 border borderSubtle`, leading glyph (clipboard / list / arrow-up-right), trailing nothing. Labels: "Copy again", "Edit in History", "Resend to another device".
- **Primary "Done"** at bottom.

Auto-dismiss after 3 s OR on Done.

### 4.6 History list (3f)

Body padding-top 10.

- **Header row**: "History" 20/600 · 32×32 search icon button (`surface2`, `radius 50%`)
- **Filter chips row**: "All" (active), "MacBook", "Work PC" — gap 6, marginBottom 18
- **Grouped sections**: each starts with `meta` label ("Today", "Yesterday", "Monday"...) then history cards stacked gap 8, group spacing 14.
- Card body: 1-line meta header (time + device left, "Nw" word count right `primary` .7) + 1–2 line preview (truncated). Press → 3g.
- Tab bar: History active.

### 4.7 History detail (3g)

Body padding-top 10.

- **Top bar**: back chevron + "History" left · `⋯` overflow button right (28×28, radius sm, `surface2`).
- **Meta block** (marginBottom 14): `meta` label "Today · 9:24 AM" · device row (20×20 device tile + "MacBook Pro" 13/600 + " · 14s · 38 words" meta)
- **Playback bar** (see 2.6)
- **Transcript card** (flex 1, scrollable for long content)
- **Action row** (bottom, gap 8): Ghost "Edit", Ghost "Copy", Primary "Resend" (flex 1.3 to weight it).

### 4.8 Pair new device (3h)

Body padding-top 10. Modal presentation from Settings → Devices.

- **Back row**: chevron + "Pair a computer" 14/600
- **Instruction copy** `bodySm` `textSecondary` — "Open Flume on your computer and point your camera at the code shown."
- **Viewfinder** (see 2.12) — backed by `expo-camera` `BarCodeScanner` in production
- **Helper line** `bodyXs` `textMuted`, center — "No computer? Get the app" (last 3 words `primary`)
- **Ghost button** "Enter code instead" at bottom

### 4.9 Your devices (3i)

Body padding-top 10.

- **Top bar**: back chevron + "Your devices" 16/600 · trailing 32×32 `+` add button (primary tint)
- **Section label** `meta` "Paired · 3"
- **List of device rows**, gap 8:
  - **Default** row: trailing "DEFAULT" chip (active, compact)
  - **Online secondary** row: trailing chevron
  - **Offline** row: opacity 0.75, offline dot, trailing chevron dimmed
- **Spacer (flex 1)**
- **Dashed CTA tile** at bottom: `bg primarySofter`, `border 1px dashed primaryDashed`, leading 26×26 `+` in primary disc, label "Pair another device" `primary` 600/12. Press → 3h.

---

## 5. Assets

| Asset                  | Spec                                                                                  |
|------------------------|---------------------------------------------------------------------------------------|
| **Bird logo (dark)**   | `assets/flume-mark-dark.png` — current `Gemini_Generated_Image_vdyoynvdyoynvdyo.png`. Square crop the bird+branch tightly (you currently have 1408×768 with black bg; for in-app use, export a square PNG ≥ 512×512 OR have the designer deliver an SVG). Round mask in code; do not bake the circle into the asset. |
| **Bird logo (light)**  | TBD for light theme.                                                                  |
| **Brand wordmark**     | Set as text — Geist 600, letter-spacing 0.5 px. No image needed.                       |
| **Icons**              | Ionicons (already in Expo). Mapping below.                                            |

### 5.1 Icon mapping (Ionicons)

| Use                | Ionicon                |
|--------------------|------------------------|
| Mic                | `mic`                  |
| Stop               | `stop` (or filled square) |
| Pause              | `pause`                |
| Cancel / close     | `close`                |
| Back               | `chevron-back`         |
| Chevron right      | `chevron-forward`      |
| Search             | `search`               |
| Settings (tab)     | `settings-outline`     |
| History (tab)      | `time-outline` or `list-outline` |
| Record (tab)       | `mic-outline`          |
| Apple              | `logo-apple`           |
| Email              | `mail-outline`         |
| Clipboard          | `copy-outline`         |
| Resend / send-to   | `paper-plane-outline`  |
| Add device         | `add`                  |
| Laptop             | `laptop-outline`       |
| Desktop            | `desktop-outline`      |
| Phone              | `phone-portrait-outline` |
| Lock (privacy)     | `lock-closed-outline`  |
| Online dot         | render `View` w/ `colors.online` |

### 5.2 Haptics

Use `expo-haptics`. **Restrained — only on these moments**:

| Event                    | Haptic                                  |
|--------------------------|-----------------------------------------|
| Tap mic (start record)   | `ImpactFeedbackStyle.Medium`            |
| Tap stop (success)       | `NotificationFeedbackType.Success`      |
| Tap cancel               | `ImpactFeedbackStyle.Light`             |
| Pair success             | `NotificationFeedbackType.Success`      |
| Filter chip toggle       | `Selection`                             |
| Device chip toggle       | `Selection`                             |

Do NOT haptic on every list tap.

---

## 6. Microcopy used in the wireframes

Lift these verbatim for v1:

- Welcome (3a) title: **"Welcome to Flume"** · sub: **"Voice typing that lands in your computer's clipboard."**
- Onboarding 1 hero: **"Voice / to text, / anywhere."** (line breaks intentional)
- Onboarding 1 sub: **"Speak into your phone. Watch it appear on your laptop."**
- Onboarding 2 steps: **Speak** "Hold the mic, talk freely" / **Transcribe** "Words appear in seconds" / **Paste** "Lands in your computer"
- Onboarding 3 title: **"Connect a computer."** · sub: **"Install Flume on Mac or Windows. You'll pair it next."**
- Home greeting: **"Good morning"** + first name
- Home CTA: **"Hold to speak"**
- Recording hint: **"Listening — tap stop when done"**
- Recording target chip: **"→ MacBook Pro"** (arrow before name)
- Confirmation title: **"Pasted to MacBook"** · sub format: `{Ns} · {Nw} words · {Ns} to transcribe`
- Pair instruction: **"Open Flume on your computer and point your camera at the code shown."**
- Pair help: **"No computer? Get the app"**
- Devices header: **"Your devices"** · section: **"Paired · {N}"**
- Devices empty add tile: **"Pair another device"**

---

## 7. State + behavior notes

- **Single-device routing locked at record-time**: the active chip on Home (3c) and Recording (3d) is set BEFORE pressing the mic. If you ever support multi-device, the chip becomes multi-select but otherwise the recording screen design doesn't change.
- **No transcription review step**: 3e is a confirmation, not an editor. The only edit path is via History detail (3g).
- **Auto-dismiss confirmation**: 3e dismisses after ~3 s OR on Done, returning the user to Home (3c).
- **Default device**: the device shown on the Home chip is whichever device in `Devices` (3i) has `isDefault: true`. Tapping a non-default chip on home re-targets the next recording (does not change the default).
- **Offline devices** are listed but visually dimmed (opacity 0.75) and cannot be the recording target — chip is disabled.
- **History grouping**: by calendar day (`Today`, `Yesterday`, then weekday name, then full date once older than 7 days).
- **Pairing code expiry**: shown on the compute-side; the phone side just scans. If QR fails, fall back to numeric pairing code.

---

## 8. Implementation checklist (incremental)

**Phase 1 — Tokens + primitives**
- [ ] Install `expo-google-fonts/geist` and `expo-google-fonts/jetbrains-mono`
- [ ] Create `theme/{colors,typography,spacing,radius,shadow,motion}.ts`
- [ ] Create primitives: `<Text variant="...">`, `<Button>`, `<Card>`, `<Chip>`, `<IconButton>`, `<ListRow>`

**Phase 2 — Auth + onboarding**
- [ ] Screen `3a` (Welcome / sign in) — wire Google sign-in (`expo-auth-session` w/ Google provider)
- [ ] Screens `3b/1`, `3b/2`, `3b/3` (onboarding) + page indicator
- [ ] Persist `hasOnboarded` in `expo-secure-store`

**Phase 3 — Record loop**
- [ ] Tab nav (Record · History · Settings)
- [ ] Screen `3c` (Home idle) — load default device + last transcription
- [ ] Screen `3d` (Recording) — `expo-av` audio recorder + Reanimated bars (see 2.7)
- [ ] Wire transcription (cloud upload OR on-device)
- [ ] Screen `3e` (Confirmation) — auto-dismiss

**Phase 4 — History**
- [ ] Screen `3f` (list) — grouped sections, filter chips, swipe-to-delete optional
- [ ] Screen `3g` (detail) — `expo-av` playback for the audio + waveform render

**Phase 5 — Devices**
- [ ] Screen `3i` (Your devices) — list, default toggle, online/offline status
- [ ] Screen `3h` (Pair) — `expo-camera` + `BarCodeScanner`, fallback numeric code input

**Phase 6 — Polish**
- [ ] Haptics per §5.2
- [ ] Empty states + offline states
- [ ] Settings screens (TBD — design next)
- [ ] Light theme (TBD — design next)

---

## 9. What is NOT in this handoff

If you see these elsewhere they were not designed:
- A Canvas tab
- A Notes tab
- Long-press card context menus
- A 40-bar dense waveform on recording
- A bottom tab bar of 5 tabs
- Mic button size 88 (it's 92)
- A transcription review/edit step between record and paste

If your existing app has those concepts and they should be merged, treat the Flume screens as a feature module slotted into your existing nav, not a wholesale replacement.

---

## 10. Reference

- Wireframe: `Flume Wireframes.dc.html` — screens are anchored at `#3a` through `#3i`.
- Standalone export: `Flume Wireframes.html` (offline-ready).
- Logo source: `uploads/Gemini_Generated_Image_vdyoynvdyoynvdyo.png`.
