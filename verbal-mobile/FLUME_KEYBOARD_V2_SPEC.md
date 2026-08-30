# Flume Keyboard v2 — FINAL Buildable Spec (iOS + Android)

Single source of truth for building the Flume keyboard v2 on both platforms. Grounded in `FLUME_KEYBOARD_V2_DESIGN.md`, the four research reports, the current code, and **both supervisor reviews (design fidelity + feature/feasibility) merged in**. Where this doc differs from the prior draft, the change tag (e.g. `[C1]`, `[D3]`, `[F]`) points to the review finding it applies.

**Code baseline:** Android working-tree v2 at `verbal-mobile/plugins/keyboard/FlumeInputMethodService.kt` (uncommitted, ~80% to target); iOS dictation spike at `verbal-mobile/targets/keyboard/KeyboardViewController.swift` (untracked, ~10%); bridge at `verbal-mobile/lib/keyboardBridge.ts`.

**Reality baseline:** The design says "Applies to BOTH," so the bulk of net-new work is iOS (a real keyboard, not a spike), plus Android overlay-fidelity polish, plus a cross-platform bridge upgrade. **iOS build is honestly a 6–10 week single-engineer effort** (see §3.4), not the naive sum of the S/M item estimates.

---

## 0. Correction summary (what changed from the draft)

**Design-fidelity fixes (Supervisor 1):**
- `[C1]` **BLOCKER FIXED** — Vocabulary "14 words" count is now JetBrains **Mono**, not Geist. Token split into `type.overlayRight` (Geist, non-meta labels) and `type.mono.count` (Mono).
- `[C2]` **Suggestions strip is flagged NET-NEW / NOT-IN-DESIGN.** It requires explicit design sign-off, its own tokens are now specified, and it is **excluded from `keyboard.totalH` until signed off**.
- `[C3]` **F-logo sizing flagged as ambiguous** (34px is the glyph per design, not the box) — box must grow if glyph is 34px. Marked PROVISIONAL pending mockup eyedropper.
- `[C4]` **All non-orange/green hexes marked PROVISIONAL.** Only `#E8522A` and `#34C759` are authoritative; token-drift policing applies only to those two until the rest are eyedropper-verified.
- `[C5]`/`[C6]`/`[C7]`/`[C8]`/`[C9]`/`[C10]` — mono subheader assignment, literal per-overlay header labels, non-inverting white F token, "mono-ish" comment removed, symbols page marked inferred, orphaned green avatar/"online" flagged to design.

**Feature/feasibility fixes (Supervisor 2):**
- `[A1/A2/A3]` **Auto-capitalization, double-space→". ", and basic `UITextChecker` autocorrect promoted to v1** (baseline typing behavior; none need Full Access).
- `[A4]` **Contextual Return-key label** (Go/Send/Search/Done/Next) added to v1.
- `[A6]` **Punctuation long-press popups** added (not just letter accents).
- `[C1/A7]` **Emoji picker promoted to v1.**
- `[C3]` **Canvas overlay demoted to v1.5** (bespoke differentiator, depends on data that may not be populated).
- `[B1]` **Second dictation unknown surfaced:** a keyboard extension may not be able to open the containing app at all — the handoff fallback is itself unvalidated.
- `[B3]` Glide typing re-framed as **XL-effort, not API-blocked** on iOS.
- `[B4]` **iOS GIF dropped entirely — Android-only.**
- `[B5]` **Memory budget standardized to ~40MB** everywhere (was 48/60 inconsistent).
- `[B7]` Key-click sound needs Full Access; haptics unreliable in extensions — stated accepted degradation.
- `[D3]` **`PrivacyInfo.xcprivacy` privacy manifest is a MANDATORY submission blocker** — added to Phase 0 and DoD.
- `[D1/D2/D4/D5]` iOS default-`deviceId` behavior, plaintext-PII hardening, `schemaVersion` writer/reader defaults, and "Full Access off" vs "not synced yet" states all nailed down.
- `[E1]` Automated gate honesty: `tsc` covers <10%; added `./gradlew` and account-gated Xcode build.

---

## 1. Design tokens

Faithful to the design file. Both platforms consume these from a **shared token source** (§4 T0.1).

> **`[C4]` Authoritativeness rule:** Only `accent.orange` `#E8522A` and `accent.green` `#34C759` are design-authoritative hexes. **Every other hex below is PROVISIONAL** — an inference to be eyedropper-verified against the mockups before "token drift = doc-sync failure" (T0.1) is enforced on it. Do not treat provisional values as canonical.

### 1.1 Color tokens

| Token | Light (prov. unless noted) | Dark (prov. unless noted) | Usage |
|---|---|---|---|
| `bg.keyboard` | `#F2F2F5` | `#0E0E0E` | Keyboard + overlay panel background |
| `bg.flumeBar` | `#F2F2F5` | `#0E0E0E` | Flume bar (same as panel; separated by top border) |
| `border.flumeBar` | `rgba(0,0,0,0.08)` | `rgba(255,255,255,0.10)` | Subtle top border above Flume bar |
| `key.letter.bg` | `#FFFFFF` | `#3A3A3C` | Letter/number keys |
| `key.letter.fg` | `#111113` (~500 wt) | `#FFFFFF` | Letter glyphs |
| `key.letter.shadow` | `rgba(0,0,0,0.12)` y1 r2 | none (flat) | Subtle key drop shadow (light only) |
| `key.modifier.bg` | `#CDD1D6` | `#2A2A2C` | shift `^`, `⌫`, `?123`, `,`, `.` (darker than letters in dark) |
| `key.modifier.fg` | `#111113` | `#EDEDED` | Modifier glyphs |
| `key.space.bg` | `#FFFFFF` | `#3A3A3C` | Space bar |
| `key.space.label` | `#8A8A8E` | `#9A9A9E` | "English (US)" centered gray `[C8]` (Geist, not mono) |
| `key.return.bg` | `#000000` | `#FFFFFF` | Return key (inverted vs theme) — AUTHORITATIVE inversion behavior |
| `key.return.fg` | `#FFFFFF` | `#000000` | Return glyph/label |
| `flumeBar.icon` | `#6E6E73` | `#B5B5BA` | Outline overlay icons |
| `flumeBar.iconActive.bg` | `#E2E2E6` | `#2C2C2E` | Rounded highlight behind active icon |
| `flumeF.bg` | `#E8522A` **(auth.)** | `#E8522A` **(auth.)** | F logo box fill (does NOT invert) |
| `flumeF.fg` | `#FFFFFF` **(non-inverting)** `[C7]` | `#FFFFFF` **(non-inverting)** `[C7]` | White "F" glyph — must NOT be theme-inverted like mic/return |
| `mic.bg` | `#000000` | `#FFFFFF` | Mic button circle (inverts) |
| `mic.fg` | `#FFFFFF` | `#000000` | Mic glyph (inverts) |
| `mic.dotBadge` | `#E8522A` **(auth.)** | `#E8522A` **(auth.)** | Orange dot badge top-right of mic |
| `accent.orange` | `#E8522A` **(AUTHORITATIVE)** | `#E8522A` **(AUTHORITATIVE)** | F fill, snippet triggers, "+ Add"/"+ New", mic dot |
| `accent.green` | `#34C759` **(AUTHORITATIVE)** | `#34C759` **(AUTHORITATIVE)** | `SENT` badge (see `[C10]` note below re: avatar/"online") |
| `overlay.card.bg` | `#FFFFFF` | `#1C1C1E` | Overlay row/card surface |
| `overlay.card.border` | `rgba(0,0,0,0.06)` | `rgba(255,255,255,0.08)` | Card hairline |
| `overlay.header.label` | `#8A8A8E` | `#9A9A9E` | UPPERCASE mono section label |
| `overlay.text.primary` | `#111113` | `#EDEDED` | Row primary text |
| `overlay.text.secondary` | `#6E6E73` | `#9A9A9E` | Expansion previews, truncated body |
| `pill.time.bg` | `#E2E2E6` | `#2C2C2E` | History time pill |
| `pill.time.fg` | `#6E6E73` | `#B5B5BA` | Time pill mono text |
| `chip.vocab.bg` | `#FFFFFF` | `#1C1C1E` | Vocabulary pill chip |
| `chip.vocab.border` | `rgba(0,0,0,0.10)` | `rgba(255,255,255,0.12)` | Chip outline |
| `dashed.addWord.border` | `#E8522A` (dashed) | `#E8522A` (dashed) | "+ Add a word…" dashed input |
| `suggest.chip.bg` `[C2]` | `#FFFFFF` (PROV, pending sign-off) | `#1C1C1E` (PROV) | **NET-NEW** suggestion candidate chip bg |
| `suggest.chip.fg` `[C2]` | `#111113` (PROV) | `#EDEDED` (PROV) | **NET-NEW** suggestion candidate text |
| `suggest.chip.divider` `[C2]` | `rgba(0,0,0,0.08)` (PROV) | `rgba(255,255,255,0.10)` (PROV) | **NET-NEW** vertical dividers between candidates |

**`[C10]` Design-origin ambiguity (flag to design, do not build blind):** the design assigns `accent.green` to "avatar, 'online', SENT badge," but only the `SENT` badge is actually placed in any described overlay. There is no avatar or "online" indicator in any overlay layout. Locate these elements in the mockup or drop the two usages; until resolved, only `SENT` badge uses green.

**Theme source:** driven by the **host field / system appearance** — Android `Configuration.uiMode`/`isNightModeActive`; iOS `textDocumentProxy.keyboardAppearance` via `UIInputViewController.traitCollection.userInterfaceStyle` — **not** the app's own setting. Fail to light if undetermined.

### 1.2 Typography tokens

| Token | Font | Size | Weight | Usage |
|---|---|---|---|---|
| `type.key` | Geist | 22pt (letter), 16pt (modifier text) | 500 | Key glyphs |
| `type.spaceLabel` | Geist | 13pt | 400 | "English (US)" `[C8]` (Geist — not mono) |
| `type.flumeF` `[C3]` | Geist | **PROVISIONAL — see sizing note** | 700 | F logo glyph |
| `type.overlayHeader` | JetBrains Mono | 12pt, +0.06em tracking | 600 | UPPERCASE section labels **and** the Canvas `RECENTLY SENT` subheader `[C5]` |
| `type.overlayRight` `[C1]` | Geist | 12pt | 400 | Right header **non-meta** labels only: "Tap to insert", "Tap to expand", "→ MacBook Pro" |
| `type.mono.count` `[C1]` | JetBrains Mono | 12pt | 500 | **Vocabulary "14 words" count** (was wrongly Geist — this is the C1 blocker fix) |
| `type.rowPrimary` | Geist | 15pt | 500 | Row main text |
| `type.rowSecondary` | Geist | 13pt | 400 | Expansion preview, truncated |
| `type.mono.trigger` | JetBrains Mono | 13pt | 500 | Snippet triggers (orange), phonetics |
| `type.mono.time` | JetBrains Mono | 11pt | 500 | Time pills |
| `type.mono.badge` | JetBrains Mono | 10pt | 600 | `SENT` badge |
| `type.chip` | Geist | 13pt | 500 | Vocab chip word |
| `type.chip.phonetic` | JetBrains Mono | 11pt | 400 | Phonetic beside chip word |
| `type.suggestChip` `[C2]` | Geist | 15pt | 400 | **NET-NEW** suggestion candidate (pending sign-off) |
| `type.returnLabel` `[A4]` | Geist | 15pt | 500 | Contextual Return verb (Go/Send/Search/Done/Next); falls back to `↵` glyph |

**`[C3]` F-logo sizing note (PROVISIONAL — verify against mockup):** Design line 34 attaches "~34px" to the **white bold "F" glyph**, not to a box dimension. The draft mis-read this by making 34px the box and shrinking the glyph to ~20pt. Two resolutions, decide from the mockup:
- If 34px is the **glyph** cap-height: box must grow to ~44–48px and `type.flumeF` ≈ 34px.
- If 34px is the **box** (current `size.flumeF`): glyph ≈ 20pt as drafted.
Do not ship until this is confirmed by eyedropper; a wrong read here is a visibly-off logo.

**Font loading:** **Android** bundle Geist + JetBrains Mono as `res/font` assets (an IME cannot rely on app-side loaded fonts). **iOS** bundle both `.ttf` in the **extension** target and register via `UIFont`/Info.plist `UIAppFonts` (the extension has its own bundle; app-registered fonts do not cross into it).

### 1.3 Spacing / radii / sizing tokens

| Token | Value | Notes |
|---|---|---|
| `space.keyGap` | 6px | Gap between keys |
| `space.rowGap` | 10px | Gap between key rows |
| `space.keyboardPadH` | 4px | Side padding of key grid |
| `radius.key` | 8px | Keys |
| `radius.flumeF` | 8px | F logo box |
| `radius.iconHighlight` | 10px | Active Flume-bar icon bg |
| `radius.card` | 12px | Overlay cards |
| `radius.chip` | 16px | Vocab chips (pill) |
| `radius.timePill` | 8px | History time pill |
| `size.keyH` | 42px | Standard key height |
| `size.rowH` | 52px | Row height incl. gap |
| `size.flumeBarH` | 48px | Flume bar height |
| `size.suggestBarH` `[C2]` | 40px | **NET-NEW suggestions strip — NOT counted in `keyboard.totalH` until design sign-off** |
| `size.flumeF` | 34px (PROV — see C3 sizing note) | F logo box |
| `size.micBtn` | 34px | Mic circle diameter |
| `size.micDot` | 8px | Orange dot badge |
| `size.overlayHeaderH` | 40px | Overlay header row |
| `size.canvasTarget` | 88×72px | Text/Link/Image target box |
| `keyboard.totalH` | **~250px** letters (bar 48 + keys ~200) `[C2]` | **Suggestions strip excluded** until signed off; add 40px only if approved. iOS via height constraint; Android via measured input-view height. **Portrait iPhone / phone only for v1 — landscape & iPad are out of scope, see §3.5.** |

---

## 2. Component / screen inventory

Every component must exist on **both** platforms with identical layout/behavior. "Android status" = present in working-tree v2 unless noted.

### 2.1 Persistent chrome

| Component | Contents | Android | iOS |
|---|---|---|---|
| **Suggestions strip** `[C2]` **(NET-NEW — NOT IN DESIGN; needs sign-off)** | Up to 3 candidate chips; tap → replace partial word via `documentContextBeforeInput` lookup + delete+insert. Vocab-prefix only for v1 — **do not claim "next-word prediction" unless a model actually ships** `[F]`. | Present (vocab-prefix only) | Build (if approved) |
| **Flume bar** | F logo · ⚡ Snippets · ▦ Canvas · 🕐 History · 📖 Vocabulary · (spacer) · ● mic; active icon highlighted; keyboard-glyph toggle returns to typing | Present (needs explicit kbd-glyph toggle A9, mic dot badge A11) | Build |

### 2.2 Keyboard layers

| Layer | Rows | Android | iOS |
|---|---|---|---|
| **Letters** | `qwertyuiop` / `asdfghjkl` / `⇧ zxcvbnm ⌫` / `?123 , [space:English (US)] . ↵` | Present | Build |
| **Numbers (?123)** | `1234567890` / `@#$_&-+()/` / `=\< *"':;!? ⌫` / `ABC , [space] . ↵` | Present | Build |
| **Symbols (=\<)** `[C9]` | Gboard-style secondary page. **Exact glyphs NOT design-specified** — the set (`~ \` | € £ ¥ • § ¶ …`) and the `?123`-back-to-numbers key are inferred placeholders, not canonical. `ABC` → letters is the only design-stated behavior. | Present (verify page contents A10) | Build |

State machines (both platforms): shift (off → one-shot → caps-lock via double-tap), layer toggle, long-press **accent AND punctuation** popups `[A6]` (long-press `.` → `… ! ? ; :`), constrained **within** the keyboard view on iOS (no above-top-edge popup `[C3-style limitation]`).

**Baseline typing behaviors — v1 `[A1/A2/A4]`:**
- **Auto-capitalization** — first letter of a field, after `.?!`, and after newline; via `documentContextBeforeInput` parsing on both platforms. Degrade silently if context is `nil` (some hosts).
- **Double-space → ". "** (period + space).
- **Contextual Return label** — render Go/Send/Search/Done/Next from iOS `returnKeyType` / Android `EditorInfo.imeOptions`; fall back to `↵`.
- **Basic autocorrect `[A3]`** — iOS `UITextChecker` (built-in, no Full Access) + a small frequency dictionary; Android an equivalent lightweight dictionary. Not a neural model (that is v2+).

### 2.3 Overlays (replace key area; Flume bar stays)

Each: header = literal UPPERCASE mono label (left, `type.overlayHeader`) + right label/action, then content. Cards on panel bg. **Literal left labels are fixed by design `[C6]` — do not invent.**

| Overlay | Left label `[C6]` | Header right | Content | Footer | Android gaps | iOS |
|---|---|---|---|---|---|---|
| **History** 🕐 | `HISTORY` | "Tap to insert" (`type.overlayRight`) + return glyph | Rows: time pill (`9:24`/`Yd`, mono) + truncated text + `→` | "See all history" (centered) | Add time pills + footer (A6); bridge sends timestamps (X2) | Build |
| **Snippets** ⚡ | `SNIPPETS` | "Tap to expand" (`type.overlayRight`) | Rows: orange mono trigger (left) + gray expansion preview (right) | "+ New snippet" (orange +) | Add footer (A7) | Build |
| **Vocabulary** 📖 | `VOCABULARY` | **"14 words" (`type.mono.count`, MONO)** `[C1]` | Dashed "+ Add a word Flume keeps mishearing…" (orange +); flow-wrap pill chips; optional mono phonetic beside word | — | Flow-wrap chips (A3); show phonetic (A4); real count (A8) | Build |
| **Canvas** ▦ **(v1.5 — demoted `[C3]`)** | `CANVAS` | "→ MacBook Pro" (paired device, `type.overlayRight`) | 3 targets row: Text / Link / Image (outlined, icon over label); subheader `RECENTLY SENT` (`type.overlayHeader`, MONO `[C5]`); rows: icon+text + green `SENT` badge | — | Build 3 targets + recently-sent list (A5); needs canvas data (X2) | Build (v1.5) |

### 2.4 Behavior-bearing sub-components

- **Mic pill / dictation controller** — records, POSTs to `groq-proxy`, applies replacements + snippet expansion, inserts. Android present. **iOS dictation is a Phase-2 spike GATE — see §4.5; do not commit the iOS dictation architecture until validated on-device.**
- **Secure-field guard** — disables mic + fails closed in password/secure fields. Android present; iOS: system swaps the keyboard out for secure fields automatically, plus disable mic if `hasFullAccess == false`.
- **Config reader** — reads shared config snapshot (vocab/replacements/snippets/history/canvas/deviceId). Android reads `filesDir/flume_kbd_config.json`; iOS must read the **App Group** container (net-new, I4 — §4.2).
- **Key-click sound / haptics `[A5/B7]`** — deliberate decision, not omission. iOS `UIDevice.playInputClick()` fires **only** with Full Access (`RequestsOpenAccess`); `UIImpactFeedbackGenerator` haptics are unreliable/suppressed in extensions. **Accepted degradation:** a no-Full-Access iOS user gets a silent, non-haptic keyboard — this is tied to the fail-closed matrix and stated to users.

---

## 3. Feature matrix (tiers v1 / v1.5 / v2 / v3)

Effort: S ≤ 2d, M ≤ 1wk, L ≤ 2wk, XL > 2wk (per platform, one engineer). "iOS" reflects extension-sandbox constraints. **Per-item sums are unreliable for iOS — see §3.4 re-baseline.**

### Tier v1 — MUST-HAVE (a keyboard people will actually leave enabled)

| # | Feature | iOS feasibility | iOS effort | Android feasibility | Android effort |
|---|---|---|---|---|---|
| 1 | QWERTY letters + shift/caps state | ✅ | M | ✅ done | — |
| 2 | Numbers `?123` + symbols `=\<` layers | ✅ | M | ✅ done | S (verify A10) |
| 3 | Backspace / delete (+ repeat) | ✅ (`deleteBackward`) | S | ✅ done | — |
| 4 | Return honoring editor action **+ contextual label** `[A4]` | ✅ | S | ✅ (label add) | S |
| 5 | Globe / next-keyboard key | ✅ (mandatory) | S | ✅ done | — |
| 6 | Long-press accents **+ punctuation popups** (in-view) `[A6]` | ⚠️ no above-top-edge popup | M | ✅ | S |
| 7 | Light/dark theme following host | ✅ | S | ✅ done | S |
| 8 | **Auto-capitalization** `[A1]` | ✅ (`documentContextBeforeInput`) | S | ✅ | S |
| 9 | **Double-space → ". "** `[A2]` | ✅ | S | ✅ | S |
| 10 | **Basic autocorrect** (`UITextChecker` / dictionary) `[A3]` | ✅ (no Full Access) | M | ✅ | M |
| 11 | Flume bar (logo/icons/mic + active highlight + kbd toggle) | ✅ | M | ✅ (A9, A11) | S |
| 12 | Suggestions strip `[C2]` **(net-new, sign-off gated)** — vocab-prefix only | ✅ | S | ✅ done | S |
| 13 | **Emoji picker** (grid + categories + recents) `[C1/A7]` | ✅ hand-built collection view, ~40MB-disciplined | M | ✅ `emoji2-emojipicker` | S |
| 14 | Dictation via `groq-proxy` + replacements + snippet expansion | ⚠️ **SPIKE GATE — two unknowns (§4.5)** | M–L | ✅ done | — |
| 15 | History overlay (time pills + footer) | ✅ | M | ✅ (A6) | S |
| 16 | Snippets overlay (orange triggers + "+ New") | ✅ | S | ✅ (A7) | S |
| 17 | Vocabulary overlay (wrap chips + phonetics + **mono count**) | ✅ | M | ✅ (A3/A4/A8) | M |
| 18 | Secure-field fail-closed | ✅ | S | ✅ done | — |
| 19 | Shared config bridge read | ⚠️ needs App Group + Full Access | M | ✅ done | — |
| 20 | Key-click sound/haptics decision `[A5/B7]` | ⚠️ sound=Full-Access-only; haptics unreliable | S | ✅ | S |
| 21 | **`PrivacyInfo.xcprivacy` privacy manifest** `[D3]` | ✅ (mandatory to submit) | S | n/a | — |

### Tier v1.5 — Verbal differentiators (once core is solid) `[F]`

| # | Feature | iOS | iOS effort | Android | Android effort |
|---|---|---|---|---|---|
| 22 | **Canvas overlay** (3 targets + RECENTLY SENT + paired device) `[C3]` | ✅ | M | ✅ (A5) | M |
| 23 | Canvas write-back (send Text/Link/Image to canvas table) | ⚠️ needs Full Access network | M | ✅ | M |
| 24 | Spacebar-drag cursor control | ✅ `adjustTextPositionByCharacterOffset` | S | ✅ | S |
| 25 | Number-row toggle | ✅ | S | ✅ | S |
| 26 | Backspace-swipe word delete | ⚠️ no visual selection; delete-only | M | ✅ | S |
| 27 | Undo chip after bulk delete (app-managed) | ⚠️ own inserts/deletes only | S | ✅ | S |
| 28 | Voice punctuation / "delete/clear" commands in dictation | ✅ (post-process) | M | ✅ | M |

### Tier v2 — competitive polish

| # | Feature | iOS | Android | Notes |
|---|---|---|---|---|
| 29 | Emoji search + skin-tone + full category set | ✅ | ✅ (library) | v1 ships grid+categories+recents; this is the polish delta |
| 30 | Key-press magnifier popups (within view) | ⚠️ not above top edge | ✅ | |
| 31 | Neural/frequency autocorrect upgrade | ⚠️ own model in ~40MB | ⚠️ | Beyond the v1 `UITextChecker` baseline |

### Tier v3 — ADVANCED (defer)

| # | Feature | iOS | Android | Notes |
|---|---|---|---|---|
| 32 | **GIF search + insert (Tenor)** | ❌ **NOT PLANNED — Android-only** `[B4]` | ✅ Commit Content API + FileProvider + Tenor GCP key | iOS path (pasteboard copy + tap-to-paste, host-dependent, ~40MB wall) is too degraded to ship — dropped, not carried as parity. See §4.4 |
| 33 | **Glide / swipe typing** `[B3]` | ⚠️ **feasible but XL** — keyboard owns its touch events (Gboard ships it on iOS); blocker is decoder effort in the ~40MB budget, **NOT a missing API** | ⚠️ no production-grade OSS decoder; neural model/fork | **Deferred** (XL both sides) |
| 34 | ML autocorrect / prediction engine | ⚠️ own model | ⚠️ | **Deferred** (v1 ships basic UITextChecker instead) |
| 35 | Multilingual / >1 language | ⚠️ ~125 variants | ✅ 900+ subtypes | **Deferred — English (US) only for v1/v1.5/v2** |
| 36 | Clipboard history manager | ❌ no background pasteboard | ✅ | **iOS hard-blocked** — Android-only if ever, never promised as parity |
| 37 | One-handed / floating / width-resize | ❌ frame fixed full-width | ✅ | **iOS hard-blocked** — Android-only |
| 38 | Live Translate | ❌ | ✅ | **iOS hard-blocked** — Android-only |
| 39 | Stickers / Emoji Kitchen | ⚠️/❌ | ✅ (Kitchen Android-only) | Deferred |
| 40 | Handwriting input | ✅ (own canvas) | ✅ | Deferred |

### 3.4 iOS effort re-baseline `[C4-review]`

**Do not trust the per-item S/M sum for iOS.** Replacing the 219-line spike with a real keyboard — full QWERTY + 3 layers + shift/caps timing + accent/punctuation popup gesture handling + auto-cap/autocorrect + 4 overlays + dictation + theme + App Group + privacy manifest — is realistically **6–10 weeks for one engineer**. Hand-built iOS keyboards are notoriously fiddly on key-repeat timing, shift-after-punctuation, popup gestures, and cursor sync. Plan and communicate the iOS timeline honestly against this range, not the optimistic item sum.

### 3.5 Form-factor scope

**v1 is portrait iPhone / portrait phone only.** `keyboard.totalH` is a single constant; landscape and iPad need different heights and layouts and are explicitly **out of scope** for v1. State this to stakeholders; revisit in v2+.

---

## 4. Phased build plan

Work split **Shared / iOS (Swift) / Android (Kotlin)**. Each phase ends with the automated gates in §6 (bridge `tsc`, Android `./gradlew`, account-gated Xcode build) plus on-device smoke test. Peripheral features **fail closed** and never break record→transcribe→inject.

### Phase 0 — Shared foundation (tokens + bridge contract + privacy manifest)

**Shared:**
- **T0.1** Create `verbal-mobile/lib/keyboardTokens.ts` — the token table from §1. Emit two artifacts: Android `res/values/flume_tokens.xml` + `values-night/…` (via build script or hand-synced with a pointer comment); iOS `FlumeTokens.swift` (static `UIColor`/`CGFloat`, `.light`/`.dark`). Keep the **two authoritative hexes** (`#E8522A`, `#34C759`) byte-identical; **provisional hexes are placeholders** until eyedropper verification — token-drift policing applies to the two authoritative values now, the rest after verification `[C4]`.
- **T0.2** Bundle Geist + JetBrains Mono `.ttf` into **both** targets: Android `res/font/`, iOS keyboard-extension bundle with `UIAppFonts`.
- **T0.3** Upgrade `keyboardBridge.ts` data contract (§4.1) + add the iOS App Group write (§4.2). Single most important shared change — unblocks all iOS overlays and Android fidelity gaps.
- **T0.4 `[D3]`** Add **`PrivacyInfo.xcprivacy`** to BOTH the app and the keyboard extension — declare `NSPrivacyAccessedAPICategory` reasons + network/tracking disclosures. **Missing manifest blocks App Store submission** (mandatory since 2024). This is a Phase-0 deliverable and a DoD gate, not optional.
- **T0.5 `[D2]`** PII-at-rest hardening for the config file (both platforms): set no-backup (`NSURLIsExcludedFromBackupKey` on iOS), truncate/limit persisted `history[].text` and `canvas[].text` bodies (store fewer items; consider not persisting full bodies). Fail-closed protects availability, not confidentiality.

### Phase 1 — iOS core keyboard (largest net-new)

**iOS (Swift):** Replace the 219-line spike with a real keyboard.
- **T1.1** `UIInputViewController` subclass: root stack = [suggestions strip if signed off] → Flume bar → content container; height constraint = `keyboard.totalH` (250px letters; +40px only if the strip is approved `[C2]`).
- **T1.2** Key model + renderer: data-driven rows (letters/numbers/symbols), custom `UIView`/`UIButton` per key, `insertText`/`deleteBackward`, contextual editor-action Return **with label** `[A4]`, globe (`advanceToNextInputMode`, `needsInputModeSwitchKey`).
- **T1.3** Shift/caps state machine + uppercase rendering; layer toggles (`?123`/`ABC`/`=\<`); **auto-capitalization + double-space-period** `[A1/A2]` via `documentContextBeforeInput`.
- **T1.4** Long-press **accent + punctuation** popups **inside** the primary view (no above-top-edge draw) `[A6]`.
- **T1.5** Theme from `traitCollection.userInterfaceStyle` / `textDocumentProxy.keyboardAppearance`; apply `FlumeTokens`.
- **T1.6** Secure-field / no-Full-Access guards; `hasFullAccess` gate on mic + network + click-sound. **Fail closed.** Distinguish "Full Access off" from "not synced yet" `[D5]`.
- **T1.7 `[A3]`** Basic autocorrect via `UITextChecker` + frequency dictionary (no Full Access).

### Phase 2 — iOS Flume bar + dictation spike gate + overlays + emoji

**iOS (Swift):**
- **T2.1** Flume bar (F logo — non-inverting white glyph `[C7]`; 4 outline icons; mic pill w/ orange dot; active highlight; keyboard-glyph return-to-typing toggle).
- **T2.2** App Group config reader (`FlumeConfig` decoding §4.1 JSON from the shared container); fail closed with the two distinct states `[D5]`. Define default-`deviceId` behavior when App Group unavailable `[D1]`.
- **T2.3 — DICTATION SPIKE GATE `[B1/B2/§4.5]`.** Before committing any iOS dictation architecture, validate ON-DEVICE, in order:
  1. **Path A (likely OK):** in-extension `AVAudioRecorder` with Full Access → `groq-proxy`. Gboard ships in-extension voice, so this probably works; the real risks are `AVAudioSession` interruption/activation and encode-time memory, not a flat "no mic." Validate A **first**.
  2. **Path B (fallback — ALSO unvalidated):** main-app handoff. **A keyboard extension may not be able to open the containing app at all** — `extensionContext.open(_:)` is restricted for keyboard extensions and the responder-chain `openURL` workaround is fragile/rejection-prone. **Two load-bearing unknowns, not one.** Confirm "can the extension open the host app" before relying on B.
  - Only after the gate: apply replacements + snippet expansion (parity with Android, fixes I5).
- **T2.4** Emoji picker `[C1/A7]` — hand-built `UICollectionView`, categories + recents (App Group; falls back to in-memory without Full Access) + skin-tone long-press; insert via `insertText` (no Full Access needed — Unicode). Memory-disciplined: cell reuse + lazy glyph rendering, tested against jetsam `[B5/B6]`.
- **T2.5** Overlays **History / Snippets / Vocabulary** rendered from `FlumeConfig`, inserting via `textDocumentProxy`. (**Canvas deferred to v1.5 `[C3]`.**)

### Phase 3 — Android overlay-fidelity + parity polish

**Android (Kotlin):** close audit gaps in `FlumeInputMethodService.kt`.
- **T3.1** History: mono time pill + `→` + "See all history" footer (A6) — consume `history[].ts`.
- **T3.2** Snippets: "+ New snippet" orange footer (A7).
- **T3.3** Vocabulary: flow-wrap chips (A3), phonetic mono beside word (A4), real **mono** "N words" count (A8, `[C1]`).
- **T3.4** Flume bar: explicit keyboard-glyph toggle (A9), mic orange dot badge (A11).
- **T3.5** Verify `=\<` secondary page matches design (A10) — remember its glyphs are inferred, not canonical `[C9]`.
- **T3.6** Baseline typing parity: contextual Return label `[A4]`, auto-cap `[A1]`, double-space-period `[A2]`, punctuation long-press `[A6]`, basic autocorrect `[A3]`.
- **T3.7** Emoji: `androidx.emoji2:emoji2-emojipicker` `EmojiPickerView` into the content area; `setOnEmojiPickedListener { commitText(it.emoji, 1) }`; `emoji2` EmojiCompat so chips/labels don't tofu.

### Phase 4 — v1.5 Canvas (both platforms)

- **Android:** 3 targets (Text/Link/Image) + `RECENTLY SENT` list + green `SENT` badge; header "→ {pairedDevice}" (A5). Consume `canvas` + `pairedDevice`. Write-back via existing network path.
- **iOS:** Canvas overlay + write-back (Full-Access-gated network).
- **Shared:** confirm `pairedDevice`/`canvas[]` are actually populated before shipping — Canvas is meaningless without data.

### Phase 5 — v2 polish and v3 (only if prioritized)

- Emoji search/skin-tone/full categories (v2); magnifier popups; autocorrect upgrade.
- **GIF: Android-only** `[B4]` — Commit Content API + `FileProvider` + MIME gating (`EditorInfoCompat.getContentMimeTypes`) + Tenor via Google Cloud key. **No iOS GIF.**
- **Deferred entirely:** glide (XL both, not API-blocked `[B3]`), ML autocorrect, multilingual, iOS-hard-blocked features (clipboard history, floating/one-handed/resize, Live Translate) — Android-only if ever.

### 4.1 keyboardBridge data contract (upgraded — shared)

```jsonc
{
  "schemaVersion": 2,                      // [D4] writer now ALWAYS emits 2; reader defaults missing -> 1
  "deviceId": "…",
  "pairedDevice": "MacBook Pro",           // NEW — Canvas/History header label
  "vocabulary": [                          // phonetic optional (A4)
    { "word": "Idiaz", "phonetic": "i-DEE-uhz" },
    { "word": "Flume" }
  ],
  "replacements": [ { "from": "…", "to": "…" } ],
  "snippets": [ { "trigger": "my sig", "expansion": "…" } ],
  "history": [                             // NEW: object w/ ts (was text-only). Truncate bodies [D2]
    { "text": "…", "ts": 1720000000000 }
  ],
  "canvas": [                              // NEW (v1.5): recently-sent items. Truncate bodies [D2]
    { "kind": "link|text|image", "text": "…", "sentAt": 1720000000000 }
  ]
}
```

- **`[D4]`** The current writer emits NO version field. Reader rule: **missing `schemaVersion` → treat as 1**; writer now always emits `2`. This prevents the Android v2 reader from choking on an old snapshot written before the app updates.
- Readers tolerate v1 (history strings → `{text}` no ts; empty canvas).
- Keep `vocabulary` back-compatible: accept `string[]` and `{word,phonetic}[]`.
- Triggers unchanged (`storage.ts:95`, `dictionary.ts:90`), plus a canvas-change trigger.

### 4.2 iOS App Group write (shared — critical, closes I4/X2)

- Android writes to `FileSystem.documentDirectory` (= Android filesDir). **iOS `documentDirectory` is NOT the App Group container** — the extension can't read it.
- On iOS, also write `flume_kbd_config.json` into the **App Group** shared container (`group.io.idiaz.verbal.keyboard`, `expo-target.config.js:25-28`). RN can't write App Group paths via `expo-file-system`; use a tiny native module exposing the container URL, then write there.
- Extension reads via `FileManager.containerURL(forSecurityApplicationGroupIdentifier:)`. **Requires Full Access at runtime** — fail closed to an "Enable Full Access" prompt otherwise, **distinct from a "not synced yet" state** `[D5]`.
- Harden the file at rest: no-backup flag + truncated bodies `[D2]`.

### 4.3 Emoji — per platform

- **Android:** `emoji2-emojipicker` — solved problem, light effort, skin tones + recents + search built in.
- **iOS:** hand-built grid, Unicode insert, **no Full Access required**; recents/skin-tone default in App Group (falls back to in-memory). **Memory-disciplined** against the ~40MB budget `[B5/B6]`: cell reuse + lazy glyph rendering, jetsam-tested on-device.

### 4.4 GIF — Android-only `[B4]`

- **Android:** Commit Content API + `FileProvider` + MIME gating + Tenor (Google Cloud key; network perm → extra store-review scrutiny). Gray out when the field rejects `image/gif`; fallback = copy to clipboard.
- **iOS: NOT PLANNED.** No direct insert API; only `UIPasteboard` copy + user-paste, Full-Access-gated, host-dependent, against the ~40MB jetsam wall. Too degraded to ship — **dropped**, not carried as cross-platform parity.

### 4.5 Dictation architecture (iOS — TWO load-bearing unknowns) `[B1/B2]`

Resolve on real hardware in Phase 2 (T2.3) before committing the architecture:
- **Unknown 1 — in-extension mic (likely OK):** Gboard ships in-extension voice with Full Access, so Path A probably works on modern iOS. Real risks: `AVAudioSession` interruption/activation in an extension, and memory during encode. The archival Apple "no mic in extensions" guide is over-pessimistic; validate A first.
- **Unknown 2 — host-app open for the fallback (also uncertain):** the main-app handoff depends on the extension opening the containing app, which Apple **restricts** for keyboard extensions. If Path A fails AND the extension can't open the host app, there is no dictation on iOS. Add "can a keyboard extension open the containing app at all" to the §5 validate list.
- Android is unaffected (in-IME `RECORD_AUDIO` already works).

### 4.6 Security / identity `[D1]`

- The Supabase anon key + URL are hardcoded in `KeyboardViewController.swift` (lines 29–30). The anon key is public by design, but shipping it in the extension binary means anyone can extract it and hit `groq-proxy`; the only abuse control is the per-`deviceId` rate limit. On iOS the `deviceId` comes from the App Group, which is **unavailable without Full Access** — a default/shared identity would collapse rate-limiting. **Action:** define the iOS no-App-Group `deviceId` behavior explicitly and confirm `groq-proxy` rate-limits sanely on a shared/default identity.

---

## 5. Gated on Apple Developer account / on-device testing

### Requires Apple Developer account (paid) + provisioning — BLOCKED until available
- **App Group entitlement** (`group.…`) shared app↔extension — registered in the Developer portal, enabled on both App IDs. **Without it: no iOS config bridge (I4), no dictation handoff.**
- **Full Access** (`RequestsOpenAccess=true`, already in `Info.plist:17`) — needed for network (`groq-proxy`), App Group at runtime, key-click sound, and (if permitted) mic. Users toggle it in Settings; keyboard fails closed when off.
- **Keyboard-extension App ID + provisioning profiles**, **TestFlight** distribution, and **App Store review** (third-party keyboard + network + mic = maximum-scrutiny category).
- **`PrivacyInfo.xcprivacy` acceptance `[D3]`** — mandatory to submit; the review outcome cannot be pre-tested, treat as a gating risk.
- **Xcode build of the extension `[E1]`** — the only real compile gate for the Swift code requires the account + provisioning; essentially all iOS correctness validation is device-bound.

### Must be validated on-device (Simulator insufficient / misleading)
- **In-extension mic (Path A) `[B2]`** — the primary dictation unknown; test with Full Access on hardware.
- **Can a keyboard extension open the containing app at all `[B1]`** — the handoff fallback's core assumption.
- **~40MB jetsam wall `[B5]`** — emoji grid and any thumbnails; the extension silently disappears when OOM-killed. Simulator doesn't reproduce it. Design to ~40MB everywhere.
- **Key-click sound + haptics with Full Access `[A5/B7]`** — device only.
- **Auto-cap / suggestion-replace across real hosts `[E2]`** — `documentContextBeforeInput` returns nil/partial in some hosts (Safari address bar, Messages, secure-ish fields), silently breaking both features.
- **Host-app paste acceptance** (only relevant to Android GIF now, but validate host behavior generally).
- **Secure-field swap** and per-app keyboard vetoes (banking/HIPAA).
- **Full Access toggle semantics + App Group cold-start** — Simulator won't reproduce these realistically.
- **Above-top-edge popup limitation** — confirm accent/punctuation/magnifier popups render acceptably inside the bounded view.

### Android device/config to validate (not account-blocked)
- **API 35 edge-to-edge / gesture-nav insets** via `onComputeInsets` (2025 gotcha).
- `RECORD_AUDIO` runtime prompt routed through the settings Activity (a Service can't prompt directly).
- Commit Content MIME gating across target apps (if/when GIF is built).

---

## 6. Definition of done (per CLAUDE.md) — with honest verification `[E1]`

**Automated gates (note: these cover a minority of the native work):**
- Bridge TS: `cd verbal-mobile && npx tsc --noEmit` clean. *(Covers <10% of this work — bridge only.)*
- Android: `./gradlew` compile of the IME as a real CI gate — `FlumeInputMethodService.kt` compiles.
- iOS: **Xcode build of the extension — gated on the paid Apple account + provisioning.** Until then there is no automated iOS compile gate; iOS correctness is manual + device-bound. State this plainly.

**Product DoD:**
- Android: overlays match design; bridge v2 consumed; baseline typing (auto-cap, double-space, contextual Return, punctuation popups, basic autocorrect) present.
- iOS: extension compiles; QWERTY + 3 layers + shift/caps + auto-cap/double-space/autocorrect + Flume bar + History/Snippets/Vocabulary overlays + emoji + dictation (per spike-gate outcome) + App Group bridge; theme-aware; fails closed without Full Access with the two distinct states.
- **`PrivacyInfo.xcprivacy` present on app + extension `[D3]`** — DoD gate; blocks submission otherwise.
- Shared: `keyboardTokens.ts` is the token source of truth (two authoritative hexes locked, rest provisional); PII-at-rest hardened; `schemaVersion` writer=2 / reader defaults missing→1.
- Commit the Android v2 (currently `M`) and the iOS target (currently untracked).
- **Update `context/`:** `03-features.md` (keyboard v2 overlays/emoji/baseline-typing), `01-product.md` feature matrix, `04-data-model.md` §Schema gaps (canvas read, `history.ts`, App Group, PII-at-rest), `05-conventions.md` (bundled-font rule, fail-closed-on-Full-Access with two states, ~40MB jetsam gotcha, `PrivacyInfo.xcprivacy` requirement, token-drift = doc-sync failure for the two authoritative hexes).

## 7. Realistic v1 scope (the recommendation) `[F]`

**v1 — "a keyboard people will actually leave enabled":**
- QWERTY + numbers/symbols layers, shift/caps, backspace+repeat, **Return-with-label**, globe. (both)
- **Auto-capitalization + double-space-period + basic `UITextChecker` autocorrect.** (both) — newly promoted
- Long-press accents **and punctuation** popups (in-view on iOS). (both)
- Theme-follows-host; fail-closed without Full Access with a clear "Enable Full Access" prompt distinct from "not synced yet". (iOS)
- **Dictation** via `groq-proxy` — but the iOS mic/handoff decision is a **Phase-2 spike gate**; do not commit the iOS dictation architecture until validated on-device.
- Suggestions strip (**net-new, design sign-off required**; vocab-prefix only — no "next-word prediction" claim).
- **Emoji picker** (grid + categories + recents) — promoted from v2.
- Flume bar + **History, Snippets, Vocabulary** overlays. (both)
- Shared token source + bundled fonts + **`PrivacyInfo.xcprivacy`** + App Group bridge write + PII-at-rest hardening.

**v1.5 (Verbal differentiators, once core is solid):** Canvas overlay + write-back (only when `pairedDevice`/`canvas[]` are populated); spacebar-drag cursor; number-row toggle; backspace-swipe (degraded on iOS); undo chip; voice-punctuation commands.

**v2+ / deferred:** autocorrect neural upgrade; glide (XL both, **not** API-blocked); multilingual; **GIF Android-only**; iOS-hard-blocked features (clipboard history, floating/one-handed/resize, Live Translate) Android-only, never promised as parity.

---

**Relevant files:** `/Users/muhammadshabbar/Work/Verbal/FLUME_KEYBOARD_V2_DESIGN.md`, `/Users/muhammadshabbar/Work/Verbal/verbal-mobile/plugins/keyboard/FlumeInputMethodService.kt`, `/Users/muhammadshabbar/Work/Verbal/verbal-mobile/targets/keyboard/KeyboardViewController.swift`, `/Users/muhammadshabbar/Work/Verbal/verbal-mobile/targets/keyboard/expo-target.config.js`, `/Users/muhammadshabbar/Work/Verbal/verbal-mobile/targets/keyboard/Info.plist`, `/Users/muhammadshabbar/Work/Verbal/verbal-mobile/lib/keyboardBridge.ts`, and new `/Users/muhammadshabbar/Work/Verbal/verbal-mobile/lib/keyboardTokens.ts` (to create) + new `PrivacyInfo.xcprivacy` (app + extension).
