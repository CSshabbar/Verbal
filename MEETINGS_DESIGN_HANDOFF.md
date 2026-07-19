# MEETINGS_DESIGN_HANDOFF.md

Developer handoff for the **Meetings** feature in the Flume desktop app.
Every value below references a **token** from the existing system. Unmapped
values are called out inline and consolidated in **Token Gaps** at the end.

Token source of truth:
- `whisperflow/app/theme.py`
- `whisperflow/app/fonts_css.py`
- `verbal-mobile/flume-ui/theme/` (parity mirror)
- `context/05-conventions.md`

Screens referenced in the design: `#31a`–`#31h` in `Flume Wireframes.dc.html`.

---

## Widgets

Reused across multiple screens. Defined once, referenced by name below.

### `WindowChrome`

**Purpose:** Standard app-window title bar for every Meetings screen.
**Where it lives:** All top-level screens (31a, 31b, 31c, 31e, 31f, 31g, 31h).

**Layout**
- Direction: row · align: center · gap: `space.xs`
- Height: `height.titleBar` — **[Token Gap · titleBarHeight]**
- Padding: 0 `space.m`
- Background: `color.chrome.bar` — **[Token Gap · chromeBar]**
- Border-bottom: 1px `color.divider.subtle`

**Children (in order)**
1. Traffic-light group — 3 discs, `size.trafficLight`, gap `space.xs`. Colors are macOS-native, not Flume tokens.
2. Center title — `type.chrome` (Geist 500 · **[Token Gap · size.chrome ≈ 11.5]** · `color.text.dim`)
3. Right spacer — same width as traffic lights for optical centering

**States:** `focused`, `unfocused` (title fades to `color.text.faint`).

**Interactions:** drag = move window. Double-click title = maximize.

---

### `SidebarNav`

**Purpose:** Left navigation column on desktop screens.
**Where it lives:** 31a, 31f, 31g. Also present on all non-meeting desktop screens.

**Layout**
- Width: `size.sidebar.width` — **[Token Gap · sidebarWidth ≈ 196]**
- Padding: `space.m` `space.s`
- Direction: column
- Background: `color.chrome.sidebar` — **[Token Gap · chromeSidebar]**
- Border-right: 1px `color.divider.subtle`

**Children (in order)**
1. Brand row — `LogoMark` (16pt cream/accent) + wordmark `type.brand` (Geist 600 · **[Token Gap · size.brand ≈ 12.5]**)
2. Section eyebrow — `type.eyebrow` (JetBrains Mono 500 · 10pt · `color.text.faint` · uppercase · tracking `letter.eyebrow`)
3. Nav items — see `NavItem` below
4. Flex spacer
5. Account row — avatar disc + name (`type.body.sm`) + settings glyph

**Responsive:** hidden below `breakpoint.desktop.md` — **[Token Gap · breakpoints]** — replaced by icon-only column.

---

### `NavItem`

**Purpose:** Single row inside `SidebarNav`.
**Where it lives:** `SidebarNav`.

**Layout**
- Direction: row · align: center · gap: `space.s`
- Padding: `space.s` `space.m`
- Radius: `radius.md`

**Content**
- Leading icon: 14pt line icon, stroke `stroke.thin` — **[Token Gap · strokeThin ≈ 1.6]**
- Label: `type.body` (Geist 500 · **[Token Gap · size.body ≈ 12]** · `color.text.primary`)
- Trailing count: `type.mono.sm` (`color.text.faint`)

**States**
- `default` — bg transparent, label `color.text.secondary`
- `hover` — bg `color.surface.hover`
- `active` — bg `color.surface.raised`, label `color.text.primary`, weight 600
- `disabled` — opacity `opacity.disabled`

**Interactions:** click = navigate. `⌘1..9` shortcuts bound in order.

---

### `PrimaryButton`

**Purpose:** Main accent CTA.
**Where it lives:** 31a (Start meeting), 31b (Start recording), 31f (New meeting), 31h (Test capture).

**Layout**
- Direction: row · align: center · gap: `space.xs`
- Padding: `space.s` `space.m`
- Radius: `radius.md`
- Background: `color.accent.primary` (Flume terracotta)
- Text color: `color.accent.on` — **[Token Gap · accentOn]**

**Content**
- Optional leading icon 12pt (semantic: "record start" = filled disc)
- Label: `type.button` (Geist 600 · **[Token Gap · size.button ≈ 12]**)

**States**
- `default` — as above
- `hover` — `color.accent.primaryHover` — **[Token Gap · accentHover]**
- `pressed` — `color.accent.primaryPressed` — **[Token Gap · accentPressed]**
- `disabled` — bg `color.accent.primary` at `opacity.disabled`, label at `opacity.disabled`
- `loading` — spinner replaces icon, label unchanged

**Interactions:** click = fire action. Fires haptic `haptic.tap` — **[Token Gap · hapticTokens]**. Focus ring: `focus.ring` — **[Token Gap · focusRing]**.

---

### `SecondaryButton`

**Purpose:** Non-accent alternative (Cancel, Settings, Skip).
Same layout as `PrimaryButton`, differences:
- Background: transparent
- Border: 1px `color.border.subtle`
- Text: `color.text.primary`
- Hover: bg `color.surface.hover`

---

### `IconButton`

**Purpose:** Square action buttons in headers (star, share, edit, refresh).
**Where it lives:** 31c (mark, pause, stop), 31d (mark, return), 31e (edit, regenerate, share).

**Layout**
- Size: `size.iconButton.md` — **[Token Gap · iconButtonSizes: 24 / 26 / 30]**
- Radius: `radius.sm`
- Background: `color.surface.raised`
- Icon: 12–13pt line icon, `color.text.primary`

**States:** `default`, `hover` (bg `color.surface.hoverStrong`), `pressed`, `disabled`, `active` (bg `color.accent.subtle`, icon `color.accent.primary`).

**Semantic-role variants:**
- `destructive` — bg `color.danger.subtle`, icon `color.danger`
- `record` — bg `color.record`, icon `color.record.on` — **[Token Gap · recordColor ≈ #E05049]**

---

### `SpeakerChip`

**Purpose:** Colored capsule identifying a meeting speaker.
**Where it lives:** 31c (utterance headers), 31e (participants + action items), 31f (participant row).

**Layout**
- Padding: `space.xxs` `space.xs` — **[Token Gap · xxsSpace ≈ 2 · 3]**
- Radius: `radius.xs`
- Font: `type.chipLabel` (Geist 600 · **[Token Gap · size.chip ≈ 9.5–10]**)

**Palette (per-speaker tint families)**
- Speaker A — `color.speaker.terracotta` (bg `accent.subtle`, text `accent.soft`)
- Speaker B — `color.speaker.slate` — **[Token Gap · speakerSlate]**
- Speaker C — `color.speaker.sage` (mirrors sage feature color)
- Speaker D — `color.speaker.ochre` — **[Token Gap · speakerOchre]**
- Self — `color.speaker.self` — **[Token Gap · speakerSelf]** — maps to ochre in current comp

**States:** `default`, `editing` (renamed inline — input replaces label, border `color.accent.primary`), `unknown` (text "Speaker N", `color.text.dim`).

**Interactions:** double-click = rename inline. `Enter` commits, `Esc` cancels.

**Edge cases:** long name → truncate with ellipsis at `size.speakerChip.maxWidth` — **[Token Gap · speakerChipMax]**.

---

### `LiveIndicator`

**Purpose:** Blinking "REC" / "LIVE" pill.
**Where it lives:** 31c header, 31d (all HUD states except paused).

**Layout**
- Direction: row · align: center · gap: `space.xs`
- Padding: `space.xxs` `space.s`
- Radius: `radius.pill`
- Background: `color.record.subtle` — **[Token Gap · recordSubtle]**
- Border: 1px `color.record.border` — **[Token Gap · recordBorder]**

**Content**
- Pulsing dot — 6pt, `color.record`, animation `motion.pulse` — **[Token Gap · pulseDuration ≈ 1.4s / easeInOut]**
- Label: `type.mono.eyebrow` · text `color.record.soft` — **[Token Gap · recordSoft]**

**States:** `recording` (dot pulses), `paused` (dot `color.text.faint`, no animation, label "PAUSED"), `starting` (dot solid, no pulse).

---

### `WaveformStream`

**Purpose:** Live audio activity indicator.
**Where it lives:** 31d (expanded HUD).

**Layout**
- Direction: row · align: center · gap `space.xxs`
- Height: `size.waveform.hud.height` — **[Token Gap · waveHeights]**
- Bars: `size.waveform.bar.w` × `size.waveform.bar.h` · fill `color.text.primary`

**Bar count:** 5 for HUD, 20 for keyboard recording bar (see mobile handoff).

**States:** `active` (bars animate on 250–1100ms cycle via `motion.wave`), `paused` (frozen at last frame at 40% opacity), `muted` (all bars at min height).

**Interactions:** none — passive.

---

### `Toggle`

**Purpose:** On/off switch for a setting or capture source.
**Where it lives:** 31b (audio sources), 31g (all Behavior/Storage/Capture rows).

**Layout**
- Track: 30×17, `radius.pill`
- Thumb: 13×13 disc, `color.thumb` — **[Token Gap · toggleThumb]**
- On: track `color.accent.primary`
- Off: track `color.surface.raisedStrong`

**States:** `off`, `on`, `disabled` (opacity `opacity.disabled`), `pending` (spinner replaces thumb — for permission grants).

**Motion:** thumb slides 250ms `easing.standard`.

---

### `PermissionBadge`

**Purpose:** Compact status pill for permissions and capture readiness.
**Where it lives:** 31a (audio badges), 31b (audio source rows), 31g (Capture section), 31h (step rows).

**Content**
- Dot: 5pt, semantic color
- Label: `type.mono.eyebrow` — **[Token Gap · eyebrowSize ≈ 10]**

**Variants**
- `ready` — bg `color.success.subtle`, dot `color.success`, text `color.success.soft`
- `pending` — bg `color.warning.subtle`, dot `color.warning`, text `color.warning.soft` — **[Token Gap · warningTokens]**
- `denied` — bg `color.danger.subtle`, dot `color.danger`, text `color.danger.soft` — **[Token Gap · dangerTokens]**
- `offline` — bg `color.surface.raised`, dot `color.text.faint`, text `color.text.secondary`

---

### `SectionEyebrow`

**Purpose:** Small uppercase label above a group of content.
**Where it lives:** Nearly every screen (Recent meetings, Live transcript, Your notes, Marks, etc.).

**Content**
- `type.eyebrow` (JetBrains Mono 500 · **[Token Gap · size.eyebrow ≈ 10]** · uppercase · tracking `letter.eyebrow ≈ 0.14em` · color `color.text.faint`)

Two color variants:
- `neutral` — `color.text.faint`
- `accent` — `color.accent.primary` (used inside cards where content is scoped: Summary, Decisions, Action items, Notes header)

---

### `MetaLine`

**Purpose:** Timestamps, durations, speaker counts, byte counts. Always monospaced.
**Where it lives:** every recording/meeting listing.

**Content**
- `type.mono.body` (JetBrains Mono 500 · **[Token Gap · size.mono ≈ 10.5]** · `color.text.dim`)

---

## Screens

---

## `MeetingLauncherHome` — `#31a`

**Purpose:** Entry point for starting a new meeting from the dashboard, with a mirrored menubar entry.
**Where it lives:** Top-level screen (Home dashboard). Menubar variant lives in the tray popover.

### Layout — dashboard variant

- Container: `WindowChrome` header + row body
- Body direction: row · gap 0
- Body children:
  1. `SidebarNav`
  2. `HomeMain` — flex 1 · padding `space.l` `space.lg` · direction column

### `HomeMain` children (in order)

1. **Greeting block**
   - eyebrow: "Good morning" · `type.caption` (Geist 400 · **[Token Gap · size.caption ≈ 11]** · `color.text.dim`)
   - name: `type.h4` (Geist 600 · **[Token Gap · size.h4 ≈ 22]** · `color.text.primary` · tracking `letter.tightMinus2`)
2. **`MeetingLauncherCard`** (see below)
3. **Section header**
   - eyebrow (neutral): "Recent meetings"
   - trailing link: "See all →" — `type.linkSm` (Geist 500 · size 11 · `color.text.dim`)
4. **Recent list** — 3× `MeetingListRow` (`variant="compact"`)

### `MeetingLauncherCard` (widget scoped to this screen)

**Layout**
- Padding: `space.m` — **[Token Gap · card padding sits between space.m and space.l]**
- Radius: `radius.lg`
- Background: `color.surface.gradient` — **[Token Gap · surfaceGradient (17191c → 1c1e22)]**
- Border: 1px `color.divider.subtle`
- Direction: row · gap `space.m` · align: start · justify: between

**Left column**
1. Row: `Badge`("NEW", `variant="accent"`) + title "Record a meeting" (`type.h6` · **[Token Gap · size.h6 ≈ 13.5]** · `color.text.primary`)
2. Description — `type.body` (Geist 400 · 12 · `color.text.secondary` · line-height 1.5)
3. Actions row — gap `space.xs`
   - `PrimaryButton` "Start meeting" · leading icon = filled disc (record)
   - `SecondaryButton` "Settings" · leading icon = gear
   - Right-aligned mono shortcut: `type.mono.body` "⌘⌥M" · `color.text.faint`

**Right column**
- Stack (column, gap `space.xs`): two `PermissionBadge` (`variant="ready"`) — "System audio", "Microphone"

### States

- `default`
- `permissions-missing` — badges show `variant="denied"`, PrimaryButton opens permission modal instead of starting
- `already-recording` — card collapses; replaced by `ActiveMeetingCard` — **[Token Gap · define ActiveMeetingCard variant]**
- `hover` — no visual change to card; button hover states apply

### Interactions

- Click `Start meeting` → open `PreMeetingModal` (31b). If shift-held → skip modal.
- Click `Settings` → nav to Settings > Meetings (31g).
- Enter shortcut `⌘⌥M` from anywhere → same as Start meeting.

### Edge cases

- No recent meetings → `RecentMeetingsEmpty` (2-line copy, no rows). Cf. Empty states section.
- Very long meeting titles in recent rows → truncate with ellipsis.
- Permissions denied → the row becomes non-clickable, opens permission modal.

### Responsive

- Below `breakpoint.desktop.md` — **[Token Gap]**: sidebar collapses to icons; card two columns stack to one.

### Layout — menubar variant (`MenubarLauncherPopover`)

- Width: `size.menubar.width` — **[Token Gap · menubar width ≈ 280]**
- Radius: `radius.lg`
- Background: `color.surface.popover` — **[Token Gap · surfacePopover]**
- Border: 1px `color.divider.subtle`
- Shadow: `shadow.popover` — **[Token Gap · shadowPopover]**

**Sections**
1. Header row — logo mark + brand + status (`PermissionBadge` inline mini variant)
2. Menu items — 2× `MenuRow` (Start dictation, Start meeting). "Start meeting" is `active` (`bg color.accent.subtle`)
3. Footer bar — Open window · Quit — `type.linkSm`

**Interactions:** Escape or click-outside closes. `↑/↓` navigates items. `Enter` fires.

**Edge cases:** first-launch shows onboarding badge; when a meeting is active, this popover switches to the HUD-style status (see 31d).

---

## `PreMeetingModal` — `#31b`

**Purpose:** Confirmation step after clicking Start meeting.
**Where it lives:** Top-level modal, invoked from launcher or shortcut.

### Layout

- Backdrop: `color.scrim` — **[Token Gap · scrim ≈ rgba(0,0,0,0.55)]**
- Panel width: `size.modal.md` — **[Token Gap · modalWidths]**
- Panel background: `color.surface.modal` — **[Token Gap · surfaceModal]**
- Panel radius: `radius.xl`
- Panel shadow: `shadow.modal` — **[Token Gap · shadowModal]**

### Children (top to bottom)

1. **Title block** · padding `space.m` `space.l` `space.s`
   - `SectionEyebrow`(neutral) "New meeting"
   - Editable title field — `TextField` variant `title` (`type.h5` · `color.text.primary`) — **[Token Gap · size.h5 ≈ 15]**
   - Helper caption — `type.caption` · `color.text.faint`
2. **Capturing group** · padding 0 `space.l` `space.s`
   - `SectionEyebrow`(neutral) "Capturing"
   - Stack (column, gap `space.xs`) of 2× `AudioSourceRow` (System audio, Microphone)
3. **Footer** · padding `space.s` `space.l` · border-top `color.divider.subtle` · bg `color.surface.footer` — **[Token Gap · surfaceFooter]**
   - Left: hint `type.caption` "Press Enter to start"
   - Right: `SecondaryButton` "Cancel" + `PrimaryButton` "Start recording"

### `AudioSourceRow` (component)

- Direction: row · align center · gap `space.s` · padding `space.s` `space.m` · radius `radius.md` · bg `color.surface.raised` · border 1px `color.divider.subtle`
- Icon disc: 26pt, `radius.sm`, bg `color.success.subtle`, icon `color.success`
- Text stack: label `type.body` (Geist 600) + sub `type.caption` (`color.text.dim`)
- Trailing: `Toggle`

### States

- `default` — both sources granted, Start enabled
- `mic-denied` — mic Toggle disabled, sub text swaps to "Not permitted · Grant"; Start becomes disabled and shows tooltip. **[Token Gap · define tooltip token]**
- `system-audio-denied` — same as above; clicking Grant opens `PermissionChecklistModal` (31h)
- `dismissable-skip` (shift-Enter or "Skip setup" preference) — modal short-circuits and starts immediately

### Interactions

- `Enter` → Start (unless disabled)
- `Esc` or Cancel → close, no state change
- Editable title accepts free text; auto-saves. `Cmd+Backspace` clears to default.
- Toggles fire immediately; no confirmation.

### Edge cases

- No microphone hardware → mic row hidden, note added in helper caption
- Empty title → falls back to default "Meeting — {date}" on submit

### Responsive

- Modal max-width caps at `size.modal.md`. On very small windows, shrinks to `size.modal.sm` — **[Token Gap · modal sizes]**.

---

## `InMeetingTwoPanel` — `#31c`

**Purpose:** The primary in-meeting workspace.
**Where it lives:** Top-level screen. Enters after `PreMeetingModal` submit or menubar Start.

### Layout

- Container: `WindowChrome` + column
- Width: `size.window.meetingLg` — **[Token Gap · meeting window width ≈ 820]**
- Height: `size.window.meetingLg` height — **[Token Gap]**
- Column children (in order):
  1. `MeetingHeader` (widget)
  2. Body row — flex 1 · direction row · min-height 0
     - `TranscriptPane` — flex 1.4
     - `ScratchpadPane` — flex 1 · bg `color.surface.subtle` — **[Token Gap · surfaceSubtle ≈ #0c0e10]**
  3. `MarksFooter` (widget)

### `MeetingHeader`

- Direction row · align center · gap `space.s` · padding `space.s` `space.lg` · border-bottom `color.divider.subtle`
- Children:
  1. `LiveIndicator` (state `recording`)
  2. Title (editable inline) — `type.h5` · `color.text.primary` · trailing hint `type.caption` "click to rename" · `color.text.faint`
  3. Elapsed timer — `type.mono.h5` — **[Token Gap · size.mono.h5 ≈ 16]** · `color.text.primary`
  4. Action group: `IconButton(role="star")` accent · `IconButton(role="pause")` neutral · `IconButton(role="stop")` variant `record` label "Stop"

### `TranscriptPane`

- Direction column · min-width 0
- Header row (padding `space.s` `space.l` · gap `space.s`): `SectionEyebrow`("Live transcript") + `SearchField` (compact)
- Body: overflow y auto · padding 0 `space.l` `space.s` · direction column · gap `space.m`
- Auto-scroll-to-bottom unless user is scrolled up ⇒ show "Jump to live" pill (see below)

**`Utterance` component**
- Structure: header row + body paragraph
- Header row: `SpeakerChip` + timestamp `MetaLine`
- Optional trailing chip: "★ MARKED" — `type.mono.chip` in `color.accent.primary` on `color.accent.subtle`
- Body: `type.body` · `color.text.secondary` · line-height 1.55
- Currently-transcribing utterance shows caret `▌` in `color.text.dim`

**States of `Utterance`:**
- `default`, `marked` (adds left border `color.accent.primary` 2px + inset), `active/streaming` (caret visible, body slightly emphasized), `searched-hit` (bg `color.accent.subtle`)

**"Jump to live" pill:** floating, bottom-center of pane, `radius.pill`, bg `color.surface.raised`, appears when scroll offset > 0.

### `ScratchpadPane`

- Direction column · bg `color.surface.subtle`
- Header row: `SectionEyebrow`("Your notes") + `DictateChip` (accent subtle pill with mic glyph)
- Editor: rich text with H1/H2, bullets, checkboxes — **[Token Gap · rich-text formatting palette]**
- Body: `type.body` · `color.text.primary` · line-height 1.65
- Bullet marker: `color.text.faint` · em-dot

**`DictateChip` states:** `idle`, `dictating` (bg `color.record.subtle`, icon animates), `paused`.

### `MarksFooter`

- Direction row · align center · gap `space.s` · padding `space.xs` `space.lg` · border-top `color.divider.subtle` · bg `color.chrome.sidebar`
- Left: `SectionEyebrow` (accent variant, prefixed with ★ glyph)
- Middle: horizontally-scrollable row of `MarkPill`

**`MarkPill`:** timestamp (mono) + label. Bg `color.accent.subtle`. Truncates.

### States (screen-level)

- `preparing` — before capture actually starts (buffer warm-up); header LiveIndicator shows `starting`, transcript shows skeleton
- `recording` — as drawn
- `paused` — LiveIndicator → paused; transcript continues to display but no new utterances; caret hidden
- `error` — top banner appears with `color.danger`; capture stops
- `background` — window loses focus → HUD (31d) appears; this screen keeps state

### Interactions

- Star icon or `⌘.` → mark current transcript position; `MarkPill` inserted, corresponding `Utterance` gains `marked` state
- Pause icon or `⌘P` → toggle capture pause
- Stop icon or `⌘Enter` → confirm-dismiss → transitions to `PostMeetingSummary` (31e)
- Click mark pill → smooth-scroll transcript to that utterance
- Double-click speaker chip → rename inline
- `⌘F` in transcript → focus search field
- `⌘K` in scratchpad → toggle dictate

### Edge cases

- Empty transcript — placeholder "Listening…" centered in pane, muted `type.body`
- Empty scratchpad — placeholder "Type here or tap Dictate to speak notes." `color.text.faint`
- Multiple simultaneous speakers — utterances interleave; speakers ordered by first-heard
- Very long meeting (>1h) — transcript virtualizes rows — **[Token Gap · virtualization row height]**
- Speaker rename applies retroactively to all their utterances

### Responsive

- Below window width `size.window.meetingLg` min: scratchpad collapses to a tab toggle above transcript
- Below `breakpoint.desktop.sm`: header actions group collapses to overflow menu

---

## `FloatingMeetingHUD` — `#31d`

**Purpose:** Passive activity indicator when window loses focus.
**Where it lives:** Top-level floating panel; anchored bottom-left of active screen by default.

### Window characteristics

- `NSNonactivatingPanelMask` + `NSScreenSaverWindowLevel` (per project convention)
- Ignores mouse events except within HUD bounds
- Draggable to any corner; position persisted per user

### Layout — collapsed pill (default)

- Direction row · align center · gap `space.s`
- Padding: `space.xs` `space.s`
- Radius: `radius.pill`
- Background: `color.surface.hud` — **[Token Gap · surfaceHud (translucent ~90%)]**
- Backdrop-filter: `blur.hud` — **[Token Gap · blurHud ≈ 14px]**
- Border: 1px `color.divider.subtle`
- Shadow: `shadow.hud` — **[Token Gap]**

**Children (in order)**
1. Pulsing dot 8pt · `color.record` · anim `motion.pulse`
2. Elapsed timer — `type.mono.body` · `color.text.primary`
3. `WaveformStream` (5 bars)
4. Meeting title — `type.caption` · `color.text.dim` · single-line ellipsis

### Layout — expanded (on hover)

- Same shape, radius `radius.lg` · min-width `size.hud.expanded.min` — **[Token Gap ≈ 380]**
- Adds:
  - Title block (row with meta subtitle "Recording · N speakers" in `type.captionXs` — **[Token Gap · captionXs ≈ 10]**)
  - Actions: `IconButton(role="star")` accent · `IconButton(role="pause")` · `IconButton(role="return")` — return uses "external link" glyph

### Layout — paused

- Same as collapsed pill
- Pulsing dot swaps to static `color.text.dim` dot
- Timer color drops to `color.text.secondary`
- Adds `SectionEyebrow` (mono, tracking) "PAUSED"
- Adds small `IconButton(role="resume")` disc (`radius.pill`, bg `color.accent.primary`)

### States

- `collapsed`, `expanded` (on hover), `paused`, `stopping` (buttons disabled + spinner), `error` (dot swaps to danger, tooltip shows message)

### Interactions

- Hover for ≥120ms → expand
- Mouse-leave with 400ms grace → collapse
- Click "return" → focuses main window
- Click "star" → drops mark; brief `motion.pop` on the star glyph — **[Token Gap · motion.pop]**
- Click "pause" → switches to paused variant
- Right-click → context menu: Move to corner, Hide until unpaused, Stop recording

### Edge cases

- Window is fullscreened over the HUD → HUD auto-hides for that space; reappears when user tabs
- Timer > 60 min → format switches from `M:SS` → `H:MM:SS` — **[Token Gap · timer format tokens]**
- Very long meeting title on expanded → ellipsize at `size.hud.title.max` — **[Token Gap]**

### Responsive

- Not window-relative. Position clamped to nearest 16pt from screen edges.

---

## `PostMeetingSummary` — `#31e`

**Purpose:** Payoff view immediately after a meeting ends.
**Where it lives:** Top-level screen. Auto-navigated on Stop from 31c. Reachable from list.

### Layout

- Container: `WindowChrome` + main flex column
- Padding: `space.l` `space.xl` — **[Token Gap · space.xl ≈ 32]**
- Direction: column · gap `space.m`
- Width: `size.window.meetingLg`
- Overflow: hidden (inner blocks scroll independently)

### Children (top to bottom)

1. **`MeetingSummaryHeader`**
   - Left column:
     - `SectionEyebrow` (neutral) — "Meeting · {relativeDate} {time}"
     - Title `type.h4` · `color.text.primary`
     - Meta line: duration + separator dot + participant `SpeakerChip`s
   - Right column: 3× `IconButton` (edit, regenerate, share)
2. **`SummaryCard`** — rounded card, bg `color.surface.raised`, border `color.divider.subtle`, padding `space.m` `space.l`
   - `SectionEyebrow`(accent) "Summary"
   - Body — `type.body.lg` (Geist 400 · **[Token Gap · size.body.lg ≈ 12.5]** · `color.text.primary`)
3. **Row: hybrid notes + decisions/actions column** — flex 1 · gap `space.m`
   - `HybridNotesCard` — flex 1.4 (see below)
   - Right stack (column · gap `space.s`) — flex 1:
     - `DecisionsCard`
     - `ActionItemsCard` (flex 1)
4. **Row: marks + transcript teasers** — gap `space.s`
   - `MarksTeaser`
   - `TranscriptTeaser`

### `HybridNotesCard`

- Padding: `space.m` `space.l`
- Radius: `radius.lg`
- Background: `color.surface.raised`
- Border: 1px `color.divider.subtle`

**Header row:** `SectionEyebrow`(neutral) "Notes" + `LegendPair` — two labeled swatches (accent line = "Your notes", faint line = "AI additions")

**Body:** Note items in a stack. Each item is a **`HybridNoteRow`** with:
- Left border 2px `color.accent.primary`
- Body — user text (`type.body` · `color.text.primary`)
- Beneath body — AI enhancement (`type.body.sm` · italic · `color.text.dim`, prefixed with arrow "→")

**State per row:** `user-only`, `enhanced` (has AI line), `user-edited` (user edited after AI added; italic block replaced with strikethrough of AI + user override).

### `DecisionsCard`

- Same card shell as `HybridNotesCard`, smaller padding `space.s` `space.m`
- `SectionEyebrow`(accent) "Decisions"
- Body: bulleted list · bullets `color.text.faint` · text `color.text.primary`

### `ActionItemsCard`

- Same shell, flex 1
- `SectionEyebrow`(accent) "Action items"
- Body: rows of `[SpeakerChip] [task text]`
- If owner unknown, `SpeakerChip` variant `unknown`
- State per row: `open`, `done` (checkbox, task strike-through) — **[Token Gap · define checkbox tokens]**

### `MarksTeaser` / `TranscriptTeaser`

- Row cards, radius `radius.md`, padding `space.s` `space.m`, bg `color.surface.raised`
- Leading icon (star / list)
- Middle label: `type.body.sm`
- Trailing action: `SectionEyebrow`(neutral) "EXPAND"

**Expanded state:** replaces card with a full section inline (marks list / full transcript with per-line click → jump to audio).

### States (screen-level)

- `processing` — Summary/Decisions/ActionItems bodies render as skeleton bars with subtle shimmer; header retains real data
- `processed` (default)
- `edited` — header shows "Edited {relative}" meta; Regenerate button gains attention indicator
- `regenerating` — same as processing but only the affected cards
- `error` — Summary card body replaced with `color.danger.soft` message + Retry button

### Interactions

- Click title → inline rename
- Click any `MarkPill` inside expanded marks → open per-mark modal with 3-sentence transcript excerpt and audio play button
- Click any transcript line → play audio at that offset; the row highlights via `state.audioActive` — **[Token Gap · audioActive highlight color]**
- Edit action → toggles the screen to edit mode: cards get subtle border `color.accent.subtle`; content editable inline; Save/Cancel bar appears docked bottom
- Regenerate → confirmation, then swaps card content with skeletons

### Edge cases

- No decisions extracted → `DecisionsCard` body renders empty state "No explicit decisions found."
- No action items → similar
- Very short meeting (<2 min) → Summary body may be one sentence; layout unchanged
- All speakers unknown → participants row shows count only "N speakers"
- Audio deleted (transcript-only) → audio play buttons disabled; explanation tooltip

### Responsive

- Below `size.window.meetingLg`, right column stacks under `HybridNotesCard`
- Below `breakpoint.desktop.sm`, header action buttons collapse to overflow

---

## `MeetingsFolderList` — `#31f`

**Purpose:** All past meetings, presented as a folder inside Notes.
**Where it lives:** Top-level screen (Notes > Meetings).

### Layout

- Container: `WindowChrome` + row body
- Body children:
  1. `SidebarNav` (Notes filters variant — All notes, Meetings [active], Voice notes, Starred)
  2. `NotesMain` — flex 1 · padding `space.l` `space.lg` · column

### `NotesMain` children (in order)

1. Header row (`space-between`):
   - Left: caption "18 meetings · 12h captured" (`type.caption` · `color.text.dim`) + title `type.h4`
   - Right: `PrimaryButton` "New meeting" · leading icon = record disc
2. `SearchBar` (see below)
3. Body — overflow y · column · gap `space.s`
   - Group headers `SectionEyebrow`(neutral): "Today" / "This week" / etc.
   - Each group followed by stack of `MeetingListRow`

### `SearchBar`

- Direction row · align center · gap `space.s` · padding `space.s` `space.m`
- Radius: `radius.md`
- Bg: `color.surface.raised`
- Border: 1px `color.divider.subtle`
- Children: leading search glyph · placeholder input · trailing filter pills (Date, Participant) · trailing count MetaLine

### `MeetingListRow` (used here and in Home Recent list · `variant="compact"` for the latter)

**Layout**
- Padding: `space.s` `space.m`
- Radius: `radius.md`
- Bg: `color.surface.raised`
- Border: 1px `color.divider.subtle`
- Direction: column · gap `space.xs`

**Content**
1. Title row (`space-between`, align baseline, gap `space.s`)
   - Title: `type.body.strong` (Geist 600 · **[Token Gap · size.body.strong ≈ 13]**) · `color.text.primary` · truncate
   - Meta: `type.mono.body` "10:00 · 42:18" · `color.text.dim`
2. One-line preview: `type.body.sm` · `color.text.secondary` · truncate
3. Participants row: horizontal stack of `SpeakerChip`s

**States**
- `default`, `hover` (bg `color.surface.hoverStrong`, border stays), `selected` (border `color.accent.subtle`, bg `color.accent.faint` — **[Token Gap · accentFaint]**), `processing` (subtitle replaced with skeleton bar and label "Summarizing…"), `errored` (small pill in title area, `color.danger`)

**Variants**
- `full` (this screen) — 3 rows of content
- `compact` (Home 31a) — no participants row; time+duration compressed to a single MetaLine on left

### Interactions

- Click row → nav to `PostMeetingSummary` (31e) for that meeting
- Right-click → context: Rename, Duplicate, Delete, Move to folder, Export…
- Cmd-click → multi-select; toolbar appears with bulk actions
- Search field: instant filter as you type; matches title, transcript, notes, participant names

### Edge cases

- No meetings yet → empty state screen (below)
- Only today's meetings → hide older group headers
- Extremely long titles → truncate; full title on hover tooltip
- Row currently being recorded (return from HUD) → shows `LiveIndicator` where the meta line would be

### Empty state — `MeetingsEmpty`

- Centered stack, padding `space.xxl` — **[Token Gap · space.xxl ≈ 48]**
- Illustration: three concentric rings ending in cream disc + record glyph (same visual family as 18c empty)
- Title `type.h5` "No meetings yet"
- Body `type.body.sm` · `color.text.secondary` · max-width `size.emptyState.textMax` — **[Token Gap]** "Start your first meeting from the dashboard or the menubar. Flume captures system audio and your mic silently — no bot joins the call."
- `PrimaryButton` "Start your first meeting"

### Responsive

- Sidebar collapses same as elsewhere
- SearchBar filter pills collapse to icon-only below `breakpoint.desktop.sm`

---

## `MeetingsSettingsPane` — `#31g`

**Purpose:** Meeting-specific settings subsection.
**Where it lives:** Inside Settings top-level screen. `SidebarNav` here is the **Settings sidebar** variant.

### Layout

- Container: `WindowChrome` + row body
- Body children:
  1. Settings sidebar — items: General · Hotkeys · Audio · **Meetings (active)** · Dictionary · Snippets · Privacy · Account
  2. `SettingsMain` — flex 1 · padding `space.l` `space.xl` · column · overflow y

### `SettingsMain` children (in order)

1. Header block
   - `SectionEyebrow`(neutral) "Meetings"
   - Title `type.h4` "Meeting capture"
2. Group: **Capture** — `SettingsGroup`
3. Group: **Storage & privacy** — `SettingsGroup`
4. Group: **Behavior** — `SettingsGroup`

### `SettingsGroup`

- Title above: `type.body.strong` · `color.text.primary` · margin-bottom `space.xs`
- Rows container: rounded card `radius.md` · bg `color.surface.raised` · border `color.divider.subtle` · overflow hidden
- Rows separated by 1px `color.divider.faint` — **[Token Gap · dividerFaint]**

### `SettingsRow`

- Padding: `space.s` `space.m`
- Direction: row · align center · gap `space.m`
- Left: label + sublabel stack
  - Label: `type.body` (Geist 500 · `color.text.primary`)
  - Sublabel: `type.caption` (Geist 400 · `color.text.dim`)
- Right: control — `Toggle` OR `Dropdown` OR `PermissionBadge`

### Row specifications

**Capture**
- System audio · trailing `PermissionBadge`(ready|denied|pending)
- Microphone · trailing `PermissionBadge`(ready|denied|pending)
- Max meeting length · trailing `Dropdown` options: 30 min · 1 h · 2 h · 3 h · 6 h · No limit

**Storage & privacy**
- Keep audio files · `Toggle`
- Auto-delete after · `Dropdown`: 7 / 30 / 90 days · Never
- Sync to other devices · `Toggle` (default off)
- Include content in analytics · `Toggle` disabled `on:true` — locked to off; note "Meeting text is never sent, ever." — **[Token Gap · locked-toggle token]**
- Footnote row: "Storage used · 1.8 GB across 18 meetings" + trailing link "Manage"

**Behavior**
- Show floating HUD when tabbed away · `Toggle`
- Speaker labeling · `Toggle`
- Auto-start from calendar events · `Toggle` disabled + trailing chip "coming soon" (`type.caption` · `color.text.dim`)

### States

- `default`
- `permission-denied` — badge switches, sublabel adds "Grant" link that opens `PermissionChecklistModal`
- `saving` — control temporarily disabled with spinner
- `blocked` — analytics toggle: cursor becomes disallowed; tooltip explains

### Interactions

- Toggle click → optimistic set, IPC round-trip; on failure, revert with error toast
- Dropdown → native menu; keyboard nav supported
- Manage link → deep-links to a per-meeting storage view
- All settings persist per user account, sync across devices only if `Sync` toggle is on

### Edge cases

- First launch (no permissions granted) → Capture badges = denied, all Storage rows disabled with tooltip "Grant permission first"
- Extremely small window → sidebar collapses; SettingsMain unchanged

### Responsive

- Below `breakpoint.desktop.sm`: labels/sub-labels wrap; dropdowns keep min-width

---

## `PermissionChecklistModal` — `#31h`

**Purpose:** First-time system-audio permission flow.
**Where it lives:** Modal, invoked when a user tries to record without permission, or from Settings > Meetings > Grant.

### Layout

- Backdrop: `color.scrim`
- Panel width: `size.modal.md` (500)
- Radius: `radius.xl`
- Bg: `color.surface.modal`
- Shadow: `shadow.modal`

### Children (top to bottom)

1. **Header block** · padding `space.l` `space.l` `space.s`
   - Row: `IconTile` (36pt · radius `radius.md` · bg `color.accent.subtle` · icon `color.accent.primary`, semantic = audio waveform) + text stack (title `type.h5` + sub `type.caption`)
   - Info paragraph — `type.body.sm` · line-height 1.55 · padding `space.s` `space.m` · radius `radius.md` · bg `color.surface.subtleAlt` — **[Token Gap · surfaceSubtleAlt ≈ rgba(255,255,255,0.03)]** · border 1px `color.divider.faint`
2. **Steps section** · padding `space.s` `space.l` `space.m`
   - `SectionEyebrow`(neutral) "Steps · N of 3 complete"
   - Stack of 3× `ChecklistStep` rows
3. **Footer** · padding `space.s` `space.l` · border-top `color.divider.subtle` · bg `color.surface.footer`
   - Left: `type.caption` "Denied by mistake? Recovery steps" (recovery is a link `color.accent.primary`)
   - Right: `SecondaryButton` "Skip for now" + `PrimaryButton` "Test capture" — Primary is disabled until all 3 steps complete

### `ChecklistStep`

- Direction: row · align start · gap `space.s` · padding `space.s` `space.m` · radius `radius.md`

**Variants**
- `done` — bg `color.success.subtle`, border 1px `color.success.border` — **[Token Gap · successTokens]**
  - Leading disc: 20pt, bg `color.success.strong`, check glyph `color.success.on` — **[Token Gap · successStrong / successOn]**
  - Label `type.body` · `color.text.primary` + sub `type.caption` "Installed 2 min ago" · `color.text.secondary`
- `active` — bg `color.accent.subtle`, border 1px `color.accent.borderStrong` — **[Token Gap · accentBorderStrong]**
  - Leading disc: 20pt, bg `color.accent.subtleStrong` — **[Token Gap · accentSubtleStrong]**, index numeral (mono) `color.accent.primary`
  - Label + sub + action row (`PrimaryButton` "Open Sound settings" + `SecondaryButton` "Show me how")
- `pending` — bg `color.surface.raised`, border `color.divider.subtle`
  - Leading disc: outline only
  - Label at `color.text.secondary`, sub at `color.text.faint`

### States (modal-level)

- `initial` — steps 1-2-3 all `pending`
- `in-progress` — steps advance one at a time; a completed step animates from `active` → `done` (`motion.checkmark`) — **[Token Gap · motion.checkmark]**
- `all-complete` — Primary "Test capture" enabled; footer copy adjusts
- `testing` — button becomes `loading`; a temporary strip appears showing audio input meter
- `test-failed` — inline error appears above footer, offering "Retry" + "Recovery steps"
- `denied` — if user actively denied in System Settings, step 2 flips to a `denied` variant (bg `color.danger.subtle`, retry action)

### Interactions

- "Open Sound settings" → deep-links to `x-apple.systempreferences:...` pane
- "Show me how" → inline expander (~200ms `motion.expand`) with numbered mini-tutorial
- "Test capture" → runs a 3-second test; UI stays open; on success shows success badge + auto-closes after 1200ms
- Escape / Skip → closes; meeting proceeds with system audio disabled and a persistent info banner appears in `MeetingLauncherCard`

### Edge cases

- Extension already installed (updating a previous install) → step 1 auto-completes on open
- User quits Sound Settings without applying → checklist re-checks on window focus regain
- Multiple denials → after 2 fails, "Recovery steps" surfaces automatically
- Non-macOS platforms (future) → different step set — this component is macOS-only for v1

### Responsive

- Panel remains fixed width. Content overflow: internal scroll if step "Show me how" expander overflows.

---

## Token Gaps

Consolidated list of every unresolved token or value in this document. Resolve
these with the design owner **before** implementing. Each is annotated with the
component(s) that need it.

1. **`titleBarHeight`** — 36pt used in `WindowChrome`. Existing token?
2. **`chromeBar` / `chromeSidebar` / `surfacePopover` / `surfaceModal` / `surfaceHud` / `surfaceFooter` / `surfaceSubtle` / `surfaceSubtleAlt` / `surfaceGradient`** — various background layers.
3. **`sidebarWidth`** — 196pt sidebar.
4. **`size.brand`** — 12.5pt brand wordmark.
5. **`size.chrome`** — 11.5pt title in chrome.
6. **`size.body`** — 12pt for `type.body`.
7. **`size.body.sm`** — 11pt.
8. **`size.body.lg`** — 12.5pt for summary paragraph.
9. **`size.body.strong`** — 13pt for card titles.
10. **`size.caption`** — 11pt.
11. **`size.captionXs`** — 10pt HUD subtitle.
12. **`size.eyebrow`** — 10pt.
13. **`size.chip`** — 9.5–10pt speaker chip.
14. **`size.mono`** — 10.5pt.
15. **`size.mono.h5`** — 16pt meeting timer.
16. **`size.h4` / `size.h5` / `size.h6`** — 22 / 15 / 13.5.
17. **`size.button`** — 12pt primary/secondary button label.
18. **`iconButtonSizes`** — 24 / 26 / 30 discrete sizes in use.
19. **`strokeThin`** — 1.6 for line icons in nav; 1.7 elsewhere; 1.8 for record buttons. Formalize.
20. **`accentOn`** / **`accentHover`** / **`accentPressed`** / **`accentFaint`** / **`accentSubtleStrong`** / **`accentBorderStrong`** — tints of the terracotta accent for various button/card states.
21. **`recordColor`** / **`recordSubtle`** / **`recordBorder`** / **`recordSoft`** — the red used for REC ≠ terracotta. New family?
22. **`speakerSlate`** / **`speakerOchre`** / **`speakerSelf`** — speaker chip palette not defined in `theme.py`.
23. **`warningTokens`** — full family for `pending` badge state.
24. **`dangerTokens`** — full family for `denied`/`error` states.
25. **`successTokens`** — subtle, strong, on, border for the checklist done state.
26. **`toggleThumb`** — thumb color; assumed `color.text.primary` but should be explicit.
27. **`dividerFaint`** — 1px row divider inside a settings card (weaker than `divider.subtle`).
28. **`focusRing`** — keyboard focus outline for all buttons/inputs.
29. **`opacity.disabled`** — used repeatedly; canonicalize.
30. **`scrim`** — modal backdrop opacity.
31. **`shadow.popover` / `shadow.modal` / `shadow.hud`** — three distinct elevation shadows.
32. **`blurHud`** — backdrop-filter blur radius for HUD.
33. **`modalWidths`** — sm / md sizes in use.
34. **`menubar width`** — 280 for tray popover.
35. **`hud.expanded.min`** — 380 minimum width.
36. **`hud.title.max`** — max width for HUD title before ellipsis.
37. **`meeting window size`** — `size.window.meetingLg` 820×540 / 820×580 (summary is taller).
38. **`emptyState.textMax`** — max text width in empty state.
39. **`space.xxs`** / **`space.xl`** / **`space.xxl`** — 2 / 32 / 48 not present in every spec.
40. **`letter.tightMinus2`** — tracking used on headings (~-0.02em).
41. **`letter.eyebrow`** — tracking used on eyebrows (~0.14em).
42. **`hapticTokens`** — the tokens for tap/success/error haptics (macOS has NSHaptic taps).
43. **`motion.pulse` / `motion.wave` / `motion.pop` / `motion.checkmark` / `motion.expand`** — animation curves and durations.
44. **`checkbox` tokens** — for Action items done state.
45. **`locked-toggle`** — the appearance of a Toggle that is disabled but explicitly `on:true` (analytics).
46. **`tooltip` tokens** — bg / text / shadow / radius / max-width.
47. **`audioActive`** — the highlight color for a transcript line whose audio is playing.
48. **`rich-text formatting palette`** — colors for bullets, checkboxes, code, quote used in the scratchpad.
49. **`virtualization row height`** — canonical row height for utterance virtualization.
50. **`timer format tokens`** — canonical formats for `M:SS`, `H:MM:SS`, `HH:MM:SS`.
51. **`breakpoints`** — `desktop.sm`, `desktop.md` values.
52. **Speaker chip palette assignment** — how does the app decide which color a given speaker gets? By first-heard order? By hash of name?
53. **`ActiveMeetingCard`** — variant of `MeetingLauncherCard` when a meeting is already recording. Not drawn.

---

## Component Inventory

Flat checklist for tracking build progress.

### Widgets (build first — reused everywhere)
- [ ] `WindowChrome`
- [ ] `SidebarNav`
- [ ] `NavItem`
- [ ] `PrimaryButton`
- [ ] `SecondaryButton`
- [ ] `IconButton` (roles: default · accent · destructive · record)
- [ ] `SpeakerChip` (variants: A · B · C · D · self · unknown · editing)
- [ ] `LiveIndicator` (states: recording · paused · starting)
- [ ] `WaveformStream` (variants: hud · keyboardBar)
- [ ] `Toggle` (states: off · on · pending · disabled · locked-on)
- [ ] `PermissionBadge` (variants: ready · pending · denied · offline)
- [ ] `SectionEyebrow` (variants: neutral · accent)
- [ ] `MetaLine`
- [ ] `SearchField` (compact + full)
- [ ] `Dropdown`
- [ ] `TextField` (title variant)
- [ ] `SettingsGroup`
- [ ] `SettingsRow`
- [ ] `ChecklistStep`
- [ ] `MeetingListRow` (variants: compact · full)
- [ ] `HybridNoteRow`
- [ ] `Utterance`
- [ ] `MarkPill`
- [ ] `IconTile`

### Screens
- [ ] `MeetingLauncherHome` — 31a
  - [ ] `MeetingLauncherCard`
  - [ ] `MenubarLauncherPopover` (mirror variant)
- [ ] `PreMeetingModal` — 31b
  - [ ] `AudioSourceRow`
- [ ] `InMeetingTwoPanel` — 31c
  - [ ] `MeetingHeader`
  - [ ] `TranscriptPane` + `Utterance` + "Jump to live" pill
  - [ ] `ScratchpadPane` + `DictateChip`
  - [ ] `MarksFooter`
- [ ] `FloatingMeetingHUD` — 31d
  - [ ] Collapsed pill · Expanded · Paused variants
- [ ] `PostMeetingSummary` — 31e
  - [ ] `MeetingSummaryHeader`
  - [ ] `SummaryCard`
  - [ ] `HybridNotesCard`
  - [ ] `DecisionsCard`
  - [ ] `ActionItemsCard`
  - [ ] `MarksTeaser` + expanded state
  - [ ] `TranscriptTeaser` + expanded state
- [ ] `MeetingsFolderList` — 31f
  - [ ] `SearchBar`
  - [ ] `MeetingsEmpty`
- [ ] `MeetingsSettingsPane` — 31g
- [ ] `PermissionChecklistModal` — 31h

### Cross-screen states to verify at review
- [ ] Recording in progress → HUD appears when tabbing away
- [ ] Recording in progress → InMeetingTwoPanel resumes cleanly on focus
- [ ] Post-meeting `processing` state on `MeetingListRow`
- [ ] Speaker rename propagates to all utterances, summary, action items
- [ ] Permission denied at any point surfaces the same `PermissionChecklistModal`
- [ ] Long-running meeting → HUD timer format switches to `H:MM:SS`
