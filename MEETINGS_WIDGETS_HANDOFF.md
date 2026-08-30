# MEETINGS_WIDGETS_HANDOFF.md

Developer handoff for the 10 Meetings **widgets** (IDs 13–22).
**Status: implemented on desktop** (meeting window + dashboard Meetings list, Jul 2026) — mobile mirror pending.
Implemented: ALL 10 widgets including every previously-deferred sub-feature — notes-on-marks,
due-date extraction, voice fingerprinting (local-only prints, `app/voiceprint.py`), markdown-lite
scratchpad, per-row AI regenerate, pinned/unread meeting states, and the mobile compact list variant.
Reference wireframes: turn `#t33` in `Flume Wireframes.dc.html`,
options `#33a`–`#33j` (modernized v2 — supersedes turn 32).

Every value below references a **token** from the existing Flume design
system. Values not currently in the system are flagged inline and
consolidated in **Token Gaps** at the end. Do not paper over gaps with hex.

Each widget block includes: Purpose · Used in · Variants · Layout · Content ·
States · Interactions · Edge cases · Responsive · **Accessibility** ·
**Data contract** (the TypeScript shape Claude Code builds the props against).

Token source of truth:
- `whisperflow/app/theme.py`
- `whisperflow/app/fonts_css.py`
- `verbal-mobile/flume-ui/theme/`
- `context/05-conventions.md`

## Global v2 design rules

All widgets in this doc follow these shared conventions. The old v1
patterns (see turn 32) are deprecated; do not implement those.

1. **No chip backgrounds.** Speaker / status / metadata chips are always a **6pt colored dot + label** — never a filled pill. The dot carries the color; the label is `color.text.primary` (or `.secondary` when muted).
2. **One card per group, dividers inside.** Never nest cards. Group related rows inside a single `radius.lg` card, separated by 1px `color.divider.faint` rows. Card border: 1px `color.divider.subtle`.
3. **Icon rows, not icon buttons.** Trailing action icons are inline glyphs at stroke `stroke.icon ≈ 1.4` — **[Token Gap · strokeIcon]** — with `space.m` gap. No individual button chrome.
4. **Segmented controls are underline tabs.** No inner bg fill, no border, no radius. Active tab: text `color.text.primary` + 1.5px underline `color.accent.primary`.
5. **Eyebrows tighten.** All section eyebrows: `type.eyebrow.tight` — **[Token Gap · size.eyebrow ≈ 9.5]** · uppercase · tracking `letter.eyebrow.wide` ≈ 0.16em · color `color.text.faint`.
6. **AI enhancements** in hybrid notes are prefixed with a plain `↳` arrow and a color-shifted paragraph — no tint bg block, no accent chip.
7. **Timer numerals** use `type.mono` at weight 500 (not 600) with `letter.tight` tracking for a lighter feel.

---

## `TranscriptLine` — 33a

**Purpose:** A single utterance. Reused live (dense) and post-meeting (spacious).
**Where it lives:** `TranscriptPane` (31c) · expanded transcript teaser (31e).

### Layout

- Direction: column
- Density variants:
  - `dense` — padding `space.xs` 0, gap 0 between rows (they stack tightly)
  - `spacious` — padding-bottom `space.m`, gap between rows `space.l`

### Content

**Header row** (direction: row · align: baseline · gap `space.s`)

*Dense variant*
1. Speaker name — `type.body.strong` (Geist 600 · **[Token Gap · size.body.strong ≈ 10]**) · color per speaker palette · fixed width `size.speakerCol ≈ 60` — **[Token Gap · speakerCol]**
2. Timestamp — `type.mono.tiny` (JetBrains Mono 500 · **[Token Gap · size.mono.tiny ≈ 9.5]**) · `color.text.faint` · fixed width `size.timestampCol ≈ 38` — **[Token Gap · timestampCol]**
3. Utterance body — `type.body.sm` (Geist 400 · **[Token Gap · size.body.sm ≈ 12]**) · `color.text.secondary` · line-height `line.body.tight` — **[Token Gap · line-heights]**

*Spacious variant*
1. Speaker `SpeakerDot` (6pt colored dot) + name (`type.body` Geist 600 · **[Token Gap · size.body ≈ 11]** · `color.text.primary`)
2. Timestamp — `type.mono.body` · `color.text.dim`
3. Optional inline "edited" — `type.mono.tiny` · `color.text.faint` · letter-spacing `letter.mono.subtle` ≈ 0.08em — **[Token Gap]**

**Body** (spacious)
- `type.body.reading` (Geist 400 · **[Token Gap · size.body.reading ≈ 13]**) · `color.text.primary` · line-height `line.body.reading ≈ 1.7`
- Reserve right padding `size.actionRailGap ≈ 70` for inline action icons — **[Token Gap · actionRailGap]**

**Action rail (spacious only)**
- Absolutely positioned top-right of body
- Inline row · gap `space.m`
- Three glyphs, stroke `stroke.icon`, 12pt, color `color.text.faint`
- Icons: Play (semantic `play`), Star (`mark`), Overflow (`more`)

### States

- `default`
- `playing` — timestamp prefixed with `▶`, timestamp color `color.accent.primary`; body color `color.text.primary`
- `marked` — 1.5px left border `color.accent.primary`, negative left margin to bleed the border
- `edited` — inline "edited" eyebrow present in header
- `searched-hit` — matched substring gets 1px underline `color.accent.primary`; no bg fill
- `hover` (spacious) — action rail opacity 1 (default 0), color lifts to `color.text.secondary`
- `streaming` — trailing caret `▌` in `color.text.dim`
- `error` — body replaced with "Transcription failed" · `color.danger.soft` · trailing Retry link

### Interactions

- Click body → play audio from utterance offset
- Click star icon → toggle mark; haptic `haptic.success` — **[Token Gap · hapticTokens]**
- Overflow → context menu: Copy · Edit text · Delete
- Double-click body (spacious) → inline edit; Cmd+Enter saves, Esc cancels; gains "edited" eyebrow
- Double-click speaker name → rename (see 33d)

### Edge cases

- Long single utterance → dense clamps to 3 lines with "show more" (Geist 400 · `color.text.dim`); spacious never clamps
- Non-verbal audio → body is italic "[music]" in `color.text.dim`
- Overlapping speakers → each renders own row, ordered first-heard
- Buffering (no timestamp yet) → timestamp cell shows `–:–` in `color.text.faint`

### Responsive

- Below `breakpoint.desktop.sm` — **[Token Gap · breakpoints]** — action rail collapses to overflow only
### Accessibility

- Row: `role="listitem"` inside `role="log"` (live) / `role="list"` (post-meeting); live pane announces new lines via `aria-live="polite"`
- SR label: "{speaker}, {timestamp}: {text}" (+ ", marked" / ", edited" when set)
- Action rail glyphs: real buttons with labels "Play from {timestamp}" / "Mark this moment" / "More options"; min hit target `iconTap` (desktop), ≥44pt (mobile)
- Keyboard: rows focusable in document order; Enter = play, `m` = toggle mark while focused; inline edit is a standard textbox (Esc/Cmd+Enter announced)
- `marked` left border must not be the only signal — SR label carries it

### Data contract

```ts
type TranscriptLine = {
  id: string;
  speakerId: string;                 // 'self' | 's<N>'
  speakerName: string;               // resolved display name
  speakerPalette: SpeakerPaletteKey; // see SpeakerChipAvatar
  timestamp: number;                 // seconds from meeting start (t0)
  endTimestamp?: number;             // t1; absent while streaming
  text: string;
  density: 'dense' | 'spacious';
  isPlaying: boolean;
  isMarked: boolean;
  isEdited: boolean;
  isStreaming?: boolean;             // trailing caret
  isNonVerbal?: boolean;             // renders italic "[music]"
  error?: string | null;             // "Transcription failed" row
  searchRanges?: Array<[start: number, end: number]>; // searched-hit underlines
};
// callbacks: onPlay(id) · onToggleMark(id) · onEditText(id, text) ·
//            onRenameSpeaker(speakerId) · onCopy(id) · onDelete(id)
```

- On mobile mirror — action rail becomes long-press context menu, no visible icons

---

## `MarkedMomentCard` — 33b

**Purpose:** A single bookmarked moment. Standalone card with optional user note.
**Where it lives:** `PostMeetingSummary` (31e) marks-expanded state · `InMeetingTwoPanel` (31c) marks side rail.

### Layout

- Padding: `space.m` `space.l`
- Radius: `radius.lg`
- Background: `color.surface.raised`
- **No border.** Elevation comes from bg contrast alone.
- Direction: column · gap `space.m`

### Content

**Header row** (`space-between`, align: center)
- Left: star glyph `color.accent.primary` (12pt) + timestamp `type.mono.body` · `color.accent.primary` · letter-spacing `letter.mono.tracked`
- Right (per rule 3, icon row not buttons): gap `space.l`, glyphs 12pt stroke `stroke.icon` · `color.text.faint`
  - Optional clip duration precedes the icons: `▶ 0:14` — `type.mono.tiny` · `color.text.dim` (shown when the mark has a bounded audio clip; see 33b second card)
  - Play (semantic `play`) — hover → `color.text.primary`
  - Jump to transcript (`link-out`)
  - Delete (`destroy`) — hover → `color.danger.soft`

**Excerpt block**
- Body: `type.body.sm` · `color.text.primary` · line-height `line.body.reading`
- Speaker prefix inline: `"{Name} — "` in `color.text.dim`
- **No left border, no border-based emphasis.** The card padding is enough.

**Optional user note** (when present)
- Separator: `margin-top space.m`, `padding-top space.m`, `border-top 1px color.divider.faint`
- Eyebrow: "YOUR NOTE" · `type.eyebrow.tight` · `color.note.strong` — **[Token Gap · note.strong ≈ ochre]**
- Body: `type.body.sm` · `color.text.primary`
- **No note bg fill.** The eyebrow color signals authorship.

### States

- `default`
- `no-note` — user note block absent
- `hover` — bg `color.surface.hoverStrong`; action icons lift
- `active` (playing this segment) — inset 1.5px left `color.accent.primary`
- `note-editing` — user note body becomes inline `TextField`; Save/Cancel row appears at bottom of card
- `deleted-pending` — card fades to `opacity.dim`; single Undo link replaces action row
- `audio-unavailable` — Play glyph `opacity.disabled`, tooltip "Audio was auto-deleted"

### Interactions

- Click excerpt → jump to transcript position
- Play → play from mark offset with 3s pre-roll — **[Token Gap · playback.preRoll]**
- Click empty area beneath excerpt → reveal note editor
- Delete → `deleted-pending` state with 5s undo — **[Token Gap · toast.undoTimeout]**

### Edge cases

- Excerpt spans 2 speakers → both speaker prefixes on new lines
- Very long user note → wraps to `line.max ≈ 8` — **[Token Gap · line.max]** then clamps with "Show more"
- Very short excerpt → card flexes down; no minimum height

### Responsive

### Accessibility

- Card: `role="group"`, label "Marked moment at {timestamp}{, note attached}"
- Action glyphs are buttons: "Play clip" / "Jump to transcript" / "Delete mark"; hit target `iconTap` desktop, ≥44pt mobile
- `deleted-pending`: Undo link receives focus automatically; SR announces "Mark deleted, undo available"
- Note editor: labelled textbox "Your note"; Save/Cancel reachable by Tab
- Timestamp is text, not only color — accent color is decorative

### Data contract

```ts
type MarkedMoment = {
  id: string;
  timestamp: number;              // seconds from meeting start
  clipDurationSec?: number;       // renders "▶ 0:14"; absent → no duration label
  speakerId?: string;             // excerpt attribution; absent → no prefix
  speakerName?: string;
  excerpt: string;                // transcript text around the mark
  note?: string | null;           // user note; null/absent → no-note variant
  hasAudio: boolean;              // false → audio-unavailable state
  isActive: boolean;              // this clip is currently playing
  pendingDelete?: boolean;        // 5s undo window
};
// callbacks: onPlay(id) · onJump(id) · onDelete(id) · onUndoDelete(id) ·
//            onSaveNote(id, note)
```

- Full width in narrow layouts; caps at `size.card.max ≈ 520` in wide layouts — **[Token Gap · card.max]**

---

## `ActionItemRow` — 33c

**Purpose:** A single action item extracted from a meeting.
**Where it lives:** `ActionItemsCard` in `PostMeetingSummary` (31e).

### Layout

- Rows live inside a **single parent card** (per rule 2), separated by 1px `color.divider.faint` between rows. Row itself has no border, no radius, no bg.
- Padding: `space.m` 0 (vertical only — horizontal padding comes from the parent card)
- Direction: row · align: center · gap `space.m`

### Content (left to right)

1. `Checkbox` — 16pt, radius `radius.xs`, border 1.4px `color.border.strong` — **[Token Gap · checkboxSize / borderStrong]**
2. `SpeakerDot` — 6pt colored dot per palette
3. Speaker name — `type.body.strong` (Geist 600 · **[Token Gap · size.body.strong ≈ 11]**) · `color.text.primary`
4. Task text — `type.body.sm` · `color.text.primary` · flex 1 · truncate
5. Optional inline "edited" eyebrow — same style as `TranscriptLine`
6. Trailing due — `type.mono.tiny` · `color.accent.primary` (near) or `color.text.faint` (far / none) · letter-spacing `letter.mono.subtle`

### States

- `pending` (default)
- `done` — checkbox filled `color.success`, task text `text-decoration: line-through` with strike color `color.text.dim`, row opacity `opacity.done ≈ 0.55` — **[Token Gap · opacity.done]**
- `edited` — inline "edited" eyebrow after task text
- `ai-uncertain` — speaker dot is `color.text.faint`, speaker name "Unknown" in `color.text.dim`, task text `color.text.secondary`, trailing "low confidence" eyebrow in `color.danger.soft`, plus two trailing text links Keep (`color.success.soft`) / Reject (`color.text.dim`). **No red row bg.**
- `hover` — bg `color.surface.hover` (very subtle)

### Interactions

- Click checkbox → toggle `done`
- Click task text → inline edit; Cmd+Enter saves, Esc cancels
- Click speaker dot/name → assign menu
- Keep / Reject → resolve `ai-uncertain`; Reject deletes with 5s undo toast

### Edge cases

- No owner → dot is faint, name "Unknown"
- No due date → due cell shows "—" in `color.text.faint`
- Long task text → dense truncates with tooltip; wide screens wrap

### Responsive

### Accessibility

- Row: `role="listitem"`; checkbox is a real `role="checkbox"` with label "{task}, assigned to {owner|Unknown}{, due {due}}"
- `done` is conveyed by `aria-checked`, not strike-through alone
- Keep / Reject are buttons ("Keep suggested item" / "Reject suggested item"); `ai-uncertain` announced as "AI-suggested, low confidence"
- Checkbox hit target ≥ `iconTap` desktop / 44pt mobile despite 16pt visual
- Inline edit: textbox labelled "Edit task"; Cmd+Enter/Esc

### Data contract

```ts
type ActionItem = {
  id: string;
  ownerId?: string | null;        // speaker id; null → "Unknown" (faint dot)
  ownerName?: string | null;
  ownerPalette?: SpeakerPaletteKey;
  task: string;
  done: boolean;
  isEdited: boolean;
  due?: { label: string; isNear: boolean } | null;  // "WED" accent when near; null → "—"
  aiConfidence: 'high' | 'low';   // 'low' → Keep/Reject links + eyebrow
};
// callbacks: onToggleDone(id) · onEditTask(id, text) · onAssign(id, speakerId) ·
//            onKeep(id) · onReject(id)
```

- Below `breakpoint.desktop.sm`: due drops beneath task text as caption

---

## `SpeakerChipAvatar` — 33d

**Purpose:** Represents a detected speaker. Chip (dot + name) inline; avatar (initial disc) in headers and participant lists.
**Where it lives:** every widget that references a speaker.

### Chip variant (default per rule 1)

- Direction: inline-flex · align: center · gap `space.xs`
- Dot: 6pt disc, per-speaker palette
- Name: `type.body.strong` (Geist 600 · **[Token Gap · size.chip ≈ 11]**) · `color.text.primary`
- **No padding, no bg fill, no radius.** The dot IS the chip.
- Palette (dot color only):
  - Palette A `speaker.terracotta` → `color.speaker.terracotta` — **[Token Gap · speaker palette · A/B/C/D/self/unknown]**
  - Palette B `speaker.slate`
  - Palette C `speaker.sage`
  - Palette D `speaker.ochre` (reserved for `self`)
  - Palette E `speaker.unknown` → dot `color.text.faint`, name in `color.text.secondary`

### Avatar variant

- Size: `size.avatar.md ≈ 34` — **[Token Gap · avatar sizes: sm 22 / md 34]**
- Radius: `radius.pill`
- Content: single initial (or 2 if disambiguating), `type.avatar` (Geist 600 · **[Token Gap · size.avatar ≈ 12]**)
- Bg: `color.speaker.<name>.subtle`; text `color.speaker.<name>.soft`
- `self` variant: `outline 1.5px color.speaker.self.strong · outline-offset 2px` (a "ring" effect that respects the pill radius)
- `unknown` variant: transparent bg, 1px dashed `color.border.faint`, content `?`
- Optional trailing corner dot: 10pt `color.accent.primary` disc with 2px `color.surface.base` border — indicates voice fingerprint recognition

### Editing state (chip only)

- Bg transparent, no border-box border, gains a **1.5px bottom border** `color.accent.primary` under the name only
- Content: `TextField` (compact), text `color.text.primary`, caret `color.accent.primary`
- Enter commits, Esc reverts

### `VoiceFingerprintBanner` (companion element)

- **No bg tint, no border.** Sits inside its parent card, separated by `padding-top space.m; border-top 1px color.divider.faint`
- Direction: row · align: center · gap `space.s`
- Star glyph (11pt) `color.accent.primary`
- Body: `type.body.sm` · `color.text.secondary` · name bolded in `color.text.primary`
- Trailing eyebrow: "FINGERPRINT" · `type.eyebrow.tight` · `color.text.faint`

### States

- `named` · `unnamed` · `editing` · `self` · `hover` · `recognized`

### Interactions

- Chip: double-click → editing mode
- Avatar: click → speaker sheet (rename · merge · hide · block)

### Edge cases

- Unknown → "?"
- Long name → truncate at `size.chipMaxWidth` — **[Token Gap · chipMaxWidth]** with ellipsis; full name in tooltip
- Rename to existing name → merge confirmation
- More than 5 speakers → palettes cycle deterministically by first-heard order

### Responsive

- Avatar `sm` in dense mobile lists (`size.avatar.sm ≈ 22`)
### Accessibility

- Chip: `role="button"` when editable, label "Speaker {name}, double-tap to rename"; dot color is decorative (never the sole identity signal — the name text is)
- Avatar: `role="img"`, label "{name}{, recognized from previous meetings}{, you}"; unknown → "Unidentified speaker"
- Editing: textbox labelled "Speaker name", Enter commits / Esc reverts (announced)
- Fingerprint corner dot pairs with the `VoiceFingerprintBanner` text — the banner is the accessible articulation
- Hit target for chip/avatar interactions ≥ 44pt on mobile (pad invisibly)

### Data contract

```ts
type SpeakerPaletteKey = 'terracotta' | 'slate' | 'sage' | 'ochre' | 'unknown';

type Speaker = {
  id: string;                     // 'self' | 's<N>'
  name: string | null;            // null → "Speaker N" (unnamed state)
  paletteKey: SpeakerPaletteKey;  // 'ochre' reserved for self
  isSelf: boolean;
  isRecognized: boolean;          // voice fingerprint matched → corner dot
  recognizedFromCount?: number;   // banner: "from 3 previous meetings"
};

type SpeakerChipProps = {
  speaker: Speaker;
  variant: 'chip' | 'avatar';
  size?: 'sm' | 'md';             // avatar only
  editable?: boolean;
  onRename?: (id: string, name: string) => void;
};
```

- Chip keeps size; reduces to first-initial pair ("Marcus J." → "M. J.") in narrow contexts

---

## `ElapsedTimer` — 33e

**Purpose:** Time-elapsed display for the active meeting.
**Where it lives:** `FloatingMeetingHUD` (31d) · `MeetingHeader` (31c) · `MeetingSummaryHeader` (31e, static).

### Variants

**Compact — HUD**
- Direction: row · align: center · gap `space.xs`
- Dot: `size.dot.sm ≈ 6` — **[Token Gap · dot sizes]** · color per state
- Numerals: `type.mono.body` (JetBrains Mono 500 · **[Token Gap · size.mono ≈ 13]**) · `color.text.primary` · letter-spacing `letter.tightMinus2` ≈ -0.02em — **[Token Gap]**
- Optional inline "paused" — `type.eyebrow.tight`

**Large — header**
- Direction: row · align: center · gap `space.s`
- Dot: `size.dot.md ≈ 8`
- Numerals: `type.mono.h4` (JetBrains Mono **500** · **[Token Gap · size.mono.h4 ≈ 26]**) · letter-spacing `letter.tightMinus3 ≈ -0.03em`
- Weight is deliberately **medium, not bold** — creates the lighter, editorial feel of v2

### States

- `live` — dot `color.record`, animation `motion.pulse`; numerals `color.text.primary`
- `paused` — dot `color.text.dim` static; numerals `color.text.secondary`; "paused" eyebrow shown
- `starting` — dot solid `color.record`, no pulse; numerals dim until t > 0
- `stopping` — as paused, numerals frozen at final value

### Interactions

- Passive
- Hover in large variant → tooltip "Started at 10:00:03"

### Edge cases

- < 1h → `M:SS`
- ≥ 1h → `H:MM:SS`
- ≥ 24h → `HH:MM:SS`, dot flips to `color.warning`
- Reserve width with `font-variant-numeric: tabular-nums` so format switch causes no layout jump
- Timer derived from stream length, not wall clock

### Responsive

### Accessibility

- `role="timer"`, `aria-live="off"` (announcing every second is noise); SR label on demand: "Elapsed {h} hours {m} minutes, {live|paused}"
- Paused state carries the literal "paused" text — never dot color alone
- Not focusable/interactive (tooltip in large variant also bound to focus for keyboard users)

### Data contract

```ts
type ElapsedTimerProps = {
  seconds: number;                 // derived from stream length, not wall clock
  state: 'live' | 'paused' | 'starting' | 'stopping';
  variant: 'compact' | 'large';
  startedAtLabel?: string;         // tooltip: "Started at 10:00:03"
};
```

- Below `breakpoint.desktop.sm`, large variant uses `size.mono.h5` — **[Token Gap]**

---

## `MarkMomentButton` — 33f

**Purpose:** High-frequency "star this moment" action. Per rule 3, this is a **plain glyph**, not a chip-styled button.

**Where it lives:** `MeetingHeader` (31c) inline icon row · `FloatingMeetingHUD` (31d) expanded state · `TranscriptLine` action rail (spacious).

### Layout

- Container: `size.iconTap ≈ 28` — **[Token Gap · iconTap]** (invisible hit target)
- Direction: relative (for count numeral and pulse ring)
- **No bg, no border, no radius.** The glyph is the whole button.

### Content

- Star glyph — 16pt, stroke `stroke.icon` · fill only in `just-marked` state
- Optional count numeral — `type.mono.body` (500 · **[Token Gap · size.mono ≈ 10]**) · `color.accent.primary` · absolute top `-3`, right `-6`. No badge disc, no bg.

### States

- `idle` — glyph `color.text.secondary` (stroke)
- `hover` — glyph `color.accent.primary` (stroke); tooltip appears (see below)
- `just-marked` — glyph `color.accent.primary` (fill); 1.5px ring `color.accent.primary` opacity 0.5 pops out (`motion.pop` 200ms ease-out, scale 1 → 1.4, opacity 0.5 → 0)
- `with-count` — same as idle plus count numeral to the right (no badge shape)
- `disabled` — opacity `opacity.disabled`
- `focused` (keyboard) — 2px outline `focus.ring` — **[Token Gap · focus.ring]** offset 4

### Tooltip

- Appears after `hover.delay ≈ 500ms` — **[Token Gap · hover.delay]**
- Padding: `space.xs` `space.s`
- Radius: `radius.sm`
- Bg: `color.tooltip.bg` — **[Token Gap · tooltip family]**
- Content: "Mark" + inline keyboard chip "⌘M" (`type.mono.tiny` · `color.text.dim`)
- **No border on tooltip** — bg contrast alone

### Interactions

- Click → drop mark; button enters `just-marked` 400ms; count increments
- `⌘M` global shortcut when meeting active
- Haptic `haptic.tap`

### Edge cases

- Meeting starting → disabled
- Meeting paused → still works; mark timestamp = last live moment
- Rapid multi-click → debounce ≈ 250ms
- 99+ marks → shows "99+"

### Responsive

### Accessibility

- `role="button"`, label "Mark this moment" (+ ", {count} marks so far" when count > 0); shortcut exposed via `aria-keyshortcuts="Meta+M"`
- `just-marked` announced politely: "Moment marked at {timestamp}"
- Hit target `iconTap` minimum desktop, ≥44pt mobile — the 16pt glyph is never the target
- Focus ring per `focus.ring`; operable via Enter/Space

### Data contract

```ts
type MarkMomentButtonProps = {
  count: number;                  // 0 hides the numeral; >99 renders "99+"
  disabled: boolean;              // meeting starting
  justMarked: boolean;            // transient ~400ms; parent clears after pop
  onMark: () => void;             // debounced ≈250ms upstream
};
```

- Below `breakpoint.desktop.sm` in header, glyph drops to 14pt; count numeral unchanged

---

## `LiveWaveform` — 33g

**Purpose:** Real-time audio activity indicator. Same widget, three sizes and a split-source variant.

**Where it lives:** `FloatingMeetingHUD` (small) · `MeetingHeader` (medium) · Recording bar in keyboard · `PreMeetingModal` audio-source rows (mini).

### Bar geometry — v2 (thinner, quieter)

| Variant | Bars | Bar w | Gap | Height | Notes |
|---|---|---|---|---|---|
| `mini` | 3 | 1.5 | 2 | 8 | modal audio-source rows |
| `small` | 5 | 1.5 | 3 | 12 | HUD, dictation strip |
| `medium` | 12 | 2 | 3 | 18 | header combined |
| `medium-split` | 6 + 6 | 1.5 | 2 | 14 | header SYS + MIC |

### Content

**Combined variant**
- Direction: row · align: center · gap `space.xxs` — **[Token Gap · xxs ≈ 3]**
- Bars fill `color.text.primary`

**Split variant**
- Direction: column · gap `space.s`
- Two `SourceGroup`s, each: label (`type.mono.tiny` · width `size.sourceLabel ≈ 28` · `color.text.faint` · letter-spacing `letter.eyebrow.wide`) + bar row
- SYS bars: `color.speaker.slate` — **[Token Gap · speaker.slate]**
- MIC bars: `color.speaker.terracotta` — **[Token Gap · speaker.terracotta]**

### States

- `active` — bars animate `motion.wave` (per-bar staggered 250–1100ms cycle, scaleY 0.15 → 1, `easing.easeInOut`) — **[Token Gap · motion.wave]**
- `silence` — all bars scaleY 0.15, color drops to `color.text.faint`
- `paused` — bars frozen at last frame, opacity 40%
- `muted-source` (split, one source disabled) — that row's bars at 0.15 scaleY, label strike-through
- `clipping` — bars flash `color.warning` for 120ms — **[Token Gap · warning family]**

### Interactions

- Passive
- Post-v1: click bar group in HUD expanded to toggle SYS/MIC mute

### Edge cases

- No driver → muted state with tooltip "Audio driver missing"
- Very quiet meeting → bars at min; silence state waits `silence.window ≈ 30s` — **[Token Gap · silence params]**

### Responsive

### Accessibility

- Decorative: `aria-hidden="true"` everywhere it accompanies a textual state (timer, "Listening" label). When it is the ONLY activity signal (HUD collapsed), give the container `role="img"` with label "Audio {active|silent|paused}"
- Never conveys information by animation alone — the paired label/timer does
- Honors reduced-motion: bars hold a static mid-height pose (state still distinguishable via color/opacity)

### Data contract

```ts
type LiveWaveformProps = {
  variant: 'mini' | 'small' | 'medium' | 'medium-split';
  state: 'active' | 'silence' | 'paused' | 'clipping';
  level?: number;                 // 0..1 combined loudness (combined variants)
  sysLevel?: number;              // 0..1 (medium-split)
  micLevel?: number;              // 0..1 (medium-split)
  mutedSources?: Array<'sys' | 'mic'>;   // split: strike-through label + floor bars
};
```

- Not viewport-sensitive. Variant chosen by parent surface.

---

## `ScratchpadEditor` — 33h

**Purpose:** User's private notepad. Rich text with dictation.
**Where it lives:** `ScratchpadPane` in `InMeetingTwoPanel` (31c) · post-meeting edit mode in `HybridNotesCard` (31e).

### Layout

- Direction: column
- Padding: `space.l`
- Bg: `color.surface.base` (**no surface-subtle nested fill** per rule 2)
- Radius: `radius.lg`
- Border: 1px `color.divider.subtle` (only when standalone; as pane, inherits from parent)

### Content

**Header row** (`space-between`)
- Left: `type.eyebrow.tight` label ("Your notes" during meeting; hidden in post-meeting inline edit)
- Right: `DictateGlyph` — inline gesture, not a filled chip
  - Direction: row · gap `space.xs`
  - Icon: mic 11pt stroke `stroke.icon`
  - Label: "Dictate" · `type.body.tiny` (Geist 500 · **[Token Gap · size.body.tiny ≈ 10]**)
  - Color: `color.text.secondary` (idle); `color.accent.soft` (dictating, replacing icon with mini `LiveWaveform`)

**Body**
- Rich-text editor supporting H1/H2, bullets, numbered, checkboxes, code, quote — **[Token Gap · rich-text palette]**
- Bullet marker: em-dash "—" prefix in `color.text.faint` (v2 replaces filled disc with typographic dash)
- Base font: `type.body.sm` · `color.text.primary` · line-height `line.body.notes ≈ 1.75` — **[Token Gap]**
- Caret color: `color.accent.primary`

### States

- `empty` — placeholder centered, muted: "Type or dictate — Flume will fill in the details around your notes." (`type.body.sm` · `color.text.faint`)
- `typing` — caret visible, no chrome change
- `dictating` — pane border becomes `color.accent.primary` (1px), header eyebrow shifts to accent color; freshly-inserted text highlighted with `color.accent.soft` for 800ms then fades to base color (no bg fill)
- `read-only` (post-meeting default) — caret hidden, Dictate hidden; hover shows an inline "Edit" affordance top-right
- `edit-mode` (post-meeting active) — as typing plus a floating Save/Cancel row docked bottom of pane
- `error` — border `color.danger.border`; inline error line below header
- `permission-missing-dictate` — Dictate row shows lock glyph + "Enable mic to dictate"

### Interactions

- Dictate press → mic starts, transcription streams into editor (never into meeting recording); press again stops
- `⌘K` toggles Dictate; `⌘B`/`⌘I` for emphasis; `-` at line start becomes bullet
- Autosave every 1s idle — **[Token Gap · autosave.debounce]**

### Edge cases

- Meeting stops while dictating scratchpad → dictation continues; only meeting capture stops
- Low confidence dictation → dotted underline `color.warning.border` — **[Token Gap · warning.border]**
- Autosave conflict → conflict banner top of pane

### Responsive

### Accessibility

- Editor: `role="textbox"` `aria-multiline="true"`, label "Your notes"; placeholder is NOT the accessible name
- Dictate: toggle button, label "Dictate notes", `aria-pressed` reflects state; state change announced ("Dictation started/stopped"); `⌘K` via `aria-keyshortcuts`
- `dictating` accent border pairs with the header label change — never color alone
- Checkboxes inside content are real `role="checkbox"` items; keyboard toggling supported
- `permission-missing-dictate` row is a button that opens the permission flow

### Data contract

```ts
type ScratchpadEditorProps = {
  content: string;                // markdown-lite (em-dash bullets, "- [ ]" checkboxes)
  mode: 'live' | 'read-only' | 'edit';
  dictating: boolean;
  micPermission: 'granted' | 'denied' | 'undetermined';
  error?: string | null;
  onChange: (content: string) => void;   // caller debounces autosave (≈1s)
  onToggleDictate: () => void;
  onSave?: () => void;            // edit-mode Save/Cancel row
  onCancel?: () => void;
};
```

- Below `breakpoint.desktop.sm`, scratchpad becomes a tab peer of transcript

---

## `HybridNotesRenderer` — 33i

**Purpose:** Merged view of user scratchpad + AI-added context. The distinctive Flume-vs-Granola surface.

**Where it lives:** `HybridNotesCard` in `PostMeetingSummary` (31e).

### Layout

- Direction: column
- Padding: `space.l`
- Bg: `color.surface.raised`
- Border: 1px `color.divider.subtle`
- Radius: `radius.lg`

### Content

**Header row** (`space-between`)

*Left: `LegendPair` — dot + label per rule 1*
- Terracotta 6pt dot + "Your notes" (`type.body.tiny` · `color.text.secondary`)
- Faint 6pt dot + "AI additions"

*Right: `ViewTabs` — underline segmented control per rule 4*
- Direction: row · gap `space.xxs`
- Three labels: "Yours" · "Merged" · "AI" (`type.body.small` · Geist 500)
- Active label: `color.text.primary` + 1.5px underline `color.accent.primary` (padding-bottom `space.xxs`)
- Inactive: `color.text.dim` · no underline

**Body**
- Title `type.h6` · `color.text.primary` · letter-spacing `letter.tightMinus1 ≈ -0.01em` — **[Token Gap]**
- Stack of `HybridNoteRow`s, gap `space.l`

### `HybridNoteRow`

- **No left border, no per-row card.** Structure is:
  - User line: 6pt terracotta dot (aligned to text baseline) + text
  - AI enhancement (when present): indented `space.l`, prefixed with `↳` (`color.text.faint`), body `type.body.sm` in `color.text.dim`

### States

- `merged` (default)
- `yours-only` — AI blocks hidden; rows without user text also hidden
- `ai-only` — user lines dim to `opacity.dim ≈ 0.5` — **[Token Gap · opacity.dim]**; AI blocks emphasized to `color.text.primary`
- `editing` — user or AI block enters inline edit; the other block dims
- `ai-regenerating` (per-row) — enhancement replaced by skeleton lines; small inline spinner replaces `↳`
- `ai-edited-by-user` — enhancement gains strike-through of original + user override underneath
- `error` — enhancement replaced with `color.danger.soft` message "Couldn't regenerate. Retry"

### Interactions

- Click view tab → view mode changes (persist per-user)
- Click user line → inline edit
- Click AI enhancement → inline edit
- Right-click AI enhancement → context: Regenerate · Remove enhancement · Report as wrong
- Hover row → nothing loud; user dot lifts to `color.accent.primary` full opacity

### Edge cases

- No AI yet (generating) → skeleton beneath each user line
- No user notes → placeholder: "No notes captured. Add notes to see AI enhancements."
- User line deleted → its AI enhancement is also removed
- Very long AI enhancement → clamp to `line.enhancement.max ≈ 6` — **[Token Gap]** with "Show more"

### Responsive

- Below `breakpoint.desktop.sm`, header stacks — legend above tabs
### Accessibility

- View tabs: `role="tablist"` with three `role="tab"`s (Yours/Merged/AI); arrow-key navigation; selection announced
- Each row: `role="listitem"`; SR label "Your note: {userLine}{. AI adds: {aiAddition}}" — the `↳` glyph is decorative
- Legend dots are decorative; the labels carry meaning
- Inline editors are labelled textboxes ("Edit your note" / "Edit AI addition")
- `ai-regenerating` announced politely ("Regenerating addition")

### Data contract

```ts
type HybridNote = {
  id: string;
  userLine: string;
  aiAddition?: string | null;     // absent/null → user-only row (33i third row)
  aiState?: 'ready' | 'regenerating' | 'error';
  aiEditedByUser?: boolean;       // strike original + override underneath
  aiOriginal?: string | null;     // shown struck-through when aiEditedByUser
};

type HybridNotesProps = {
  title?: string;
  notes: HybridNote[];
  view: 'yours' | 'merged' | 'ai';     // persisted per-user
  generating: boolean;                 // skeleton under every user line
  onViewChange: (view: HybridNotesProps['view']) => void;
  onEditUserLine: (id: string, text: string) => void;
  onEditAi: (id: string, text: string) => void;
  onRegenerateAi: (id: string) => void;
  onRemoveAi: (id: string) => void;
};
```

- On extremely narrow: `↳` remains inline; body wraps beneath it

---

## `MeetingCard` — 33j

**Purpose:** A single meeting entry in a list.
**Where it lives:** `MeetingsFolderList` (31f) `full` variant · Home Recent list (31a) `compact` variant · mobile Meetings list `compact-mobile` variant.

### Layout — list container (per rule 2)

- **Meetings are rows inside a single parent card**, not individual card frames.
- Container: `radius.lg` · bg `color.surface.raised` · border 1px `color.divider.subtle` · padding `space.xs` `space.l`
- Rows separated by 1px `color.divider.faint`; last row has no divider
- Each row `MeetingCard` has:
  - Padding: `space.m` 0 (vertical only)
  - Direction: column · gap `space.xs`
  - **No border, no radius, no bg.** The parent card owns those.

### Content — standard row

**Title row** (`space-between`, align: baseline)
- Left group: optional pin glyph 10pt `color.accent.primary` + title `type.body.strong` (Geist 600 · **[Token Gap · size.body.strong ≈ 13.5]**) + optional "NEW" eyebrow (`type.eyebrow.tight` · `color.accent.primary`)
- Right: date/duration `type.mono.body` · `color.text.dim` · letter-spacing `letter.mono.subtle`

**Preview**
- `type.body.sm` · `color.text.secondary` · truncate

**Footer row** (`space-between`, align: center)
- Left: **participant chips as dot + name** (per rule 1) · direction row · gap `space.l`
  - `+N` overflow label in `color.text.faint` when >3
- Right: attribute glyphs — inline row · gap `space.m` · `type.mono.tiny` · `color.text.dim`
  - Marks: `★ N` (star in `color.speaker.ochre` · **[Token Gap]**)
  - Action items: `✓ N`
  - Has recording: `▶`

**Hover actions (standard variant)**
- Absolutely top-right (aligned with date), icon row per rule 3
- Direction: row · gap `space.m`
- 12pt glyphs stroke `stroke.icon`, color `color.text.faint`
- Icons: Play · Open (link-out) · Delete (delete glyph in `color.danger.soft`)
- Opacity 0 by default → 1 on row hover; entrance `motion.fadeInSlow ≈ 120ms` — **[Token Gap]**
- Meta cell shifts to reserve space (no jump)

### `NewIndicator`

- 3×12 pill, `color.accent.primary`, radius 2, absolute `left -20 top 22` (inside parent card padding)

### Content — compact row (Home Recent + mobile)

- Direction: row · align: center · gap `space.m`
- Padding: `space.s` 0
- Left: date + duration stack (`type.mono.tiny` · date `color.text.faint` · duration `color.text.secondary`) · width `size.metaCol ≈ 48` — **[Token Gap · metaCol]**
- Middle: title `type.body.sm` (Geist 600) + preview `type.body.tiny` (Geist 400 · `color.text.secondary`)
- Right: participant dot+initial pairs, gap `space.s`

### States

- `default` (read)
- `unread / new` — `NewIndicator` visible, "NEW" eyebrow visible; auto-flips to `read` after user opens
- `pinned` — pin glyph visible; row bg unchanged (per rule 2, no per-row fill); optional inset 1.5px left `color.accent.primary`
- `processing` — preview replaced with skeleton bar + "Summarizing…"; participants render dashed dots
- `errored` — inline "PROCESSING FAILED" eyebrow in `color.danger.soft`; retry in overflow menu
- `active` (currently open) — inset 1.5px left `color.accent.primary`
- `hover` — hover-action row visible; participant dots lift +6% opacity
- `selected` (multi-select) — 1.5px outline inside `color.accent.primary`; checkbox appears at row start (pushes content right)
- `live` (currently being recorded) — meta cell replaced by inline `LiveIndicator`

### Interactions

- Click row → open `PostMeetingSummary` (31e) for this meeting
- Right-click → context: Rename · Pin/Unpin · Duplicate · Move to folder · Export… · Delete
- Cmd-click → toggle multi-select
- Hover actions: Play (from beginning) · Open (new window) · Delete (inline confirm with 5s undo)

### Edge cases

- No participants detected → single count "N speakers" chip on left
- Duration unknown → time cell shows "· processing"
- Long title → truncate with ellipsis; tooltip on hover after `hover.delay`
- Currently-recording card → click brings user back to live view, not summary
- Compact-mobile → hover actions replaced with long-press context menu

### Responsive

- Standard collapses to compact below `breakpoint.desktop.sm`
### Accessibility

- Row: `role="listitem"` + an inner `role="button"` covering the whole row, label "{title}, {relative date}, {duration}{, new}{, pinned}{, processing}" — attribute glyphs (★ ✓ ▶) are decorative duplicates of that label's counts
- Hover actions are real buttons ("Play meeting" / "Open in window" / "Delete meeting"), also reachable via the row context menu for keyboard users (Shift+F10 / long-press mobile)
- Multi-select checkbox: `role="checkbox"`, label "Select {title}"
- `new`/`pinned`/`live` must be text-bearing (eyebrow / SR label), not indicator-pill color alone
- Touch target: whole row ≥44pt tall on mobile

### Data contract

```ts
type MeetingCardData = {
  id: string;
  title: string;
  startedAt: string;              // ISO; rendered "Today · 10:00" / "Mon" / "FRI"
  durationSeconds: number | null; // null → "· processing" in the meta cell
  preview: string;                // one-line summary teaser
  participants: Array<{ id: string; name: string; paletteKey: SpeakerPaletteKey }>;
  participantOverflow?: number;   // "+N" beyond the first 3
  marksCount: number;             // ★ N (0 hides)
  actionItemsCount: number;       // ✓ N (0 hides)
  hasRecording: boolean;          // ▶ glyph
  isNew: boolean;
  isPinned: boolean;
  status: 'ready' | 'processing' | 'failed' | 'live';
  isActive: boolean;              // currently open
  isSelected?: boolean;           // multi-select
  variant: 'standard' | 'compact' | 'compact-mobile';
};
// callbacks: onOpen(id) · onPlay(id) · onOpenWindow(id) · onDelete(id) ·
//            onPin(id) · onSelectToggle(id) · onContextMenu(id)
```

- Compact-mobile omits preview line on very narrow screens

---

## Token Gaps

Consolidated from the widgets above. Resolve with the design owner **before** implementing.

1. **`strokeIcon`** — 1.4 canonical stroke for all inline icons (v2)
2. **`size.eyebrow`** — 9.5pt (was 10)
3. **`letter.eyebrow.wide`** — 0.16em uppercase tracking
4. **`letter.tightMinus1` · `letter.tightMinus2` · `letter.tightMinus3`** — -0.01 / -0.02 / -0.03 em
5. **`letter.mono.tracked`** — 0.05–0.08em for stat-style mono meta lines
6. **`letter.mono.subtle`** — 0.05em subtle tracking on timestamps
7. **`space.xxs`** — 2/3 canonical fine spacing
8. **`speakerCol`** / **`timestampCol`** — 60 / 38 pt fixed columns in dense transcript
9. **`actionRailGap`** — 70 pt reserved right padding in spacious transcript
10. **`iconTap`** — 28 pt invisible hit target for glyph-only buttons
11. **`size.mono.tiny`** — 9.5 pt smallest mono
12. **`size.mono.body`** — 10.5 pt normal mono
13. **`size.mono` (compact)** — 13 pt (HUD)
14. **`size.mono.h4`** — 26 pt for large timer (medium weight, not bold)
15. **`size.mono.h5`** — 22 pt (fallback below breakpoint)
16. **`size.body.tiny`** — 10 pt smallest body
17. **`size.body.sm`** — 12 pt
18. **`size.body`** — 11 pt (SpeakerChip / speaker name in header)
19. **`size.body.reading`** — 13 pt spacious transcript body
20. **`size.body.strong`** — 10–13.5 pt used in multiple contexts (formalize discrete steps)
21. **`size.chip`** — 11 pt speaker chip label
22. **`size.avatar`** — canonical sizes `sm 22 / md 34`
23. **`size.avatarInitial`** — 12 pt for the letter inside an avatar disc
24. **`size.checkboxSize`** — 16 pt
25. **`size.metaCol`** — 48 pt compact row date/duration column
26. **`size.card.max`** — 520 pt MarkedMomentCard width cap
27. **`size.sourceLabel`** — 28 pt label column in split waveform
28. **`size.chipMaxWidth`** — SpeakerChip ellipsis threshold
29. **`size.dot.sm / md`** — 6 / 8 pt indicator dots
30. **`line.body.tight` · `line.body.reading` · `line.body.notes`** — 1.55 / 1.7 / 1.75 canonical body line heights
31. **`line.max`** — 8 lines for MarkedMomentCard user note before Show more
32. **`line.enhancement.max`** — 6 lines for AI enhancement in hybrid notes
33. **`color.divider.faint`** — the 1px inter-row divider inside a card (weaker than `divider.subtle`)
34. **`color.border.strong`** / **`color.border.faint`** — checkbox border / dashed unknown-avatar border
35. **`color.surface.base` · `.raised` · `.hover` · `.hoverStrong`** — the 4 canonical surface layers used across widgets
36. **`color.speaker.<name>` family** — terracotta / slate / sage / ochre / self / unknown, each with a single dot color plus `subtle` (avatar bg) and `soft` (avatar text) tints
37. **`color.accent.primary` · `.soft` · `.on`** — accent variants (`soft` used for text on accent bg, `on` for text on solid accent)
38. **`color.record.*`** — dot color + subtle/soft variants
39. **`color.note.strong`** — ochre-adjacent for "YOUR NOTE" eyebrow
40. **`color.success.*`** — dot / soft / on (for checkbox, permission ready)
41. **`color.warning.*`** — soft / border for near-due chip, dictation, clipping
42. **`color.danger.*`** — soft / border for destructive icon, ai-uncertain, errors
43. **`color.tooltip.bg`** — tooltip background (no border in v2)
44. **`color.text.inverse`** — bar fill on light-mode waveform
45. **`opacity.disabled`** / **`opacity.done`** / **`opacity.dim`** — canonicalize the muting scale
46. **`focus.ring`** — keyboard focus outline style
47. **`hapticTokens`** — `tap` / `success` / `error`
48. **`hover.delay`** — 500ms canonical tooltip hover-in delay
49. **`toast.undoTimeout`** — 5s canonical undo window
50. **`autosave.debounce`** — 1s scratchpad autosave delay
51. **`playback.preRoll`** — 3s pre-roll before mark playback offset
52. **`silence detector params`** — RMS threshold + 30s window
53. **`motion.pop`** — 200ms scale/opacity ring around just-marked button
54. **`motion.wave`** — per-bar staggered scaleY cycle for waveform
55. **`motion.pulse`** — 1.4s ease-in-out dot pulse for record indicators
56. **`motion.fadeInSlow`** — 120ms fade for hover actions on meeting card
57. **`motion.checkmark`** — checkmark stroke reveal animation
58. **`breakpoints`** — `desktop.sm`, `desktop.md`
59. **`rich-text formatting palette`** — em-dash bullet / ordered / checkbox / code / quote styling in scratchpad
60. **Speaker palette assignment rule** — deterministic by first-heard order or by hash of fingerprint?
61. **Voice-fingerprint UI location** — inline chip corner-badge (avatar) vs standalone `VoiceFingerprintBanner`: confirm one canonical treatment (spec keeps both)
62. **RESOLVED (Jul 2026):** `color.accent.primary` = terracotta `#C85A3E` (record red `#E05049` stays a separate family). The stale `#E8522A` line in `context/05-conventions.md` has been corrected. Speaker dot palette as implemented: terra `#D98A72` · slate `#8FA7C2` · sage `#A9BD98` · ochre `#D9B36B` (self).
63. **`clipDurationSec` display rule** — 33b shows `▶ 0:14` on marks with a bounded clip; confirm when a mark gets a bounded clip vs open-ended playback (fixed window around the mark? silence-delimited?).

---

## v1 → v2 migration notes

If a widget was already built against turn 32, apply these deltas:

- **Remove all chip background fills.** Speaker chip / status chip / meta chip become dot + label. Delete `padding`, `radius.xs`, and `bg` from the chip element; keep the color on the dot.
- **Flatten card-in-card layouts.** In `ActionItemsCard`, `MarkedMomentCard` list, `MeetingCard` list: remove the per-row card border/bg/radius; move borders/bg to a single parent card; separate rows with 1px `color.divider.faint`.
- **Convert `IconButton` chrome to plain glyphs** for MarkMomentButton, MarkedMomentCard action row, MeetingCard hover actions, ScratchpadEditor DictateChip. Keep the invisible hit target (`iconTap`).
- **Replace segmented controls with underline tabs** (HybridNotesRenderer ViewToggle).
- **Delete "AI enhancement bg block"** in `HybridNoteRow`; use indented `↳ …` line in `color.text.dim` instead.
- **Timer numerals weight 500** (not 600). Tighten tracking to `letter.tightMinus3`.
- **Eyebrows go to 9.5pt, 0.16em tracking.**
- **Reduce all icon strokes to 1.4**; consolidate the previous 1.6/1.7/1.8 variants.
- **Drop dashed / colored row borders** used to signal AI uncertainty; use inline eyebrow "low confidence" plus muted text color instead.

---

## Component Inventory

Flat checklist for tracking build progress across the widget kit v2.

### Base primitives (build first — referenced by many widgets)
- [ ] `SpeakerDot` — the 6pt colored dot (used everywhere a speaker or category is referenced)
- [ ] `GlyphButton` — invisible-hit-target inline icon (no bg, no radius)
- [ ] `UnderlineTabs` — segmented control per rule 4
- [ ] `Checkbox` — 16pt, states `unchecked / checked / disabled / indeterminate`
- [ ] `Tooltip` — no border, bg-only, appears after `hover.delay`
- [ ] `TextField` (inline) — used by SpeakerChip editing, ScratchpadEditor headings, ActionItemRow edit
- [ ] `Divider` — 1px `color.divider.faint` inter-row line (used inside parent cards)

### Widget checklist
- [ ] `TranscriptLine` — 33a (dense · spacious · 7 states)
  - [ ] Action rail (inline glyphs, no chrome)
  - [ ] Streaming caret
  - [ ] Searched-hit inline underline
- [ ] `MarkedMomentCard` — 33b
  - [ ] Excerpt block (no border-emphasis)
  - [ ] User note block (eyebrow-only signal)
  - [ ] Note-editing sub-state
  - [ ] Deleted-pending + 5s undo
- [ ] `ActionItemRow` — 33c
  - [ ] `pending / done / edited / ai-uncertain / hover`
  - [ ] Rows-in-single-card layout
  - [ ] Owner assignment sheet
  - [ ] Keep / Reject text links (not chips)
- [ ] `SpeakerChipAvatar` — 33d
  - [ ] Chip (dot + label, no bg) — `named / unnamed / editing / self / recognized / hover`
  - [ ] Avatar (`sm / md`) — `named / unnamed / self / recognized`
  - [ ] Editing state uses bottom-underline only
  - [ ] `VoiceFingerprintBanner`
  - [ ] Speaker sheet (rename / merge / hide / block)
- [ ] `ElapsedTimer` — 33e
  - [ ] `compact / large` × `live / paused / starting / stopping`
  - [ ] Medium weight numerals, tight tracking
  - [ ] Format switch `M:SS` ↔ `H:MM:SS` ↔ `HH:MM:SS` with tabular-nums
- [ ] `MarkMomentButton` — 33f
  - [ ] Glyph-only, no bg/chrome
  - [ ] `idle / hover / just-marked / with-count / disabled / focused`
  - [ ] Count numeral (no badge disc)
  - [ ] `⌘M` shortcut + tooltip
- [ ] `LiveWaveform` — 33g
  - [ ] Variants `mini / small / medium / medium-split` (thinner bars in v2)
  - [ ] States `active / silence / paused / muted-source / clipping`
- [ ] `ScratchpadEditor` — 33h
  - [ ] `empty / typing / dictating / read-only / edit-mode / error / permission-missing-dictate`
  - [ ] Border-only dictating signal (no bg fill)
  - [ ] Em-dash bullet marker
  - [ ] Dictate as inline glyph+label, not chip
  - [ ] Autosave + conflict banner
- [ ] `HybridNotesRenderer` — 33i
  - [ ] `merged / yours-only / ai-only`
  - [ ] `HybridNoteRow` (dot + text; AI as `↳` indent, no bg block)
  - [ ] `ai-regenerating / ai-edited-by-user / error` per-row
  - [ ] UnderlineTabs view toggle
  - [ ] Dot+label legend pair
- [ ] `MeetingCard` — 33j
  - [ ] Variants `standard / compact / compact-mobile`
  - [ ] States `default / unread / pinned / processing / errored / active / hover / selected / live`
  - [ ] Rows-in-single-card layout (no per-row frames)
  - [ ] `NewIndicator` bleed pill
  - [ ] Hover action glyph row (no bg)
  - [ ] Multi-select checkbox layer

### Cross-widget behaviors to verify at review
- [ ] Speaker rename in one place propagates to every widget instance
- [ ] Voice fingerprint banner appears only on first meeting a voice is recognized
- [ ] Marking a moment updates `MarkMomentButton` count AND inserts a `MarkedMomentCard` AND stamps the correct `TranscriptLine`
- [ ] Toggling `HybridNotesRenderer.UnderlineTabs` preserves scroll position
- [ ] Deleting an `ActionItemRow` marked as AI-uncertain does not remove other AI-extracted items
- [ ] Compact `MeetingCard` on mobile: long-press = desktop right-click menu
- [ ] Dictating into `ScratchpadEditor` never affects meeting audio capture
- [ ] Playing audio from any widget reuses the same audio player state (only one thing plays at a time)
- [ ] Nowhere in this kit does a chip have a background fill — reviewer should visually check
- [ ] Nowhere in this kit is a row card nested inside another card — reviewer should visually check
