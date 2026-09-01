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
   `tempfile.mkstemp` name + `os.replace` under `_config_lock`, an RLock because `load_config` may
   save while holding it). Never share a temp filename across threads (a shared `config.tmp` caused a
   rename race). Cloud fetches write config **only when content changed** (avoids save churn) —
   `load_config` itself used to rewrite the file on every call, which on Windows collided with a
   reader and raised WinError 5 Access Denied (`os.replace` of an open destination). Reads take the
   same lock; `os.replace` retries a short backoff on PermissionError. `load_config` only saves when
   defaults/migrations actually mutated the dict, and (2026-08-28) that read → migrate → `save_config`
   sequence runs inside ONE `_config_lock` hold — releasing between the read and the persist let another
   thread's save land in the gap and be overwritten by the just-loaded copy (lost update at Windows
   startup). Callers that do their own load → mutate → save must wrap all three in `with
   config._config_lock:` for the same reason; `config_lock_fixtures.py` stress-tests this.
   **Windows hardening (2026-08-26 — user logs showed ~12 WinError 5s per session, each of which
   discarded the save and dropped auth to the anon key):** (a) both the read and the `os.replace`
   retry the Windows lock family only (`_is_lock_error`: WinError 5/32/33, `PermissionError`) with a
   `_RETRY_BACKOFF` of 20→320 ms; (b) if the rename still loses, `save_config` **falls back to an
   in-place write** (`_write_in_place`) after snapshotting the current file to `config.json.prev` —
   a handle that blocks a rename (no `FILE_SHARE_DELETE`) normally still allows writes, so the save
   is kept instead of lost; `load_config` restores from `.prev` if a crash left `config.json`
   truncated and deletes it once the file reads clean; (c) an **unreadable** `config.json` (exists,
   but locked for the whole retry window) is NOT corruption: `load_config` serves the last text this
   process read/wrote (`_last_good_json`) and, on a first load with no copy, runs on defaults but
   sets `_serving_unread_defaults`, which makes every later `save_config` raise `OSError` **without
   touching the file** until a `load_config` actually reads it — the old code moved the locked file
   to `.bak` and saved `DEFAULT_CONFIG` over it, i.e. an antivirus scan could sign the user out and
   drop their history; (d) a genuinely corrupt file (JSON *or* UTF-8 error — the read is bytes and
   the decode happens inside the corrupt-file handler, because a `UnicodeDecodeError` is a
   `ValueError` that used to escape and crash `VerbalWinApp.__init__` on every launch) goes aside via
   `os.replace(..., config.json.bak)` — `Path.rename` failed with WinError 183 whenever a previous
   `.bak` existed — then in-memory copy → `.prev` → factory reset, in that order; (e) defaults are
   `copy.deepcopy`'d (`DEFAULT_CONFIG` holds mutable lists); (f) orphaned `.config-*.tmp` files older
   than 60 s are swept (`_sweep_stale_tmps`, throttled to 10 min) — the `os._exit` quit path can leave
   one behind, and the temp file is now unlinked in a `finally` on every outcome.

4. **Main-thread discipline (macOS).** WKWebView and all AppKit UI must be touched on the main thread —
   route every background→UI hop through `main._on_main` / the `rumps.Timer` UI queue. Background threads
   never call WebView/AppKit directly.

5. **AX / Electron accessibility (file-tagging, auto-learn).** Cursor/Windsurf/VS Code/Antigravity/Kiro do
   NOT expose their web-content AX tree until you set **`AXManualAccessibility` + `AXEnhancedUserInterface`**
   on the app element; the tree builds **lazily** (needs a settle delay ~1.3 s), and the file-explorer rows
   sit ~depth 25 (walk depth ≤40). Do the deep harvest on a **background thread at record-start**, off the
   critical path. Always **exclude terminals and secure fields**; require the inserted text to be found in
   the field before trusting a read (Electron reads are flaky). See `electron-ax-file-tagging` memory.

6. **Groq prompt 896-char cap — and the bias prompt is a CONTINUATION prompt, so it must be scrubbed
   out of the result.** The Whisper bias prompt (dictionary glossary + open-file list) must stay under
   Groq's 896-char limit or every call 400s. `transcriber.py` trims to `_GROQ_PROMPT_CHAR_CAP=850` at a
   comma boundary, glossary first. The real caps are much tighter (`dictionary._MAX_PROMPT_TERMS=80`,
   `_MAX_PROMPT_CHARS=600`, keeping the **last** terms — Whisper only conditions on the prompt's ~224-token
   tail, and every extra term is another word it can sprinkle into an unrelated sentence).
   Whisper's `prompt` is **not an instruction** — the model is conditioned on it as if it were the
   transcript so far, so on quiet/short/speech-free audio it simply continues the list and the glossary
   comes back **as the transcription** (`"Glossary, M.T.:"` injected into the user's editor). Every
   transcription result therefore goes through `dictionary.strip_prompt_echo(text, prompt)` **before**
   replacements/tagging. It deletes (a) label-introduced runs, where the label is followed by terms we
   sent **or stands alone** — as its own fragment (`"Glossary. So, the thing is…"`, the model often drops
   the list and echoes just the heading) or, for a heading we *invented*
   (`_OWNED_LABELS` = glossary/vocabulary), on **any** punctuation — and (b) bare comma-lists of ≥2 terms
   we sent. That `_OWNED_LABELS` rule is the 2026-08 follow-up fix: the separator rules treated a comma as
   "the clause keeps going, so this is speech", but `"Glossary, <real speech>"` is exactly what Whisper
   emits most of the time, so the dominant form of the leak survived the original fix for weeks
   (`"Glossary, Right now,"` pasted into VS Code). Its cost is that a sentence genuinely opening with the
   word "glossary" loses it on a run where a glossary was sent — accepted, because that heading is our own
   invention. **`files` is deliberately NOT owned**: `"Files, I need to check them"` is real dictation.
   It never drops a lone dictionary word (that's the user saying a word they taught us) or a label that
   runs on inside its clause, and **only words actually sent as labels in that
   call count as labels** (`prompt_labels`) — with no file list in the prompt, "Files" is just a word.
   Returns `""` for an echo-only transcript — which the caller reports as **silent**, with no fallback to
   the other providers (they'd parrot the same prompt on the same audio). Mirrored in all four dictation
   front doors: `dictionary.py`, `lib/dictionary.ts` (`stripPromptEcho`), `KeyboardViewController.swift`,
   `FlumeInputMethodService.kt` — edit one, edit all four. Pinned by `prompt_echo_fixtures.py`.

7. **Fonts:** AppKit views use CoreText-registered faces (`theme.py`); **WKWebViews can't resolve those by
   name** → inline TTFs as base64 `@font-face` via `fonts_css.web_font_css()`.

8. **Non-activating panels:** the overlay + auto-learn widget use
   `NSWindowStyleMaskBorderless | NSNonactivatingPanelMask` at `NSScreenSaverWindowLevel` so they never
   steal key focus from the app being dictated into. Any new floating HUD must too — **and must carry the
   rest of the panel recipe**: the `meeting_window._webview_class()` `acceptsFirstMouse:` subclass, the
   Stage Manager opt-outs `.auxiliary` + `.canJoinAllApplications`, and a page-ready handshake before
   emitting into its WKWebView (Rules #18 and #25).

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
   **Notes v3 corollaries (2026-08):** (a) editing the ORIGINAL transcript persists via `save_note` with
   the **`no_cleanup` control field** — without it, a format-failed note (raw set, content empty) has
   exactly the initial-dictated shape and every raw keystroke's debounce save would fire a surprise LLM
   call. Control fields (`run_cleanup`/`no_cleanup`) are never stored or synced. (b) The named restyle
   prompts (`NOTES_STYLE_PROSE_RULES` / `NOTES_STYLE_TRANSCRIPT_PROMPT`) are mirrored between
   `whisperflow/app/ai_cleanup.py` and `verbal-mobile/lib/groq.ts` — edit one, edit both (same
   discipline as the notes/meeting prompts). Styles and `ask_notes` fire on explicit user action ONLY.
   (c) **A pin write never bumps `updated_at`** (desktop `set_note_pinned`, mobile `setPinned`): a pin is
   a preference, not an edit — bumping would reorder the recency lists and could mint a conflict pair;
   mobile's `toEntry` must carry the note's REAL `isPinned` (a hard-coded `false` clobbered other
   devices' pins in the cache — fixed in v3).

13. **Wipe account-scoped caches on sign-out / account switch (data isolation).** Mobile keys all data by
   `getUserId()`, but the id + local caches persist across sign-ins. If they aren't cleared, a *different*
   Google account signing in on the same device sees the previous account's history/notes/devices/vocabulary
   (a real cross-account leak that shipped). `useAuth.signOut` and `afterSignIn` (when the uid changed) must
   call `clearAccountData()` (`lib/storage.ts` — removes `verbal_user_id`, `verbal_history`, `verbal_pinned`,
   `verbal_notes_cache`, `flume_dictionary`, `flume_target_device`) **and** `historyStore.reset()` (drops the
   items singleton + the realtime channel keyed by the old id). Any new per-account cache/singleton must be
   added to that teardown. Device-level config (Groq key, device name, feature-flag prefs) is preserved.
   `signOut` uses `supabase.auth.signOut({ scope: 'local' })` so it can't hang on the network.

14. **Mobile `confirm()`/`notify()` are native-`Alert`-backed on iOS (since 2026-08-27); the JS
   `ConfirmDialog` only renders on Android/web.** History: `ConfirmHost` renders a JS `<Modal>` from the
   root, and on iOS a JS modal shown over a native-stack `presentation:'modal'` screen (**Settings,
   Devices, Snippets, Team**) never appears, so every confirm there was a dead tap — first seen as the
   Sign-out button "doing nothing", then re-found on the simulator with Settings → "Replay onboarding".
   Team's Remove/Leave had the same bug while its comment claimed otherwise. Rather than each screen
   remembering to import `Alert`, `confirm()` itself routes to `Alert.alert` on iOS, so callers stay
   uniform. Don't add a JS `<Modal>` dialog to a Menu-modal screen.

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
   `openai/gpt-oss-120b` so notes never fail (`meetings.generate_meeting_notes`, `lib/groq.ts::generateMeetingNotes`).
   Set/rotate via `supabase secrets set OLLAMA_API_KEY=…` (key from ollama.com/settings/keys). The earlier
   `app_config` **provider-secret-key-table** idea is correctly **SUPERSEDED** (a client must never be able
   to read `GROQ_API_KEY` itself). The whole mobile client-key resolution chain
   (`storage.ts::getGroqKey`/`setGroqKey` → `lib/remoteConfig.ts` → `app_config` table) was **removed in
   IDI-160 (2026-08)**: the table never existed in the live schema, so the empty-key gate falsely failed
   every in-app dictation/retry/note-cleanup while `lib/groq.ts` ignored the key anyway. The proxy is the
   sole authority; the `_apiKey` params on `transcribeAudio`/`formatText`/`formatNoteWithTitle`/
   `formatNotes` are now optional and ignored. Only DESKTOP keeps a local-key fallback path for
   resilience (proxy always tried first) — the iOS keyboard has none (an earlier claim here that it did
   was wrong; it holds only the anon key + proxy, and since IDI-161 sends `x-flume-device` like Android). **Groq returns HTTP 413 (not 429) when a request would
   exceed the shared key's tokens-per-minute budget** — this shows up on long meetings, since the summary
   prompt can carry up to `TRANSCRIPT_CHAR_BUDGET` (24,000) chars. `groq_proxy.chat_via_proxy` raises
   `ProxyPayloadTooLarge` on 413 instead of swallowing it; `meetings.generate_meeting_summary` catches it
   and retries with a halved transcript budget (up to 3 attempts total) rather than repeating the identical
   oversized request.
16. **Keyboard data bridge is App-Group–gated on iOS.** The app hands the keyboard its config
    (`flume_kbd_config.json`: theme, vocabulary, replacements, snippets, recent history, deviceId,
    `spokenLanguage`, feature toggles) via a JSON snapshot written by
    `lib/keyboardBridge.ts::syncKeyboardConfig()`. Since IDI-161/162 BOTH natives consume `replacements`,
    `deviceId` (→ `x-flume-device`) and `spokenLanguage` ('auto' → omit the Whisper param); two keys remain
    write-only (`theme`, `schemaVersion` — natives hardcode/never validate, tracked in IDI-179/180).
    **Two hard-won rules from the flow-audit batch:** (a) never cache a FAILED config parse against the
    file's mtime — Android did, and one malformed write silently killed dictation until the next mtime
    change; a null config must FAIL OPEN (raw transcript committed, stages skipped). (b) Anything a
    keyboard commits **asynchronously** into the host must pass the **field-identity guard** (IDI-163):
    input-session counter captured at start + fresh secure-field re-check at insert time + ≤90s age —
    otherwise a slow transcription lands in whatever field (incl. passwords) the user focused meanwhile. On **Android** the IME reads `context.filesDir`, which is
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
    permission check on a background thread — main-thread work froze every first click. The meeting detail
    view scrolls as ONE page (expanded sections grow into the page) — inner-only scroll containers were
    unusable in small windows. Since MER-46 it lives inside the dashboard's `.main`, which owns the scroll
    container, so its header is static there: a `position:sticky` header inside a *padded* scrollport leaves
    content visible above it.
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
    The meeting window uses a dedicated JS namespace (`VerbalMeeting`; the HUD's `VerbalMeetingHud` died with `meeting_hud.py`, IDI-179) — never emit
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
- Meeting chunks that look like ASR garbage are DROPPED before they enter the transcript
  (`meetings.is_meeting_hallucination`): exact silence phrases ("Thank you.", "you", "Bye.",
  …), token/phrase repetition loops, dense `name.ext` filename soup, and `sql`/`supabase`
  spam. They pollute summaries and once helped trigger the wrong-language bug. Dictation is
  untouched (someone may really dictate "Thank you.").
- **Meetings never file-tag.** `transcribe_with_status(..., filetags=False)` skips IDE harvest,
  the Whisper `Files:` bias fragment, and `@name.ext` rewrite. The meeting panel is
  non-activating so Cursor/VS Code often stays focused; enabling filetags there turned quiet
  chunks into filename loops. Dictionary glossary bias still applies on English meetings.
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

### Meeting speaker labels (desktop)

- **Two speakers, period (2026-08-28).** `self` = the signed-in user's name, `s1` = "Them" (`THEM_LABEL`).
  Do not reintroduce "Speaker N" guesses, gap heuristics, or the VERIFIED/ESTIMATED tag; if per-person
  names ever come back it must be from a source that knows them (meeting-platform bot/SDK, calendar),
  not from audio. The rules below describe the retired diarization code, which must stay green in
  `diarize_fixtures.py` while it exists but no longer runs in the end flow.
- **(retired) Speaker ids are labelled per TURN, not per Groq chunk.** `split_utterances_by_turns()` runs before
  `map_diarized_speakers()` in `MeetingSession._diarize()`. Any change to either must keep
  `diarize_fixtures.py` green (32 cases, incl. the "interjecting third voice survives" case — the bug
  that made 3 people show as 2). Keep both functions pure/total: no I/O, never raise.
- **`words` never leave the session.** Utterance `words` (per-word timestamps) are a diarization aid;
  every persisted/synced/emitted transcript copy goes through `_public_transcript()` (or strips the key
  inline, as the live `utterance` event does). Do not add a new code path that writes `self.transcript`
  out raw.
- **Only placeholder labels are auto-renamed.** Transcript-derived `speaker_names` and voiceprint hits
  may replace "Speaker N" only; a name the user typed always wins (`apply_speaker_names` checks the
  current label, `voiceprint.learn_speaker` rejects `_DEFAULT_NAME`). A wrong name is worse than a
  placeholder, so `_parse_summary_json` validates hard (real `s<N>` id, 1–2 alphabetic words, unique).
- **(retired) Never present an estimated split as fact.** `speakers_source` used to drive the SPEAKERS VERIFIED /
  ESTIMATED tag (removed 2026-08-28 on both platforms; column still written as `estimated`).
- Self-cluster exclusion threshold is `SELF_CLUSTER_SHARE = 0.7` — a bare plurality silently deleted
  remote participants who talked over the user. Don't lower it without a fixture that shows why.

### Meeting-notes generation (both platforms)

- `MEETING_NOTES_SYSTEM` lives in **two places that must stay byte-for-byte in sync**:
  `whisperflow/app/meetings.py` (desktop) and `verbal-mobile/lib/groq.ts` (mobile). Edit one → mirror
  the other in the same change, and keep `max_tokens=4000` on both `generate_meeting_notes` /
  `generateMeetingNotes` (rich output needs the headroom; 2500 truncated tables/roadmaps).
- Notes run on **Ollama Cloud `gpt-oss:120b`** (`NOTES_MODEL`, mirrored in both files) via
  `provider:"ollama"` through the proxy, with an automatic **Groq `openai/gpt-oss-120b` fallback** if Ollama
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

23. **Dashboard scroll (`flume_dashboard_html.py`): the scroller is the per-screen `.main`, and its height
    chain must stay pinned.** `body{overflow:hidden}` (intentional — body never scrolls); each visible
    `section.screen` fills the grid, and `.main{height:100%;overflow-y:auto}` is the actual scroller. This
    only works if the chain resolves to the viewport: `.app` sets `grid-template-rows:100vh`, `.screen`
    sets `height:100%;min-height:0`, and `.main` sets `min-height:0`. If you drop the pinned row / screen
    height, WebKit can size the auto grid row to content, `.main` never engages `overflow-y`, and
    everything past the fold is clipped by `body{overflow:hidden}` — the "can't scroll after the meetings
    section" bug (Jul 2026). Also keep `overscroll-behavior:contain` on `.main` (kills the rubber-band
    "resistance" at the scroll boundary in the WKWebView).
    **Second cause of the same symptom (Aug 2026): a `renderSettings()` loop.** `renderSettings()` ends in
    `loadMeetSettings()`, whose `get_spoken_language` callback used to call `renderSettings()`
    unconditionally — render → load → callback → render, forever, rebuilding `settingsMain.innerHTML` every
    bridge round-trip. Each rebuild collapses the async Meetings/Transform sections to short "Loading…"
    stubs, so the scroll height shrinks and the `scrollTop` restore clamps back to ~the Meetings section
    (flicker + "pulled back up"). Two invariants: (a) **a settings sub-load must not re-render at all when
    its data is static** — the language list is fetched ONCE behind a `LANGS_LOADED` guard (reset to
    `false` on failure so a retry can happen) and thereafter patched into the live `<select>` by
    `patchSpokenLangSelect()`; a callback that does need to re-render must do so only on a real change;
    (b) `renderSettings()` synchronously refills the async sections from cache
    (`renderMeetSettings()`/`renderTfSettings()`/`fillHotkeyLabels()`) *before* restoring `scrollTop`, so
    the height is full-size when the restore happens. Both halves are required — (a) alone still flickers
    on the first paint, (b) alone still loops. (The Mac and Windows sessions each hit this and fixed it
    independently; the merge kept the fetch-once form of (a).)

24. **A dead refresh token must fall back to the anon key, never send an expired JWT (`auth.py`).** When
    `_refresh_access_token` gets a 400/401/403 from the token endpoint (invalid_grant /
    `refresh_token_not_found` — the session is unrecoverable), it MUST return `None` (so `auth_header`
    uses the anon key, which works under the current `USING (true)` RLS) and drop the dead tokens, NOT
    return the stale `access_token`. The old code returned the expired token, so every authed REST read
    401'd silently — which manifested as **"can't open meeting notes"** (`get_meeting`'s cloud fetch 401'd
    → fell back to local metadata that has no `notes_md`/`transcript` → notes regeneration failed), an
    empty device list, and dead dictionary sync. A module-level `_dead_session` flag short-circuits further
    refresh attempts within the process, and since IDI-166 it is ALSO persisted to
    `config['auth']['session_dead']` (local config only, no Supabase column) so the state survives restart:
    `auth.session_dead(cfg)` is the accessor, `get_state` exposes it, and the dashboard renders a
    "Session expired — sign in again" banner (sidebar + Settings); `delete_account` returns that actionable
    message instead of "Not signed in". A fresh `_store_session` resets it. This is safe only because RLS
    is still permissive — when RLS tightens to `auth.uid()`, a dead session must instead force
    re-authentication. NOTE the asymmetry (IDI-170): a DEAD SESSION keeps `sync_user_id` (anon fallback
    keeps working, per this rule), but an explicit SIGN-OUT clears `sync_user_id`/`sync_enabled` and
    deletes this device's `devices` row — post-sign-out, `auth.cloud_allowed()` gates every cloud path,
    and desktop now also has the mobile-style uid-change cache wipe (`auth._clear_account_caches`, which
    covers `voice_prints` + `meetings_opened` too).

26. **Sign-in is REQUIRED, and auth UI renders from state — never latch a button on an optimistic ok
    (IDI-166).** The first-run "Later"/anonymous path was removed; the dashboard's sign-in wall is the only
    entry. **macOS enforces it as of IDI-183** — `_on_record_start` refuses while signed out (the one choke
    point all three start paths reach) and the menubar menu disables every account row; the old "hotkey
    dictation still works signed-out but is not advertised" carve-out is GONE. Windows still has it.
    Both gates fail closed: an auth error is treated as signed out. The `#signin` pane renders from
    `get_state` (`auth_error` field, cleared on retry/success) via `applyAuthGate`/`renderSignin` — the
    OAuth flow returns an optimistic `_ok()` immediately, so any failure must be pushed back as state, and
    `auth.cancel_sign_in()` frees the loopback port so a retry can bind.

27. **Desktop pressed-state + double-fire discipline (IDI-167/168).** `app/shared_css.py::pressed_css()`
    is the single source of the canonical pressed rule (`transform: scale(0.97)` + `filter:
    brightness(0.92)`, 60ms ease) — every new surface must inject it AFTER its own CSS (so it beats hover
    rules that set `filter`). Row containers, dropzones and drag targets are deliberately excluded (a 3%
    scale on a full-width row reads as a jolt). Mutating dashboard actions go through the `busyGuard(el,
    thunk)` helper (takes a THUNK so the second click never even creates the call). Mobile's equivalent
    token is `flume-ui/theme/press.ts` (`PRESSED_OPACITY = 0.85`, `pressedStyle`) — all five shared
    components and every screen Pressable consume it; invisible backdrop scrims/tap-swallowers are the
    only exempt Pressables (commented in place). **Every vertical ScrollView must be flex-bounded**
    (`style={{flex:1}}`, or `flexShrink:1` inside a `maxHeight` sheet): an unbounded ScrollView with
    header siblings sizes to its content and gets clipped by the screen — it *looks* scrollable (overscroll
    glow/"resistance") but the bottom is unreachable. Bit SettingsScreen the moment it grew past one
    viewport (2026-08); all 11 screen ScrollViews were bounded in the same fix.

28. **The B4/B5 sync architecture (flow-audit waves 1-3, 2026-08) — the rules that keep it coherent:**
    - **One sync flag.** `lib/syncStore.ts` (`verbal_sync_enabled`) is the only source; Menu/Settings/
      Devices/DevicesSyncSheet all render `useSyncEnabled()`. The toggle is LIVE (ON → catch-up + channel
      join; OFF → `disconnect()`, channels closed, local data untouched) and it gates
      **history/notes/canvas/dictionary**; meetings edits + recording uploads gate on being signed in only
      (`auth.cloud_allowed` on desktop, `getCloudUserId()` on mobile — which never mints a guest id).
    - **Singleton stores.** history/canvas/meetings/notes/devices are module-level stores
      (subscribe/getSnapshot + `reset()` on account teardown + `catchUp()` on foreground/reconnect +
      channel rejoin with capped backoff). `useAuth`'s teardown calls every store's `reset()`; the
      AppState catch-up lives in `flume-ui/hooks/syncLifecycle.ts` (NOT in `lib/supabase.ts`, whose
      AppState listener is auth-only). One realtime channel per domain — `lib/meetings.ts` multiplexes its
      single channel to N listeners.
    - **Suppress your own realtime echoes.** A store that writes a row WILL receive its own echo; unmuted,
      `mergeRemoteNote` minted a FALSE conflict pair whenever the user typed within the 60s window, and a
      meetings refetch clobbered in-flight text. Track last-written signatures and skip matching echoes;
      never overwrite a field with a pending local edit.
    - **Tombstones, never DELETE.** `notes.deleted_at` + `transcriptions.deleted_at`: delete = UPDATE with
      content cleared; merges treat a tombstone as unconditionally authoritative; back-fills skip anything
      not `source:'local'`. A tombstone is an UPDATE — it never moves `created_at`, so reconnect backfills
      need the separate `deleted_at`-keyed sweep (`sync.py`).
    - **CAS on `updated_at`** for shared-row writes (`dictionary`, `meetings`): write filtered on the last
      witnessed `updated_at`; 0 rows = conflict → refetch (+ merge-and-retry-once for dictionary; freeze-
      and-offer-Reload for meeting notes). Never blind-update, and always `.eq('user_id', …)`.
    - **Canvas writes** stamp `device_id`+`device_name`, OMIT columns they aren't changing (a text edit
      must never null the image), and a clear is an EXPLICIT `{content:'', image_url:null}` write that
      receivers apply (no falsy-drops). Own-event filtering is by `device_id` (name only for old rows).
    - **Device identity is a per-install uuid** — desktop `config.get_device_id()` (`device_uuid`), mobile
      `storage.getDeviceId()` (`verbal_device_uuid`, deliberately NOT wiped by `clearAccountData`). Never
      derive identity from hostname/deviceName/user id. The per-device sync switch is SELF-only.
    - **Fixture harnesses for this area:** `whisperflow/idi170_171_fixtures.py` +
      `idi172_174_fixtures.py` — run them for any auth/sync/canvas/dictionary-sync change
      (+ `idi178_fixtures.py` for the ESC-cancel ordering).
    - **Two mobile gotchas (IDI-180):** `lib/groq.ts` ↔ `lib/keyboardBridge.ts` is a cycle waiting to
      happen — keyboardBridge statically imports from groq, so groq must reach keyboardBridge only via
      dynamic `import()` (the `setSpokenLanguage` pattern). And `documentDirectory/recordings/` is SHARED
      by dictation audio and note audio segments — any cleanup must consult BOTH `storage.getHistory()`
      and `notesStorage.getCachedNotes()` for referenced files (see `recordings.sweep`, fail-closed).

25. **The recording overlay's Cancel button must go through `main._on_esc_pressed`, never
    `_cancel_recording` (IDI-165).** `_cancel_recording` only stops the *recorder*; it never sets
    `_cancel_flag` — so clicking Cancel on the *Transcribing* pill let the in-flight transcription finish
    and still paste into the focused app. `_on_esc_pressed` sets the flag, and **since IDI-178
    `_reset_to_ready` no longer clears it** — the clear lives at RECORDING START (both platforms), so the
    flag reliably means "this dictation was canceled" for the whole cycle and the old race (reset draining
    before the worker's `is_set()` check → cancel lost) is closed; proven by `idi178_fixtures.py`.
    `overlay.overlay_cancel` delegates to `_on_esc_pressed` (safe off the main thread — it hops itself).
    Rule: ESC and the Cancel button must stay literally the same code path. The same ticket established three more overlay rules:
    - **Failures get their own pill.** `overlay.update_status(status, error=True)` renders `mode:'error'`
      — danger red `#E05049`, a `!` disc, **no ✓ and no "Copy again"** (that CTA re-copied the *previous*
      dictation's text). `main.py` passes the flag explicitly at the `silent` / `failed` call sites; the
      `_ERROR_HINTS` string sniff in `overlay.py` is only a backstop.
    - **Pause must be reflected in the UI.** `overlay_pause` pushes `mode:'paused'` with the recorder's
      new state; the page flips the pause↔play glyph and **freezes** the JS elapsed timer (audio stops
      accruing, so a ticking clock drifts from the real recording length). Both glyphs live in the DOM
      and are toggled by `display` so the JS never embeds SVG markup (keeps backslashes out of the
      non-raw `_js()` string).
    - **Ready handshake, like `meeting_window`/`transform_widget`.** The overlay page calls
      `api('overlay_ready')`; emits made before that are buffered (bounded at 20) and flushed — without
      it, record-at-launch showed **no pill at all**. A 3 s timer un-blocks the buffer if the page never
      reports ready, so the overlay fails open.
    The overlay panel and the auto-learn widget now also carry the full Rule-#18 panel recipe: the
    `_webview_class()` `acceptsFirstMouse:` subclass (imported from `meeting_window`) plus the Stage
    Manager opt-outs `.auxiliary (1<<17)` + `.canJoinAllApplications (1<<18)`. Stock `WKWebView` swallowed
    the first click on both surfaces.

29. **Windows log streams must be forced to UTF-8 — our log messages are full of non-ASCII.** Windows
    defaults `sys.stdout`/`sys.stderr` and `logging.FileHandler` to **cp1252**, which cannot encode the
    em dashes, `→`, `✓` and `…` used in log strings across `sync.py`, `transcriber.py`, `recorder.py`,
    `meetings.py`, `auth.py`, `theme.py` and `win_main.py` (12 files). `logging` swallows handler
    exceptions, so the affected line is **silently dropped** and replaced by a `UnicodeEncodeError`
    traceback — including on the dictation path (`win_main.py` "No speech detected —", `transcriber.py`
    "VAD filtered everything —"), which makes a real Windows debugging session unreadable. `win_main.py`
    therefore (a) `reconfigure(encoding="utf-8", errors="replace")`s both streams immediately after the
    PyInstaller `None`-stream guard, and (b) passes `encoding="utf-8"` to `FileHandler`. Fix the streams,
    never the log strings. macOS is UTF-8 by default and was never affected.

30. **`requirements-win.txt` pins numpy and scipy as a matched pair.** The Windows target is **Python
    3.11**; scipy 1.18+ requires 3.12+, and scipy 1.15+ requires numpy 2. Verified working set:
    **Python 3.11.9 + numpy 1.26.4 + scipy 1.14.1**. Before bumping either, check the Python floor —
    the previous pins (`numpy==1.24.3` + `scipy==1.18.0`) were unsatisfiable on *every* Python version
    (1.24.3 has no wheels past 3.11, scipy 1.18 needs 3.12+), so `pip install -r requirements-win.txt`
    failed outright and Windows setup was blocked. Also note `requirements.txt` is **macOS-only** — it
    omits scipy (imported by `recorder.py`, `transcriber.py`, `recordings.py`) and carries `rumps`/pyobjc
    behind `sys_platform == 'darwin'` markers. On Windows always use `requirements-win.txt`.
    **A LAZY import still needs declaring — in requirements AND the PyInstaller specs.** `qrcode` (used
    only inside `app/pairing.py::qr_svg`) was missing from *both* requirements files and *both* specs for
    months: nothing failed until someone opened "Pair a device" on a machine that didn't happen to have it,
    which then read as "pairing is broken" (`No module named qrcode`). It works on a dev Mac purely because
    it was pip-installed there ad hoc. When adding a function-level import of a third-party package, add it
    to `requirements.txt`, `requirements-win.txt`, and the `hiddenimports` list in `verbal-win.spec` /
    `whisperflow.spec` — bytecode analysis of a lazy import is not something to rely on for a frozen build.
    Audit with `importlib.util.find_spec` over every import in `app/` (find_spec, not import — it doesn't
    execute module side effects). Known-and-fine absences on Windows: `faster_whisper` (optional offline
    transcription, guarded at `transcriber.py:358` — but note `verbal-win.spec` lists it in
    `hiddenimports`, so the BUILD env does need it), `win10toast` (undeclared *second* fallback in
    `_notify_native`; `winotify` is primary and installed), and the pyobjc/AppKit family (macOS-only).
    **A spec `hiddenimports` entry does NOT guarantee the module ships** — PyInstaller silently skips
    hiddenimports that aren't installed in the build env. Fourth confirmed instance of this bug class
    (2026-08-31): `ScreenCaptureKit` was in `whisperflow.spec` hiddenimports but
    `pyobjc-framework-ScreenCaptureKit` was only in `requirements.lock.txt`, and CI's mac jobs
    (`build-release.yml` / `build-mac-app.yml`) install `requirements.txt` — so released 1.0.44
    shipped without it, `system_audio.is_supported()` returned False, and every meeting captured
    **mic-only** ("self" chunks only, no "Them") with no warning; dev-venv runs worked fine. Now
    declared in `requirements.txt` behind the darwin marker, and `meetings.py` logs a WARNING
    ("system audio unsupported … recording mic-only") on the previously-silent `is_supported()`-False
    skip.

31. **Windows: declare DPI awareness at import, and scale every tkinter/PIL surface by it.** The app
    runs **DPI-aware** — pywebview flips the process to per-monitor awareness when WebView2 builds its
    first window — so tkinter geometry and PIL drawing are in **real device pixels**. Any surface using
    96-DPI pixel constants renders at **half** size on a 200% display (a third at 300%). Two halves to
    the rule:
    - `win_main.py` calls `SetProcessDpiAwarenessContext(-4)` (PER_MONITOR_AWARE_V2, falling back to
      `SetProcessDpiAwareness(2)` then `SetProcessDPIAware()`) **before any window exists**. Without
      this, awareness flipped *after* the overlay had already sized itself from a 96-DPI reading, so the
      result depended on startup ordering.
    - `win_overlay.py` keeps its 96-DPI numbers in `_DESIGN` and calls `_apply_scale(dpi/96)` at setup,
      with `_s()` / `_i()` for inline offsets and stroke widths. `_probe_scale()` returns 1.0 when the
      process is DPI-unaware, so it never double-scales. Verify with the startup line
      `overlay: dpi scale=2.00 pill=940x88`.
    **Still unscaled (known gap):** `win_autolearn_widget.py`, `win_meeting_hud.py`,
    `win_transform_widget.py` all use fixed-pixel geometry with no scale factor and will render at half
    size on a scaled display. Give them the same `_DESIGN` / `_apply_scale` treatment when touched.

32. **Windows overlay position must be recomputed on every show, from the WORK AREA.** `win_overlay`
    computed `y` once in `_run_tk` from `winfo_screenheight()`, so any later resolution change (VM/RDP
    auto-fit, docking, display swap) stranded the pill mid-screen, and using full screen height rather
    than the work area put it behind the taskbar. `_reposition()` now runs from both `_run_tk` and
    `_show_internal`, using `SystemParametersInfoW(SPI_GETWORKAREA)` with a `winfo_*` fallback.

33. **Don't use PIL `rounded_rectangle` for thin shapes (Pillow 10).** It derives its own inner radius
    and builds `(y0 + r + 1 .. y1 - r - 1)`, which inverts and raises
    `ValueError: y1 must be greater than or equal to y0` for a band of short boxes — 3.5-4.4px tall fail
    while 3.0 and 4.4 pass, so it is **not monotonic** and clamping the radius you pass does not avoid
    it. The overlay's waveform bars hit this on ~2.6% of animation frames, and because `_render` wraps
    the whole repaint in one try/except, a single bad bar dropped the entire pill frame. Use
    `draw.rectangle` when a shape is only a few pixels across — corner rounding is invisible there.

34. **"Online" must mean online, and device rows are NEVER auto-pruned.** Two halves, both learned from a
    test account that had accumulated 16 `devices` rows (14 identically-named dead "iPhone"s):
    - **Presence is tight, not generous.** `sync.PRESENCE_ONLINE_SEC = 120` against a 60 s heartbeat — one
      missed beat of tolerance. The old 300 s let a device that vanished four minutes ago read "Online",
      which makes the whole indicator untrustworthy. Any UI that says "online now" must use this window,
      and must show a relative `last_seen` for anything offline so staleness is visible rather than implied.
    - **Pruning is manual, always.** A phone that is switched off is *offline, not gone* — auto-deleting
      its row would make it silently disappear and force a re-pair. Cleanup is an explicit, confirmed user
      action (`remove_offline_devices`). Fix the *cause* of row growth instead: identity must survive
      reinstall (mobile keeps `verbal_device_uuid` in the Keychain, not just AsyncStorage — see
      `04-data-model` §`devices`). Never add a TTL sweep to this table.

35. **The recording pill's waveform is REAL audio, and its shaping lives in the recorder.** The bars used
    to be a CSS keyframe loop (Mac) / a sine over `_phase` (Windows) — they animated identically whether
    you were shouting or silent, which made the pill read as decorative rather than as feedback.
    - **One meter, one curve.** `recorder.Recorder` computes the level inside `_audio_callback`: block
      peak → dBFS → mapped from `LEVEL_FLOOR_DB=-55` … `LEVEL_CEIL_DB=-12` onto 0..1, `** LEVEL_GAMMA`
      (1.5, so room tone stays flat), then asymmetric smoothing (`LEVEL_ATTACK=.55` / `LEVEL_RELEASE=.12`
      — snap up on a syllable, ease down between words). `recorder.level` returns **0.0 when not
      recording or paused**. Both platforms render that one number as-is; never re-shape it per-UI, or the
      two waveforms drift apart. It's computed **outside** the buffer lock and wrapped in `try/except` —
      metering is cosmetic and must never break capture. This works for meeting-mode dictation too
      (`feed_external` goes through the same callback).
    - **Mac: Python pushes, the page interpolates.** `overlay.py` runs a daemon pump at `LEVEL_HZ=15`
      that hops to main (WKWebView discipline, Rule #18) and calls `window.VerbalWave(level)`. The pump is
      started in `show()` and stopped in `update_status`/`show_briefly`/`hide`/`cleanup`. It carries
      **backpressure** (`_level_inflight`): a stalled main thread can never accumulate a queue of stale
      level evals. The page keeps its own 30 fps `requestAnimationFrame` scroll (13-slot history, newest
      at the right) so it stays smooth *between* pushes.
    - **Fail-open, both platforms.** If no level arrives for ~0.9 s the page re-adds `.wave.idle` and the
      old keyframe animation takes back over (and the inline heights we set are cleared, so the keyframes
      own the bars again); `win_overlay` falls back to the sine whenever its level history is empty. A
      broken meter degrades to the old decoration, never to a blank pill.

36. **The macOS menubar is an `NSMenu`, and the rules for living inside one are not obvious** (IDI-183,
    `menubar_menu.py`). The old `NSPopover` was replaced because a menu inherits light/dark, the user's
    accent colour, Increase Contrast, Reduce Transparency and keyboard navigation, while a WKWebView panel
    has to re-implement each one and then drift. Five things bite:
    - **Rebuild on open; never push state in.** `MenuController.menuNeedsUpdate:` is the only place that
      refreshes titles, checkmarks and the Recent/Canvas submenus. The popover needed
      `popover._refresh()` at six call sites in `main.py` precisely because a webview can't read app
      state; a menu can, so those calls are gone. Don't reintroduce a push path.
    - **A timer must be registered in `NSEventTrackingRunLoopMode` too.** While a menu is open AppKit runs
      that mode, so a timer added only to `NSDefaultRunLoopMode` never fires — the header's waveform would
      freeze the instant you opened the menu it lives in. `_HeaderView.startAnim` adds it to both, and
      only between `menuWillOpen:`/`menuDidClose:`.
    - **`setEnabled_` does NOTHING until you turn off auto-enabling.** `NSMenu.autoenablesItems` defaults
      to YES, so AppKit re-derives every item's enabled state at display time from target/action
      validation. Our items all target rumps' `NSApp` with a live `callback:` action, so AppKit re-ENABLES
      them and any manual gate silently evaporates — it looked correct in a unit test (which never runs a
      display pass) and did nothing in the real menu. `MenuController.attach()` calls
      `setAutoenablesItems_(False)`; from then on enabled state is ours to manage. This is what the
      sign-in gate and the signed-out sync row depend on.
    - **Menu item targets are held WEAKLY.** The dynamically built Recent/Canvas rows target the
      controller and carry their payload in `representedObject`; `MenuController._keepalive` holds the
      submenus so nothing is collected between rebuilds.
    - **A view-backed item draws its own highlight, and a parent item with a submenu never fires its own
      action.** The header is therefore `setEnabled_(False)` (passive, nothing to highlight), and Sync is
      a plain checkmark row rather than the checkmark-plus-submenu the mockup showed — the submenu would
      have swallowed the click.
    - **pyobjc turns underscores into colons.** A helper named `start_anim` becomes the selector
      `start:anim` and blows up at class-creation time. Methods on `_HeaderView`/`MenuController` are
      camelCase with no inner underscores (`startAnim`), or trailing-underscore for real one-arg
      selectors (`tick_`, `copyItem_`).
    Two smaller findings from building it: `⎋` (U+238B) has no SF Pro glyph at 11px and rendered as an
    unrelated symbol — write "esc"; and menu key equivalents (⌘O, ⌘,) only fire **while the menu is
    open**, so the global dictation hotkey stays in `hotkey.py` and is advertised in the header subtitle
    (`config["hotkey_label"]`, e.g. "Right ⌘") rather than faked as a key equivalent.

37. **The dictation upload is 16 kHz mono FLAC, and nothing on the critical path may block on
    non-transcript work** (2026-08, Tier-1 latency pass). Three rules, all measured:
    - **Never upload at the mic's native rate.** Every Whisper backend resamples its input to 16 kHz mono
      before the mel frontend, so the 48 kHz capture was paying **3×** the bytes to send information the
      model discards; FLAC (lossless) roughly halves it again. `transcriber.transcribe_with_status`
      downsamples ONCE via `_to_16k_array` and writes the upload with `_write_temp(..., ".flac", "FLAC")`.
      Measured on 8 real dictations (2–36 s): **5.0–6.1× smaller**, proxy round-trip **median −24%,
      mean −41%**, with **identical WER** against 48 kHz ground truth. `_write_temp` falls back to WAV if
      libsndfile can't encode FLAC (Rule #1). The 48 kHz array is still what `recordings.save_wav`
      archives — only the wire format changed. Side effect: a max-length 300 s recording was 27.5 MiB at
      48 kHz PCM_16, over Groq's 25 MB upload limit; at 16 kHz FLAC it is ~5 MB.
    - **Groq identifies the audio container from the multipart FILENAME.** Both call sites used to
      hardcode `"audio.wav"`. `groq_proxy.transcribe_via_proxy` and `transcriber._transcribe_groq` now
      derive the name + mime from the real path (`_MIME`). Send FLAC bytes labelled `.wav` and you are
      relying on server-side sniffing that is not contractual.
    - **The 16 kHz WAV is materialized lazily.** Gemini needs `audio/wav` bytes and local `faster_whisper`
      needs a WAV path, but neither runs unless Groq already failed — so `_wav16()` writes it on demand
      and the hot path never pays for it. (This also removed a second, redundant resample that the local
      fallback used to do from scratch.)
    - **Don't sleep where you can wait for the actual event.** `main._process_audio` used a flat
      `time.sleep(0.3)` to let the overlay pill disappear before `inject_text()` restores focus — a guess,
      paid on every dictation. It now sets a `threading.Event` inside the `_on_main` closure and waits on
      it (0.5 s ceiling); the UI queue drains on a 0.1 s timer, so it typically returns in <100 ms.
      **The Windows path still sleeps 0.3 s** — `win_overlay.hide()` schedules an animated `_fade_out` via
      `root.after`, so the wait is covering a real fade, and changing it needs a Windows visual check.
    - **`recordings.save_wav` runs on a background thread** in both `main._process_audio` and
      `win_main._process_audio` (resample + encode + `prune()` of the recordings dir ≈ 19 ms at 11 s,
      54 ms at 35 s). It has nothing to do with the transcript. A local `_saved_path()` closure joins the
      thread before the path is first used — by then transcription has long since paid for it. Anything
      else added here (uploads, analytics, learning) belongs off the path the same way.
    - **Nothing persists before the paste.** The order in `_process_audio` (both platforms) is: transcribe
      → transform/cleanup → snippets → **`inject_text`** → `add_to_history` → `update_daily_words`
      (→ `_update_tray_menu` on Windows) → autolearn → sync push → cloud upload. Cross-device sync and the
      Storage upload were always after the paste and on daemon threads; the two `save_config` writes moved
      after it too (~1.75 ms each on a 34 KB config, ~7 ms at 250 KB — it scales with config size, so watch
      it if the history/meetings caps ever rise). Three constraints hold this together, and each one broke
      something when reasoned about carelessly:
      - **`get_focused_app_name()` must be read BEFORE injection**, into a local `target_app`.
        `inject_text()` calls `restore_focused_app()`, so a post-paste read can name a different app and
        the history entry records the wrong dictation target. Only the *writes* move; this *read* cannot.
      - **The history write must still precede the sync-push and upload blocks**, which both resolve the
        entry via `self._history_entry(rec_id)`. Deferring it further (e.g. onto its own thread) races
        them into writing a row that doesn't exist yet.
      - **On Windows `_update_tray_menu()` must follow the counter bump** (`_total_words` /
        `_total_transcriptions`), so it moved with them rather than staying in front of the paste.
      Known, accepted trade-off: a cancel in the ~50–100 ms window between the overlay-hide wait and
      injection now discards the transcript instead of filing it — consistent, since that path doesn't
      paste either. And a crash between paste and persist loses the History entry for text already
      injected; the window is the two writes above.

37. **Pillow's ImageDraw does NOT alpha-composite, and the Windows overlay window keys on COLOUR, not
    alpha.** Two facts that multiply: `draw.ellipse(..., fill=(240,240,240,24))` writes that pixel
    verbatim — alpha included — rather than blending 9% white over the pill; and the layered window uses
    `LWA_COLORKEY`, which ignores the alpha channel entirely. So every "faint tint" in `win_overlay.py`
    was landing at FULL strength: the pause/cancel chips, meant to be barely-there dark discs, rendered as
    solid near-white blobs (found in IDI-184 by rendering the PIL output and looking at it). Pre-composite
    with `_over(fg, alpha, bg=BG_RGB)` and pass an opaque colour. Anything that wants translucency on
    Windows has to be blended by us, in advance.

38. **`win_overlay.ACC_RGB` was the RETIRED orange.** It shipped as `(232,82,42)` = `#E8522A`, with the
    comment "--acc (orange)", while Rule #16 retired that in favour of terracotta `#C85A3E`. Fixed to
    `(200,90,62)` in IDI-184. When a platform port hardcodes design tokens as tuples, they drift silently —
    the CSS side got the memo and the PIL side didn't.

39. **Verify a rendered surface by rendering it.** Three separate bugs in one week reached the user because
    HTML/PIL was written and shipped without being looked at (a `.rec` class collision that turned every
    pill into a CSS grid; a `<div>` inside a `<p>` that auto-closed the paragraph and exploded an inline
    widget; a menu gate whose `setEnabled_` was silently undone by auto-enabling). The scratchpad harnesses
    are the answer and are cheap to rebuild: load the page in an offscreen `WKWebView`, report every
    element overflowing its parent or the viewport, and snapshot it; for Windows, stub `tkinter`/`ImageTk`
    (this venv has no `_tkinter`) and drive the PIL draw functions directly, knocking out `CHROMA_TK` so
    the sheet shows only what is actually visible and clickable.
    - **Gotcha inside the gotcha:** an offscreen `WKWebView` has no window, so its animation timeline never
      advances — CSS transitions stay pinned at their START value. Every "hovered" screenshot came back
      identical to the resting one until the harness injected
      `*{transition:none!important;animation:none!important}`. The reveal was correct all along.

40. **CSS `:hover` does not work in the overlay panel — hover has to be driven from Python.** macOS
    delivers `mouseMoved` only to the **active** application, and the recording pill's panel belongs to a
    background app by definition (you are typing in someone else's window). So the Capsule's hover-to-expand
    did nothing until the pill was clicked, which is not the interaction. `overlay.py` now runs a **global**
    `NSEvent` monitor (`NSEventMaskMouseMoved`, no Accessibility grant needed — only key events require
    one), converts the cursor to panel-local coordinates (AppKit screen space is bottom-up, CSS is
    top-down), and calls `window.VerbalHover(x, y)`; the page hit-tests against its own pill rect so the
    geometry has exactly one definition. Throttled to ~25/s and only while the cursor is over the panel,
    with a single `x<0` "left" message on the way out. `:hover` stays in the CSS as a bonus for when Flume
    IS the active app, and `showPill()` clears a stale `.peek` across state changes.
    **Windows has the same problem for different reasons** and the same answer: the tk window is
    colour-keyed (so most of it is masked and click-through) and never focused, so `<Motion>` cannot be
    relied on. `win_overlay._poll_hover()` reads `winfo_pointerxy()` against the drawn pill's rect inside
    the 33 ms loop that already repaints the waveform; the `<Motion>`/`<Leave>` bindings remain only as
    latency accelerators.
    **The meeting bar (`meeting_window.py`) uses the identical macOS recipe** for its own short-by-default
    pill: `_start_hover_monitor`/`_on_global_mouse` run only while `layout==='bar'` (started/stopped from
    `set_layout`, torn down in `hide()`) and call `window.VerbalMeetingHover(x, y)` — a distinct global so it
    never collides with the overlay's `VerbalHover`. The Windows meeting window (`win_meeting_window.py`,
    pywebview/WebView2) is a normal, focusable OS window rather than a colour-keyed always-background one,
    so plain CSS `:hover` is expected to work there without a polling workaround.

41. **In the overlay panel, CSS animations and JS timers are both unreliable — anything that must MOVE has
    to be pushed from Python.** The transcribing ring was a plain `animation:spin .8s linear infinite` and
    it sat perfectly still on macOS (reported 2026-08; Windows was fine, its arc rides the 33 ms
    `_start_animation_loop` phase). This is the third instance of the same family as Rule #40: the pill
    lives in a WKWebView owned by an accessory app that is never active, and its animation timeline and
    timer throttling cannot be relied on. `setInterval` is affected too — a timer-based watchdog for the
    spinner never fired when measured, so a JS fallback would have been exactly as dead as the animation
    it was rescuing.
    - **The mechanism:** `overlay.py::_start_spin_pump` (a daemon thread, `SPIN_HZ=20`,
      `SPIN_DEG_PER_SEC=420`, same `_on_main` + `_inflight` backpressure shape as the level pump) pushes an
      absolute angle to `window.VerbalSpin(deg)`, which sets an inline `transform`. A JS-driven style
      change forces a repaint, which is precisely why the waveform never suffered from this.
    - **`.spinner.idle` carries the keyframes as the fail-open fallback**, and an inline transform cannot
      override a RUNNING animation — so the two must never both be active. `VerbalSpin(-1)` means
      "release": re-add `.idle`, drop the transform. `_stop_spin_pump()` sends it explicitly, because the
      page has no timer it can trust to notice that ticks stopped.
    - **Still outstanding:** the recording pill's elapsed clock is a `setInterval(tick, 1000)` in the same
      webview, so it is exposed to the same throttling and may drift or stall. Python already computes the
      elapsed seconds for the transcribing state — pushing them for the recording state too is the fix if
      anyone reports a wrong duration.

40. **If you move a pipeline stage across the client/server boundary, move the ORDER with it.** `chained_mode`
    (2026-08-14) makes `groq-proxy` transcribe *and* format in one round trip. That is purely a network
    change on paper, yet the first two cuts produced *different text* than the two-trip path — both times
    because a step that runs before formatting on the client no longer did on the server. Both are now
    fixed in edge fn **v10**; both cost a full measure-and-diagnose cycle, so treat them as the template
    for any future stage that migrates server-side:
    - **Whisper's transcript has a LEADING SPACE, and every client strips it.** `groq_proxy.py` and
      `lib/groq.ts` both `.strip()`. `chainFormat` did not, so the formatter received one extra leading
      token, which re-tokenizes the first line. Measured: the chained path lost the `Subhan`→`Siobhan`
      grounding fix **3/3** runs that the local path made **3/3** runs, on a byte-identical prompt. Never
      hand a raw upstream transcript to a second model without the same normalization the client applies.
    - **The dictionary must be applied BEFORE the formatter, so the RULES have to cross the wire.**
      `dictionary.apply_replacements()` runs inside `transcriber.finalize()`, i.e. before `process_text`
      ever sees the text. Chained, the server holds the transcript first — so the formatter read the
      uncorrected word and then "corrected" the grammar around it: `so ideas needs a new one` came back as
      `so ideas need a new one`, and applying `ideas`→`Idiaz` to the *output* could not restore `needs`.
      Fix: `build_chain_spec()` ships the `{from,to}` rules as `chain_replace`, and the edge function's
      `applyReplacements()` mirrors the Python semantics (word-boundary, case-insensitive) before
      formatting. **Only the rules cross; the dictionary itself stays on the client.** The dictionary
      rewrites **4 of 20** of this user's own clips, so this was a 20% exposure, not an edge case.
      Parity between the two implementations is pinned by comparing outputs on real rules — do that again
      if either side changes. Note the JS side replaces via a **function** (`() => r.to`) so `$1`/`$&` in a
      user-typed word can never be read as a backreference; Python's `re.sub` template would.
    - **Corollary for measurement:** when comparing arms, pass the *same* `active_app`. The eval harness's
      `new` arm calls `process_text(text, cfg)` with none, so a chained arm passing one adds an
      `Active app:` line to the grounding block and the comparison silently measures the prompt difference
      instead of the round trip.

41. **A flat `time.sleep()` on the dictation path is a latency bug, not a safety margin.** Three of them
    shipped, each waiting for something the code could simply observe. The pattern is always the same:
    replace the sleep with a wait on the real signal, keeping the old duration as the CEILING — that makes
    the change strictly non-regressive (never slower than before) while removing the cost in the common case.
    - `recorder.start()` — `sleep(0.3)` guessing when CoreAudio would deliver audio → `_first_block` Event
      set by the audio callback, ceiling 0.6s. Measured first-buffer arrival: median 230ms.
    - `injector.inject_text()` — `sleep(0.05)` after `pyperclip.copy` and `sleep(0.2)` after
      `restore_focused_app()`, i.e. **250ms on every dictation, after the transcript was already in hand**.
      Now `_await_clipboard` (poll the pasteboard, ceiling 50ms — measured 0.14ms median, 8.4ms worst) and
      `_await_focus` (poll `NSWorkspace.frontmostApplication()` until the target pid is frontmost, ceiling
      200ms). `activateWithOptions_` is **asynchronous**, which is what that 200ms was blindly covering;
      pasting before focus lands sends Cmd-V to the wrong app, so the wait is real — it just should end
      when focus actually arrives. Both log their real wait so production reveals the true numbers.
    - `main.py` `_ui_timer` — every main-thread hop goes through `_ui_queue`, so the timer interval is the
      floor on any UI hop the dictation path *waits* for (it waits for exactly one: hiding the pill before
      focus restore). Dropped 0.1s → **0.04s**, turning a 0-100ms wait into 0-40ms for 25 wakeups/sec.
    A fourth, worse variant of the same mistake: `asr_stream.start()` opened its websocket
    INLINE from the hotkey handler, so every record start blocked on a network round trip —
    measured **703ms median** between the keypress and the widget appearing, and it failed anyway
    while the relay secret was unset. The connect now happens on a background thread and `start()`
    returns in **0.5ms**; audio queues from the first callback and the pump holds it until the
    socket is up (the relay buffers pre-handshake audio too, so connecting late loses nothing).
    Two follow-on traps found while fixing it: `finish()` must wait on EITHER connected OR
    already-failed, not just success, or a dead relay costs the grace period at the STOP end; and
    the post-failure cooldown must mark the arm dead, or a skipped take still pays that grace.
    **Nothing that touches the network belongs between the hotkey and the overlay.**

    The remaining fixed sleep in `recorder.stop()` (0.1s, letting in-flight callbacks land) is deliberate and
    is NOT on the perceived path — it runs before transcription, not after.

42. **pywebview on Windows mixes units under DPI scaling: `create_window(width=…)` takes LOGICAL px, but
    `window.width/height` REPORT physical px and `resize()` SETS physical px.** Verified live on the winvm
    at 200% scaling (2026-08-15): a `create_window(980,680)` window reports `(1934,1289)`, and a naive
    `resize(1220,700)` SHRANK it to 597 CSS px of innerWidth. Consequence: any size compare between a
    CSS/logical target and `window.width` silently fails on scaled displays — this is exactly why the
    Notes auto-grow "did nothing" on Windows while working on macOS. `SharedDashboard.ensure_window_size`
    scales its logical minimums by `GetDpiForSystem()/96` before comparing/resizing (no-op at 96 dpi);
    apply the same conversion to ANY future pywebview geometry code. The JS side keeps a fallback
    (`.nbgrid.force3`) for hosts where resize still can't deliver. Also remember: BOTH desktop hosts reuse
    their window object across open/close, so a running app serves the OLD page until process restart —
    "feature missing on Windows" is often just a stale process (restart via the `FlumeRun` scheduled task
    on the winvm).
    **The meeting window's bar mode hit the same unit trap plus WinForms `MinimumSize` clamping
    (2026-08-28 report — the collapsed bar rendered as a full 700×480 titled window with the tiny
    pill floating inside it).** The canonical fix lives in `win_meeting_window._apply_chrome`
    (native `MinimumSize(0,0)`/`FormBorderStyle`/`TopMost` flips on the UI thread) +
    `app/win_geometry.py` (one DPI-aware `SetWindowPos` in physical px, pill region via
    `SetWindowRgn`) — see rule #71 (pywebview unit mixing) and #75 (bar hover invariants), and the
    Windows meeting-surface notes in `02-architecture.md`. Keep design constants LOGICAL module-wide
    and convert to physical in ONE place.

42. **A bulk backend UPDATE on a synced table REPLAYS every touched row to every connected client** —
    Realtime `postgres_changes` emits an UPDATE event per row, and the desktop's `_deliver` used to treat
    each as fresh content: clipboard overwritten per row, local history flooded with old rows stamped
    "today" (real incident, 2026-08-15: an account merge moved ~700 `transcriptions` rows and both
    running desktops replayed them; local histories had to be rebuilt from the cloud). Two rules:
    (a) `sync.SyncClient._deliver` now DROPS content rows whose `created_at` is >3 days old — fresh
    dictation is seconds old and the disconnect backfill is watermark-bounded, so nothing legitimate is
    that stale; the row is still `_remember`ed. (b) When running a bulk migration on `transcriptions` /
    `notes` / `meetings` / `canvas`, prefer doing it while clients are stopped anyway — Realtime also has
    its own rate limits and a partial replay is confusing to debug. Related repair details in
    `04-data-model.md` §Sync model (history bootstrap).
    NB the account merge itself: the legacy `shabbaraza26@gmail.com` account (`cc57c93e…`) was folded into
    `sraza@idiaz.io` (`1e642227…`) on 2026-08-15 — reversal ids in the `_acct_merge_20260815` table;
    storage objects deliberately stayed under the old uid's path prefix (rows store bare object paths, and
    signed URLs don't care whose prefix the path carries).

43. **Native contenteditable undo cannot survive this codebase — the note editor owns its own stack.**
    Any programmatic `innerHTML` replacement (AI reformat, restyle, `renderNotes()` re-render) wipes the
    browser's undo history, so Ctrl+Z "did nothing" exactly when users wanted it most (undoing an AI
    format). `flume_dashboard_html.py`'s `NU` stack snapshots per idle autosave + around every
    programmatic replacement; `noteKeys()` handles Ctrl/Cmd+Z / Ctrl+Y / Ctrl/Cmd+Shift+Z at the editor
    container. Any future surface with a programmatically-replaced editable region needs the same
    treatment — don't rely on `document.execCommand('undo')`. (The plaintext transcript view is left on
    native undo on purpose: nothing replaces it programmatically while it's open.)

44. **Three dashboard chrome rules from the 2026-08-15 small-window feedback:** (a) every icon-only
    button class needs an explicit `svg{width;height}` rule — an SVG with only a viewBox defaults to
    300×150 and paints outside a 32px button, which renders as a BLANK button (bit the notes ⋯ menu);
    (b) dropdowns inside `.npane` (which clips overflow) must open `position:fixed`, anchored to the
    trigger's rect and clamped to the viewport (`toggleNoteMenu`) — in-flow absolute menus get cut at
    the pane edge in small windows; (c) the WebView's native right-click menu is suppressed outside
    editable fields (`contextmenu` preventDefault) because its "Reload" blanks the window — the
    dashboard is loaded from a string, not a URL, so a reload has nothing to reload.

45. **A synthetic paste can be REFUSED without failing — check, never assume.** Both platforms have an OS
    gate that swallows injected keystrokes and returns no error, so `inject_text` reported success while
    the user's transcription never appeared. macOS: `CGEventPost` does **nothing** without the
    Accessibility grant — no exception, no return code. Windows: **UIPI** drops synthetic input aimed at a
    window owned by a higher-integrity process (target launched as administrator) and `SendInput` returns
    **0** events inserted, a value `pyautogui.hotkey()` throws away. This was a nasty bug to diagnose
    because the text *is* on the clipboard, so manual ⌘V/Ctrl+V works — it reads as "paste is broken",
    not "a permission is missing". Rules now:
    (a) pre-flight `paste_guard.can_paste()` before any CGEvent paste (including `_inject_with_mentions`,
    which posts CGEvents too), and re-read it **every dictation** — it's a cheap TCC cache read and the
    user can grant the permission while Verbal runs;
    (b) never call `SendInput` for a paste without checking the returned count, and always send the
    key-ups even when the downs were refused, or a partial delivery leaves a phantom Ctrl/Cmd held down;
    (c) an *unknown* or failed permission probe means **try the paste anyway** — never let the guard be
    what stops a dictation (Hard Rule #1);
    (d) prompt **once per reason per app run** (`paste_guard._prompted`, re-armed when the grant flips).
    Nagging on every dictation is worse than the silent failure it replaced;
    (e) `paste_guard` owns detection/copy/throttle but **not the popup** — `main.py`/`win_main.py` register
    a hook, because the alert must hop to the main thread (`rumps.alert` = modal NSAlert, conventions #4)
    and only they own the toolkit. This alert is *allowed* to steal focus, unlike the overlay panels
    (#8), since the paste has already failed;
    (f) the Windows fix relaunches elevated via `ShellExecuteW "runas"` — it **must `CloseHandle` the
    singleton mutex first** (`sys._verbal_singleton_mutex`), or the elevated copy hits
    `ERROR_ALREADY_EXISTS` and exits instantly; and it must **re-acquire** the mutex if UAC is declined
    (`rc <= 32`), or the window left open lets a second Verbal start. `CloseHandle`, not `ReleaseMutex`:
    the mutex is created with `bInitialOwner=False`, so the process never owns it and closing the handle
    is what frees the *name*.

46. **A nested `navigate()` into a sub-stack REPLACES its history unless you pass `initial: false`.**
    `navigate('Main', { screen: 'NotesTab', params: { screen: 'MeetingList' } })` seeds the Notes stack
    with MeetingList as its **only** route — verified in
    `@react-navigation/core/src/useNavigationBuilder.tsx` (`getStateFromParams`, and again at the
    rehydrate branch: the guard is `params?.initial !== false`). The screen's Back then has nothing to pop,
    so the action **bubbles to the bottom-tab navigator**, whose default `backBehavior` is `'firstRoute'`
    (`@react-navigation/routers/src/TabRouter.tsx`) — you land on **Home**, and NotesTab stays parked on
    MeetingList with NotesList unreachable. This bit the SidePanel's "Meetings" row. Rules: when a nested
    navigate targets a screen that is **not** its stack's root, pass
    `params: { screen: X, initial: false }` so the root sits underneath and Back means "up one level";
    and remember that a **deliberately** single-route stack is fine — inside the `Menu` modal, bubbling up
    to dismiss the modal is exactly what you want (`Canvas` makes it explicit with
    `navigation.getParent()?.goBack()`).
    Related invariant, since iOS has no hardware back button: **every non-root route needs its own
    top-left `chevron-back`** (see `02-architecture.md` for the intentional exception list). Settings
    shipped without one and was escapable only by an undiscoverable modal swipe-down.

47. **Never key a list by its own display text — axis/tick labels repeat by design.** Insights' rhythm chart
    keyed its hour ticks `['12AM','6','NOON','6','11PM']` by label (`key={t}`), and the two sixes (6AM and
    6PM) produced a live `Encountered two children with the same key, '6'` on device — React's own warning
    says duplicate keys may **duplicate or omit** children, so this is a correctness risk, not just noise.
    Key by **index** for a static presentational row, or by a real id (`Object.keys`/`entries` output, a
    row `id`) for data. Text is only a safe key when it is genuinely a unique identifier.

47. **The team layer is the one place with REAL RLS — and the two rules that come with it (IDI-216).**
    The four `organization*` tables are `TO authenticated` + `auth.uid()`, unlike every legacy table's
    `TO public USING(true)`. Two things follow that are easy to get wrong:
    - **An RLS policy must never answer "is the caller a member?" by selecting the membership table** —
      that recurses. Every policy calls `public.org_member_role(p_org)`, a SECURITY DEFINER function
      that reads it with RLS bypassed. It is the single definition of who may see an org; add a table to
      the layer and its policy asks the same function, never its own SELECT.
    - **Postgres RLS cannot restrict which COLUMNS a policy lets you write.** A "members may update
      their own row" policy on `organization_members` would also let a member set their own `role` to
      `owner`. So that table has **no** INSERT/UPDATE/DELETE policy at all and every write goes through
      an RPC (`org_set_role`, `org_remove_member`, `org_set_consent`) that touches exactly the columns
      it is for. Apply the same shape to any future table where a row's owner may edit some of their own
      fields but not all of them.
    Corollaries worth keeping in mind: a paired-but-never-signed-in device sends the anon key, so it
    reads zero org rows and simply has no team — **that is the fail-closed outcome, not a bug to route
    around**; and the whole layer was designed so nothing reads another user's row in a legacy table,
    which is precisely why it could ship without `supabase_auth_uid_rls.sql` (IDI-29) and its unresolved
    pairing trade-off. Don't "simplify" the shared dictionary by widening the personal `dictionary`
    table's policy — that reintroduces the exact dependency this design avoids.

48. **A team feature must be invisible to the dictation path (IDI-216).** `dictionary.effective()` /
    `getEffectiveDictionary()` merge personal ∪ team on every dictation, and both read a LOCAL cache
    (`config['org']` / AsyncStorage `flume_org` + an in-memory mirror) — never the network. Any future
    team-aware behavior on the hot path must be cached the same way, and must fail closed to
    personal-only (Hard Rule #1). Two details that are load-bearing and non-obvious:
    - **Personal wins a key collision, and team entries are ordered FIRST.** The union is what applies;
      only an identical vocabulary word / replacement `from` / snippet `trigger` needs a tiebreak, and
      there the user's own entry wins, so joining a team can never silently change what an existing
      trigger expands to. The ORDER matters separately: `build_prompt` keeps the *tail* of the
      vocabulary (Whisper conditions on the last ~224 tokens; trimming happens from the front), so team
      terms go first and personal last — reversed, joining a team quietly evicts your own words from the
      bias prompt.
    - **The sync toggle gates the shared DICTIONARY, not membership.** Sync off ⇒ dictate with your own
      dictionary exactly as before joining, while still being a member with a role and a roster. Putting
      the sync check in the org fetch instead would make an admin stop being an admin on a machine where
      they'd turned sync off.
    Also: the org cache is account-scoped in the strongest sense and belongs in BOTH teardown paths
    (`auth._clear_account_caches` → `config['org']`; `clearAccountData` → the `flume_org` key **and**
    `clearOrgCache()` for the in-memory mirror). Leaving it behind lets the next account signed in on
    that machine dictate with a team it was never in — the Hard Rule #13 leak, in a new place.

49. **"Latest release" is a SEMVER question, and `released_at` cannot answer it.** `app_versions`
    timestamps are written by CI and are not monotonic — production had win `1.0.9` stamped
    `00:00:00` beside win `1.0.8` stamped `09:13:24` on the same day, so
    `order=released_at.desc&limit=1` (what `updater.py` did for months) returned **1.0.8** as newest
    and no Windows user on 1.0.7 could ever be offered 1.0.9. Read `app_versions_latest`, which sorts
    on `semver_key(version)` — an `int[]`, because a TEXT sort ranks `1.0.9` above `1.0.10`. Both the
    in-app updater and the public `download` redirect read that one view, so they cannot disagree
    about which build is current.
    Two related release-process rules now enforced rather than remembered: the CI **release job fails
    if the git tag does not equal `config.APP_VERSION`** (conventions #33 flagged that drift as
    unenforceable in the spec file — it is enforceable in the workflow), and the `download` function
    **logs an error and returns 503** when a platform has no row, because a missing `app_versions`
    insert is a pipeline failure that otherwise shows up as a silently un-updatable app. That is not
    hypothetical: `mac` sat at `1.0.0` in production while `APP_VERSION` was `1.0.10`.

50. **The desktop release pipeline is GitOps-automatic and GitHub-Releases-only (IDI-224, 2026-08-20).**
    `.github/workflows/auto-release-desktop.yml` watches pushes to `dev` **path-filtered to
    `whisperflow/**`** — a mobile-only change under `verbal-mobile/**` never triggers it, and this
    workflow never touches mobile (mobile's own CI, if/when it exists, must use its own
    `verbal-mobile/**` path filter). A qualifying push auto-bumps `config.APP_VERSION`'s patch digit,
    commits, and pushes a `vX.Y.Z` tag — that tag push is what fires `build-release.yml`, unchanged.
    Mac and Windows **always build and ship together** as one versioned bundle (they share the same
    Python core and one `APP_VERSION`; releasing them independently is exactly how mac got stuck on
    `1.0.0` while `APP_VERSION` read `1.0.10`). There is **no human approval gate** — a merge to `dev`
    ships to every auto-updating install directly (a deliberate speed-over-review tradeoff; revisit with
    an environment-protection rule or a beta/stable split if that ever needs walking back).
    **Anti-loop guard:** the bump job is gated `if: github.actor != 'github-actions[bot]'` — its own
    commit is itself a push to `dev` touching `whisperflow/**`, which would otherwise retrigger the
    workflow forever. Don't swap this for a `[skip ci]` commit-message trick: that suppresses ALL
    workflows for every ref in the push, including the tag push meant to fire `build-release.yml`.
    **GitHub Releases is the SOLE artifact host** — the old TUS-upload-to-Supabase-Storage step is
    gone. A live check (2026-08-20) found the `releases` Storage bucket had **zero objects, ever**;
    GitHub Releases assets land correctly whenever the job runs, so it's the one place a binary lives
    now. `app_versions.file_url` is always a `github.com/<repo>/releases/download/...` URL.
    **Filenames are renamed to a deterministic, versioned form (`Verbal-X.Y.Z-mac.dmg` /
    `Verbal-X.Y.Z-win-setup.exe`) in ONE place** before the GitHub Release is created, and the hash/URL
    registered in `app_versions` is computed from that same renamed file — production had shipped with
    the registered filename (hand-assembled in the Supabase-upload step) drifting from the actual
    uploaded asset name (e.g. a row pointing at `Verbal-1.0.9-setup.exe` when the real asset was named
    `Verbal.exe`), which is exactly how "the tag/version says 1.0.9 exists" and "the download 404s"
    coexisted. The release job now **smoke-tests itself**: after registering both `app_versions` rows,
    it curls the public `download?platform=...&json=1` endpoint (the same one the website button hits)
    for both platforms and fails the job unless `ok && reachable` and the version matches — a broken
    pipeline fails LOUD in CI, not silently as a user's 503.
    **macOS is code-signed + notarized (2026-08-21); Windows is still unsigned — known gap.**
    `build-mac` imports a Developer ID Application cert into a throwaway per-job keychain (secrets
    `MACOS_CERTIFICATE_P12`/`MACOS_CERTIFICATE_PASSWORD`/`MACOS_KEYCHAIN_PASSWORD`), signs every
    nested Mach-O binary leaf-first with hardened runtime (`whisperflow/entitlements.plist`) before
    signing `Verbal.app` itself — **never `codesign --deep`**, which Apple's own docs warn can sign a
    bundle this size (ctranslate2/numpy/scipy dylibs) in the wrong order — then notarizes the DMG via
    `notarytool` using an **App Store Connect API key** (`APPLE_API_KEY_P8`/`APPLE_API_KEY_ID`/
    `APPLE_API_ISSUER_ID` — chosen over Apple-ID + app-specific password specifically so CI auth
    can't break on a password rotation or 2FA change) and staples the ticket so Gatekeeper can verify
    offline. The signing identity is **discovered from the imported cert at runtime**
    (`security find-identity`), never hardcoded as a secret, so a cert renewal can't drift out of sync
    with a separately-stored identity string. `whisperflow.spec`'s `BUNDLE()` is deliberately left
    unsigned (`codesign_identity` omitted) — PyInstaller's own signing can't do the leaf-then-bundle
    ordering hardened runtime requires. **Windows has no code-signing cert yet** — the installer ships
    unsigned and will hit a SmartScreen warning; separate follow-up, deliberately out of scope here.
    **`build-windows-exe.yml`** is a separate, `workflow_dispatch`-only workflow that builds a
    throwaway test EXE/installer as CI artifacts — it does **not** create a GitHub Release or touch
    `app_versions`, and is unrelated to this pipeline.

50. **WKWebView does not give you `alert`/`confirm`/`prompt` — you must implement
    `WKUIDelegate`, and RETAIN it.** With no UI delegate, WebKit resolves a JS dialog
    immediately with the default: `confirm()` returns **false** without drawing
    anything. It does not throw, warn, or log. So every `if(!confirm(…)) return;`
    guard in `flume_dashboard_html.py` was a silent no-op on macOS — 16 of them,
    including Delete note, Clear history, Remove offline devices, **Delete your
    account** and Remove from team. Nothing worked and nothing complained; it
    surfaced only when someone reported a button doing nothing.
    **Windows was never affected**, which is exactly why it survived the parity
    work: pywebview/WebView2 provides these panels natively. A macOS-only silent
    failure in shared HTML is the shape to watch for.
    `flume_web_dashboard.py::_ui_delegate_class()` now implements all three panels
    over `NSAlert`. Three details that matter: the delegate is stored on `self`
    because **`setUIDelegate_` holds a WEAK reference** (a local is collected and
    the panels quietly die again); the confirm handler **fails CLOSED** — an alert
    we could not draw must read as "cancelled", never as consent to a destructive
    action; and our `"Title?\n\nDetail"` copy is split onto NSAlert's
    messageText/informativeText rather than dumped into the title, with
    `NSCriticalAlertStyle` applied when the copy contains delete/remove/erase.

51. **Metadata you never recorded cannot be backfilled — say so in the UI instead of rendering a
    zero.** `transcriptions.app` shipped 2026-08-21 so the team view could answer "which app does each
    person dictate into?". Every row written before that is NULL, and the frontmost app at capture time
    exists nowhere else, so there is nothing to recover it from. A panel that renders an empty stacked
    bar over that is indistinguishable from a broken feature — the same failure as the blank WPM gauge on
    a new member's page (#47). Both new surfaces name the cutoff date in prose and say why, including
    that **iOS contributes nothing** (a phone has no frontmost window). Whenever a new column starts
    collecting data going forward, the first version of the UI is a sentence, not a chart.

52. **Widening what a team can see about a member is a COPY change, not just a schema change.** The team
    layer's promise was literally "only counts and durations"; an app name is neither. `org_app_breakdown`
    keeps the same `usage_consent` gate and still never touches text or audio, but three separate strings
    became false the moment it shipped (the overview privacy card, the member-page footnote, the mobile
    usage footnote). The migration's own header carries the note demanding they change. Grep the promise,
    not just the code: `grep -rn "counts and durations"` is what caught all three.

53. **When a screen has two audiences, pick the data source per audience rather than showing one of them
    an empty box.** (Superseded 2026-08-27: the per-member opt-in is gone; the board lists every sharing
    member once the owner enables it.) The first team ranking read only from the opt-in `org_leaderboard`, which is off by
    default and needs BOTH an org switch and a per-member opt-in — so a brand-new owner's ranking said
    "nobody has opted in yet" while the admin usage list right above it had rows. Now owners/admins rank
    from the consent-gated `org_usage_summary` they can already see and everyone else ranks from the
    opt-in board: same rows, same order, different audience. The privacy model is unchanged; only the
    honesty of the empty state is.

54. **A privacy switch belongs in Settings, not on the feature it governs.** The team consent toggles
    shipped on the Team screen, which is a reasonable place to *read* them and the wrong place to *find*
    them: "where do I turn that off?" then had two answers depending on which feature you were thinking
    about. They now sit in a `Team privacy` settings group (desktop) / `TEAM PRIVACY` section (mobile),
    with the feature screen keeping a one-line summary of the current state and a link across. Two
    things this forces: the group must be **hidden when the user has no team** and must fall back if they
    leave while sitting on it, and the payload now feeds two screens — hence `teamRepaint()`, because a
    toggle that does not move while the backend has already changed is indistinguishable from a bug.
    While moving it, check the action you are moving actually works: `Leave team` was rendered
    unconditionally, but `org_remove_member` returns `cannot_remove_owner`, so it had always failed
    silently for owners. It is now hidden for them, with the reason stated.

55. **When one RPC in a family disagrees with the others about who may read it, the client will not
    tell you — the screen will just be empty.** `org_usage_series` and `org_app_breakdown` both end their
    role check with `or m.user_id = v_uid` (an admin sees everyone consenting, anyone else sees only
    themselves). `org_usage_summary` did not, and every total on the Team overview is derived from it, so
    a plain member's page was zeroes end to end. Three layers had to agree before a single number
    appeared: the SQL split, `organizations.usage_summary`'s `role not in (...)` early return, and the
    JS `if(teamAdmin())` around the request. Fixing any one of them changes nothing, which is exactly why
    it survived so long.
    Two habits from this: when you add a role guard to an RPC, diff it against its siblings' guards; and
    **never let an empty state assert a cause it cannot distinguish**. "Usage appears here as people turn
    sharing on" was false the whole time — the cause was the caller's role, not anyone's consent. Not
    loaded, loaded-and-genuinely-empty-for-an-admin, and loaded-and-genuinely-empty-for-a-member are three
    different sentences now.

56. **Minimizing the dashboard window leaks a Regular activation policy, which silently kills the pill's
    full-screen visibility for the rest of the session.** `flume_web_dashboard.py`'s `show()` flips the app
    to Regular (`setActivationPolicy_(0)`) so the dashboard is a normal Cmd+Tab/Dock window while open —
    every floating panel (`overlay.py`'s recording pill, `autolearn_widget.py`, `transform_widget.py`,
    `meeting_window.py`) needs the app back on Accessory (1) to reliably stay visible over ANOTHER app's
    full-screen Space, even with the right `NSWindowCollectionBehavior` set. The delegate's
    `windowWillClose_` reverts it on close, but clicking the yellow button (miniaturize) never fires that
    — the window just leaves the screen without closing, so the app was stuck on Regular until quit.
    Reported as "the pill works right after restarting the app, then disappears over full-screen apps
    after a while" (a restart resets the policy at launch; the degradation only shows up once the user has
    minimized the dashboard at some point in the session, which is why it took "a lot of use" to notice).
    Fixed by adding `windowDidMiniaturize_` (revert to Accessory) and `windowDidDeminiaturize_` (restore
    Regular) to the same delegate.
    **A third leak (2026-08): Cmd+H.** Hiding the app doesn't fire `windowWillClose_` or the miniaturize
    pair either, so the policy stuck at Regular the same way — and this one reproduced with NO full-screen
    app involved, matching a later report of the pill failing "even on the desktop where there is no full
    screen app": a Regular-policy app that's been Cmd+H'd also fails to reliably re-show its OWN
    non-activating panels afterward, so `overlay.py`'s `orderFrontRegardless()` became a no-op until the
    user quit and relaunched. `applicationDidHide_`/`applicationDidUnhide_` are NSApplication notifications,
    not NSWindow delegate methods — rumps already owns the `NSApp.delegate` slot, so they're wired via
    `NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(...)` in `_build()` instead of
    assuming AppKit will call them automatically. `applicationDidUnhide_` only restores Regular if
    `self._window.isVisible()` — otherwise an unrelated hide/unhide (the dashboard already closed) would
    wrongly flip an Accessory app back to Regular.
    **The fourth path (2026-08-29) has no event at all: the dashboard is simply LEFT OPEN** on some other
    Space while the user goes full-screen in another app. The policy is legitimately Regular the whole time,
    so the per-event reverts above can never help — reported as "works for the first hour, then the pill
    never shows over full-screen VS Code" (the hour was how long it took to open the dashboard and leave
    it). Instead of hunting for a fifth event, `overlay.py` now handles it at the point of need:
    `_order_front()` calls `_borrow_accessory_policy()`, which flips to Accessory only when the policy is
    Regular AND our app is inactive AND the Space under the cursor looks full-screen (no menu-bar gap
    between `NSScreen.frame` and `visibleFrame`; errors count as full-screen so we err toward showing the
    pill). `hide()` calls `_return_accessory_policy()`, which gives Regular back only if the dashboard
    window is still visible, not miniaturized, and the app isn't hidden — so it never re-creates the
    leaks above. The Dock icon blinking for the pill's lifetime is the accepted cost (and invisible on a
    full-screen Space anyway). The other floating panels (`autolearn_widget.py`, `transform_widget.py`,
    `meeting_prompt.py`) still rely on the dashboard-side reverts only.

57. **A conditionally-shown element must be in the pixel budget, not just the steady-state one.**
    `meeting_html.py`'s ambient bar expands `.barOpt`'s `max-width` from 0 to a hardcoded cap on
    hover/peek/paused; the cap (340px) was sized for title+wave+3 buttons and never accounted for
    `.barPausedTag` ("PAUSED"), which only renders while paused — so the one state that should show
    MORE content (a paused meeting) was also the one state most likely to overflow, and `overflow:hidden`
    silently clipped the trailing button (`stop`, sitting rightmost) instead of erroring. Reported as
    "the pause button — the [one to its] right, stop — renders half" (a clipped edge reads like a broken
    render, not a layout overflow). Any inline-flex row with a hover/peek-revealed `max-width` needs its
    cap computed from the WIDEST real combination of children, including ones normally invisible — and
    `meeting_window.py`'s `BAR_W` (the actual NSPanel width) has to grow to match, not just the CSS cap,
    or the panel itself clips before the CSS ever gets the chance to.
    Also added while touching this surface: a real **Cancel** action for a live meeting (`cancel_meeting`
    on `DashboardApi` → `MeetingManager.cancel_active()` → `MeetingSession.cancel()`), distinct from Stop
    — Stop finalizes (drains transcription, uploads audio, generates the summary, keeps a history row);
    Cancel skips all of that and deletes anything already persisted (the cloud row/audio and local WAV
    exist from the moment recording starts, via `_cloud_insert`/`_persist_local` in `_start()`), mirroring
    `MeetingManager.delete()`'s cleanup but callable mid-flight since `delete()` refuses while a meeting
    is active. Gated behind a real `confirm()` in JS — which meant `meeting_window.py` first needed a
    `WKUIDelegate` at all: unlike `flume_web_dashboard.py`, its webview had never had one installed, so
    every `confirm()` in this panel was a silent, always-false no-op (the exact bug in convention #50,
    just not yet triggered here because nothing had called `confirm()` from this window before).

58. **A "force-reveal while X" rule needs an exit, or the pill is stuck revealed for as long as X lasts.**
    The ambient meeting bar's `.barOpt` used to expand on `:hover`, `.peek` (real hover, proxied from
    Python — 05-conventions Rule #40) OR `.paused` — that last one was meant to surface the resume button
    without requiring a hover a background, non-activating panel can't reliably get. But `.paused` is a
    STATE, not a momentary gesture: the pill stayed maximally wide for the entire time the meeting was
    paused, never shrinking back to dot+timer, however long that was. Reported as "its bar remains in
    expanded mode" after pausing. Dropped `.paused` from the reveal selector — hover/peek are the only
    triggers now, same as every other state — and kept the dot's own paused styling (greyed, no pulse) as
    the at-rest signal, which needs no width at all. The general lesson: a state-driven reveal is fine for
    something that resolves itself quickly (a toast, an animation); for a state with no time bound (paused
    can last indefinitely), tie the reveal to the USER'S ATTENTION (hover) instead, or it reads as stuck.

59. **A forced model swap can regress latency even when it's a straight upstream retirement, not a choice
    — and `reasoning_effort` is the knob, not a fix.** Groq retired the whole `llama-3.x` tier on
    2026-08-18 (every call 404'd `model_not_found`), forcing `ai_cleanup.py`'s `SPEED_CLEANUP_MODEL` from
    `llama-3.1-8b-instant` to `openai/gpt-oss-20b` and the quality tier from `llama-3.3-70b-versatile` to
    `openai/gpt-oss-120b` (commit 3f952ff). Both replacements are REASONING models — Groq defaults
    `reasoning_effort` to `"medium"` — so a purely mechanical formatting request now burns hundreds of
    hidden thinking tokens before answering: measured in the `SPEED_CLEANUP_MODEL` comment at 1.54s / 430
    output tokens vs the old model's 0.82s / 51, on the identical task. Nothing about the app's own model
    OR pipeline selection logic changed or regressed — `speed_mode`/`chained_mode` still pick the same
    tiers they always did — which is exactly why it read as mysterious ("sudden slowdown despite the
    optimized pipeline"): the regression came from what the selected model IS now, not from which model
    got selected. Fixed (2026-08-22) by passing `reasoning_effort="low"` on every dictation-formatting
    call — `cleanup_with_groq()`, `process_text()`'s `chat_via_proxy` call, and `build_chain_spec()`'s
    chain payload in `ai_cleanup.py`. The `chained_mode` path needed a matching server-side change since
    `groq-proxy/index.ts`'s `chainFormat()` hand-builds its request body rather than forwarding the client
    payload wholesale (unlike the plain JSON `/chat/completions` branch, which needed nothing — it already
    forwards `reasoning_effort` through automatically): added a `chain_reasoning_effort` form field,
    parsed and stripped alongside the other `chain_*` fields, threaded into the request body only when
    present. `"low"` is a mitigation, not a full recovery to the old baseline — there is no way to turn
    reasoning off entirely for this model family, only down. Left `format_note()` (notes formatting, a
    separate feature) untouched: the same regression logic applies there too, but changing it wasn't asked
    for and risks an unreviewed quality trade on a task that leans more on structural judgment.
    A related, unrelated-cause gap this surfaced: `context/03-features.md`'s `speed_mode` entry and
    `context/04-data-model.md`'s latency-flags entry both still named `llama-3.1-8b-instant` as
    `SPEED_CLEANUP_MODEL` after the 3f952ff swap, even though that same commit's message claimed "context/
    docs updated for the above" — the quality-tier references got fixed, the speed-tier one didn't. Doc
    sync claims in a commit message are not self-verifying; grep the actual model constant name across
    `context/` when a model swap lands, don't trust that the commit already did it.

59c. **Mobile `Card` (and any Pressable-or-View wrapper): never hand a plain `View` a function-valued
    `style`.** `Card` used `Wrap = onPress ? Pressable : View` but always passed the
    `({pressed}) => [...]` callback form; `View` silently ignores it, so every Card WITHOUT `onPress`
    rendered with no surface, no padding and no `flex: 1` — History detail's transcript card collapsed
    to zero height (found on the simulator 2026-08-27; regression from the app-wide press-feedback pass,
    commit `4bfe159`). Branch on `onPress` and pass a static style array to `View`.

59a. **Mobile: any `<Text>` with a large `fontSize` must set `lineHeight` too.** The shared
    `components/Text` applies the `body` variant by default (`fontSize 17 / lineHeight 25`) and a style
    prop that only overrides `fontSize` keeps that 25px line box — iOS clips glyphs to it, so a 52px
    number renders with its top half missing (Insights WPM hero, 2026-08-26). Rule of thumb:
    `lineHeight ≈ fontSize × 1.08` for display numerals; check any `fontSize > 25` on a variant-less
    `<Text>`.

59b. **Windows: never `sys.exit()` off the main thread — quit with `os._exit(0)`, and a second launch must
    WAKE the first, not die.** `win_main._tray_quit` runs on the pystray thread (or an `_on_main` daemon
    thread from the popover's `quit_app`), never on the main thread, which is parked in `webview.start()`.
    `sys.exit()` there raises `SystemExit` in that thread only: the tray icon vanished but the process
    lived on, still holding `VerbalSingletonMutex_v1`, so every later double-click hit
    `ERROR_ALREADY_EXISTS` and exited silently ("after closing the app it doesn't open again",
    2026-08-26 — the same lesson `updater.install_update` already learned). `_tray_quit` is now a thin
    wrapper over **`_hard_exit(reason)`**, the ONE teardown every exit path shares (tray Quit, the
    popover's `quit_app`, the elevated relaunch, the bootloader watcher below): set `self._exiting`
    (so `SharedDashboard._on_window_closed` and the pywebview `closing` interceptors of #67 can tell
    "quitting" from "user closed a window"), hide the tray icon (`icon.visible = False` — a
    synchronous `NIM_DELETE`; `stop()` alone only posts `WM_STOP` and, when Quit is clicked, we ARE on
    the pystray loop thread that never gets to run its `finally`, so the icon stayed as a ghost),
    destroy the pywebview windows, `logging.shutdown()`, `os._exit(0)`. The optional teardown runs on
    a daemon thread **joined for at most 1 s**: pywebview's winforms `destroy()` is a synchronous
    `Control.Invoke` onto the GUI thread, so with that thread stalled an inline destroy never returns
    and `os._exit` is never reached — exactly the "looks hung, kill it in Task Manager" state. It is
    re-entrant (a second caller sleeps 1.5 s and exits) and does no network, no meeting-stop, no config
    write — anything that can block or raise there is a way to lurk again. `webview.start()` returning
    (every window gone — Windows shutdown destroys the hidden anchor too) also calls `_hard_exit`
    rather than falling off `VerbalWinApp.start()` into a tray-only zombie that still holds the mutex.
    And because closing the
    dashboard with X deliberately leaves Flume in the tray, the *losing* second process now pulses the
    named auto-reset Event `VerbalShowDashboardEvent_v1` (`_signal_running_instance`) and the running
    app's `_second_instance_watch` thread answers with `dashboard.show()` — "opening the app" opens the
    app. `SharedDashboard` hooks `events.closed` to drop its window reference so that show() rebuilds
    rather than poking a destroyed handle — and, on Windows only, shows a **one-time toast** the first
    time the dashboard is X'd ("Flume is still running in the system tray … right-click the tray icon
    and choose Quit"; `_maybe_show_tray_close_hint`, flag `config['tray_close_hint_shown']`, winotify
    → `pystray` `notify` fallback, config write + toast on a daemon thread, suppressed while
    `_exiting`) — users read the vanished window as "closed" and then found Flume.exe in Task Manager.
    All fail-closed: if the Event plumbing breaks, behavior is exactly the old tray-only one. The Event
    name is a machine identity like the mutex — see #60.
    **The shipped build is ONE process (PyInstaller ONEDIR) since 2026-08-28** — `verbal-win.spec` ends
    in `COLLECT(...)`, `verbal-setup.iss` packages `dist\Flume\*`. Everything below about the bootloader
    parent describes builds ≤ 1.0.35 and stays as the reason the watcher exists (it self-disarms in
    onedir). *History:* `verbal-win.spec` was `EXE(...)` with
    no `COLLECT`, so a running Flume was a ~9 MB **bootloader parent** (child of explorer.exe; unpacks
    to `%TEMP%\_MEIxxxx` and waits) plus the ~300 MB **real app child** that owns the tray icon, hotkey,
    WebView2 windows and `VerbalSingletonMutex_v1`. Task Manager shows both `Flume.exe`. "End task" on
    the parent used to orphan the child — headless, still holding the mutex, so the next double-click
    died on `ERROR_ALREADY_EXISTS` ("if I end the program it still lurks around in the task manager",
    2026-08-26). `win_main._watch_bootloader_parent(app._hard_exit)` closes that hole: the child opens
    `os.getppid()` with `SYNCHRONIZE`, blocks in `WaitForSingleObject` on a daemon thread and
    `_hard_exit`s when the parent dies. It arms ONLY when all four hold — `sys.frozen`; one-file layout
    (`sys._MEIPASS` is OUTSIDE the exe's directory — in onedir it is the exe dir or `_internal`, and
    there "parent is another Flume.exe" is legitimate: the elevated relaunch gets reparented onto the
    requester, and the healthy copy would die when the old one quits); parent image path ==
    `sys.executable`; parent created before us (PID-reuse guard) — and any ctypes failure just means no
    watcher (old behavior). Never in a dev run (the parent is your terminal). The **structural** fix — the
    onedir (`COLLECT`) build — landed 2026-08-28; the watcher is now a safety net only.
    **Windows branding lives in three places, all must say Flume:** the exe icon (`assets/icon.ico`,
    regenerated by the spec whenever it is missing OR older than `app_icon.png`), the exe version
    resource (`version_info.txt` is a *template* — the spec stamps `APP_VERSION` into
    `build/version_info.txt`; it shipped "Verbal Speech-to-Text 1.0.10" on every build through 1.0.35,
    which is what Task Manager showed), and the installer (`UninstallDisplayIcon` for Settings > Apps;
    `[Icons] IconFilename` → `{app}\assets\icon.ico` so the shell icon cache gets a NEW key instead of
    serving the cached Verbal art for `{app}\Flume.exe`; `CurStepChanged` calls
    `SHChangeNotify(SHCNE_ASSOCCHANGED)` after install to flush the cache).
    **The installer kills a running Flume itself** (`PrepareToInstall` → `taskkill /IM Flume.exe /F /T` +
    wait): `CloseApplications=force` depends on the Restart Manager, which can answer "Permission
    Denied" (seen live 2026-08-28 when a SYSTEM process also mapped our files) — then `Flume.exe` is
    never closed, `DeleteFile` fails (code 5) and a `/SUPPRESSMSGBOXES` install silently **aborts and
    rolls back**. Always read the Inno `/LOG=` when an update "did nothing".
    `config.py` decodes `config.json` as **utf-8-sig**: a BOM (PowerShell `Set-Content -Encoding UTF8`, some
    editors) used to be treated as corruption → file moved to `.bak`, defaults restored, user signed out.

60. **The product is branded "Flume" everywhere user-facing (renamed from "Verbal", 2026-08-23) — but
    every internal identity string stays "Verbal"/`com.verbal.app`, deliberately.** App bundle/executable
    name, window/dialog titles, the installer name, tray/menu text, and dashboard copy all say "Flume"
    now. Left UNCHANGED on purpose: macOS `bundle_identifier='com.verbal.app'` (`whisperflow.spec`), the
    mobile `bundleIdentifier`/`package`/URL `scheme` (all `com.verbal.app`/`verbal` in `app.json`), the
    Windows installer's AppId GUID (`verbal-setup.iss` — see #50's sibling note there), and the Windows
    single-instance mutex name (`win_main.py`, `"VerbalSingletonMutex_v1"`). Every one of those is a
    machine identity, not a display string: changing any of them would make macOS/Windows treat an
    existing install as a brand-new, never-authorized app — losing every already-granted TCC permission
    (mic/accessibility/screen-recording), breaking the updater's "is this a newer version of the same
    app" detection, and orphaning old Windows Programs-and-Features entries. That migration is a real
    product decision, not a rename, and stays out of scope until deliberately planned.

61. **`assets/icon.png` is a 44x44 menu-bar/tray glyph — it is NEVER the real app icon, and every
    icon-conversion step must read `assets/app_icon.png` instead.**
    (2026-08-25: all brand icons are now the fire-crested parrot mascot, regenerated by
    `whisperflow/scripts/generate_brand_icons.py` from the two checked-in masters in
    `whisperflow/assets/brand/` — head → menubar template pair, head-chest → app icons on every
    platform including the four `verbal-mobile/assets/` files. The old generators —
    `generate_icons.py`'s mic art and `generate_app_icon_flume.py`'s terracotta "F" — are superseded
    for these assets. Two hard-won details live in the new script: the masters carry a baked
    rounded-rect + shadow, so every square icon must be recomposed from a color-distance CUTOUT of the
    bird, never a flatten of the master; and the macOS menu-bar template silhouette must knock the
    near-black feature pixels (eye/beak) out as HOLES — template rendering uses only the alpha channel,
    and a solid fill of the head reads as a shapeless flame blob at 22-44px.) Both the mac (`sips`+`iconutil` →
    `.icns`) and Windows (PIL → `.ico`) build pipelines read `assets/icon.png` for years, which is why
    the Dock/Finder/DMG/installer icon looked blank/wrong the whole time (found and fixed 2026-08-23,
    alongside the Flume rebrand) — a 44px monochrome glyph scaled up to a 512px app icon just looks like
    a smudge. The real app icon is generated separately: `whisperflow/scripts/generate_app_icon_flume.py`
    → `assets/app_icon.png` (1024x1024, terracotta background + Geist Bold "F"); every `sips`/PIL
    conversion step in `.github/workflows/build-release.yml`, `build-mac-app.yml`,
    `build-windows-exe.yml`, and the inline conversion in `verbal-win.spec` must point at that file, not
    `assets/icon.png`. **A second, separate icon-conversion step existed and had to be fixed too** —
    `build-release.yml`'s Windows job has its own standalone "Convert icon to ICO" CI step that runs
    BEFORE PyInstaller and pre-creates `assets/icon.ico`; `verbal-win.spec`'s own inline conversion only
    fires `if not os.path.exists(icon_ico)`, so fixing only the spec file left that earlier CI step
    silently overriding the fix back to the wrong source — check for every place an icon gets converted,
    not just the first one you find. Mobile had the analogous bug: `verbal-mobile/assets/icon.png` was
    literally Expo's unreplaced default placeholder template (grid lines + guide circles) the whole time;
    fixed via `verbal-mobile/scripts/generate_app_icons.py`, which also correctly follows Expo's actual
    per-platform convention (a full-bleed opaque square for iOS/`icon`, vs. a transparent-background
    foreground-only layer sized to the ~66% safe zone for Android's `adaptiveIcon.foregroundImage`) rather
    than reusing one image for both, which was the mobile app's second bug.

62. **The Hardened Runtime gates microphone (and camera, and Apple Events) behind ENTITLEMENTS —
    without `com.apple.security.device.audio-input` in `entitlements.plist`, macOS never shows the mic
    permission prompt, never lists the app in System Settings > Privacy & Security > Microphone, and
    hands the recorder pure silence (peak=0.0000).** This was the root cause of the shipped app's dead
    mic across every notarized release up to v1.0.22 (fixed 2026-08-25). The killer property of this
    bug class: **local dev builds are ad-hoc signed WITHOUT the hardened runtime, so they have no
    entitlement gate and every local test passes** while every CI build fails identically in users'
    hands — testing mic/camera/AppleEvents behavior requires a build signed with
    `--options runtime --entitlements entitlements.plist`, launched via `open` (a Terminal-child exec
    inherits the terminal's TCC identity and lies to you). Same rule got
    `com.apple.security.automation.apple-events` added (tccd names the mechanism outright in its log:
    "Prompting policy for hardened runtime; service … requires entitlement … but it is missing").
    Screen Recording is NOT entitlement-gated, which is why it kept working and made the mic bug look
    impossible. Diagnostics gotchas that hid this for a whole day: zsh has a `log` BUILTIN that shadows
    `/usr/bin/log` (bare `log stream` fails with "too many arguments" — always call `/usr/bin/log`),
    and `tccutil reset` does not affect a RUNNING process (AVFoundation caches the authorization verdict
    per-process — relaunch before re-testing).

63. **Objective-C class definitions are PROCESS-GLOBAL — a `class X(NSObject)` inside a factory function
    crashes with "overriding existing Objective-C class" the second time any window calls it.** Memoize
    the class in a module global (`flume_web_dashboard._ui_delegate_class`). The live failure: the
    meeting window installed its WKUIDelegate after the dashboard already had, the install raised, and
    with no delegate its JS `confirm()` silently resolved false — the meeting widget's discard/delete
    button was a permanent no-op (2026-08-25).

64. **`sys.exit()` from a non-main thread only kills THAT thread.** Every updater/install path runs on a
    worker thread (native alert's daemon thread, the dashboard bridge), so `sys.exit(0)` left the app
    running and the mac update helper polling `kill -0` forever — "Installing…" stuck until the user
    happened to quit by hand. `updater.install_update` uses `os._exit(0)` (safe: config writes are
    atomic, rule #3). Anything else that must terminate the app from a worker thread has the same
    choice: hop to the main thread or `os._exit`.

65. **Incremental cloud caches keyed on a `created_at > watermark` can never see rows MERGED or
    BACKFILLED into the account** — backfilled rows land with timestamps older than an
    already-advanced watermark. `insights._refresh_cloud_locked` self-heals (a watermark with an empty
    fold rewinds to a full re-scan); any future watermark-style cache needs the same escape hatch. Live
    case: the 2026-08-15 account merge moved 772 transcriptions in after the first refresh had already
    advanced `last_ts`, and Insights showed two days while seven weeks sat invisible.

66. **Never put a native `<select>` in a constrained modal — WebView2 draws it as an OS popup.**
    Chromium/WebView2's combo list is a system window: it ignores CSS `overflow`, `z-index`, and the
    parent modal's bounds. On the New Meeting screen that list painted through the footer and covered
    **Start recording**, with the last languages fading off the bottom of the window. WKWebView on
    macOS is more forgiving, which is why the bug only showed up in the Windows port of the same
    `meeting_html.py`. The pre-meeting language control is now a custom listbox (`#preLangBtn` +
    `#preLangMenu`, sibling of `.prePanel`, `position:fixed`, max-height clamped to the webview,
    opens upward so it cannot cover the Start button). Apply the same recipe to any picker that
    sits above a primary action in a pywebview window. Settings-page `<select>`s are fine: they
    live on a scrolling pane with room below.

67. **Every Windows pywebview window that is built once and re-used MUST handle `events.closing`
    (hide + cancel) and `events.closed` (drop the handle).** pywebview's winforms backend DESTROYS the
    form on the title-bar X / Alt+F4 (`Form.Close` → the BrowserView leaves `webview.windows`), while
    our `self._window` keeps pointing at the corpse — and `Window.show()` on a dead uid is a **silent
    no-op** (`gui.show(uid)` finds no instance; nothing raises). That is why "Start meeting" on Windows
    logged `meeting open: ready=True skipped=False`, called `show()`, and nothing appeared, forever,
    after the first close (2026-08-26). `WinMeetingWindow` and `WinPopover` now follow the same recipe,
    which any new pywebview surface must copy: (a) `closing += _on_closing` — runs synchronously ON the
    WinForms UI thread; it `hide()`s (mid-meeting it collapses to the bar instead, macOS
    `windowShouldClose_` parity) and **returns False** so pywebview sets `FormClosingEventArgs.Cancel`.
    Keep it trivial: `hide()` is safe there (Control.Invoke on the owning thread) but **`evaluate_js` —
    hence `emit`/`set_layout`/`_refresh` — deadlocks the UI thread**; anything touching the page goes
    through `app._on_main`. Let programmatic teardown through: `self._destroying` (set by the class's
    own `destroy()`) or `app._exiting` (`_hard_exit`'s generic `webview.windows` destroy sweep, #59b).
    (b) `closed += _on_closed` — the safety net when the form dies anyway: reset every reference
    (`_window`, api/bridge, `_page_ready`/`_loaded`, `_visible`, pending queues) so the next `show()`
    rebuilds; take the build lock (it runs on a pywebview thread). (c) `show()` first checks
    `_window_alive()` — `self._window in webview.windows`, since pywebview prunes that list BEFORE
    `closed` fires — and rebuilds once on a stale handle; there is deliberately NO
    "show() raised → rebuild" fallback because show() never raises on a dead handle and a rebuild on
    the `shown` timeout would orphan a second form. (d) `_wait_shown()` bounds the wait for the fresh
    form's `shown` Event to `SHOWN_WAIT_S` (5 s): every `Window` method show() calls next (`resize`/
    `move`/`show`) is `_shown_call`-decorated and blocks **20 s each** when Shown never fires (WebView2
    runtime mid-update) — a silent ~60 s freeze per click became one warning + early return, handle
    kept for the next retry. (e) set `_visible = True` BEFORE `_wait_shown()` (not merely before
    `.show()`) — `_on_loaded` fires on a pywebview thread during the Shown wait and hides the window
    when `_visible` is False, so a first-open load-during-wait used to hide the window we were about
    to show. If Shown times out, set `_visible` back to False. (f) **Veto USER closes only.** pywebview's `closing` Event hides the `CloseReason`, and WinForms
    routes Windows shutdown/log-off (`WM_QUERYENDSESSION` → `WindowsShutDown`), Task Manager "End task"
    (`TaskManagerClosing`) and `Application.Exit` through the same `FormClosing` — hidden forms
    included. Cancelling those parks Windows on "Flume is preventing you from shutting down" (review of
    the same-day fix). So `_build` also subscribes a NATIVE `FormClosing` handler on
    `self._window.native` (`_attach_native_closing`; `create_window` is synchronous for non-master
    windows so `.native` is already the `BrowserForm`) — it runs after pywebview's, and for every
    `CloseReason` other than `UserClosing` sets `_destroying = True` and clears `args.Cancel`.
    (g) **`SharedDashboard` still needs `_window_alive()` even though X is *supposed* to destroy.**
    Dashboard close is destroy-and-rebuild (the hotkey must keep working with no window), and
    `_on_window_closed` drops the handle — but `Window.show()` does not raise on a dead uid, so a
    reopen that races `closed` (or a missed hook) was the same silent no-op as Start meeting. `show()`
    checks `self._window in webview.windows` and rebuilds; `_device_refresh_loop` is latched once
    (`_device_refresh_started`), not spawned on every rebuild. **Known race (2026-08-28, unfixed):**
    with the persistent WebView2 profile (`private_mode=False, storage_path=…`), a window CREATED
    within ~2 s of another window's `destroy()` can have its WebView2 init bail and Close the fresh
    form (observed in the smoke harness: "close intercepted" 2 s after a rebuild; the fresh dashboard
    closed itself). Test-only in practice — the user path hides windows, destroy happens at quit —
    the smoke's rebuild steps settle 6 s and retry once; if a real destroy→recreate flow ever ships,
    it needs a settle or a re-init retry.
    (h) **Minimize mid-meeting collapses to the bar, and the interception has its own traps
    (2026-08-28 report — "when I minimize it should only show that record and time button not the
    whole window").** `WinMeetingWindow._attach_native_minimize` subscribes a native `Resize` handler
    (`_on_native_resize`); when `WindowState` hits `Minimized` while `_recording_active()`, it
    collapses to the bar (macOS parity: losing key while recording auto-collapses) — idle minimize
    stays a plain taskbar minimize. Two rules inside the handler: a **re-entrancy guard**
    (`_minimize_intercepting`) is mandatory, because assigning `WindowState` back inside a Resize
    handler fires Resize again; and the WHOLE `set_layout("bar")` is deferred via `app._on_main` —
    `set_layout` emits to the page FIRST when entering the bar (so expanded content is never shown
    clipped inside the pill) and `emit` → `evaluate_js` would deadlock the UI thread the handler runs
    on, exactly as in (a). The cost is a brief flash of the restored window before it snaps to the
    pill — accepted, because inverting the order clips the page. Fail-closed: no hook → a plain
    minimize; anything else failing → at least restore `WindowState.Normal`, because a live recording
    must never run invisibly.

68. **No glibc-only `strftime` directives — the Windows CRT raises `ValueError("Invalid format
    string")`.** The `-` (no-pad) flag family (`%-d`, `%-I`, `%-m`, `%-H`, …) is a glibc/BSD extension,
    not C89; Python's `time.strftime` hands the format to the platform CRT, so it works on macOS and
    blows up on Windows. `MeetingSession.__init__`'s default title used `'%b %-d, %H:%M'`, so every
    meeting started on Windows without a typed title failed with "manager start failed: Invalid format
    string" (2026-08-26). Build unpadded fields from the struct instead (`lt = time.localtime()`;
    `f"{time.strftime('%b', lt)} {lt.tm_mday}, {time.strftime('%H:%M', lt)}"`) — `tm_mday`/`tm_hour`
    are already unpadded everywhere — or `.lstrip('0')`. Grep for `%-` before shipping any shared
    module's date formatting; the code path is identical on both platforms, only the CRT differs.

69. **The shared `DashboardApi` reads host-app state by ATTRIBUTE NAME — every attribute it touches must
    exist on BOTH `VerbalApp` (main.py) and `VerbalWinApp` (win_main.py), and a Windows-only "one-shot"
    is not a schedule.** Two halves, one report (Flume 1.0.33 never saw 1.0.34, 2026-08-26):
    (a) `get_update_status` read `app._update_available/_update_phase/_update_progress` directly, and
    Windows only had `_pending_update` — so every 30 s dashboard poll raised `AttributeError` into the
    log for the whole session and the in-app banner / Settings › Updates button were dead there. Fix on
    both sides: `VerbalWinApp` now owns the SAME state machine (`_update_available`, `_update_phase`,
    `_update_progress`, `_update_ready_path`, `_update_download_lock`; `_pending_update` survives as a
    read/write **property alias** so the tray badge/menu code reads the same state), and the bridge
    reads with `getattr(..., default)` / `callable()` checks and returns `_err` instead of raising —
    a host without the machine reports "no update", never a traceback. When you add a field to one
    app class, add it to the other in the same change (or make the bridge tolerate its absence).
    (b) The Windows startup check was **permanently defeated by two guards stacked on each other**:
    `updater.check_for_update()` returns `None` for the first 30 s after launch (the auto-install-loop
    gate keyed off `sys._verbal_start_time`), and `win_main._check_update` fired its ONLY check at
    t=0 — inside that gate — then set a once-per-session flag that turned every later call into a
    no-op. Net effect: the Windows app never asked Supabase at all. Now: `_update_check_loop` (daemon;
    first check after `UPDATE_STARTUP_DELAY=35` s, then every `UPDATE_CHECK_INTERVAL=4 h`, mirroring
    main.py's `rumps.Timer`), no session flag, and **`check_for_update(force=True)` for every explicit
    click** (dashboard button on both platforms, mac menubar "Check for Updates…", the new Windows
    tray "Check for updates..." row) — a human clicking cannot produce the loop the gate guards
    against, and a gated click was a silent no-op / a false "You're up to date". Lessons: a gate that
    returns `None` for "too early" is indistinguishable from "no update", so callers that skip a check
    must be *scheduled* to try again; and `DashboardApi.check_for_updates` is now **synchronous,
    bounded by `CHECK_UPDATES_WAIT_S=8 s`** and returns `available`/`version` — the old fire-and-forget
    + a fixed 1.5 s JS poll toasted "You're up to date" and then grew a banner on the next 30 s poll
    whenever Supabase took >1.5 s (safe to block: both bridges run API calls on their own daemon
    thread). Two adjacent latent bugs fixed in the same pass: `updater.py` imported `time` INSIDE
    `check_for_update`, so `download_update`'s retry backoff raised `NameError` on the first transient
    error and the 3-attempt retry never happened; and `main.py::_start_update_download`'s thread had no
    try/except, so a raise left the banner stuck at "Downloading… N%" until relaunch — both now land on
    phase `'failed'` (banner offers Retry).

70. **Dashboard tab indices are one map, and callers pass NAMES.** `DASHBOARD_TAB` in
    `shared_dashboard.py` is the single `{int → screen-id}` used by both `FlumeWebDashboard` (Mac) and
    `SharedDashboard` (Windows). They had drifted — Mac `3=settings`/`4=canvas`, Windows the reverse —
    so the Windows tray popover's Preferences button (`_open_tab(3)` with a "settings" comment) opened
    Canvas. Call `dashboard.show_tab("settings")` / `"canvas"` / `"notes"` from the menubar, tray, and
    popover; do not pass a raw index. `win_bugs_fixtures.py` asserts the map and the popover wiring.

80. **Shared HTML renderers must route every user-visible platform-ism through the platform seam — no
    hardcoded "This Mac", no raw ⌘ chords.** The Flume surfaces were written Mac-only and the literal
    strings survived the Windows port: the dashboard's sidebar/canvas/settings/wizard all said
    "This Mac" on a Windows box (2026-08-28 report — "why is it showing mac? whose mac is that?"),
    and `meeting_html`'s shortcut hints showed ⌘ chords. The seam already existed for keys —
    `flume_dashboard_html.py` injects `PL_KEYS` (the per-platform key-label table) and `IS_WINDOWS`
    ahead of the body — so the fix extends it rather than sprinkling ternaries: **`THIS_DEVICE` /
    `THIS_DEVICE_LC`** ("This PC"/"this PC" vs "This Mac"/"this Mac") are injected beside
    `IS_WINDOWS` (the tray popover needs no const since its 2026-08-29 rewrite into the menu-style
    flyout — its labels come from live `popover_state()`, which is the seam there);
    `meeting_html.py` builds chord labels from Python `_MOD`
    for the static HTML plus a JS `MOD` mirror (from `IS_WIN`) for re-rendered hints — the two must
    agree. Two details worth keeping: on Windows the chord label is **"Ctrl+"**, never a ⊞ glyph —
    the keydown handlers fire on `metaKey||ctrlKey`, the Win key is OS-reserved (Win+. is the emoji
    picker) and browsers surface it as `metaKey` inconsistently — and there is a deliberate style gap
    ("⌘." vs "Ctrl+."); the JS mirror writes the mac symbol as the `\u2318` escape so the raw glyph
    never lands in the Windows page bytes. `scripts/win_smoke_isolated.py`'s `rendered_strings` step pins all of
    this: on Windows, `flume_html()` must contain "This PC", no "This Mac", and no `⌘` outside the
    runtime-guarded `IS_WINDOWS?'Ctrl+V':'⌘V'` ternaries; `meeting_html()` must say "Ctrl+." with
    zero `⌘`. Any new user-visible platform word or key glyph in a shared surface goes behind this
    seam in the same change.

## Design system (Flume)

Single source: desktop `app/theme.py` + `app/fonts_css.py`; mobile `flume-ui/theme/`. Also
`DESIGN_SYSTEM.md` at repo root.

- **Fonts:** **Geist** for all UI text; **JetBrains Mono** only for numerics + meta labels (timers,
  counts, UPPERCASE tags/eyebrows).
- **Base surface:** near-black (e.g. `#1a1512` / `rgba(22,20,18,…)`), light text `#f4f3f1`.
- **Accent:** `#C85A3E` (terracotta) — used sparingly. (Historic `#E8522A` is retired; Rule #16.)
- **Pastel stat-card palette** (dashboard "fcards", the Notes Studio "scards" (v3.1), and the auto-learn
  widget matches `cream`):
  - `cream` `#EADFCE` (ink `#2a1f18`) — "Words today"
  - `sage` `#DDE4D3` (ink `#1e2418`)
  - `plum` `#e6dae4` (ink `#221820`)
  - `slate` `#d7dfe9` (ink `#182029`) — added for the Notes Studio Export card (v3.1); scards only so far
  - fcards' icon disc = the ink color inverted (near-black bg, pastel glyph); scards use a translucent
    ink-tint disc instead (`rgba(ink,.13)`).
  - **Studio card geometry (`.scards .scard`, 2026-08-26 "align these icons"):** cards are **top-anchored**
    and equal-height — `min-height:108px`, `gap:7px`, `justify-content:flex-start`, `.sdisc{margin-bottom:0}`
    (the old `margin-bottom:auto` pinned title+description to the card's BOTTOM edge, so a two-line
    description drew its title ~2 px higher than its row-mate), and the description **reserves two lines**
    (`.ss{min-height:calc(2 * 1.35em)}`) so 1- and 2-line copy yield identical cards. The Export card's
    popup anchor `.nmenuwrap` is a `<div>` that is `display:flex; flex-direction:column; position:relative`
    with the card `flex:1 1 auto` — NOT `display:block` + `height:100%`: WebView2 resolved that percentage
    height differently from the bare sibling cards and rendered two card heights in one row. The grid is
    `align-items:stretch`. Applies to both Studios (Notes and Meeting detail).
- **Auto-learn widget** deliberately uses the `cream` card language (cream pill, dark ink, near-black
  "Add to dictionary" button) — not orange/black — per user preference.

## Dead / legacy / inconsistent code to IGNORE

**Desktop (`whisperflow/app/`):**
- `dashboard.py` (`DashboardWindow`, ~3178 lines) — legacy AppKit dashboard, only a fallback if
  `FlumeWebDashboard` fails to construct. Superseded by the WKWebView Flume dashboard.
- `history_window.py` — legacy standalone AppKit history window; not referenced.
- ~~`flume_popover.py` (`FlumePopover`, `_StatusClickHandler`, `_POPOVER_METHODS`)~~ — **DELETED in
  IDI-183.** The macOS menubar is a native `NSMenu` (`menubar_menu.py`); left-click opens it again, so the
  left/right-click split and the retrying `_install_popover_hook` timer are gone too.
  **`flume_popover_html.py` is NOT dead** — it is now Windows-only (`win_popover.py` renders
  `popover_html()`) plus `_mark_data_uri()`, which `flume_dashboard_html.py` imports for the sign-in
  pane's logo. It stays in **both** spec files' `hiddenimports`.
- `main.py::status_item` and `_status_text()` are gone with the popover: the menubar's counts live in the
  header row's right-hand column, recording/transcribing are derived from app state, and the only thing
  left to say is a transient note via `_status_note("…")` (currently just "Downloading update…").
  `_show_result` lost its `status` argument, which had only ever shadowed the real transcriber status.
  `_total_transcriptions`/`_total_words` are now **write-only on macOS** and must NOT be removed —
  `win_main.py` keeps its own `_status_text()` that reads them for its tray row, and the cross-platform
  `shared_dashboard.py` resets them on clear-history.
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
- **Deleted in MER-46 (2026-08) — the meeting panel's `summary` + `notes` content modes** (~700 lines of
  `meeting_html.py`: `_summary_screen()`, the `#notesRoot` page, `renderSummary`/`renderNotesPage`/
  `renderMarksBox`/`renderTxBox`/`mdRender` and their helpers, and the panel's `openMeeting`/`meeting`
  events). The panel holds ONE mode at a time, so a past meeting fought the live screen, could not be read
  while another meeting recorded, and was yanked back to the ambient bar whenever the panel lost focus
  mid-meeting. The view now lives in the dashboard (`#mtgDetail`, `03-features.md` §Meeting detail) and the
  panel hands off through the bar instead (`set_handoff`). `MeetingWindow.set_mode`/`show` no longer accept
  `"summary"`; nothing may emit `meeting` at the panel again.

**Mobile (`verbal-mobile/`):**
- `_old-flume/` (~27 files) — explicitly legacy.
- **Deleted outright (2026-08, flow-audit batch):** mobile `lib/remoteConfig.ts` + `getGroqKey`/`setGroqKey`
  (IDI-160 — see Hard Rule #15) and desktop `pairing.py::claim_pairing` (IDI-156 — desktop only ever HOSTS
  pairing; the claiming side is mobile `lib/pairing.ts::claimPairing`). Older docs may still reference them.
- **Deleted in the IDI-179 closing pass (2026-08)** — each verified to zero live references first. Older
  docs may still name them; they are gone, do not revive them:
  - mobile `lib/useSync.ts` (superseded by `flume-ui/hooks/historyStore.ts`), `lib/useDeviceSelector.ts` +
    the top-level `components/DeviceSelector.tsx` (superseded by `flume-ui/hooks/useDevices.ts`), the now-
    empty top-level `components/` and `screens/` dirs (all live UI is under `flume-ui/`).
  - mobile `lib/MarkdownText.tsx` and `lib/theme.ts` — the legacy renderer + its stale token file. The live
    notes markdown/checklist renderer is `flume-ui/components/MarkdownNote.tsx` (Notes v2), styled off
    `flume-ui/theme/`.
  - mobile `flume-ui/components/MicButton.tsx` (+ its `components/index.ts` barrel export) — no screen ever
    imported it; the tab-bar mic is drawn by the navigator.
  - the orphaned `onUseCode` prop on `flume-ui/screens/PairDeviceScreen.tsx` (declared, never passed, never
    destructured — the "Enter code instead" flip is internal state).
  - desktop `app/meeting_hud.py` + `app/meeting_hud_html.py` (the original separate floating meeting HUD,
    superseded by `meeting_window.py`'s morphing bar ⇄ expanded panel) together with `main.py`'s
    `_meeting_hud()` accessor / `self.meeting_hud` slot and the `MeetingSession._emit` mirror-emit block in
    `meetings.py` — the HUD had zero call sites, so nothing ever constructed it.
  - desktop `app/canvas_window.py` (`CanvasWindow`) — unreferenced by the app since IDI-178; the canvas is
    the web dashboard's tab 4. `idi172_174_fixtures.py` was its only remaining importer and its §9 gate test
    is now an absence assertion (the "a clear is an explicit empty write, never falsy-dropped" rule is still
    asserted on the two LIVE listeners).
  - desktop `DashboardApi.pin_text` / `DashboardApi.toggle_note_pin` (`shared_dashboard.py`) — zero JS
    callers in either rendered HTML file. NB `clear_history` is **wired** (IDI-172) — keep it; and
    `search_notes` is **NOT dead** — `notes_fixtures.py` asserts its ranking (11 checks) and
    `flume_dashboard_html.py`'s client-side `filteredNotes()` is documented as mirroring it.
- all `flume-ui/hooks/*.mock.ts` — contract references, never imported at runtime. As of IDI-179 every
  `useX.mock.ts` is a verified drop-in for its `useX.ts` (same exported names, params and return fields,
  proven by mutual type-assignability), including the new `useSyncEnabled.mock.ts`. Keep them in sync in the
  same change as the real hook — a drifted mock is worse than none, since it IS the design contract.
- `dist/` — stale web export.
- `flume-ui/components/ConfirmDialog.tsx` **is live** (imported directly by `useAuth`, `SettingsScreen`,
  `RootNavigator`) but intentionally **not** in the `components/index.ts` barrel.

## Verification checklist (run before considering a desktop change done)

```
cd whisperflow
.venv/bin/python -m py_compile app/<changed>.py
.venv/bin/python -c "import app.main"
# on Windows the venv is .venv/Scripts/python.exe; when win_*.py, shared_dashboard.py, config.py
# or updater.py are touched, also import the Windows shell (it is not covered by `import app.main`):
.venv/Scripts/python.exe -c "import app.win_main; import app.shared_dashboard"
# for dashboard/widget JS changes: node --check each rendered <script> block — scripted:
.venv/bin/python scripts/js_check.py       # extracts every inline <script> from flume_html/meeting_html/popover_html
# Windows shell live smoke (safe next to the installed app — isolated USERPROFILE, no mutex, signed out):
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/win_smoke_isolated.py   # update check, meeting X/re-show, bar/expanded layout geometry, minimize-to-bar, rendered platform strings (#80), dashboard rebuild, quit
.venv/Scripts/python.exe win_bugs_fixtures.py   # Windows bug-pass unit fixtures (strftime, update gate, tabs, config lock)
.venv/bin/python win_sysaudio_fixtures.py  # if win_system_audio / meeting sys-audio state touched (fake soundcard, any OS)
.venv/bin/python autolearn_fixtures.py     # if autolearn touched
.venv/bin/python qa_filetags_fixtures.py    # if filetags touched
.venv/bin/python insights_fixtures.py      # if insights/stats touched
.venv/bin/python organizations_fixtures.py # if the team layer or the dictionary merge is touched
node team_dashboard_fixtures.js             # if the Team or Dictionary SCREEN is touched
```

`team_dashboard_fixtures.js` renders `flume_html()`, runs its `<script>` blocks in a `vm` context over a
thin DOM shim, and asserts on the produced markup — 58 checks covering the ranking, the app-mix panels,
both dictionary scopes and every empty state. It exists because the bugs that reached the user on this
surface were all *rendered* bugs (a blank card, a missing control, a privacy string that had gone false),
which no Python check can see.

Mobile: `npx tsc --noEmit` in `verbal-mobile/`.

## Where the deep specs live

- `AUTOLEARN_DICTIONARY_SWARM.md` — the auto-learn feature spec (mission, algorithm, failure table, swarm).
- `FILE_TAGGING_SWARM.md` — the file-tagging feature spec.
- `GOOGLE_AUTH_SETUP.md` — auth provider setup facts (accurate table inventory).
- `DESIGN_SYSTEM.md` — design tokens.

- **Meeting `self` speaker label:** never hard-code "You". Desktop → `app.meetings.self_speaker_label(config)` /
  `with_self_name(speakers, config)`; mobile → `selfSpeakerName()` / `withSelfName()` in `lib/meetings.ts`.
  Older rows persisted the literal "You" — treat that string as a placeholder, not a user rename (2026-08-28).

71. **pywebview 5.3 (pinned in `requirements-win.txt`) mixes units: `create_window(width, height)` and
    `Window.resize()` are PHYSICAL pixels, `Window.move()` is LOGICAL, and `min_size` is set before
    `AutoScaleMode.Dpi` so WinForms doubles it itself.** Measured 2026-08-28 on a 200 % display: the
    880×620 meeting window rendered a 440×310 CSS viewport ("the meeting-name popup is square, options
    don't fit"), the 560×54 bar a 280×27 one (only dot + timer visible), and a pre-scaled `min_size`
    pinned the window to the whole work area. Rules: size pywebview windows through
    `app/win_geometry.py` — `create_size()` for width/height (identity on pywebview ≥ 6, which scales
    itself), **logical** values for `min_size`, and `set_window_rect()` (one `SetWindowPos` in physical
    px from `GetDpiForWindow`) for any runtime geometry. Never read `form._scale` (6.x only) or
    `form.scale_factor` (5.x only) directly. When testing on a HiDPI box, also make the screenshot
    process DPI-aware or `CopyFromScreen` captures only the top-left quarter.

72. **Windows tk dialogs: always `parent=root`, never on the pystray / inject / UI thread.** Every throwaway
    `tk.Tk(); root.withdraw(); messagebox.*(...)` MUST pass `parent=root` — without it tkinter's commondialog
    uses `_default_root`, which is the FIRST `Tk()` in the process = the overlay's root on the `overlay-tk`
    thread, so the recording pill's mainloop froze for as long as the box was open (and hung forever if that
    thread had died). pystray runs menu callbacks synchronously on its message loop, so tray rows that open a
    dialog (`_tray_about`, `_tray_open_update`) run it on a daemon thread; the paste-blocked prompt is
    invoked inline from the inject path by `paste_guard`, so `_prompt_paste_blocked` spawns the dialog and
    returns at once (a modal there kept `_processing` True → next hotkey refused). Review 2026-08-28.

73. **Updater rules (Windows) — 2026-08-28 review.** (a) `updater.check_for_update()` returns `None` for
    BOTH "current" and "failed"; read `updater.LAST_CHECK_FAILED` before clearing update state or saying
    "You're up to date" (a dead network used to drop the badge/parked installer and claim current).
    (b) `_is_newer` returns **False** on an unparsable version — "v1.0.37"/"1.0.37-hotfix" in `app_versions`
    would otherwise be "newer" on every 4-h check → download + silent reinstall + restart forever.
    (c) `_download_and_install` waits for `_app_busy()` to clear on BOTH the silent and the dialog-"Yes"
    path (the dialog pops unsolicited; "Yes" then dictating must not be killed by `os._exit`). (d) Dialog
    "Yes" while an installer is already parked (`ready`) installs it instead of re-downloading.
    (e) `_hard_exit` releases the singleton mutex FIRST so a relaunch during the ≤1.5 s teardown wins
    the mutex instead of signalling the dying process. (f) The mutex probe uses
    `ctypes.WinDLL("kernel32", use_last_error=True)` + `ctypes.get_last_error()`. (g) `verbal-setup.iss`
    taskkills `Flume.exe` WITHOUT `/T` — the app-launched installer is a child of Flume.exe.

74. **`load_config()` marks a defaults dict served while `config.json` was unreadable
    (`config[UNREAD_DEFAULTS_KEY]`) and `save_config()` refuses it regardless of the module flag.** The
    flag alone cleared as soon as any later `load_config()` read the file cleanly (auth/dashboard call it
    constantly) while `VerbalWinApp.config` still held the factory-default dict — the next `save_config`
    then wrote it over the real file (signed out, history gone). Also: `.prev` recovery decodes utf-8-sig.

75. **Windows meeting bar hover/anim invariants.** `_start_hover_watch` uses a generation counter (never
    `is_alive()`), the loop `continue`s on transient errors, `show()` restarts it (hide() ends it), and both
    hover and shrink-wrap are suspended while `native_confirm` is modal (`_modal`). Geometry uses the
    PRIMARY monitor's scale (`system_scale()` — the target is `SPI_GETWORKAREA`), animations start from the
    live width (`_bar_cur_w`), entering the bar emits `layout` BEFORE resizing and keeps the last measured
    width (no 560 px strip flash), and the bar is shown with `SW_SHOWNOACTIVATE` (non-activating like the Mac
    panel). `WinPopover` sizes/positions through `win_geometry` too (was half-size + off-screen at ≠100 %).

76. **WASAPI loopback blocks while silent — keep a silence player running.** (`win_system_audio.py`,
    2026-08-28.) A loopback IAudioClient yields NO frames while the endpoint plays nothing, so a blocking
    `soundcard` `record()` can outlive `stop()`'s 2 s join and leave the handle open until process exit
    (next `start()` → device-in-use). While capture runs, `_SilencePlayer` writes zero blocks
    (`sc.default_speaker().player(rate, channels, blocksize=480)`, 10 ms) into the default output — zeros
    add nothing to the mix, but the loopback stream keeps producing, so `record()` returns within one
    block and `stop()` is deterministic (join < 2 s, idempotent, always clears state; a stuck handle is
    logged at WARNING instead of hanging). Second half: a device unplug / `AUDCLNT_E_DEVICE_INVALIDATED`
    (soundcard raises `RuntimeError('Error 0x88890004')`) or a default-output switch (WASAPI keeps the
    OLD endpoint's stream alive but silent — detected by polling `default_speaker().id` every 2 s) must
    NOT silently `break` the loop: the supervisor sets `.error`, logs WARNING, re-resolves the default
    loopback device and restarts under `RestartPolicy` (3 attempts × 1 s backoff, budget refunded after
    10 s healthy). Retries apply only AFTER one successful segment — a first-segment failure is a
    `start()=False` (no orphan thread keeps calling back after `meetings.py` went mic-only). Exhausted →
    `.running=False` + `.error`, which `MeetingSession._sys_audio_state()` logs once and emits as
    `sysErr` on the `elapsed` tick. Nothing in the capture thread may propagate (Rule #1). Pinned by
    `whisperflow/win_sysaudio_fixtures.py` (fake `soundcard` in `sys.modules`, runs on macOS).

77. **Windows tk pills: calls that arrive before the root exists are QUEUED and replayed on the tk thread.**
    `WinOverlay` / `WinAutoLearnWidget` build their `tk.Tk()` on a daemon thread, so `show()` /
    `show_briefly()` / `hide()` from the hotkey or inject thread can land before `_root` exists — a hotkey
    in the first ~0.5 s after launch recorded with NO pill and its "Pasted…" toast was silently dropped
    (`_safe()` early-returned on `_root is None`). Both widgets now own an `app/tk_pending.PendingCalls`:
    `_safe(fn)` → `dispatch(fn, post)` queues in order (bounded, 32, oldest dropped) until ready, then is
    `root.after(0, fn)` exactly as before. The ready flip + replay run via `root.after(0, _replay_pending)`
    scheduled right before `mainloop()` — i.e. **inside** the loop — because a cross-thread `root.after`
    blocks in Tcl's `WaitForMainloop` until the loop runs; replayed callables are executed directly on the
    tk thread before control returns to the event loop, so anything posted concurrently after the flip is
    processed strictly after the replay (order preserved, no lock held across tk calls). A queued
    `show_briefly` arms its auto-hide at replay time (the closure calls `_schedule_hide` when it runs), not
    at enqueue time. `_run_tk`'s `finally` and the new `cleanup()` call `close()`, which drops the queue and
    refuses further dispatches — so a replay can never race exit, and a failed `setup()` leaks nothing.
    `_show_internal` / `_fade_in` / `_fade_out` / `_schedule_hide` / `_start_animation_loop` gate on
    `_tk_ready()` (root exists AND ready). Tests: `tk_pending_fixtures.py` (pure Python, no tkinter).
    Still true: tkinter objects are touched ONLY from the owning tk thread — the caller thread never
    calls tk methods, ready or not.
78. **Windows clipboard restore: only after the paste was consumed, never on the fallback path.**
    `win_injector.inject_text` snapshots clipboard TEXT before copying the transcript and restores it on a
    daemon thread ≥ `CLIPBOARD_RESTORE_DELAY_S` (0.4 s) after Ctrl+V — restoring synchronously makes the
    target paste the OLD clipboard. The restore is a no-op unless the clipboard still holds our transcript
    (`GetClipboardSequenceNumber()` unchanged AND text equal). It is skipped when the paste was blocked
    (UIPI) or raised, and for `_on_sync_receive` (`restore_clipboard=False`) — on those paths the transcript
    MUST stay on the clipboard for a manual Ctrl+V. Non-text/empty/locked clipboards → no snapshot → no
    restore. Gate: `config["restore_clipboard"]` (default True). All of it is `try/except` + `logger.debug`;
    the paste has always already happened. Decision logic is the pure `should_restore_clipboard()`; any
    change to it must keep `win_bugs_fixtures.test_clipboard_restore_decision` green (runs on macOS via ast).

79. **Deep links go through `app/deep_link.py`, never straight into UI code.** New `flume://` routes get a
    parser + a `handle()` branch there (fail-closed, config-parked state, dashboard driven via
    `show/show_tab/emit`), so macOS (Apple Event) and Windows (argv/second-launch) stay one implementation.
    Web landing pages that try a custom scheme MUST keep the token in the fallback URL and MUST offer both
    actions as buttons — scheme detection is a heuristic (visibility/blur within ~1.6 s), not a fact.

80. **Every Realtime WebSocket passes `sslopt=ws_sslopt()` (`app/supabase_config.py`).** `websocket-client`
    verifies TLS against OpenSSL's default CA path, which is EMPTY on macOS python.org/PyInstaller builds,
    while httpx uses certifi — so REST worked and every `wss://…/realtime` connection died with
    `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`. Symptom: pushes succeed, nothing is
    ever received (phone dictations never reached the Mac, 2026-08-25 → 08-30, 50k log lines before anyone
    looked). Four sites: `sync.py`, `dashboard.py`, `flume_web_dashboard.py`, `shared_dashboard.py`. When
    "sync doesn't work", grep `app.log` for `CERTIFICATE_VERIFY_FAILED` first.

## Claude Code agent team (`.claude/`, 2026-09-01)

Repo-checked-in agent definitions and skills for parallel/reviewed work:

- `.claude/agents/security-fixer.md` — implements a group of security tickets in an isolated worktree;
  one fixer per non-overlapping file area, must run the verification checklist above.
- `.claude/agents/security-reviewer.md` — adversarial read-only review of a fixer's diff (re-runs
  verification itself); verdict PASS/FAIL per ticket, MERGE / FIX FIRST overall.
- `.claude/agents/platform-parity.md` — quality gate: checks a feature exists and behaves the same on
  Mac / Windows / iOS / Android (app AND keyboard/IME separately) against the matrix in `01-product.md`.
- `.claude/skills/security-batch/SKILL.md` (`/security-batch`) — orchestrates the parallel security-fix
  run for the 2026-08-29 audit tickets: 4 file-disjoint groups (Edge Functions / desktop Python /
  mobile TS / CI), fix → adversarial review → sequential merge → Linear close-out. Live Linear state
  overrides the grouping written in the skill.
