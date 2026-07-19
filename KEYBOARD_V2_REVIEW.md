# Flume Keyboard v2 — Merged Prioritized Fix List

Merged from four reviews (iOS bugs, iOS design, Android bugs, Android design). Grouped by file. Within each file, ordered: **compile-blockers → crashes/runtime breaks → design fidelity → nice-to-haves**.

Files under review:
- iOS: `/Users/muhammadshabbar/Work/Verbal/verbal-mobile/targets/keyboard/KeyboardViewController.swift`
- Android: `/Users/muhammadshabbar/Work/Verbal/verbal-mobile/plugins/keyboard/FlumeInputMethodService.kt`
- Shared bridge (Android design fixes depend on it): `/Users/muhammadshabbar/Work/Verbal/verbal-mobile/lib/keyboardBridge.ts`

---

## 0. Ship-blockers before anything else (verify these first)

These are not code edits in the reviewed files but gate whether any of the fixes below matter.

### 0a. [ANDROID — CRITICAL] The v2 file may not be the one that ships
The copy that compiles into the app is `verbal-mobile/android/app/src/main/java/com/verbal/app/keyboard/FlumeInputMethodService.kt`, which is the **old pre-v2 keyboard**. `plugins/keyboard/FlumeInputMethodService.kt` (the file all Android findings target) only ships if the keyboard config plugin copies it over the `android/app` copy at prebuild. **Confirm the plugin overwrites the `android/app` copy** — otherwise every Android fix below lands in dead code.

### 0b. [iOS] Confirm `SWIFT_VERSION` and warning flags
- If the Expo-generated target builds in **Swift 6 language mode**, item **iOS-1** below is a hard compile failure. If Swift 5, it is a warning only. Check `SWIFT_VERSION`.
- If the target sets `SWIFT_TREAT_WARNINGS_AS_ERRORS` / `-Werror`, item **iOS-2** (deprecated APIs) becomes a compile failure. Otherwise warnings only.

### 0c. [iOS] Extension entitlements / Info.plist
App-Group read, network POST, and mic all require **Allow Full Access** + `NSExtensionAttributes → RequestsOpenAccess = YES` in the extension `Info.plist`. Without `RequestsOpenAccess`, config reads / suggestions / overlays are dead on device even with the toggle on. The code already fails closed; just confirm the plist. (`AVAudioSession.setActive(true)` from an IME is effectively disallowed by the OS — mic is device-only/deferred, leave the catch as-is.)

### 0d. [ANDROID] Manifest prerequisites
- `RECORD_AUDIO` must be declared in the manifest/config plugin or every `startRecording()` fails closed silently (compounded by Android crash-fix #3). Verify it is declared and granted.
- Line 586 `MediaRecorder(this)` requires `compileSdk >= 31`. Fine on current AGP; will not compile against an old `compileSdk`.

---

# iOS — `KeyboardViewController.swift`

**Hard Swift syntax errors: none.** Compile-blockers here are conditional on build settings (see 0b).

## COMPILE-BLOCKERS (conditional)

### iOS-1. [COMPILE if Swift 6] Main-actor access inside `@Sendable` completion handlers — lines 501–517, 520–526, 558–564
`UIInputViewController` is `@MainActor`-isolated; `URLSession.dataTask` and `AVAudioApplication.requestRecordPermission` completion handlers are `@Sendable`/non-isolated. Touching `self.textDocumentProxy` / `self.micButton` there is a hard error under Swift 6. Wrap every UI touch reached from those handlers in `Task { @MainActor in … }`.

Current (line 563):
```swift
DispatchQueue.main.async { self.textDocumentProxy.insertText(text + " ") }
```
Corrected:
```swift
Task { @MainActor in self.textDocumentProxy.insertText(text + " ") }
```
Apply the same wrapping to the UI touches in `startRecording` (lines 514–516) and the `flashMic`/UI paths reached from `requestMic`.

### iOS-2. [COMPILE only under -Werror] Deprecated APIs — lines 402, 70, 524
- Line 402 `b.contentEdgeInsets = UIEdgeInsets(...)` — deprecated iOS 15. Prefer `configuration` or `directionalLayoutMargins`.
- Line 70 `override func traitCollectionDidChange(_:)` — deprecated iOS 17 (use `registerForTraitChanges`).
- Line 524 `AVAudioSession.sharedInstance().requestRecordPermission { … }` — deprecated iOS 17 but correctly gated behind `#available`; acceptable.

These fail a normal build only if warnings-as-errors is on.

## CRASHES / RUNTIME BREAKS

### iOS-3. [LAYOUT] Required 300pt height fights the system's own input-view height constraint — line 84
A `required` (1000) height constraint conflicts with the system constraint → "Unable to simultaneously satisfy constraints" on rotation/first present. Must be `< 1000` and held as a single reusable reference (see iOS-5).

Current (line 84):
```swift
view.heightAnchor.constraint(equalToConstant: 300).isActive = true
```
Corrected:
```swift
heightC = view.heightAnchor.constraint(equalToConstant: 300)
heightC.priority = UILayoutPriority(999)
heightC.isActive = true
```

### iOS-4. [LAYOUT] Fixed row heights over-constrain the content area — lines 240, 261, 272 (with 84, 191–196)
Total 300 minus insets/spacing/strip/bar leaves ≈194pt for `contentView`, but four 46pt rows + three 6pt gaps ≈202pt pinned to all four edges → a row height or bottom pin breaks every layout pass. Make the row/key heights breakable (priority 999). Apply to all three 46pt height constraints.

Current (e.g. line 240):
```swift
row.heightAnchor.constraint(equalToConstant: 46).isActive = true
```
Corrected:
```swift
let h = row.heightAnchor.constraint(equalToConstant: 46)
h.priority = UILayoutPriority(999)
h.isActive = true
```

### iOS-5. [RESOURCE LEAK] `buildUI()` adds a new 300pt height constraint on every theme toggle — lines 77–80, 82–84
`rebuild()` removes only subviews; the height constraint attached to `view` survives, so each light/dark switch stacks another. Create it once.

Add a stored property near line 51:
```swift
private var heightC: NSLayoutConstraint!
```
In `buildUI()`, guard so it is installed once:
```swift
if heightC == nil {
    heightC = view.heightAnchor.constraint(equalToConstant: 300)
    heightC.priority = UILayoutPriority(999)
    heightC.isActive = true
}
```

### iOS-6. [LATENT CRASH] `self?.` optional-chain mixed with `self!` force-unwrap in one expression — line 442
Safe today only because optional-chaining short-circuits argument evaluation; any refactor pulling `self!.buildEmoji()` out of argument position crashes. Bind once.

Current (line 442):
```swift
b.addAction(UIAction { [weak self] _ in self?.emojiCatIdx = i; self?.setContent(self!.buildEmoji()) }, for: .touchUpInside)
```
Corrected:
```swift
b.addAction(UIAction { [weak self] _ in
    guard let self else { return }
    self.emojiCatIdx = i
    self.setContent(self.buildEmoji())
}, for: .touchUpInside)
```

## DESIGN FIDELITY (vs `FLUME_KEYBOARD_V2_DESIGN.md`)

### iOS-7. Mic is a bullet with no orange dot badge — lines 134, 154–163, 515, 531
Spec: black circle, white `mic.fill`, small orange (#E8522A) dot badge top-right (inverted in dark). Code renders `circleButton("●")` and toggles to `"■"`; no badge.
Fix: draw an SF Symbol `mic.fill` via `setImage`, tinted `pal.micFg`, inside the circle; add a small `accent` dot subview pinned to the mic's top-right. Keep recording state as a color/stop change, not a bullet swap.

### iOS-8. Bar icons use color emoji, can't tint to the required gray outline — lines 131, 144
`⚡`, `🕐`, `📖` are emoji; `setTitleColor(pal.iconTint)` has no effect (only `▦` tints).
Fix: monochrome SF Symbols — `bolt` (snippets), `square.grid.2x2` (canvas), `clock` (history), `book` (vocabulary) — as templated images tinted `pal.iconTint`; active one tinted darker on `pal.highlightBg`.

### iOS-9. F-logo glyph too small — lines 123–127
34×34 box is correct but the F is `systemFont(ofSize: 15, weight: .bold)`. Raise to ~26pt bold.

### iOS-10. No top border on the bar — buildFlumeBar 115–138
Add a 1px hairline (`pal.modBg`/separator color) along the bar's top edge.

### iOS-11. Icon distribution bunches icons to the right — line 129
Single flexible spacer only after the F. Add a second flexible spacer before the mic (or distribute the four icons evenly between F and mic).

### iOS-12. Space bar wrong on three counts — line 228
Built as `funcKey` → gray `pal.modBg`, label `"space"`, color `pal.keyText`.
Fix: give it `pal.keyBg`, label `"English (US)"`, color the label `pal.mutedText`.

### iOS-13. Comma and period not styled as modifier keys — lines 223–230
They use `charKey` (white `pal.keyBg`); spec lists them among the light-gray modifier keys.
Fix: give `,` and `.` the `pal.modBg` background (funcKey-style but still inserting the char).

### iOS-14. Keys have no drop shadow — charKey 254–264
Add subtle `layer.shadowColor/Opacity/Radius/Offset` (light theme) on letter keys.

### iOS-15. Letter weight too light — line 259
`systemFont(ofSize: 20)` is regular; spec ~500. Use `weight: .medium`.

### iOS-16. Not using the Flume type system — throughout
Everything is `systemFont`/`monospacedSystemFont`. Bundle + register Geist and JetBrains Mono in the extension; Geist for key labels, JetBrains Mono for all mono meta (section labels, times, triggers, counts, phonetics).

### iOS-17. Shift glyph — line 206
Uses `⇧`/`⇪`; mock uses caret `^` style. Render shift as `^` with a filled/underlined caps-lock state.

### iOS-18. Overlay header missing the right-side action + return glyph — buildOverlay 343–346
Header is a single left label. Spec: horizontal row of UPPERCASE mono label (left, currently correct) + trailing per-overlay action + a keyboard-return glyph to get back to typing.

### iOS-19. History rows missing time pill, `→`, and footer — lines 371–377, 396–409
History stored as bare `[String]` with no timestamps; renders text only.
Fix: extend App-Group config to carry `{time, text}` per item; render leading JetBrains-Mono time pill + transcription + trailing `→`; add "Tap to insert" header action and a centered "See all history" footer.

### iOS-20. Snippets: expansion preview in orange mono, no left/right split — lines 368, 396–405
`overlayRow(trg, exp, accent)` concatenates trigger+expansion all in accent mono.
Fix: two-part row — orange-mono trigger (left) + `pal.mutedText` non-mono expansion (right). Add "Tap to expand" header label and a "+ New snippet" footer with an `accent` plus.

### iOS-21. Vocabulary rendered as full-width rows, not chips — lines 378–384
Fix: header-right count "14 words" (mono); a dashed-border "+ Add a word Flume keeps mishearing…" input row (orange +); words as a wrapping row of pill chips (`pal.cardBg`); phonetic beside the word in small JetBrains Mono. Extend config `vocabulary` from `[String]` to `[{word, phonetic}]`.

### iOS-22. [DEFERRED — flag, don't silently skip] Canvas overlay not implemented — lines 385–386
Default case shows "Open the Flume app to use Canvas." Spec: header-right "→ MacBook Pro", three Text/Link/Image target boxes, "RECENTLY SENT" subheader with rows carrying a green (#34C759) mono `SENT` badge. Marked v1.5 in code — known gap.

### iOS-23. Accent/green never appear — consequence of iOS-20/21/22
The orange "+ Add"/"+ New" pluses and the green #34C759 "SENT" badge appear nowhere; they arrive with the footer/canvas fixes above.

*Already correct (no change):* return-key inversion (232, 38–39); bar order + active highlight (145, 166); QWERTY rows + row2 inset; `?123`/symbols/`ABC` toggles; overlay card styling `pal.cardBg` 12pt radius (406).

## NICE-TO-HAVES

### iOS-24. Emoji entry point undiscoverable — lines 297–299, 425
Reachable only via long-press comma. Acceptable as a secondary gesture; add a discoverable emoji key (e.g. on the `?123`/globe area) or document it.

### iOS-25. Emoji recents don't persist — lines 448–449, 479–483
`commitEmoji` updates `emojiRecents` but never persists or refreshes the tab; recents reset on teardown. Cosmetic.

### iOS-26. `currentWordPrefix()` splits on non-alphanumerics — lines 321–325
Apostrophe/hyphen break the current word, so `don't`, `well-known` miss vocabulary matching. Fine for v0.

*Note:* the ~40MB jetsam concern in the header applies only to the deferred full Unicode grid; current static emoji arrays are not a memory risk.

---

# Android — `FlumeInputMethodService.kt`

**Will compile with a modern toolchain.** Build prerequisites in 0a/0d. Real issues are runtime/correctness and design.

## COMPILE-BLOCKERS
None in this file (see 0a/0d for the ship-blocking prerequisites).

## CRASHES / RUNTIME BREAKS

### AND-1. Backspace splits emoji / surrogate pairs — line 325
`ic.deleteSurroundingText(1, 0)` deletes one UTF-16 code unit, so backspacing an astral char (most emoji) leaves a broken "�".

Current (line 325):
```kotlin
if (sel != null && sel.isNotEmpty()) ic.commitText("", 1) else ic.deleteSurroundingText(1, 0)
```
Corrected:
```kotlin
if (sel != null && sel.isNotEmpty()) {
    ic.commitText("", 1)
} else {
    val before = ic.getTextBeforeCursor(2, 0) ?: ""
    val n = if (before.length >= 2 &&
                 Character.isSurrogatePair(before[before.length - 2], before[before.length - 1])) 2 else 1
    ic.deleteSurroundingText(n, 0)
}
```

### AND-2. `DataOutputStream.writeBytes()` corrupts non-ASCII multipart fields — lines 668–678
`writeBytes` writes only the low 8 bits per char, so a vocabulary/glossary word with an accent/emoji/CJK char (`"café"`, names) sends an invalid `prompt` field that garbles Whisper or gets the multipart body rejected.

Current:
```kotlin
out.writeBytes("--" + boundary + "\r\n")
out.writeBytes("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n")
out.writeBytes(value + "\r\n")
```
Corrected (apply UTF-8 to every `writeBytes` header line 668–678):
```kotlin
out.write(("--$boundary\r\n").toByteArray(Charsets.UTF_8))
out.write(("Content-Disposition: form-data; name=\"$name\"\r\n\r\n").toByteArray(Charsets.UTF_8))
out.write((value + "\r\n").toByteArray(Charsets.UTF_8))
```

### AND-3. `status` TextView never created — every error message is swallowed — lines 62, 726
`status` is declared and referenced by `setStatus(...)` (mic-unavailable, "Couldn't open Flume") but never instantiated or added to the tree, so `status?.text = s` is always a no-op. Violates the "any error shows a message" contract (never crashes, but never informs). Compounds 0d.

Fix — route through the existing `suggestionStrip`:
```kotlin
private fun setStatus(s: String) = main.post {
    suggestionStrip?.apply {
        removeAllViews()
        addView(TextView(this@FlumeInputMethodService).apply {
            text = s; setTextColor(mutedText); textSize = 13f
            setPadding(dp(14), dp(6), dp(14), dp(6))
        })
    }
}
```

### AND-4. Suggestion strip cannot scroll — `MATCH_PARENT` child in a `HorizontalScrollView` — line 118
A horizontal scroll container measures its child unbounded; `MATCH_PARENT` pins the strip to the viewport, clipping more than ~2–3 suggestions instead of scrolling.

Current (line 118):
```kotlin
layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(40))
```
Corrected (keep `sugScroll` line 123 as `MATCH_PARENT`; only the inner strip wraps):
```kotlin
layoutParams = FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(40))
```

### AND-5. Astral-unsafe truncation in overlay rows — lines 482, 489
`title.substring(0, 40)` / `sub.substring(0, 28)` cut at UTF-16 boundaries → broken "�…".

Add helper and replace lines 482/489 with `text = ellipsize(title, 40)` / `text = ellipsize(sub, 28)`:
```kotlin
private fun ellipsize(s: String, max: Int): String {
    if (s.length <= max) return s
    var end = max
    if (Character.isHighSurrogate(s[end - 1])) end--   // don't split a pair
    return s.substring(0, end) + "…"
}
```

## DESIGN FIDELITY (vs `FLUME_KEYBOARD_V2_DESIGN.md`)

### AND-6. Mic missing the orange dot badge — lines 172–177
Bare circle with `●`, no badge. Wrap the mic in a `FrameLayout` and add a small `View` (≈dp(7), `rounded(ACCENT, 999)`) pinned top-right (or a `LayerDrawable`); it must persist across the `mic?.text` "●"/"■" swaps in `startRecording`/`abortRecording`/`stopAndTranscribe`.

### AND-7. Bar icons are color emoji, not tinted outline icons — lines 166–169, 183–192
`🕐`/`📖` (and `⚡`/`▦`) ignore `setTextColor(iconTint)`. Replace with monochrome `VectorDrawable`s (lightning/grid/clock/book) `setTint(iconTint)` or `ImageView`s; keep the active `highlightBg` rounded bg (already correct, 186/196).

### AND-8. Bar clusters everything to the right — line 164
Weight-1 spacer sits right after the F logo. Distribute the four overlay icons across the width (equal-weight spacers, or one weight before the mic) for full-width layout.

### AND-9. No top border on the bar — line 152
`buildFlumeBar` sets only `setBackgroundColor(barBg)`. Add a 1px top hairline divider (`highlightBg`/muted).

### AND-10. No keyboard-return glyph to leave an overlay — overlay header 396–412 (toggle line 381)
Only way back is re-tapping the active bar icon. Add a keyboard-glyph TextView on the right of every overlay header calling `showKeyboard()`.

### AND-11. Space bar rendered as gray modifier key — line 260
Built via `functionKey("English (US)", 4f)` → `modBg` gray. Give it `keyBg` background and set the label color to `mutedText`, distinct from `functionKey`'s `modBg`/`keyText`.

### AND-12. Keys have no drop shadow — charKey 283–293
Flat `GradientDrawable`. Add `elevation`/`stateListAnimator` or a shadow layer on letter keys (light theme).

### AND-13. Theme tokens from the bridge ignored — lines 89–103, 633–636
`keyboardBridge.ts` writes `schemaVersion: 2` with a `theme` block (single source per `lib/keyboardTokens.ts`), but `readConfig`/`applyTheme` hardcode all colors. Parse `cfg.theme.*` in `applyTheme`, falling back to the current constants. (Minor: dark `cardBg = #1C1A18` warm brown-black — source from the token so it stays consistent.)

### AND-14. History: no time pill, no `→`, no "See all history" footer — lines 432–438 (bridge 45)
`overlayRow(t, "", keyText)` renders plain text; the bridge maps history to `h.text` only, dropping timestamps.
Fix: (a) in `keyboardBridge.ts` emit `history` as `{ text, at }`; (b) in Kotlin parse each timestamp, format a relative mono pill (`9:24`, `Yd`), build row as `[mono pill] [truncated text] [→]`; (c) add a centered "See all history" footer. Update `context/04-data-model.md`.

### AND-15. Canvas not implemented — lines 461–463, 408
Header hardcodes `"→ device"` (should be paired device name, e.g. "→ MacBook Pro"); missing the three Text/Link/Image outlined target boxes; missing `RECENTLY SENT` subheader + rows with green `#34C759` mono `SENT` badge. Whole panel is one `overlayRow("Open Flume Canvas", …)`.
Fix: build the three target boxes; add `RECENTLY SENT` subheader + sent rows with the green badge; surface `deviceName` via config. If canvas data isn't plumbed yet, at minimum add `deviceName` + render the three targets and **flag the deferral explicitly**.

### AND-16. Snippets: missing "+ New snippet" footer — lines 421–431
Rows are correct (orange mono trigger + gray expansion). Append a footer row `+ New snippet` with the `+` in `ACCENT`, tapping opens the app's snippet editor.

### AND-17. Vocabulary header count wrong and not mono — line 408
Hardcodes literal `"words"` in plain Geist. Compute `arr.length()` → render `"$n words"` with `typeface = Typeface.MONOSPACE`.

### AND-18. Vocabulary missing the "+ Add a word…" dashed input row — lines 440–460
Add as first child of the vocab list: dashed-stroke `GradientDrawable` (`setStroke(dp(1), ACCENT, dashWidth, dashGap)`), orange `+`, tap opens the add-word flow.

### AND-19. Vocabulary chips are one scrolling row, not flow-wrap — lines 444–458
Single `LinearLayout` in a `HorizontalScrollView` (code has a TODO). Replace with true flow-wrap (Google `FlexboxLayout` or manual line-breaking by measured width).

### AND-20. Vocabulary chips have no phonetics — lines 448–456 (bridge 41)
Chips read a plain string array. Emit vocabulary as `{ word, phonetic? }` from `keyboardBridge.ts`; render the word + trailing `phonetic` span in small `Typeface.MONOSPACE`/`mutedText` (e.g. `Idiaz  i-DEE-uhz`). Update `context/04-data-model.md`.

*Already correct (no change):* QWERTY/numbers/`=\<` symbols layers; shift/caps cycle; `?123`/`ABC` toggles; comma/period/space/return row structure; return-key inversion; theme base colors (`#0E0E0E`/`#F2F2F5`); modifier-gray ordering; mic circle fill inversion; snippet row styling; active-icon highlight.

## NICE-TO-HAVES

### AND-21. Emoji picker not in spec / undiscoverable — line 258
Reached only via long-press comma; 8-per-row grid + `ABC`/`⌫` footer has no design reference. Either drop from v2 or give it a discoverable entry point and confirm against a design. Low priority.

### AND-22. Last emoji grid row stretches — line 551
Cells use weight `1f`, so a final short row over-expands. Pad the final row with empty weighted `View`s to a multiple of 8, or use a fixed cell width.

### AND-23. Dead code — lines 19, `barRow`
Unused `Button` import and `barRow` field. Harmless; remove for cleanliness.

---

## Shared bridge — `lib/keyboardBridge.ts` (required by Android design fixes; iOS overlays need the analogous App-Group config shape)

- **Line 45 (history):** emit `{ text, at }` per item instead of `h.text` only (feeds AND-14 / iOS-19 time pills).
- **Line 41 (vocabulary):** emit `{ word, phonetic? }` instead of `[String]` (feeds AND-20 / iOS-21 phonetics).
- **Add `deviceName`** to config (feeds AND-15 / iOS-22 canvas header).
- Per CLAUDE.md, update `context/03-features.md`, `context/04-data-model.md` (new history/vocab config shape + any live-DB-only column), and `context/05-conventions.md` in the same change.

## Verification per CLAUDE.md
- iOS: build the extension target; confirm `SWIFT_VERSION` and warnings-as-errors flag first (0b).
- Mobile bridge: `cd verbal-mobile && npx tsc --noEmit`.
- Peripheral paths must fail closed and never break record → transcribe → inject.
