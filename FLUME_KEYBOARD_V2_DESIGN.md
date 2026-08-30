# Flume Keyboard v2 — Visual Design Spec (extracted from the selected mockups)

> Source of truth for the redesign. The build/review agents CANNOT see the images —
> this file is the design. Match it exactly: layout, colors, fonts, spacing, states.
> Applies to BOTH iOS (Swift keyboard extension) and Android (Kotlin IME).

## Design language
- Flume design system: **Geist** for UI text; **JetBrains Mono** for mono/meta
  (section labels, times, snippet triggers, phonetics, badges, counts).
- **Accent orange** `#E8522A` — the F logo, snippet triggers, "+ Add"/"+ New" pluses,
  the mic's dot badge.
- **Green** `#34C759` (avatar, "online", "SENT" badge).

### Light theme
- Keyboard/overlay background: light gray `~#F2F2F5`.
- Keys: white, ~8px radius, subtle drop shadow, near-black letters (~500 weight).
- Modifier keys (shift `^`, backspace `⌫`, `?123`, comma, period): light gray `~#CDD1D6`.
- Space bar: white, gray centered label "English (US)".
- Return key: **black** with white `↵`.
- Flume bar: light bg; icons medium gray; active icon has a light-gray rounded highlight.
- Mic button: **black circle, white mic**, small orange dot badge top-right.

### Dark theme
- Background: near-black `~#0E0E0E`.
- Keys: dark gray `~#3A3A3C`, white letters.
- Modifier keys: slightly darker gray than letter keys.
- Space bar: dark, gray "English (US)".
- Return key: **white** with black `↵`.
- Flume bar: dark bg; icons light gray; active icon has a dark-gray rounded highlight.
- Mic button: **white circle, black mic**, orange dot badge.

## The Flume bar (persistent row directly above the keyboard/overlay)
Left → right, full width, subtle top border:
1. **F logo** — rounded square (~8px), orange `#E8522A` fill, white bold "F" (~34px).
2. **⚡ lightning** — Snippets overlay.
3. **▦ grid (4 dots/squares)** — Canvas overlay.
4. **🕐 clock** — History overlay.
5. **📖 book** — Vocabulary overlay.
6. **● mic** (far right) — circular; starts/handles dictation. Orange dot badge.
- Icons are outline style. The overlay currently open highlights its icon (rounded
  bg behind it). Tapping the mic dictates; tapping an icon swaps the panel below the
  bar between the keyboard and that overlay. A keyboard-glyph toggle returns to typing.

## Keyboard layers
### Letters (QWERTY)
- Row1 `q w e r t y u i o p` · Row2 `a s d f g h j k l`
- Row3 `⇧(^)  z x c v b n m  ⌫`
- Row4 `?123 | , | [space: "English (US)"] | . | ↵`

### Numbers/symbols (?123)
- Row1 `1 2 3 4 5 6 7 8 9 0`
- Row2 `@ # $ _ & - + ( ) /`
- Row3 `=\<  * " ' : ; ! ?  ⌫`
- Row4 `ABC | , | [space] | . | ↵`
- `=\<` opens a secondary symbols page (Gboard-style). `ABC` returns to letters.

## Overlays (replace the key area, keep the Flume bar above)
Each overlay: a header row = **UPPERCASE mono section label** (left) + a right-side
label/action. Then the content. Light = white cards on light bg; dark = subtle dark cards.

### History  (icon: clock)
- Header: `HISTORY` · right: "Tap to insert" + a keyboard-return glyph (back to typing).
- Rows: time pill (mono, e.g. `9:24`, `8:51`, `Yd`) + transcription text (truncated) + `→`.
- Footer: centered "See all history".

### Canvas  (icon: grid)
- Header: `CANVAS` · right: "→ MacBook Pro" (the paired device).
- Three large targets in a row: **Text** (lines icon), **Link** (link icon), **Image**
  (image icon) — outlined rounded boxes, icon over label.
- Subheader `RECENTLY SENT` + rows: item (link/text icon + text) + green mono `SENT` badge.

### Snippets  (icon: lightning)
- Header: `SNIPPETS` · right: "Tap to expand".
- Rows: **trigger in orange mono** (e.g. `my linkedin`, `my sig`, `book me`,
  `my address`) left; expansion preview in gray (truncated) right.
- Footer: "+ New snippet" (orange plus).

### Vocabulary  (icon: book)
- Header: `VOCABULARY` · right: "14 words" (count, mono).
- First row: dashed rounded input/button "+ Add a word Flume keeps mishearing…" (orange +).
- Then a wrap of **pill chips**, one per word (e.g. Idiaz, Flume, Aman, Superwhisper,
  Lisboa, Reanimated, Whisper.cpp, Cal.com, Expo, RN, Sarah, Bica). A chip may show a
  **phonetic** in small mono beside the word (e.g. `Idiaz  i-DEE-uhz`).

## Behavior notes
- The overlays reuse existing Flume data: history = transcriptions, snippets =
  dictionary snippets, vocabulary = dictionary vocabulary, canvas = the canvas table.
- Tapping a history row / snippet / vocab action inserts/acts via the input connection
  (Android) / `textDocumentProxy` (iOS).
- Dictation (mic) uses the existing `groq-proxy` path already wired into both keyboards.
- Both themes must follow the host field's appearance (light/dark) like the mockups.
