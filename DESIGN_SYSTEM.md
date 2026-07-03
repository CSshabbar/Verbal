# Flume — Unified Design System

**One design system, three surfaces: mobile, desktop app, menubar + widget.**

There is **no separate "mobile theme" and "desktop theme"**. There is one system, and each platform picks the right variant of each token. This doc is the authoritative source for both `flume-ui/` (React Native) and `flume-desktop/` (Electron). If a developer ever has to decide "what should this be" — the answer is in this file.

---

## 1. What varies between platforms — and what doesn't

| Concern             | Mobile           | Desktop            | Menubar / Widget       | Same across? |
| ------------------- | ---------------- | ------------------ | ---------------------- | ------------ |
| **Colors**          | `colors.*`       | `colors.*`         | `colors.*`             | ✅ Identical |
| **Fonts**           | Geist + JBM      | Geist + JBM        | Geist + JBM            | ✅ Identical |
| **Type scale**      | `type.mobile.*`  | `type.desktop.*`   | `type.desktop.*`       | ⚠ Same names, different sizes |
| **Radii**           | `radius.*`       | `radius.*`         | `radius.*`             | ✅ Identical |
| **Icons**           | 1.6 stroke line  | 1.6 stroke line    | 1.6 stroke line        | ✅ Identical |
| **Spacing scale**   | `space.*`        | `space.*`          | `space.*`              | ✅ Identical |
| **Card treatment**  | `#17191c` + 1px  | `#17191c` + 1px    | `#17191c` + 1px        | ✅ Identical |
| **Feature cards**   | Cream/sage pastels| Cream/sage pastels| Cream/sage (rare)      | ✅ Identical |
| **Layout**          | Stacked columns  | Sidebar + main     | Compact popover/pill   | ❌ Different |
| **Nav pattern**     | Bottom 5-icon    | Left sidebar       | Row of quick actions   | ❌ Different |

**Rule of thumb:** tokens are shared, layouts differ. If you're changing a color or a font size, it should ripple to all three surfaces. If you're changing a nav position or a card row into a grid, it stays platform-specific.

---

## 2. Colors (one palette, three surfaces)

```ts
// theme/colors.ts — used by mobile, desktop, widget
export const colors = {
  bgCanvas:      '#14110f',      // outermost app background (rare)
  bgScreen:      '#0e1012',      // primary screen bg — the near-black
  bgChrome:      '#0a0c0e',      // desktop title bar + sidebar bg
  surface1:      '#17191c',      // resting card surface (also list rows)
  surface2:      'rgba(240,240,240,0.06)',  // chip / icon-button bg
  surface3:      'rgba(240,240,240,0.08)',  // hover / pressed
  scrim:         'rgba(0,0,0,0.55)',

  borderSubtle:  'rgba(240,240,240,0.05)',
  borderDefault: 'rgba(240,240,240,0.08)',
  borderStrong:  'rgba(240,240,240,0.12)',
  borderDashed:  'rgba(240,240,240,0.16)',

  textPrimary:   '#f2f2f2',
  textSecondary: 'rgba(240,240,240,0.65)',
  textMuted:     'rgba(240,240,240,0.55)',
  textSubtle:    'rgba(240,240,240,0.45)',
  textDisabled:  'rgba(240,240,240,0.30)',

  primary:       '#C85A3E',      // terracotta accent (ONLY brand color)
  primaryInk:    '#0e1012',
  primarySoft:   'rgba(200,90,62,0.14)',
  primarySofter: 'rgba(200,90,62,0.06)',
  primaryBorder: 'rgba(200,90,62,0.35)',
  primaryDashed: 'rgba(200,90,62,0.32)',
  primaryAccent: '#f0b39a',      // primary text on primarySoft bg
  primaryInkAlt: '#fff5ea',      // text on solid primary

  // Feature-card pastels (only used for the 2-3 dashboard cards)
  cream:         '#EADFCE',
  creamInk:      '#2a1f18',
  creamDisc:     '#1a1512',      // dark disc icon inside cream card
  sage:          '#DDE4D3',
  sageInk:       '#1e2418',
  sageDisc:      '#1e2418',
  plum:          '#e6dae4',
  plumInk:       '#221820',
  plumDisc:      '#221820',

  // Semantic
  online:        '#4ad15a',
  onlineSoft:    'rgba(74,209,90,0.10)',
  onlineBorder:  'rgba(74,209,90,0.32)',
  onlineAccent:  '#8ee69a',
  offline:       'rgba(240,240,240,0.30)',
  recording:     '#C85A3E',

  // Device chip badge colors (when tagging which device)
  tagIPhone:     '#C85A3E',      // reuses primary
  tagIPhoneInk:  '#fff5ea',
  tagIPad:       '#4a6494',      // slate blue
  tagIPadInk:    '#eaf1ff',
  tagWorkPC:     '#4a6494',      // same as iPad by default; override per user
  tagWorkPCInk:  '#eaf1ff',
} as const;
```

**Terracotta rule:** `#C85A3E` is the ONLY brand color. It appears as small tag pills, active pill on segmented controls (mobile), active nav item highlight (rare), the record button, and the accent inside cream cards. Never use it for a whole card background. Never use it for body text. Never introduce a second accent color without updating this doc.

---

## 3. Typography

**Same families everywhere.** Sizes scale by surface.

```ts
export const fonts = {
  regular:  'Geist_400Regular',
  medium:   'Geist_500Medium',
  semibold: 'Geist_600SemiBold',
  bold:     'Geist_700Bold',
  mono:     'JetBrainsMono_500Medium',
  monoBold: 'JetBrainsMono_600SemiBold',
} as const;
```

### 3.1 Type scale — mobile (React Native, `flume-ui/`)

| Variant       | Size | Line | Weight  | Where |
| ------------- | ---- | ---- | ------- | ----- |
| displayXL     | 42   | 40   | 700     | Onboarding hero |
| displaySm     | 24   | 28   | 600     | Welcome title |
| titleSm       | 24   | 28   | 600     | Screen titles (History, Notes, Canvas) |
| subtitle      | 18   | 22   | 600     | Confirmation subtitle |
| featureNum    | 22   | 24   | 600     | "2 online" / "24 notes" on feature cards |
| featureLabel  | 13   | 16   | 600     | Card label under number |
| bodyLg        | 15   | 20   | 600     | "Hi, Aman" greeting |
| button        | 13   | 16   | 600     | Primary/ghost buttons |
| buttonSm      | 12   | 15   | 500     | Text buttons |
| cardTitle     | 14   | 18   | 600     | Recent card title |
| cardTitleLg   | 17   | 21   | 600     | Featured Notes card title |
| body          | 12.5 | 19   | 400     | Card preview text |
| bodyXs        | 11   | 15   | 400     | Card sub / muted copy |
| label         | 11   | 14   | 500     | Small helper labels |
| tagPill       | 10.5 | 13   | 600     | Device tag chips |
| pill          | 12   | 15   | 500     | Segmented pills |
| pillActive    | 12   | 15   | 600     | Segmented pill (selected) |
| meta          | 10.5 | 13   | 400     | Timestamp meta (Today · 9:24 AM) |
| metaCode      | 10   | 12   | 500     | JBM meta (SENT · TODAY · etc.), `letter-spacing: 1.4px` uppercase |
| metaCodeSm    | 9.5  | 12   | 500     | JBM meta small |
| timer         | 44   | 44   | 300 mono| Recording timer 00:23 |
| timerWidget   | 15   | 18   | 500 mono| Widget-embedded timer |
| code          | 20   | 22   | 500 mono| Pairing code cells |

### 3.2 Type scale — desktop (Electron, `flume-desktop/`)

Desktop CAN afford slightly bigger heroes but keeps body sizes similar because users sit further from the screen. The visual weight matches mobile.

| Variant       | Size | Line | Weight  | Where |
| ------------- | ---- | ---- | ------- | ----- |
| pageTitle     | 22   | 26   | 600     | "Aman" / "Paired devices" / "Preferences" |
| pageEyebrow   | 11   | 14   | 400     | "Good morning" / "General" |
| sectionTitle  | 12.5 | 16   | 600     | "Paste behavior" / "Hotkeys" |
| sectionSub    | 11   | 15   | 400     | Section descriptions |
| navHeading    | 10   | 12   | 500 mono| "WORKSPACE" / "DEVICES" nav headings |
| navItem       | 12   | 15   | 500     | Sidebar nav items |
| navItemActive | 12   | 15   | 600     | Sidebar nav item (selected) |
| featureNum    | 20   | 24   | 600     | "6 today" / "1 draft" |
| featureLabel  | 12   | 15   | 600     | Card label |
| featureSub    | 11   | 14   | 400     | Card sub |
| listTitle     | 14   | 18   | 600     | "Received today" |
| listItem      | 11.5 | 16   | 400     | List row body |
| listTime      | 10.5 | 13   | 500 mono| Row timestamp |
| tagPill       | 9.5  | 12   | 600     | Device tag (smaller than mobile) |
| statusPill    | 10.5 | 13   | 600     | Online/Offline pill |
| kbd           | 10.5 | 13   | 500 mono| Hotkey chips ⌘⌥␣ |
| titleBar      | 11.5 | 14   | 500     | Window title bar |
| version       | 10   | 12   | 500 mono| Version label bottom of sidebar |

### 3.3 Type scale — menubar + widget

Menubar and widget copy is DESKTOP sized. There's no "third scale" — use desktop values above. Notable ones:

| Where | Variant used |
| ----- | ------------ |
| Menubar app name "Flume" | `sectionTitle` (12.5/600) |
| Menubar status "Ready · iPhone 15" | `sectionSub` (11/400) |
| Menubar recent row title | `listItem` (11.5/400) |
| Menubar "Start recording" button | `sectionTitle` (12/600) |
| Widget primary text "Hold on iPhone 15…" | `sectionTitle` (12/600) |
| Widget helper "Or press ⌘⌥␣ here" | `featureSub` (10.5/400) |
| Widget timer "00:23" | `timerWidget` (15/500 mono) |
| Widget device label "IPHONE 15" | `metaCodeSm` (9.5/500 mono, uppercase, letter-spacing .08em) |

---

## 4. Spacing + radius

**Identical everywhere.**

```ts
export const space = {
  px: 1, xs: 4, s: 8, m: 12, base: 16, l: 18, lg: 22, xl: 28, xxl: 36, xxxl: 48,
};

export const radius = {
  xs: 6, sm: 8, md: 10, lg: 12, xl: 14, xxl: 18, pill: 999,
};
```

**Which radius to use where — memorize this:**

| Element                                     | Radius |
| ------------------------------------------- | ------ |
| Small tag / device chip                     | 7      |
| Kbd chip (⌘, ⌥ etc)                         | 6      |
| Icon disc inside feature card               | 50%    |
| Round icon button (16, 22, 26, 32, 34, 48px diameter) | 50%    |
| Small action tile (grid icon in feature card) | 10     |
| List row / recent card / device row / transcript card | 16 (mobile), 12 (desktop) |
| Featured card / note editor cover           | 18 (mobile), 14 (desktop) |
| Primary CTA button                          | 14 |
| Segmented pill                              | 999 (pill) |
| Status pill (Online/Offline)                | 999 |
| QR viewfinder outer                         | 20 |
| QR viewfinder inner (border)                | 14 |
| macOS window                                | 12 |
| Menubar popover                             | 14 |
| Recording widget                            | 16 |
| Toggle track                                | 9 |
| Toggle handle                               | 50% |

---

## 5. Icons

**All icons are line SVG, `stroke-width="1.6"`, `stroke-linecap="round"`, `stroke-linejoin="round"`, `fill="none"` unless explicitly filled.** Colors via `currentColor` so they inherit from parent.

Sizes by context:

| Context                                | Icon size |
| -------------------------------------- | --------- |
| Tab bar (mobile)                       | 22 |
| Sidebar nav item (desktop)             | 15 |
| Round icon button 34px (header)        | 16 |
| Round icon button 30–32px (feature card top-right ›) | 10–11 |
| Feature card top-left disc (32×32)     | 14–15 |
| List row / card ellipsis (26×26 tile)  | 13 |
| Kbd inside chip                        | 10 |
| Recording widget mic disc              | 14 |
| Confirmation success check             | 26 |
| Onboarding step number tile            | 13 (JBM text, not icon) |
| Menubar recent-row icons               | 13 |

Store icon SVG paths as a single map. See §12 for the full set.

---

## 6. Layout tokens — per platform

### 6.1 Mobile screen anatomy

```
┌────────────────── 280 pt wide (wireframe) — 390 pt on device ──┐
│ status bar          32 pt high                                  │
│ body content        padding 18px sides, 14px top, 18px bottom   │
│                                                                 │
│ …                                                               │
│                                                                 │
│ tab bar             padding 14px 22px 20px · 5 icons · 22px     │
└──────────────────────────────────────────────────────────────────┘
```

The `1.35× scale` from the earlier SCALING_GUIDE.md is now baked into the mobile type scale above. Do not multiply again in code.

### 6.2 Desktop window anatomy

```
┌────────────────── 720 × 480 (minimum) ─────────────────────────┐
│ title bar            36 pt · traffic lights left · title center │
├── sidebar 196 ──┬──────────── main ────────────────────────────┤
│ padding 16×10   │  padding 24×26                                │
│ logo row + name │  page eyebrow + page title                    │
│ nav sections    │  cards / lists / forms                        │
│ (Workspace,     │                                               │
│  Devices)       │                                               │
│ ────            │                                               │
│ user footer     │                                               │
└─────────────────┴───────────────────────────────────────────────┘
```

Minimum window: **720 × 480**. Default: **900 × 600**. Sidebar is always 196 wide, non-resizable. Title bar is always 36 tall. macOS traffic lights top-left, Windows title bar controls top-right — the sidebar accommodates both.

### 6.3 Menubar popover

```
Width  340 px  (fixed)
Height auto — grows with content, cap ≈ 500 px then scroll internally
Position anchored to the menubar icon
Radius 14
Border 1px rgba(240,240,240,0.08)
Shadow 0 24px 48px rgba(0,0,0,0.6)
Bg     #131518 (slightly warmer than #0e1012 to feel like a floating surface)
```

Structure: header (14px pad, logo+name+status+listening toggle) · quick action row · Recent list (max 3 items) · footer row (Open window / Preferences / Quit).

### 6.4 Recording widget

```
Width  420 px  (fixed)
Height 60 px   (fixed for idle/active/done states)
Position bottom-center of the main display OR near cursor (user preference)
Radius 16
Border 1px rgba(240,240,240,0.08)  · state variants change border color
Shadow 0 18px 40px rgba(0,0,0,0.5)
Bg     rgba(14,16,18,0.85–0.9) + backdrop-filter: blur(14px)
```

**State variants** (border color changes, everything else stays):
- **Idle** — border `rgba(240,240,240,0.08)`, mic disc bg `surface2`
- **Recording** — border `primaryBorder` (`rgba(200,90,62,0.28)`), mic disc solid `primary` with ring shadow `0 0 0 5px rgba(200,90,62,0.15)`
- **Done** — border `rgba(74,209,90,0.28)`, mic disc → check icon in `onlineSoft` ring

The widget NEVER exceeds 60 px tall. If you need more content, it opens the main window.

---

## 7. Component sizing — cross-platform reference

The same conceptual component may take different pixel sizes on each surface. This table locks that:

| Component                       | Mobile     | Desktop      | Widget     |
| ------------------------------- | ---------- | ------------ | ---------- |
| Logo circle (in header)         | 34         | 24 (sidebar) | 28 (menubar hdr) |
| Logo circle (in Welcome hero)   | 100        | —            | — |
| Round icon button (header)      | 34         | 32           | — |
| Round icon button (in-card ›)   | 22         | —            | 26 (close X) |
| Mic control (recording)         | 64 (stop)  | —            | 34 (widget)|
| Mic tab-bar icon                | 22         | —            | — |
| Feature card (dashboard tile)   | full-width /2 in a row of 2 | full-width /3 in a row of 3 | — |
| Feature card padding            | 14         | 14           | — |
| Feature card top-left disc      | 32×32      | 30×30        | — |
| Recent list card padding        | 14         | 11 × 13      | 8 (menubar) |
| Recent list card radius         | 16         | 10           | 8 |
| List row height                 | ~72        | ~44          | ~40 |
| Segmented pill                  | 9×15–18    | (rare)       | (rare) |
| Kbd chip                        | —          | 3×8, radius 6| 1×5, radius 4 (in-context) |
| Toggle track                    | 32×18      | 32×18        | 32×18 |
| Tab bar height (safe-area excl) | 62         | —            | — |
| Sidebar nav item height         | —          | ~30          | — |
| Waveform bar (recording screen) | 4 wide, gap 5, 10 bars | — | 2.5 wide, gap 3, 12 bars |

---

## 8. When to use each surface

Decision tree for developers building a feature.

**Something the user actively does?**
1. Is it a **daily action** (record, review latest, quick paste)?
   → **Mobile primary**, **menubar** secondary (mirror the quick action).
2. Is it a **setup / preferences / bulk-review** action (pair a device, change hotkeys, browse full history)?
   → **Desktop app primary**, mobile has a subset in Settings tab.
3. Is it a **live confirmation / status** (recording in progress, just-pasted feedback)?
   → **Recording widget primary**. Mobile confirmation screen mirrors it briefly.

**Rules of thumb:**

- **Anything that requires typing/pasting long content** → desktop app (bigger scroll surface).
- **Anything you'd do one-handed while walking** → mobile.
- **Anything that must be visible at-a-glance without opening a window** → menubar.
- **Anything that must show state during a live capture** → widget.

**Do NOT:**

- Rebuild the mobile "Home dashboard" as its own desktop screen. Desktop's "Home" is a dashboard, not a mic — the mic action lives in the menubar + widget.
- Put full settings in the menubar. Menubar shows quick toggles; deep settings live in the desktop window.
- Put the recording widget inside the desktop window. It's a top-level floating surface only.

---

## 9. Which platform gets which feature

| Feature                       | Mobile | Desktop app | Menubar | Widget |
| ----------------------------- | :----: | :---------: | :-----: | :----: |
| Sign in                       | ✅     | ✅          | —       | —      |
| Onboarding                    | ✅     | ✅ (short)  | —       | —      |
| Record voice                  | ✅ primary | —       | trigger | active state |
| Live transcription visualizer | ✅     | —           | —       | ✅ (compact) |
| See last transcription        | ✅ Home| ✅ Home     | ✅ top  | ✅ done state |
| Full history                  | ✅     | ✅ primary  | last 3  | —      |
| Edit a transcript             | ✅     | ✅ (better) | —       | —      |
| Notes list + editor           | ✅     | ✅          | —       | —      |
| Canvas (drop & send)          | ✅ primary| ✅ receive | —      | —      |
| Pair a device                 | ✅ scan| ✅ show QR  | —       | —      |
| Manage paired devices         | ✅     | ✅ better   | —       | —      |
| Change hotkeys                | —      | ✅          | —       | —      |
| Change paste behavior         | —      | ✅          | —       | —      |
| Sign out                      | ✅     | ✅          | ✅      | —      |
| Toggle listening on/off       | ✅     | ✅          | ✅ big  | —      |

**The menubar is the "always-on-top mini Flume."** It should never require a scroll (except the recent list) and should never lock focus.

---

## 10. Adding a new screen — checklist

Before you draw anything, answer:

1. **Which surface(s)?** (see §8)
2. **What's the layout skeleton?** (mobile: full-screen · desktop: sidebar+main · menubar: 340 wide popover · widget: 420×60 pill)
3. **What tokens does it use?** — should all come from `theme/*` files, zero inline hex.
4. **Does it match an existing pattern?** — reuse `Card`, `ListRow`, `Chip`, `Button`, `IconButton`, `Text` primitives from `flume-ui/components/`. Don't invent parallel components on desktop; port these instead.
5. **Icons?** — use the shared set from §5, don't introduce new visual style.

If you catch yourself:
- Hardcoding a color → **stop**, put it in `colors.*`.
- Using a font size not in the type scale → **stop**, pick the closest existing variant or extend the scale in `typography.ts`.
- Adding a new radius value → **stop**, use one of the seven in `radius.*`.
- Using an emoji as an icon → **stop**, use the line-SVG set.

---

## 11. Cross-platform code organization

Recommended repo layout when you build the desktop:

```
verbal-mobile/
├── packages/
│   ├── theme/               ← shared, imported by BOTH apps
│   │   ├── colors.ts
│   │   ├── typography.ts    ← exports type.mobile + type.desktop
│   │   ├── spacing.ts       ← space + radius
│   │   ├── icons.tsx        ← every icon component (renders SVG)
│   │   └── index.ts
│   ├── flume-ui/            ← React Native + Expo (mobile)
│   │   ├── components/
│   │   ├── screens/
│   │   ├── hooks/
│   │   └── navigation/
│   └── flume-desktop/       ← Electron + React (or Tauri) (desktop)
│       ├── main/            ← Electron main process
│       ├── renderer/
│       │   ├── windows/
│       │   │   ├── Main/    ← 720×480 window
│       │   │   ├── Menubar/ ← 340×~500 popover
│       │   │   └── Widget/  ← 420×60 always-on-top
│       │   ├── components/
│       │   └── hooks/
│       └── package.json
```

**The critical rule:** `packages/theme/*` is the ONLY place colors, type sizes, radii, and icon paths are defined. Both apps import from there. If you fork `colors.ts` between packages, the design system dies within a month.

### 11.1 How mobile and desktop share the theme in practice

Mobile (`flume-ui/`) already has `theme/*.ts` — those files should be moved into `packages/theme/` (or symlinked). Desktop imports them the same way:

```ts
// flume-desktop/renderer/windows/Main/HomeScreen.tsx
import { colors, type, space, radius } from '@flume/theme';
// use `type.desktop.pageTitle` on desktop; mobile uses `type.mobile.titleSm`
```

If you can't share a package (e.g. platform build constraints), keep the values IDENTICAL and add a CI check that greps for hex/rgba literals inside `flume-desktop/` and fails if any are found outside the theme file.

---

## 12. Icon set (canonical)

Every icon in the Flume UI is one of the below. Never introduce a new icon without adding it here first. All rendered as `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">`.

| Name       | Path                                                                                          |
| ---------- | --------------------------------------------------------------------------------------------- |
| home       | `M3 11 12 3l9 8 M5 10v10h14V10`                                                              |
| list       | `M4 6h16M4 12h16M4 18h10`                                                                     |
| mic        | `M9 3h6a3 3 0 0 1 3 3v9a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3z M19 11v1a7 7 0 0 1-14 0v-1 M12 19v3` |
| grid       | 4 × `<rect x=? y=? width="7" height="7" rx="1.2"/>` at (3,3)(14,3)(3,14)(14,14)               |
| clock      | `<circle cx="12" cy="12" r="9"/>` + `M12 7v5l3 2`                                            |
| gear       | `<circle cx="12" cy="12" r="3"/>` + `M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4` |
| bell       | `M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9` + `M10 21a2 2 0 0 0 4 0`                        |
| search     | `<circle cx="11" cy="11" r="7"/>` + `m20 20-3.5-3.5`                                         |
| dots       | 3× `<circle cx="?" cy="12" r=".9"/>` at x=5,12,19                                            |
| chevron-r  | `m9 6 6 6-6 6`                                                                                |
| chevron-l  | `m15 6-6 6 6 6`                                                                               |
| check      | `M20 6 9 17l-5-5`                                                                             |
| close      | `M18 6L6 18M6 6l12 12`                                                                        |
| plus       | `M12 5v14M5 12h14`                                                                            |
| chat       | `M21 12a9 9 0 0 1-13 8L3 21l1-5a9 9 0 1 1 17-4z`                                             |
| pencil     | `M17 3 21 7l-13 13H4v-4z` + `m14 6 4 4`                                                     |
| copy       | `<rect x="9" y="9" width="13" height="13" rx="2"/>` + `M5 15V5a2 2 0 0 1 2-2h10`             |
| send       | `M22 2 11 13` + `m22 2-7 20-4-9-9-4z`                                                        |
| link       | `M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.5 1.5` + `M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.5-1.5` |
| image      | `<rect x="3" y="3" width="18" height="18" rx="2"/>` + `<circle cx="8.5" cy="8.5" r="1.5"/>` + `m21 15-5-5L5 21` |
| stop-fill  | `<rect x="6" y="6" width="12" height="12" rx="2"/>` filled                                   |
| pause-fill | 2× `<rect x="?" y="5" width="4" height="14" rx=".8"/>` at x=6,14 filled                      |
| play-fill  | `M7 4v16l13-8z` filled                                                                        |
| keyboard   | `<rect x="2" y="6" width="20" height="12" rx="2"/>` + `M6 10h.01M10 10h.01M14 10h.01M18 10h.01M6 14h.01M18 14h.01M10 14h4` |
| star-fill  | `m12 2 2.9 6.9L22 10l-5.5 4.8L18.2 22 12 18.3 5.8 22l1.7-7.2L2 10l7.1-1.1z` filled           |
| external   | `M15 3h6v6M14 10 21 3M9 21H3v-6M10 14l-7 7`                                                  |
| phone      | `<rect x="6" y="2" width="12" height="20" rx="2.5"/>` + `M11 18h2`                           |
| tablet     | `<rect x="4" y="3" width="16" height="18" rx="2"/>` + `M10 20h4`                             |
| laptop     | `<rect x="3" y="5" width="18" height="12" rx="2"/>` + `M2 21h20`                             |
| desktop    | `<rect x="2" y="4" width="20" height="14" rx="2"/>` + `M8 20h8M12 18v2`                      |

Everything else is off-limits.

---

## 13. Frequently-missed details

These are the things that ALWAYS get lost in translation. Read them:

1. **The status pill on desktop** (Ready · iPhone 15) uses `onlineSoft` bg + `onlineBorder` border + `onlineAccent` text. NOT the terracotta soft pill. Terracotta pills are for device tagging, green pills are for connection status. Do not swap.

2. **Segmented pill row** — on mobile it uses a `#f2f2f2` active pill with `#0e1012` text. On desktop the same pattern applies but the row is rarely used (desktop uses a real sidebar for nav). If you need filter chips on desktop, keep the identical treatment.

3. **The recording widget's blur** — `backdrop-filter: blur(14px)` on macOS; on Windows/Linux fallback to solid `bgScreen` (blur not universally supported).

4. **Cream card disc** — the small icon disc INSIDE the cream feature card is `creamDisc` (`#1a1512`) with `cream` (`#EADFCE`) icon. NOT the reverse. Same rule for sage and plum.

5. **All timestamps are JBM Mono**, uppercase, `letter-spacing: 0.14em`. This is not optional. If a timestamp is not mono, it looks wrong.

6. **The mic icon in the tab bar is inactive** unless the user is currently in the recording screen. On Home tab the mic is muted `rgba(240,240,240,0.42)`. Tapping it opens the recording modal. Do not always show it as active — that suggests it's the primary action of the current tab (which it isn't; the current tab is Home).

7. **Never** put labels under tab bar icons. This is deliberate. If a user doesn't know what an icon means they long-press or check the icons in Settings. Adding labels ruins the visual restraint of the bar. (This applies to mobile only; desktop nav has labels.)

8. **The green online dot is always 5–6 px**, never bigger. If you want to emphasize "online" use the green status pill instead of a bigger dot.

9. **Feature card numbers are 20–22 pt semibold, NOT 24+**. Big numbers make dashboards look like Bloomberg terminals. Small numbers with generous surrounding padding read as calm confidence.

10. **The bird logo is always circle-cropped over a `#000` bg**. Never on transparent, never on cream. It comes with dark background baked in — that's fine — but the circular container is what gives it identity in the UI.

---

## 14. Change log discipline

When any value in this doc changes:

1. Update this file.
2. Update the corresponding token file (`packages/theme/*.ts`).
3. Commit with message `design-system: <what changed>` so anyone git-blaming can find the reasoning.
4. If the change affects both mobile and desktop, ship them together in one PR — never let them drift.

Never edit tokens directly in a screen file. Never `<div style="color: #C85A3E">` — always `<div style={{ color: colors.primary }}>`.

---

## 15. TL;DR for developers new to the codebase

- **One design system**, three surfaces.
- **Tokens live in `packages/theme/*`**. Colors, type, spacing, radii, icons. Nothing lives outside.
- **Mobile is the primary surface for daily voice actions.** Desktop is the primary for management + review.
- **Menubar is a mini-Flume for status + quick record.** Recording widget is the live capture confirmation.
- **Terracotta `#C85A3E` is the only brand color.** Green is for online status. Everything else is grays.
- **Line icons only, 1.6 stroke.** No emoji, no filled icons except play/pause/stop/star.
- **Feature-card pastels (cream, sage, plum) appear only on dashboards.** Never as full page backgrounds.
- **When in doubt, look at the wireframes** in `Flume Wireframes.dc.html` turns 7, 8, 9 (mobile, mobile v2, desktop). If a discrepancy exists between wireframe and code, the tokens win — but flag it for review.
