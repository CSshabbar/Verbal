# Flume — Claude Code Prompt

Paste this as your system message / rules file for every session with Claude Code. It bundles every rule the design assumes — colors, fonts, spacing, icons, sizing — so you don't have to re-explain.

---

## Ground rules
- Never hardcode a color, size, radius, or spacing value. Import from the tokens below.
- Never use system font. Never use lucide-react-native or Ionicons.
- All wireframe pt values are drawn in a 280pt phone frame. Multiply by **1.35** for real device pt (per `SCALING_GUIDE.md`).
- If a value you need is not in tokens, STOP and ask — do not invent one.

---

## Colors (exact hex)

```ts
export const colors = {
  // Backgrounds
  bg:            '#0e1012',   // app background (dark)
  bgLight:       '#f4f4f5',   // app background (light / keyboard)
  surface:       '#17191c',   // cards, list rows (dark)
  surface2:      '#1a1c1f',   // keyboard overlay panel (dark)
  surface3:      '#26282b',   // rows inside overlay panel (dark)
  surfaceLight:  '#ffffff',   // cards (light)
  keyboardBar:   '#ebebed',   // Flume bar bg (light)
  keyboardBarD:  '#141618',   // Flume bar bg (dark)
  titleBar:      '#0a0c0e',   // desktop title bar

  // Text
  text:          '#f2f2f2',   // primary text (dark)
  textLight:     '#141416',   // primary text (light)
  textMuted:     'rgba(240,240,240,0.55)',
  textMutedL:    'rgba(20,20,22,0.55)',
  textFaint:     'rgba(240,240,240,0.4)',
  textFaintL:    'rgba(20,20,22,0.4)',

  // Brand
  primary:       '#C85A3E',   // terracotta — THE accent
  primaryOn:     '#0e1012',   // text/icon on primary
  primaryTint:   'rgba(200,90,62,0.14)',
  primaryEdge:   'rgba(200,90,62,0.35)',

  // Feature card pastels (desktop dashboard)
  cream:         '#EADFCE',
  sage:          '#DDE4D3',
  mauve:         '#e6dae4',

  // Status
  online:        '#4ad15a',
  onlineTint:    'rgba(74,209,90,0.10)',
  onlineEdge:    'rgba(74,209,90,0.35)',
  error:         '#d95a55',
  errorTint:     'rgba(217,90,85,0.28)',

  // Device tags
  iphone:        '#C85A3E',
  ipad:          '#4a6494',

  // Borders / dividers
  border:        'rgba(240,240,240,0.06)',   // hairlines (dark)
  borderStrong:  'rgba(240,240,240,0.1)',
  borderLight:   'rgba(20,20,22,0.08)',
  borderLightS:  'rgba(20,20,22,0.1)',

  // Highlight (active button on keyboard)
  activeLight:   'rgba(20,20,22,0.09)',
  activeDark:    'rgba(240,240,240,0.1)',
};
```

---

## Fonts

```ts
// Install once:
//   npx expo install @expo-google-fonts/geist @expo-google-fonts/jetbrains-mono expo-font

export const fonts = {
  ui:      'Geist_400Regular',
  uiMed:   'Geist_500Medium',
  uiSemi:  'Geist_600SemiBold',
  uiBold:  'Geist_700Bold',
  mono:    'JetBrainsMono_500Medium',
  monoSemi:'JetBrainsMono_600SemiBold',
};
```

- **Geist** — every piece of UI text
- **JetBrains Mono** — numbers, timers, uppercase meta labels (`METADATA · 2 MIN AGO`), keyboard shortcut chips (`⌘⌥␣`)

Never fall back to system. If a font isn't loaded yet, show a splash — don't render.

---

## Type scale (already ×1.35 for real device)

```ts
export const type = {
  displayXL:  { family: fonts.uiBold, size: 60, lh: 57, ls: -1.8 },
  display:    { family: fonts.uiBold, size: 49, lh: 49, ls: -1.5 },
  displaySm:  { family: fonts.uiSemi, size: 35, lh: 39, ls: -0.7 },
  title:      { family: fonts.uiSemi, size: 30, lh: 34 },
  titleSm:    { family: fonts.uiSemi, size: 27, lh: 32 },
  subtitle:   { family: fonts.uiSemi, size: 24, lh: 30 },
  bodyLg:     { family: fonts.uiMed,  size: 19, lh: 27 },
  body:       { family: fonts.ui,     size: 17, lh: 25 },
  bodySm:     { family: fonts.ui,     size: 17, lh: 25 },
  bodyXs:     { family: fonts.ui,     size: 15, lh: 21 },
  button:     { family: fonts.uiSemi, size: 17, lh: 21 },
  buttonSm:   { family: fonts.uiMed,  size: 16, lh: 19 },
  label:      { family: fonts.uiMed,  size: 15, lh: 19 },
  caption:    { family: fonts.ui,     size: 14, lh: 18 },
  tabLabel:   { family: fonts.uiMed,  size: 12, lh: 14 },

  timer:      { family: fonts.monoSemi, size: 56, lh: 58, ls: -1 },
  code:       { family: fonts.mono,     size: 27, lh: 30 },
  meta:       { family: fonts.mono,     size: 13, lh: 15, ls: 1.4, upper: true },
  metaSm:     { family: fonts.mono,     size: 12, lh: 14, ls: 0.6, upper: true },
  wordmark:   { family: fonts.uiSemi,   size: 17, lh: 19, ls: 0.7 },
};
```

---

## Spacing (×1.35)

```ts
export const space = {
  xs:   6,   s:  11,   m:  16,   base: 22,
  l:    24,  lg: 30,   xl: 38,   xxl:  48,   xxxl: 64,
};

export const radius = {
  xs:  8,   sm: 11,   md: 14,   lg: 16,
  xl:  18,  xxl: 24,  pill: 999,
};
```

---

## Icons

- Library: **`react-native-svg`** — inline `<Svg>` + `<Path>` per icon. Do not use lucide/Ionicons/Material.
- Stroke: **1.6–1.8** width, `strokeLinecap="round"`, `strokeLinejoin="round"`, `fill="none"` unless the icon is intentionally filled (mic when recording, star when starred).
- Standard size: **22** (list rows, tab bar), **14** (inline in cards), **26** (recording controls). Never smaller than 12.
- Use `currentColor` via the `color` prop so the icon inherits text color.

Full icon source is in the wireframe file — copy the `<svg>` paths directly, don't redraw.

---

## Component patterns

- **Cards**: `bg = surface` (dark) / `surfaceLight` (light), `border = border` / `borderLight`, `radius = md`, `padding = m`.
- **Chips / status pills**: `radius = pill`, `padding = 6px 11px`, `font = tabLabel`, dot 6px if it has one.
- **Primary button**: `bg = primary`, `color = primaryOn`, `radius = md`, `padding = 13px 18px`, `font = button`.
- **Meta labels** (`RECEIVED TODAY`, `9:24 AM · MACBOOK`): use `type.meta`, letter-spacing baked in, always uppercase, `textMuted` color.
- **Active keyboard button**: `bg = activeLight` (light) / `activeDark` (dark). NEVER solid black.
- **Selected list row** (History, Notes): `bg = primaryTint`, `border = 1px solid primaryEdge`.

---

## Sizing / density rules

- Real phone width ≈ 390pt. Wireframes are 280pt. Multiply linear pt values by **1.35** when copying from wireframes.
- Mic idle: **120pt**. Icon buttons: **64pt**. Tab bar height: **78 + safeAreaBottom**.
- Body copy floor: **17pt**. Never smaller.
- See `SCALING_GUIDE.md` §2 for the full override list.

---

## Reference files (this repo)

- `Flume Wireframes.dc.html` — canonical designs. Find your screen by anchor id (`#1a`, `#9a`, `#27c`, `#28a`, etc). Every measurement is drawn.
- `DESIGN_SYSTEM.md` — text descriptions of components with dimensions.
- `SCALING_GUIDE.md` — how to size on real devices.
- `IMPLEMENTATION_GUIDE.md` — architecture / navigation setup.

---

## Working prompt (paste per screen)

> Build `<screen name>` matching the reference. Import all values from `flume-ui/theme/tokens.ts`. Use Geist for UI, JetBrains Mono for numbers/meta. Icons are inline react-native-svg with 1.6–1.8 stroke, round caps. Match the wireframe pixel-for-pixel; if a value isn't in tokens, ask before hardcoding. Reference: `Flume Wireframes.dc.html` anchor `#<id>`.
