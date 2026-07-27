# 05 — Conventions, Gotchas & Design System

> Part of the `context/` knowledge set. See `context/README.md` for the maintenance rule.
> **Keep this current:** when a new hard-won rule, gotcha, or design token is established, add it here so
> future work (and chat suggestions) don't reintroduce a fixed bug. When a module dies, list it below.

## Hard rules (violating these has broken the app before)

1. **Never break the dictation path.** File-tagging, auto-learn, sync, dictionary-cloud, and the canvas
   listener are all wrapped in try/except and **fail closed** (silent no-op). Any new peripheral feature
   must do the same — recording→transcribe→inject must always proceed. (`filetags.py`/`autolearn.py` carry
   explicit "HARD GUARANTEES" docstrings.)

2. **Verify generated web UI:** the WKWebView/pywebview HTML+JS is produced by Python strings. After any
   change, `node --check` the extracted `<script>` blocks. The desktop dashboard JS lives in a **raw
   string** (`flume_dashboard_html.py`) — inside it, JS escapes use a **single** backslash (`\s`, not
   `\\s`). (The old `shared_dashboard._html()` — a light-theme Windows-only dashboard that used doubled
   backslashes — has been **retired**; Windows now renders the same `flume_html()` as macOS.)
   Always: `py_compile` + `import app.main` + `node --check` the rendered script blocks.

3. **Config writes are atomic + locked.** Only write config via `config.py::save_config` (unique
   `tempfile.mkstemp` name + `os.replace` under `_config_lock`). Never share a temp filename across
   threads (a shared `config.tmp` caused a rename race). Cloud fetches write config **only when content
   changed** (avoids save churn).

4. **Main-thread discipline (macOS).** WKWebView and all AppKit UI must be touched on the main thread —
   route every background→UI hop through `main._on_main` / the `rumps.Timer` UI queue. Background threads
   never call WebView/AppKit directly.

5. **AX / Electron accessibility (file-tagging, auto-learn).** Cursor/Windsurf/VS Code/Antigravity/Kiro do
   NOT expose their web-content AX tree until you set **`AXManualAccessibility` + `AXEnhancedUserInterface`**
   on the app element; the tree builds **lazily** (needs a settle delay ~1.3 s), and the file-explorer rows
   sit ~depth 25 (walk depth ≤40). Do the deep harvest on a **background thread at record-start**, off the
   critical path. Always **exclude terminals and secure fields**; require the inserted text to be found in
   the field before trusting a read (Electron reads are flaky). See `electron-ax-file-tagging` memory.

6. **Groq prompt 896-char cap.** The Whisper bias prompt (dictionary glossary + open-file list) must stay
   under Groq's 896-char limit or every call 400s. `transcriber.py` trims to `_GROQ_PROMPT_CHAR_CAP=850`
   at a comma boundary, glossary first.

7. **Fonts:** AppKit views use CoreText-registered faces (`theme.py`); **WKWebViews can't resolve those by
   name** → inline TTFs as base64 `@font-face` via `fonts_css.web_font_css()`.

8. **Non-activating panels:** the overlay + auto-learn widget use
   `NSWindowStyleMaskBorderless | NSNonactivatingPanelMask` at `NSScreenSaverWindowLevel` so they never
   steal key focus from the app being dictated into. Any new floating HUD must too.

9. **Anti-nag memory:** once a word is offered by auto-learn (Add *or* dismiss) it's recorded in
   `config['autolearn_declined']` and never re-offered. (This is why re-testing the *same* word shows
   nothing — test with a fresh word, or clear the list.)

10. **Supabase RLS must be `TO public`, not `TO anon`, on any table both clients share.** The desktop
   talks to Supabase with the raw anon key (role `anon`); a *signed-in* mobile client sends the user's JWT
   (role `authenticated`). A policy scoped `TO anon` silently filters out the authenticated client's rows —
   this is what broke dictionary/snippet sync to signed-in phones (fixed via
   `whisperflow/supabase_dictionary_rls_fix.sql`). Same fix applied to `notes` (Linear MER-26, 2026-07 —
   RLS had been fully DISABLED there, not just `TO anon`; see `whisperflow/supabase_notes_rls.sql`) and to
   the **`recordings` Storage bucket's policies** (Linear MER-27, 2026-07 — found mid-fix while making the
   bucket private: its read/insert/update policies were `TO anon` only, which would have silently broken
   signed-in mobile clients' `createSignedUrl` calls; see `whisperflow/supabase_recordings_meeting_audio_private.sql`)
   and to **`pairings`** (Linear MER-28, 2026-07 — its 3 policies were `TO anon`; migrated in place in
   `whisperflow/supabase_pairings.sql`). `transcriptions`/`devices`/`canvas` were checked as part of the
   same MER-28 pass and were already correctly `TO public` — no table in this codebase is known to still
   have the `TO anon` trap.

11. **Preserve unknown fields verbatim on write-back (forward-compat sync).** A client must never replace a
   synced row with only the fields it knows about — a newer client's columns would be silently dropped.
   Notes v2 enforces this: desktop keeps a `_NOTE_KNOWN_FIELDS` allowlist and re-attaches every unknown key
   to the cloud upsert (`shared_dashboard.py`); mobile relies on `NoteEntry`'s index signature + spreading
   the whole row before overwriting known fields (`useNotes.ts`/`notesStorage.ts`). Apply the same pattern
   to any new synced table/column.

12. **Notes cleanup runs once, not on every save (cost control).** An LLM call per note save = runaway
   cost. Cleanup fires only on the initial dictated save (and on explicit Reformat/Retry); typed edits
   never auto-format; appended dictation cleans only the newly-appended segment. The LLM notes call has an
   **8 s hard timeout** → fall back to saving raw + surface "Retry formatting" (never block the editor).
   The structure-detection rules live on `NOTES_FORMATTER_SYSTEM_PROMPT`/mobile `formatNotes` (the **LLM**
   system prompt) — Hard Rule #6's 896-char cap is the **Whisper** bias prompt only; don't conflate them.

13. **Wipe account-scoped caches on sign-out / account switch (data isolation).** Mobile keys all data by
   `getUserId()`, but the id + local caches persist across sign-ins. If they aren't cleared, a *different*
   Google account signing in on the same device sees the previous account's history/notes/devices/vocabulary
   (a real cross-account leak that shipped). `useAuth.signOut` and `afterSignIn` (when the uid changed) must
   call `clearAccountData()` (`lib/storage.ts` — removes `verbal_user_id`, `verbal_history`, `verbal_pinned`,
   `verbal_notes_cache`, `flume_dictionary`, `flume_target_device`) **and** `historyStore.reset()` (drops the
   items singleton + the realtime channel keyed by the old id). Any new per-account cache/singleton must be
   added to that teardown. Device-level config (Groq key, device name, feature-flag prefs) is preserved.
   `signOut` uses `supabase.auth.signOut({ scope: 'local' })` so it can't hang on the network.

14. **Don't use the custom `confirm()`/`ConfirmDialog` inside a screen presented as a native-stack MODAL
   (mobile).** `ConfirmHost` renders a JS `<Modal>` from the root; on iOS a JS modal shown over a
   native-stack `presentation:'modal'` screen (e.g. **Settings**) doesn't reliably receive touches, so the
   dialog looks dead — this is why the Sign-out button "did nothing." Inside modal screens use React
   Native's native `Alert.alert(...)`. `confirm()` is fine on tab/stack screens (e.g. notes multi-select).

15. **All Groq access goes through the `groq-proxy` Edge Function — never a client-side key.** The Groq key
   is a Supabase **function secret** (`GROQ_API_KEY`), server-side only. Every client POSTs to
   `<SUPABASE_URL>/functions/v1/groq-proxy` (multipart → transcription, JSON → chat) authenticating with the
   signed-in user's Supabase JWT (mobile `lib/groq.ts`) or the anon key (desktop `app/groq_proxy.py`, iOS +
   Android keyboards) plus an `x-flume-device` fallback id. The function (`verify_jwt` on, source in
   `supabase/functions/groq-proxy/index.ts`) decodes the caller id from the JWT locally (no `getUser`
   round-trip) and **logs usage** to `groq_usage` fire-and-forget, then streams the Groq response back.
   It is deliberately lean for latency: no SDK import, no `getUser` round-trip.
   **Per-identity rate limiting (MER-30, 2026-07):** before any upstream call, the function computes the
   same identity used for usage logging and calls the `groq_check_rate_limit` Postgres RPC (service-role
   key), which does one indexed upsert+read against `groq_rate_limits` (fixed 60s window, per-identity
   request count + a coarse token-estimate — 500 for transcription, 2048 for chat, both env-configurable via
   `RATE_LIMIT_PER_MINUTE`/`RATE_LIMIT_TOKENS_PER_MINUTE`, defaults 30 req/min and 20000 tokens/min). Over
   either limit → `429` with a `Retry-After` header; the limiter **fails open** on any RPC/network error
   (Hard Rule #1). **This replaced an in-memory (in-isolate) counter that shipped first and turned out not
   to work**: live testing (a 35-request sequential burst from one identity) showed **zero** rejections from
   the in-memory version — every request reached Groq, confirmed via `groq_usage` row counts — because
   Supabase's edge runtime does not reliably keep module-level state warm across invocations for this
   traffic pattern. A DB round-trip on the hot path was accepted as the necessary trade-off once the
   zero-infra version was proven non-functional; correctness beat the latency micro-optimization. **The RPC
   is `SECURITY DEFINER` and its `EXECUTE` grant MUST stay revoked from `anon`/`authenticated`** (granted
   only to `service_role`) — otherwise any client can call it directly via PostgREST with an arbitrary
   `p_identity` and tamper with another identity's counter; the security advisor caught this live during
   MER-30 and it was fixed in the same migration (`supabase_groq_rate_limits.sql`). See
   `04-data-model.md`'s `groq_rate_limits` entry.
   Rotate/revoke centrally: `supabase secrets set GROQ_API_KEY=…` (no app update). The key is **never** in an
   app bundle, the repo, or a log. **Meeting NOTES route through the same function but to Ollama Cloud**
   (`gpt-oss:120b`): the client adds `{"provider":"ollama"}` to the chat payload → the function strips it
   and forwards to `https://ollama.com/v1/chat/completions` (OpenAI-compatible, pure passthrough) using a
   second secret `OLLAMA_API_KEY`. It **fails closed**: no key / Ollama down → the client retries on Groq
   `llama-3.3-70b` so notes never fail (`meetings.generate_meeting_notes`, `lib/groq.ts::generateMeetingNotes`).
   Set/rotate via `supabase secrets set OLLAMA_API_KEY=…` (key from ollama.com/settings/keys). The earlier
   `app_config` **provider-secret-key-table** idea is correctly **SUPERSEDED** (a client must never be able
   to read `GROQ_API_KEY` itself) — but **`lib/remoteConfig.ts` is NOT vestigial**, contrary to what this
   rule used to say: it's still actively called (`storage.ts::getGroqKey`'s last-resort fallback, and
   warmed on app start in `RootNavigator.tsx`) to read a *different*, same-named `app_config` table for a
   cached "shared bundled Groq key" — and a 2026-07 live-schema audit found **no `app_config` table exists
   in the current DB at all**, meaning this fallback path likely silently no-ops every time (see
   `04-data-model.md`'s `app_config` callout). Low practical impact since it's a fallback of a fallback
   (`groq-proxy` is always tried first), but the code and this rule had drifted from each other — verify
   before assuming this path does anything today. The iOS keyboard's `KeyboardViewController.swift` and
   desktop still keep a local-key fallback path only for
   resilience — the proxy is always tried first. **Groq returns HTTP 413 (not 429) when a request would
   exceed the shared key's tokens-per-minute budget** — this shows up on long meetings, since the summary
   prompt can carry up to `TRANSCRIPT_CHAR_BUDGET` (24,000) chars. `groq_proxy.chat_via_proxy` raises
   `ProxyPayloadTooLarge` on 413 instead of swallowing it; `meetings.generate_meeting_summary` catches it
   and retries with a halved transcript budget (up to 3 attempts total) rather than repeating the identical
   oversized request.
16. **Keyboard data bridge is App-Group–gated on iOS.** The app hands the keyboard its config
    (`flume_kbd_config.json`: theme, vocabulary, snippets, recent history) via a JSON snapshot written by
    `lib/keyboardBridge.ts::syncKeyboardConfig()`. On **Android** the IME reads `context.filesDir`, which is
    the same dir as Expo's `documentDirectory` — a plain `writeAsStringAsync` works. On **iOS the keyboard
    extension is a separate sandbox** and can *only* read the shared **App Group** container
    (`group.com.verbal.app`), never the app's `documentDirectory`. `expo-file-system` can't target group
    paths, so writes go through the local native module **`modules/flume-shared-store`** (`writeToGroup`);
    the bridge falls back to `documentDirectory` only when that module is absent (Expo Go / no native build).
    The Swift extension reads the group via `FileManager.containerURL(forSecurityApplicationGroupIdentifier:)`.
    Both the app and the `FlumeKeyboard` target must declare the group in their entitlements (they do, via
    `app.json` `ios.entitlements` + the apple-targets `expo-target.config.js`). **Sync must be re-triggered on
    every data change**, not just app launch — `addToHistory` / `mergeRemoteEntries` / dictionary edits all
    fire-and-forget `syncKeyboardConfig()`, else the keyboard panels go stale. Bar icons: **Ionicons**
    (bundled `plugins/keyboard/ionicons.ttf`, copied to `assets/` by `withFlumeKeyboard.js`) on Android;
    **SF Symbols** (`bolt.fill`/`square.grid.2x2`/`clock`/`book.closed`/`mic.fill`) on iOS. The keyboard's
    **dark theme uses the canonical "Minimalist dark" tokens** (`flume-ui/theme/colors.ts` +
    `CLAUDE_CODE_PROMPT.md`, the authoritative design spec): `bg #0e1012`, keys `#2a2d31`, modifiers `#1e2124`,
    text `#f2f2f2`, white `#f2f2f2` return/mic, overlay rows `#26282b` — and the accent is **terracotta
    `#C85A3E`** (NOT orange; `#E0552C` was wrong). **barBg == bg** so the Flume bar blends into the app bottom
    (no floating grey card) and the keyboard is near-full-bleed (2dp side inset). Source of truth is
    `lib/keyboardTokens.ts`, mirrored in each native `applyTheme()`. NB: the mobile theme is cool near-black +
    terracotta; the cream/sage/plum pastels are desktop dashboard feature-card colors only.
    **Fonts are bundled into the keyboards** (not system): Geist (UI/keys) + JetBrains Mono (numerals/meta) ship
    as TTFs — Android copies them to `assets/` via `withFlumeKeyboard.js` and loads with `Typeface.createFromAsset`;
    iOS ships `Geist-Regular/Medium.ttf` + `JetBrainsMono-Medium.ttf` in the target, declared in the target
    `Info.plist` `UIAppFonts` and registered at runtime via `CTFontManagerRegisterFontsForURL` (PostScript names
    `Geist-Medium` / `JetBrainsMono-Medium`). **Recording bar** (spec `RECORDING_BAR_PROMPT.md`): tapping the mic
    fades out AND collapses the overlay icons + the mic, leaving the F wordmark and swapping in — left→right — a
    **✕ cancel chip** (~38pt, discards), a **24-bar organic waveform** (bars *text-colored*, not terracotta;
    varied heights via a slow envelope × per-tick pseudo-random spike so it always animates even with no mic
    input — e.g. the iOS sim; real voice pushes higher on-device), a **`M:SS` mono timer**, and a big
    **terracotta button** (~42pt). The design has one right-side button, so it's overloaded: **tap = stop &
    transcribe, long-press = pause/resume** (paused dims the button + freezes waveform/timer). The **F wordmark
    inverts** (keyText square + terracotta F). Amplitude: Android `MediaRecorder.getMaxAmplitude()`, iOS
    `AVAudioRecorder.averagePower` (metering), polled ~70ms; timer excludes paused spans.
    **Sound effects** mirror the desktop (`whisperflow/app/sounds.py`: start / stop / done — no processing-loop
    sound). The branded `assets/sounds/{start,stop,done}.wav` are bundled three ways: RN in-app recorder plays
    them via `lib/sounds.ts::playCue()` (expo-audio, wired into `useRecorder`); the Android keyboard plays
    `flume_{start,stop,done}.wav` from `assets/` via `SoundPool` (copied by `withFlumeKeyboard.js`); the iOS
    keyboard plays them via `AVAudioPlayer` from the extension bundle. Cancel is silent. All playback is
    fail-closed and never blocks record→transcribe→insert. iOS needs Full Access + juggles the audio session
    (`.playAndRecord` for the start cue, `.playback` for stop/done); sim playback is unreliable, device is the test.
    **Typing suggestions** (completions + next-word + learning; NO autocorrect yet — that's the remaining tier).
    Two bundled data files (generated offline — `wordfreq` for words, `nltk` corpora bigrams — and bundled to
    Android `assets/` + the iOS target): `flume_words.txt` (~25k words, most-frequent first, **including ~370 contractions** like
    `wasn't`/`don't`/`i'm` — the list allows apostrophes, not alphabetic-only) drives prefix **completions**; `flume_bigrams.txt` (`prev<TAB>next1 next2 …`, ~21k prev-words) drives **next-word
    prediction**. `updateSuggestions()` branches on the current word prefix: **non-empty** → completions ranked
    personal-learned → vocabulary → dictionary; **empty** (cursor after a space) → next-word for the previous
    word, personal-bigrams → bundled-bigrams. Both capped at 3, deduped, casing-aware; iterate the lists until 3
    hits (never sort the whole dictionary). The keyboard **learns your words AND your phrasing**: a personal
    word→count map and a personal prev→next bigram map, persisted per-keyboard (Android `SharedPreferences`
    "flume_kbd_learn" keys "words"/"bigrams", bounded ~500/~400; iOS `UserDefaults` "flume_kbd_learned" /
    "flume_kbd_bigrams"), updated on every finished word / word-pair (boundary char) and accepted suggestion.
    **Typing feel (Gboard-parity):** keys commit on **touch-DOWN**, NOT `setOnClickListener`/`.touchUpInside` —
    the click path drops fast taps that slide past touch-slop, which was the "missing keys" bug. Android fires
    `performHapticFeedback(KEYBOARD_TAP, FLAG_IGNORE_VIEW_SETTING)` on down; **iOS keyboard extensions cannot do
    haptics** (Apple gates the Taptic Engine to the foreground app — do not attempt `UIFeedbackGenerator`), so
    iOS uses `UIDevice.playInputClick()` (respects the user's Keyboard Clicks setting) as the substitute. Also:
    pressed-state highlight on down, a letters-only key-preview bubble (Android `PopupWindow` `isTouchable=false`
    / iOS overlay `UILabel`), `double-space → ". "`, and auto-capitalization at sentence start (rebuilds only
    when the shift state flips). The **comma commits on UP** (not down) so its long-press→emoji works without
    inserting a stray ",". All feedback/preview paths fail closed — they never block the commit. Deferred P2:
    long-press accent popups, spacebar cursor-swipe, glide typing, and Android key-click sound (default off).
    **Gapless touch grid:** keys tile edge-to-edge with NO dead-zone margins — a tap between keys still hits the
    nearest key (Gboard behavior). The visual gap is drawn INSIDE each key: Android `InsetDrawable(rounded,dp3)`
    + zero margins + row topMargin 0; iOS transparent button filling its cell + a 3pt-inset rounded background
    subview + row `spacing=0`. **Emoji:** the picker loads a full bundled library `flume_emoji.txt` (~1900 emoji,
    9 groups + Recents, from Unicode emoji-test.txt) via comma long-press. **Word→emoji suggestions:**
    `flume_emoji_kw.txt` (~2.3k keywords, Unicode CLDR + curated) maps a typed word to emoji; an EXACT full-word
    match shows the emoji as the first suggestion cell and tapping REPLACES the word with the emoji + space.
    **Suggestion bar** is distributed: up to 3 equal-width centered cells with thin dividers spanning the full
    width (was left-packed). All emoji/dictionary/bigram data files are generated offline and bundled to Android
    `assets/` (via `withFlumeKeyboard.js`) + the iOS target. **Spacebar-swipe cursor:** dragging horizontally on
    the space key moves the caret (~1 char per 12dp/pt) instead of typing — Android sends `DPAD_LEFT/RIGHT` key
    events, iOS uses `adjustTextPosition(byCharacterOffset:)`; a swipe suppresses the space, a plain tap still
    spaces (double-space→". " intact).
    **Clipboard history (quick-paste chip + 5th bar icon) is deliberately NOT part of this bridge** — it's
    self-contained in each keyboard target, reading/writing its own `flume_kbd_clipboard.json` (iOS: same App
    Group container; Android: the IME's own `filesDir`), capped at 15 entries, because only the extension
    itself can observe a clipboard change made in another app — the main app/JS has no visibility into it.
    Only a single on/off preference, `clipboardHistoryEnabled`, rides the existing bridge. **Any future keyboard
    feature that touches the clipboard MUST skip content flagged by the password-manager "don't capture this"
    convention** — Android `ClipDescription.EXTRA_IS_SENSITIVE` (API 33+) and iOS's de facto
    `org.nspasteboard.ConcealedType` UTI (1Password/Bitwarden etc.) — and must never sync clipboard content off
    the device. iOS clipboard reads require the keyboard's "Full Access"; gate ambient UI (the quick-paste chip)
    on `hasFullAccess` silently, but an explicit user action (the clipboard overlay) must show an informative
    "enable Full Access" prompt, never fail silently.
    **"Type into the keyboard's own UI" pattern (Transform, Jul 2026) — reuse this for any future feature
    that needs free-text input from inside the extension.** Neither platform can host a real second
    text-input surface inside a keyboard extension's own view, so instead: add ONE mode flag, and have the
    already-centralized `commit()`/`onSpace()`/`onBackspace()` (every real keystroke funnels through these
    on both platforms) redirect to a local string buffer + a preview label instead of
    `textDocumentProxy`/`currentInputConnection` while that flag is set — the letters/numbers/symbols layer
    stays fully visible and usable underneath, just repointed. Also guard `doUpdateSuggestions()` to no-op
    while the flag is set (same shape as the existing `activeOverlay != nil` guard), since the suggestion
    strip is repurposed as the input-preview band. Bar chips are a shared, mode-aware slot, not one-per-
    feature: Transform's post-Replace "Undo" affordance reuses the exact same chip view as the clipboard
    quick-paste chip (`refreshQuickPasteChip`/`tapQuickPasteChip` on both platforms) — whichever ephemeral
    action is most recent wins the display; they never show at once, and that's an accepted degrade rather
    than a bug.
17. **`historyStore` loads once at app start — you MUST `refresh()` it on sign-in.** The shared singleton
    (`flume-ui/hooks/historyStore.ts`) has a `started` guard: `ensureLoaded()` runs `load()` a single time,
    and `RootNavigator` mounts `useHistory()` at app start — i.e. **before sign-in, when sync is off** — which
    trips the guard. So adopting the account id later does NOT auto-fetch. `useAuth::afterSignIn` therefore
    calls `historyStore.refresh()` (which re-runs `load()` unconditionally) after `setUserId`/`setSyncEnabled`;
    without it a fresh install shows an empty History even though the cloud rows exist. Sign-out calls
    `historyStore.reset()` (clears the guard). Remote history lives in `public.transcriptions` keyed by the
    Supabase auth `user_id`; its RLS policy is currently permissive (`USING true`, role `public`) — revisit.
    **`getUserId()` (`lib/storage.ts`) is authoritative from the live Supabase session** — it returns
    `supabase.auth.getSession()`'s user id (and caches it) whenever signed in, only falling back to a
    stored/minted local id when signed out. This is load-bearing: it scopes ALL cloud data (notes, dictionary,
    snippets, history). The earlier bug where a **restored** session (afterSignIn didn't run) read a stray
    minted id and showed everything as 0 is fixed here — don't revert `getUserId` to a pure AsyncStorage read.

18. **Meetings capture must never touch the dictation `Recorder` — and only ONE process-wide mic stream may
    exist.** A meeting opens its OWN `sounddevice.InputStream` (meetings.py); but when dictation starts
    DURING a meeting it must NOT open a second stream on the same device (CoreAudio drops one of them —
    "my voice gets ignored" — and a failed second open's PortAudio reinit killed the meeting stream).
    Instead `main._on_record_start` registers a **mic tap**: `MeetingSession.add_mic_tap(recorder.feed_external)`
    + `recorder.start_external(16000)` — the meeting's callback forwards 16 kHz blocks to the tap (even while
    the meeting is paused), and the tap is detached in `_on_record_stop`/`_cancel_recording`. `sd._terminate()`
    is guarded everywhere: never call it while the other subsystem holds a live stream. The scratchpad's
    Dictate chip rides this same path — the paste lands in the focused scratchpad and the same words
    legitimately also enter the meeting transcript via the meeting mic. **Cold-start cost lives off the main
    thread:** the ScreenCaptureKit import (~1 s) is pre-warmed at startup and `_toggle_meeting` runs its
    permission check on a background thread — main-thread work froze every first click. The summary screen
    scrolls as ONE page (sticky header, expanded sections grow into the page) — inner-only scroll containers
    were unusable in small windows.
    ScreenCaptureKit facts that cost time: SCK **audio** is gated by the *Screen Recording* TCC class
    (`CGPreflightScreenCaptureAccess`) even when no pixels are read; you must still configure a tiny video
    stream (2×2 + `CMTimeMake(1,1)` frame interval) and drop the video buffers; set
    `excludesCurrentProcessAudio` or the app re-captures its own sound cues; a `SCStream` output delegate
    must never raise into SCK's queue. pyobjc: `CMBlockBufferCopyDataBytes(block, 0, len, None)` returns
    `(status, bytes)` — the trailing `o^v` arg is an out-buffer. **An ObjC delegate class defined inside a
    function re-registers with the runtime on every call** — the second meeting in one process died with
    "_Output is overriding existing Objective-C class"; define such classes ONCE at module scope
    (`system_audio._output_class()`; the instance carries a `_capture` back-reference, cleared on stop).
    **PortAudio's device list goes stale after a macOS audio-device change** (e.g. AirPods
    connect/disconnect): every later `sd.InputStream` open — including hotkey dictation — fails with AUHAL
    `'!obj'` / `kAudioUnitErr_InvalidPropertyValue` / `paInternalError -9986` until you
    `sd._terminate(); sd._initialize()` and re-query the CURRENT default input rate. Both
    `recorder.Recorder.start()` and the meeting mic open do exactly that (reinit + native-rate retry;
    meetings resample native→16 k inside the callback). **Audio callbacks must be O(block):** the meeting
    chunker originally concatenated its whole 8–22 s buffer on EVERY callback for a tail-RMS check — that
    starved PortAudio's realtime thread and the mic stream stalled after ~a minute ("only system audio
    records me"). The silence check now uses a small rolling tail buffer, the big concat runs on the
    transcription worker, and a **mic watchdog** in the ticker reopens a stalled stream (no callbacks for
    >5 s, throttled to one attempt/10 s). The meeting's elapsed clock is **wall-time minus pause spans** —
    never one source's sample counter, which freezes the timer when that source drops. The dashboard learns
    about finished meetings via a `meetingsUpdated` VerbalNative event (meetings end in a different window)
    plus a refresh on `show('meetings'|'home')` — a load-once guard alone left the list stale.
    **Never emit bridge events into a WKWebView before its JS is ready** — `evaluateJavaScript` against a
    still-loading page silently drops the call (the `if(window.VerbalMeeting)` guard makes it a no-op), which
    is why opening a meeting into a fresh window "did nothing". Pattern: the page calls a ready handshake
    (`api('meeting_page_ready')`) after installing its handler; the controller buffers `emit()`s until then
    and flushes them (plus re-asserts the current layout) — see `MeetingWindow.page_ready()`.
    **Never gate critical UI visibility on a CSS animation in a WKWebView.** The meeting window shipped
    blank because containers had `opacity:0` base styles (and later `from{opacity:0}` + fill-mode `both`)
    with an entrance animation that WebKit can skip or park at time 0 (occluded/offscreen panels, Reduce
    Motion, styleMask-flip races) — the element then sits invisible forever. Rule: containers appear
    instantly (no entrance animation); only decorative per-row elements may animate, always with the default
    fill mode so a skipped animation leaves them visible. Debug this class of bug by SNAPSHOTTING the real
    WKWebView headlessly (`takeSnapshotWithConfiguration_completionHandler_` + event injection — see the
    harness pattern in the session that fixed this) instead of guessing from code.
    Structured LLM output from Groq must use
    `response_format={"type":"json_object"}` (strict JSON mode, passed through `chat_via_proxy`; the prompt
    must contain the word "JSON") — prompt-only "reply with JSON" was not reliable for meeting summaries.
    **The whisperflow venv's `pip` binary is a
    mismatched interpreter (py3.14) that installs into the wrong site-packages — always
    `.venv/bin/python -m pip install …`** (this bit the SCK wrapper install; the venv also carries a stale
    `lib/python3.14` tree). New deps for meetings: `pyobjc-framework-ScreenCaptureKit` +
    `pyobjc-framework-CoreMedia` (pinned 12.1; add to PyInstaller hiddenimports when bundling).
    The meeting window/HUD use dedicated JS namespaces (`VerbalMeeting`, `VerbalMeetingHud`) — never emit
    meeting events through `VerbalNative`. Meeting summary generation follows the Notes cost rule: ONE
    structured LLM call per meeting (strict-JSON contract, 24k-char transcript budget, 2 attempts, 45 s),
    regenerate only on explicit Retry; a failed summary sets row status `failed` but keeps the transcript.
    Meeting text NEVER goes into analytics (none is emitted at all in v1).
    **Only CAPTURING states flip the meeting window to the live screen** (`recording|paused|preparing`).
    'stopping'/'processing' are post-capture: a summary retry re-emits 'processing' and used to hijack the
    view into a fake in-meeting screen ("retry starts the meeting again"). Related: session broadcasts of
    `meeting` events must not replace a DIFFERENT meeting the user is reading — explicit opens go through
    the dedicated `openMeeting` event; the generic handler drops mismatched-id payloads in summary mode.
    **The meeting window is ONE reused page — reset the live panes on meeting-id change.** Opening a
    second meeting used to show the first meeting's transcript: `resetLive()` clears
    UTTS/MARKS/notes/timer/star-count when a `state` event carries a new id, and `utterance`/`moment`
    events are tagged with `mid` so stragglers from the previous meeting's still-draining worker are
    dropped.
    **Every clipboard/regenerate/save button needs visible feedback** (`flashOk`/`toast` in
    meeting_html) — a working copy button with no feedback reads as broken and gets reported as a bug.
    Regenerating a summary merges the user's done-checkboxes back in by task text (`merge_action_done`);
    deleting is blocked while that meeting's pipeline is still draining (zombie-row race).
    **Voice fingerprints are LOCAL-ONLY** (`config['voice_prints']`) — biometric-adjacent data never goes
    to Supabase/analytics; only the derived `recognized` name-hit map syncs. The embedding is a numpy
    log-mel mean+std print (`app/voiceprint.py`), matched at ≥0.92 cosine with a 0.02 margin over the
    runner-up, and the whole step fails closed (any error → meeting pipeline proceeds unnamed).
    **Floating panels of this menubar app must opt OUT of Stage Manager and never activate the app**
    ("buttons are not working", Jul 2026): with Stage Manager on, the expanded meeting panel was swept
    into the side strip (full-size to x≈-4800, or as a tiny tilted thumbnail at the left edge) seconds
    after opening — the window "flies away" and every click looks dead. Three rules, all required:
    (1) collectionBehavior must include `.auxiliary` (1<<17) **and** `.canJoinAllApplications` (1<<18)
    (macOS 13+ Stage Manager opt-outs) — `Transient`/`Stationary` alone do NOT survive the panel
    becoming key; (2) never `activateIgnoringOtherApps` and never `makeKeyAndOrderFront` eagerly — use
    `orderFrontRegardless()` + `setBecomesKeyOnlyIfNeeded_(True)` (the recipe the recording widget and
    the bar always used; activation creates a Flume "stage" that gets parked on the next app switch);
    (3) any WKWebView inside an NSPanel must be a subclass overriding `acceptsFirstMouse:` → YES
    (registered once, Rule-#18 ObjC pattern) — stock WKWebView reports `needsPanelToBecomeKey`, so the
    first click coming from another app is swallowed by the key-transfer ceremony and buttons feel dead.
    Also: `setMovableByWindowBackground_` stays False on the expanded window (drag via titlebar region).
    **Verify bridge methods against the REAL API object, not a fake resolver:** `meeting_page_ready`
    shipped reading `self._dash` on a class whose attribute is `self.dashboard`; the AttributeError was
    swallowed by its `except` and the ready-handshake silently never fired in the real app (page stuck on
    its default `permissions` screen, all buffered `mode`/`meeting` events dropped). The headless harness
    missed it because it resolved bridge calls itself — unit-test handshakes through `DashboardApi`.
    "Skip for now" on the permission checklist persists `meetings_skipped_system_audio` and
    `_toggle_meeting` honors it (skip → pre-meeting modal, capture fails closed to mic-only) — without
    that, a mic TCC status of notDetermined re-showed the checklist on every open.
    **Never interpolate `JSON.stringify(x)` bare into a double-quoted onclick attribute** — the emitted
    double quotes terminate the attribute early and the handler silently becomes a syntax error (this,
    not just the missing handshake, is why clicking a meeting row "did nothing"). Wrap it:
    `onclick="fn(${esc(JSON.stringify(x))})"` — `esc()` turns the quotes into `&quot;`, which the HTML
    parser decodes back into valid JS. Verify by reading `el.getAttribute('onclick')` headlessly.
    **Never PATCH a jsonb list you didn't actually load.** `set_action_item_done` originally fell back
    to `[]` when the trimmed local row had no `action_items` key and wiped the cloud items. Rule: if the
    local copy is missing/empty, fetch the cloud value first, and skip the PATCH entirely when there is
    nothing real to write.
    The meeting window + dashboard Meetings list are skinned to the **widget kit v2**
    (MEETINGS_WIDGETS_HANDOFF.md): dot+label speaker chips (no pill fills), rows inside ONE parent card
    with `--bd-faint` dividers, glyph-only icon buttons (28px hit target, stroke 1.4), 9.5px/0.16em
    eyebrows, timer numerals 500-weight with negative tracking, waveform bars in text-primary (not
    accent), hybrid notes as dot rows with `↳` AI additions + Yours/Merged/AI underline tabs, action
    items as real persisted checkboxes (`set_action_item_done`). CSS escapes for glyphs in the
    non-raw `_CSS` string need DOUBLE backslashes (`\\2014`) — `\2014` is an octal escape in Python.

### Language rules (multilingual transcription)

- **Never hard-pin `language="en"` in a transcription call** — resolve through
  `transcriber.resolve_language(config, override)`. `auto` = omit the param.
- The dictionary glossary is an English Whisper *prompt* and drags language detection toward
  English — attach it only when the resolved language is `en`.
- Non-English pinned languages use full `whisper-large-v3` (not turbo) via the proxy.
- **Never ask the LLM to JUDGE the output language** — an English meeting once came back with a
  Russian summary because the prompt said "use the transcript's dominant language" and the model
  guessed. Python decides (`meetings._summary_output_language`: per-meeting pin > global pin >
  script-count detection > English) and the user message states it explicitly ("OUTPUT LANGUAGE:
  English. Every field must be written in English.").
- Meeting chunks that transcribe to a bare Whisper silence hallucination ("Thank you.", "you",
  "Bye.", …) are DROPPED before they enter the transcript (`_MEETING_HALLUCINATIONS`) — they pollute
  summaries and once helped trigger the wrong-language bug. Dictation is untouched (someone may
  really dictate "Thank you.").
- LLM prompts that consume transcripts must state their output language (summary: transcript's
  dominant language; dictation formatter/notes: same language, never translate).

### Keyboard hot-path rules (native IME, both platforms)

- **Never do heavy work synchronously inside a keystroke commit.** Per-keystroke disk
  reads/JSON parses, 25k-word dictionary scans, and IPC text queries jank the UI/main
  thread and drop fast taps. Cache config by file-mtime; DEBOUNCE suggestions (~70ms) off
  the commit; persist learning writes on a background thread.
- **Never rebuild the whole keyboard view tree during typing.** Shift / one-shot-shift /
  auto-cap changes must update key labels IN PLACE (`refreshLetterCaps` / live-cased key
  titles), not call `showKeyboard()` — a mid-type rebuild races the next tap's touch target
  and eats the letter (worst right after a space/sentence boundary). Reserve full rebuilds
  for actual layer switches (letters↔symbols↔numbers).

### Per-device sync (mobile)

- Sync is PER DEVICE via the cloud `devices.sync_enabled` column, not one global flag.
  `lib/deviceSync.ts` is the shared source of truth; THIS device's own row drives the local
  `verbal_sync_enabled` gate that `lib/useSync` reads. Show the devices sheet from the ROOT
  host (`DevicesSyncHost`), never from inside the Settings/Menu native-stack modal (JS
  `<Modal>` touches are unreliable there — the same reason `confirmSignOut` uses native Alert).

### Meeting-notes generation (both platforms)

- `MEETING_NOTES_SYSTEM` lives in **two places that must stay byte-for-byte in sync**:
  `whisperflow/app/meetings.py` (desktop) and `verbal-mobile/lib/groq.ts` (mobile). Edit one → mirror
  the other in the same change, and keep `max_tokens=4000` on both `generate_meeting_notes` /
  `generateMeetingNotes` (rich output needs the headroom; 2500 truncated tables/roadmaps).
- Notes run on **Ollama Cloud `gpt-oss:120b`** (`NOTES_MODEL`, mirrored in both files) via
  `provider:"ollama"` through the proxy, with an automatic **Groq `llama-3.3-70b` fallback** if Ollama
  is unset/slow/down — so notes always generate. To try another model swap `NOTES_MODEL` in BOTH files
  (`glm-4.6`, `qwen3:235b`); to go Groq-only drop the provider. Ollama timeout is longer (90s desktop).
- The prompt is **analyst-grade and proportional**: TL;DR + topic sections + Decisions + Action items
  + Open questions, and **Markdown TABLES are mandatory** whenever 3+ items share fields (costs,
  comparisons, schedules). Weaker models only reliably emit a table when the prompt carries a
  concrete table example — keep the worked `| Item | Cost | Notes |` example in the prompt.
- **Two markdown renderers must both understand every construct the prompt emits**, or new syntax
  shows as raw text: desktop `meeting_html.py::mdRender` (JS) and mobile
  `MeetingNotesScreen.tsx::MdView` (RN). Both now parse GitHub tables (header + `|---|` divider +
  body rows). `MdView` uses an **index loop, not `forEach`** — table rendering must look ahead and
  skip consumed rows. Truth discipline is unchanged: never invent numbers/names; compute only
  derived values the speakers implied; OUTPUT LANGUAGE is computed in code, never judged by the LLM.
- **`MdView` table columns must NOT be equal `flex:1`.** Desktop's `<table>` auto-sizes columns to
  content; RN has no equivalent, so equal-flex crushed asymmetric columns (e.g. a one-word
  "Duration" column next to a long "Notes" column) into an unreadable wrapped mess — this is what
  "tables don't format correctly on mobile" meant in practice, not a parse failure (parsing was
  already correct). Fixed by computing a per-column width from `max(header, body cells)` length
  (clamped 76–200px) and wrapping the table in a horizontal `ScrollView`. Any future table-style
  tweak must keep both the content-aware widths and the horizontal scroll — reverting to `flex:1`
  reintroduces the bug.

### Transform rules (TRANSFORM_SWARM.md)

- **Transform is a SEPARATE prompt/mode — never edit `ai_cleanup.SYSTEM_PROMPT`.** The formatter must
  keep ignoring instructions in speech; Transform only engages via its gate (Mode A) or hotkey (Mode B).
- The Mode A gate biases toward MISSING an instruction over stealing content: tight trigger set,
  ≥3-word body, and the instruction must start with an editing verb (`transform.INSTRUCTION_VERBS`).
- **Clipboard capture must save/restore in try/finally** (`transform.capture_selection`) — the user's
  clipboard always survives, selection or not.
- **Mode B must call `injector.save_focused_app()` at hotkey time** (`_on_transform_hotkey`, before
  `capture_selection`). Mode B never enters the dictation core, so it doesn't otherwise capture the target
  pid — and `inject_text`→`restore_focused_app()` (the Replace paste) re-activates
  `injector._previous_app_pid`. Without the save, that global is stale/None → Replace pastes into the wrong
  app or nowhere ("Replace does nothing"). The spoken instruction is **shown for review/edit, never
  auto-run** — landing in `heard` (populate `#pin` + `makeKeyWindow`) instead of firing the LLM; don't
  re-add an immediate `tf_prompt` after transcription.
- `transform_widget.py` joins the non-activating-panel family (cream pill, ScreenSaver level,
  becomesKeyOnlyIfNeeded, acceptsFirstMouse webview subclass). The spoken prompt is BLOCKED while a
  meeting holds the mic (one mic stream process-wide).
- **Borderless NSPanels refuse key-window status by default** — any panel with a TEXT INPUT needs a
  subclass overriding `canBecomeKeyWindow → YES` (transform pill: `_panel_class()`), or the field shows
  no caret and typing goes nowhere. Buttons alone don't need it (autolearn pill, `meeting_prompt.py`).
- The **meeting-detected pill** (`meeting_prompt.py`, Granola-style auto-detect) is the newest member of
  the non-activating-panel family — buttons only, so no key-window subclass. It must never steal focus
  from the Zoom/Meet window. Detection (`meeting_detect.py`) reads on-screen **window titles** via
  **`SCShareableContent`** (ScreenCaptureKit), NOT `CGWindowListCopyWindowInfo`: on macOS 14/15
  `kCGWindowName` is empty for every window except the frontmost even WITH Screen-Recording permission, so
  CGWindowList missed background meetings entirely ("not detecting" bug). SCShareableContent returns all
  window titles with the SR permission Flume already holds; CGWindowList stays only as a fallback. The
  scan can block ~1 s → run it OFF the main thread (main.py `_detect_meeting_tick` → bg thread →
  `_md_apply` on main). Keep heuristics conservative (in-call window, not just an open app) and fail
  closed — a detection error must never reach the capture path.
- The transform pill uses the same **ready-handshake** as the meeting window (`api('tf_ready')` +
  buffered emit) — without it the first open showed a BLANK pill, read as "mic/typing not working".
- `transcribe_with_status` success status is **'ok'** (not 'done'/'success') — compare against the
  real contract ('ok'/'silent'/'failed'); the transform pill's spoken prompt shipped checking 'done'
  and every perfect transcript fell into "Didn't catch that".
- Synthetic CGEvents route to the ACTIVE app, not the key window — E2E tests must use
  `CGEventPostToPid` to type into a nonactivating panel; real hardware keys follow the key window.
- Hotkeys are user-selectable in Settings → Hotkeys via `main.capture_next_key` (one-shot NSEvent
  monitors, real macOS keycodes — never JS `keyCode`, which is a different code space). While capturing,
  `_capturing_key` suppresses all hotkey handlers; dictation↔transform collisions are rejected.
- The pill's spoken prompt shows "Transcribing…" IMMEDIATELY on the stop-click and latches
  (`_transcribing`) — the silent gap otherwise reads as "mic not working" and double-clicks restart
  the recording.
- Transform hotkey = ⌘⇧T on keydown (`hotkey.py` handles it before, and separate from, the dictation
  keys). Config keys are config-only — no Supabase columns.

19. **A filtered realtime UPDATE subscription needs `REPLICA IDENTITY FULL` on the table.** Supabase
    Realtime evaluates a `postgres_changes` filter (e.g. `user_id=eq.<uid>`) against the WAL tuple; with
    the default (PK-only) replica identity an UPDATE's tuple lacks the filter column, so the event is
    silently dropped — **INSERTs still arrive, UPDATEs don't.** This is exactly why mobile live-meeting
    transcript "only refreshed after close+reopen" (fixed Jul 2026: `meetings` → `REPLICA IDENTITY FULL`).
    Any new table that mobile subscribes to for UPDATE streams must be `REPLICA IDENTITY FULL`. Belt-and-
    suspenders: a realtime-driven live view should ALSO poll (`MeetingLiveScreen` refetches every 3s while
    `isLiveNow`) so a dropped socket on mobile can't freeze it. Realtime is the fast path, not the only one.

20. **Desktop: any new Supabase REST/Realtime call site must use `app/auth.py`'s `auth_header()`/
    `get_access_token()`, never the raw `SUPABASE_KEY` anon key directly (MER-29, 2026-07).** `auth_header(cfg,
    json=False)` returns `Authorization: Bearer <access_token>` when signed in (refreshing via the stored
    `refresh_token` when near-expiry), else falls back to the anon key — safe to use unconditionally,
    including when signed out. For Phoenix Realtime `phx_join` payloads, also set `"access_token":
    get_access_token(cfg) or SUPABASE_KEY` (Realtime evaluates `postgres_changes` RLS off that field, not
    just the WS handshake header). **Exception: Storage object calls** (`recordings`/`meeting-audio`/
    `canvas-images` uploads, signed URLs) stay on the anon key — those bucket policies are `TO public` and
    don't discriminate by caller identity (MER-27). This exists because RLS on `notes`/`transcriptions`/
    `devices`/`canvas`/`dictionary`/`meetings` is *currently* still permissive (`USING (true)`) — seeded
    ahead of a real `auth.uid()` cutover so that flipping those policies later is a pure backend/SQL change,
    not also a client rollout. See `context/04-data-model.md` §Security posture's MER-29 note for exactly
    why that cutover (`whisperflow/supabase_auth_uid_rls.sql`, written + live-verified via a rolled-back
    transaction) hasn't been applied yet: device pairing (`app/pairing.py`/`pairing.ts::claimPairing`) lets
    a second device adopt a `user_id` **without ever getting a Supabase session**, so it structurally cannot
    satisfy `auth.uid()` under the current pairing design — this needs a product decision, not just an
    engineering rollout, before the migration can go live.

21. **Self-correction resolution (`ai_cleanup.SYSTEM_PROMPT` rule 18 / `groq.ts`'s SELF-CORRECTIONS
    block, MER-42/MER-43): a repair cue is never filler, and "and" only vetoes as list grammar.** Rule 18
    is judged BEFORE rule 7's filler-stripping — rule 7 used to list "I mean" as a filler to strip while
    rule 18 relied on that exact phrase as a repair cue, silently deleting the token the correction logic
    needed (MER-43 1.1). If you touch rule 7's filler list, never re-add a word rule 18 treats as a cue.
    Separately: "and" is listed as a list/enumeration veto (so "343 and 344" doesn't collapse), but "and"
    directly followed by a repair cue is the connector INTO the correction, not a second list item ("343
    and sorry 344" must still collapse to 344) — this exception must stay explicit in the prompt text, not
    just work by accident, or a future reword breaks it silently (MER-43 1.3). Desktop (`ai_cleanup.py`)
    and mobile (`groq.ts`) must encode identical logic here (cue families, the 4-part collapse test,
    anti-cues, content-type asymmetry, punctuation-invariance, directionality) — mobile shipped with real
    gaps vs. desktop in MER-42 (missing cue families, no words-without-cue asymmetry), closed in MER-43.
    Edit one → edit the other in the same change. Live eval: `whisperflow/self_correction_fixtures.py`
    (desktop pass over the real `SYSTEM_PROMPT` + `build_dictation_user_message()`, plus a mobile pass over
    a manually-synced copy of `groq.ts`'s prompt — see that file's own docstring).

22. **Context grounding is grounding DATA, never a directive (MER-44 Phase 0).** `ai_cleanup.build_context_block`
    (mirrored in `groq.ts::formatText`) prepends the user's known terms + active-app hint to the cleanup
    call. Two hard rules when editing it: (a) it must stay **fail-closed** — any error returns `""` (no
    context) and the cleanup path proceeds unchanged; the grounding block is prepended to the *user*
    message, never the `SYSTEM_PROMPT`. (b) It must NOT tell the model to collapse/correct more aggressively
    — it only lists terms the model should prefer spelling-wise. Adding "collapse when you see a known
    prefix"-style language would raise the identifier over-collapse rate that rule 18 deliberately keeps
    near zero; the `context_grounding_fixtures.py` harness asserts the block contains no "collapse"
    directive. Known terms come from `dictionary.known_terms()` (vocabulary + replacement `to`-targets), so
    auto-learned fixes ground the cleanup automatically — no extra plumbing. Gated by
    `context_grounding_enabled` (default on). Windows passes only the window *title* as the app hint (no
    bundle id); mobile passes no app hint at all (JS has no frontmost-app API) — known-terms grounding
    still applies on both. **MER-44 Phases 1–2 (fine-tuned model, flywheel, implicit correction) are NOT
    built** — gated on a serving-provider dependency + a plateau signal; do not start them without that.

## Design system (Flume)

Single source: desktop `app/theme.py` + `app/fonts_css.py`; mobile `flume-ui/theme/`. Also
`DESIGN_SYSTEM.md` at repo root.

- **Fonts:** **Geist** for all UI text; **JetBrains Mono** only for numerics + meta labels (timers,
  counts, UPPERCASE tags/eyebrows).
- **Base surface:** near-black (e.g. `#1a1512` / `rgba(22,20,18,…)`), light text `#f4f3f1`.
- **Accent:** `#C85A3E` (terracotta) — used sparingly. (Historic `#E8522A` is retired; Rule #16.)
- **Pastel stat-card palette** (dashboard "fcards", and the auto-learn widget matches `cream`):
  - `cream` `#EADFCE` (ink `#2a1f18`) — "Words today"
  - `sage` `#DDE4D3` (ink `#1e2418`)
  - `plum` `#e6dae4` (ink `#221820`)
  - each card's icon disc = the ink color inverted (near-black bg, pastel glyph).
- **Auto-learn widget** deliberately uses the `cream` card language (cream pill, dark ink, near-black
  "Add to dictionary" button) — not orange/black — per user preference.

## Dead / legacy / inconsistent code to IGNORE

**Desktop (`whisperflow/app/`):**
- `dashboard.py` (`DashboardWindow`, ~3178 lines) — legacy AppKit dashboard, only a fallback if
  `FlumeWebDashboard` fails to construct. Superseded by the WKWebView Flume dashboard.
- `meeting_hud.py` + `meeting_hud_html.py` — the original separate floating meeting HUD; **superseded** by
  the morphing bar layout of `meeting_window.py` (one panel: bar ⇄ expanded). Not wired anymore.
- `history_window.py` — legacy standalone AppKit history window; not referenced.
- `canvas_window.py` (`CanvasWindow`) — instantiated but menu routes to the web dashboard tab; effectively
  unused.
- `transcriber._transcribe_local` has an unreachable duplicate VAD `_run()` block after its `return`.
- `flume_dashboard_html.py` is **dual-target**: loaded into a WKWebView by `FlumeWebDashboard` on macOS
  and into a pywebview window by `SharedDashboard.show()` on Windows (its docstring is accurate again).
- `shared_dashboard._html()` (the old light-theme Windows dashboard) and `win_dashboard.py`
  (`WinDashboard`, tkinter) are **retired** — `_html()` is removed; `WinDashboard` remains only as a
  last-resort fallback if `import webview` fails. Windows renders the Flume UI.
- `whisperflow/WINDOWS_PARITY_PLAN.md` + `whisperflow/windows_specs/W3–W9*.md` are the **active** handoff
  specs for the remaining Windows-native workstreams (overlay/popover/injection/meetings/auto-learn/
  file-tagging/visual-QA) — not legacy; execute on a Windows dev session.
- ~~Three near-identical macOS specs (`verbal.spec`/`pico.spec`/`whisperflow.spec`) with drifting version
  strings~~ — **consolidated** (MER-33, 2026-07): `verbal.spec` and `pico.spec` are **retired/deleted**;
  `whisperflow.spec` is the one canonical macOS spec (it's what CI already built from —
  `.github/workflows/build-release.yml`; `build.sh`, the local dev build script, was pointed at
  `verbal.spec` and is now fixed to match). Its plist `CFBundleShortVersionString`/`CFBundleVersion` now
  import and read `config.APP_VERSION` directly (`sys.path.insert(0, '.')` + `from app.config import
  APP_VERSION`) instead of a separate hardcoded string — one number to bump, not three. **Whoever cuts a
  release must still make the git tag / `app_versions.version` match `config.APP_VERSION` at build time** —
  `updater.py` compares the DB row against the running app's `APP_VERSION`, and this fix only closes the
  spec-vs-config drift, not the tag-vs-config one; that's a release-process discipline, not something the
  spec file can enforce. `hiddenimports` reconciled against actual runtime usage: added `scipy`/
  `scipy.signal` (used by `recorder.py`/`transcriber.py`/`recordings.py`, was missing from `verbal`/
  `whisperflow`'s list — a real gap), `ScreenCaptureKit`/`CoreMedia` (meetings, Hard Rule #18's packaging
  note — was missing from ALL THREE specs, meaning every prior packaged build likely had broken meetings),
  and `websocket` (Realtime, defensive); removed `pyautogui` (that's `win_injector.py` — Windows-only, macOS
  injection is `Quartz`+`pyperclip`) and `groq` (no file imports it directly anymore — all Groq access is
  server-mediated via `groq-proxy`, Hard Rule #15).
- `ai_cleanup.apply_file_tags`/`FILE_TAG_PATTERNS` kept for reference/tests only — real tagging is in
  `filetags.py`.

**Mobile (`verbal-mobile/`):**
- `_old-flume/` (~27 files) — explicitly legacy.
- top-level `screens/` (empty) and `components/` (only `DeviceSelector.tsx`, imports legacy `lib/theme.ts`)
  — dead; live UI is under `flume-ui/`.
- `lib/useSync.ts` (superseded by `historyStore.ts`), `lib/useDeviceSelector.ts` (superseded by
  `flume-ui/hooks/useDevices.ts`), `lib/MarkdownText.tsx`, `lib/theme.ts` — not imported by live code.
  **Do not revive `lib/MarkdownText.tsx`** (it depends on stale `lib/theme.ts`); the live notes markdown/
  checklist renderer is `flume-ui/components/MarkdownNote.tsx` (Notes v2), styled off `flume-ui/theme/`.
- all `flume-ui/hooks/*.mock.ts` — contract references, never imported at runtime.
- `dist/` — stale web export.
- `flume-ui/components/ConfirmDialog.tsx` **is live** (imported directly by `useAuth`, `SettingsScreen`,
  `RootNavigator`) but intentionally **not** in the `components/index.ts` barrel.

## Verification checklist (run before considering a desktop change done)

```
cd whisperflow
.venv/bin/python -m py_compile app/<changed>.py
.venv/bin/python -c "import app.main"
# for dashboard/widget JS changes: node --check each rendered <script> block
.venv/bin/python autolearn_fixtures.py     # if autolearn touched
.venv/bin/python qa_filetags_fixtures.py    # if filetags touched
```

Mobile: `npx tsc --noEmit` in `verbal-mobile/`.

## Where the deep specs live

- `AUTOLEARN_DICTIONARY_SWARM.md` — the auto-learn feature spec (mission, algorithm, failure table, swarm).
- `FILE_TAGGING_SWARM.md` — the file-tagging feature spec.
- `GOOGLE_AUTH_SETUP.md` — auth provider setup facts (accurate table inventory).
- `DESIGN_SYSTEM.md` — design tokens.
