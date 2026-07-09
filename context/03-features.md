# 03 — Features & Implementation

> Part of the `context/` knowledge set. See `context/README.md` for the maintenance rule.
> **Keep this current:** when you add/change a feature, update its section here (desktop + mobile impl,
> status, limitations) AND the matrix in `01-product.md`. Reference code by file/function, not pasted code.

Each feature: **what it does · desktop impl · mobile impl · backend · status/limitations.**

---

## Recording & transcription

- **What:** capture mic audio, produce cleaned text.
- **Desktop:** `recorder.py::Recorder` — `sounddevice.InputStream`, mono float32 at the mic's native
  rate (default 48k), capped 300s (keeps the beginning), normalizes to peak 0.5; `toggle_pause` for the
  overlay pause button. The noise-reduction/enhancement chain exists but is **disabled** (it "destroyed
  speech content"). `transcriber.py::transcribe_with_status` returns `(text, status ∈ ok|silent|failed)`;
  silence gate `peak<0.01`. **Fallback chain:** ① Groq `whisper-large-v3-turbo` (each key), ② Gemini
  `gemini-2.0-flash`, ③ local `faster_whisper` (cpu/int8, 16 kHz). `main._transcribe_with_retry` retries
  `failed` ×3 with backoff.
- **Mobile:** `flume-ui/hooks/useRecorder.ts` — `expo-audio` capture + `lib/groq.ts::transcribeAudio`
  (Groq `whisper-large-v3-turbo` only; no Gemini/local). `stop()` **persists audio first** (so a failed
  transcription is never lost → `status:'failed'`, retryable), transcribes, stashes the full result in a
  module-level `lastRecording` read once via `consumeLastRecording()`.
- **Backend:** none for transcription itself (API calls to Groq/Gemini). Audio → `recordings` bucket.
- **Status:** solid. Local Whisper is a desktop-only offline fallback (`faster_whisper` bundled).

## AI cleanup / formatting

- **What:** turn a raw transcript into clean, correctly-formatted text without adding content.
- **Desktop:** `ai_cleanup.py::process_text` — ① `clean_raw_transcript` (regex: strip hallucinations,
  fillers, doubled words; capitalize; terminal punctuation), ② LLM format via Groq
  `llama-3.3-70b-versatile` (`cleanup_with_groq`) → Gemini fallback with key rotation. `SYSTEM_PROMPT` =
  17 rules ("you are a TEXT FORMATTER, not an assistant"). Separate `NOTES_FORMATTER_SYSTEM_PROMPT`.
- **Mobile:** `lib/groq.ts::formatText` (same `llama-3.3-70b-versatile`) — used on **retry** and where
  screens call it. `formatNotes` exists but is **not wired** into the note editor (mobile notes stored raw).
- **Status:** desktop runs cleanup on every dictation; mobile is lighter (copy raw, format on retry).

## Custom dictionary (vocabulary + replacement rules)

- **What:** two mechanisms — **vocabulary** biases the model toward names/terms; **replacement rules**
  deterministically rewrite a misheard word (`{from,to}`).
- **Desktop:** `dictionary.py` — `build_prompt` ("Glossary: w1, w2, …", ≤180 words) injected into the
  Whisper `prompt`; `apply_replacements` (word-boundary, case-insensitive `re.sub`); `add_replacement`
  de-dupes by `from`, tags auto rules `auto:True` (✨ in UI). Stored `config["dictionary"]`, synced to
  Supabase `dictionary` (one row/user) via `fetch_remote`/`_push_remote`.
- **Mobile:** `lib/dictionary.ts` — direct mirror (`buildPrompt`, `applyReplacements`, `addReplacement`,
  `fetchRemote`), AsyncStorage `flume_dictionary` + Supabase upsert. Managed in `SettingsScreen`.
- **Backend:** `dictionary` table (`user_id` PK, `vocabulary` jsonb, `replacements` jsonb, `updated_at`).
- **Status:** full parity. Rule shape `{from, to, auto?}`.

## Snippets (spoken trigger → text expansion)

- **What:** a generalization of replacement rules — a spoken `trigger` **phrase** expands into a longer
  saved `expansion` block (LinkedIn URL, email signature, scheduling link, disclaimer). Spoken naturally
  inside normal speech (no command syntax); expands in place, rest of the sentence untouched. Stored on
  the same per-user `dictionary` row (third array beside vocabulary + replacements).
- **Desktop:** `dictionary.py` — `apply_snippets(text, config, save_config_fn=None)` (phrase-boundary,
  case-insensitive, multi-word aware) plus CRUD `add_snippet`/`update_snippet`/`remove_snippet`/
  `get_snippets` (dedupe by trigger, mirror `add_replacement`). Runs in `main.py` **after**
  `ai_cleanup.process_text` and **before** injection. Match rules: **longest trigger first** (so a
  substring trigger can't shadow a longer one) and **single pass only** — an inserted expansion is never
  re-scanned (no recursive/nested expansion, no cascades or loops). On each match the snippet's `used`
  counter is bumped and persisted. Dashboard **Snippets** tab in `flume_dashboard_html.py`. Assertion
  harness `snippets_fixtures.py`.
- **Mobile:** `lib/dictionary.ts` — direct mirror (`applySnippets`, `getSnippets`, `addSnippet`,
  `updateSnippet`, `removeSnippet`, `Snippet` type), same longest-first/single-pass algorithm and `used`
  bump; `flume-ui/screens/SnippetsScreen.tsx` + `flume-ui/hooks/useSnippets.ts` (mock contract
  `useSnippets.mock.ts`).
- **Backend:** `dictionary.snippets` jsonb column (default `'[]'`), `supabase_snippets.sql` (idempotent
  `ADD COLUMN IF NOT EXISTS`). Snippet shape `{id, trigger, expansion, label, used, created_at, updated_at}`.
  Same sync path as the rest of the dictionary (one row/user, last-write-wins). `_push_remote` preserves
  the sibling `snippets` array so a vocab/replacement save never wipes it.
- **Caps:** `trigger` ≤ 40 chars, `expansion` ≤ 500 chars (match the design mockups; enforced both sides on normalize + CRUD + UI counters).
- **Status:** full parity (desktop + mobile). Fails closed — any `apply_snippets` error returns the text
  unchanged, never breaking the transcribe → inject path.

## Auto-learn from corrections (desktop only)

- **What:** after inserting a transcript, if you fix a mis-transcribed word in the target field, offer to
  add a replacement rule so it's fixed forever. See the spec `AUTOLEARN_DICTIONARY_SWARM.md`.
- **Impl:** `autolearn.py` — **pure core** (stdlib, unit-tested by `autolearn_fixtures.py`):
  `align()` (Needleman-Wunsch token diff), `classify(inserted, edited, config)` → Decision
  `{action: offer|silent_learn|ignore, old, new, confidence, is_proper_noun, reason}`. The intelligence
  (`§2` of the spec): edit-shape gate (**exactly one substitution, no insert/delete** — distinguishes a
  *correction* from a deletion/rephrase) → changed-ratio → **Double Metaphone** phonetic gate → Levenshtein
  orthographic gate → case/punct filter → **common-word filter** (`COMMON_WORDS` = inline set ∪
  `/usr/share/dict/words`, so real words aren't offered, proper nouns are). Anti-nag: `record_offered`/
  `is_declined` in `config['autolearn_declined']`; `apply_observation_guard` drops OS-autocorrect (change
  <300 ms post-insert, no keystrokes).
  - **`EditWatcher`** (AX read-back, daemon thread): armed by `main._arm_autolearn` after injection; polls
    `AXValue` (0.15 s interval, **1.6 s debounce**, 30 s deadline) on the original focused element. Fails
    **closed**: skips secure fields, terminals, and cases where the inserted text isn't found (Electron
    reads are flaky). Never touches the clipboard/injection path.
  - **UI:** `autolearn_widget.py::AutoLearnWidget` — a **non-activating cream pill** (matches the dashboard
    "Words today" card: bg `#EADFCE`, dark ink, near-black "Add to dictionary" button) shown bottom-center;
    never steals focus. Title names the word: *Add "Ramiz" to your dictionary?* / *Replaces "Rameez"…*.
    Add → `main._autolearn_result` → `dictionary.add_replacement(..., auto=True)` + `sounds.play_added()`
    chime + forces the dashboard to re-fetch (`loadDict()`).
  - History-view edits (`DashboardApi.edit_text` → `_learn_from_edit`) run the same `classify()`.
- **Gated by** `config['autolearn_enabled']` (default off). Toggle on Dictionary **and** Settings screens.
- **Known limits:** in-place watching is best-effort — reliable in native Cocoa fields, skipped in
  Electron/terminal/secure. Typo-of-a-typo can still be *offered* (the confirm widget is the user's gate).

## File tagging — spoken filenames → `@name.ext` (desktop only)

- **What:** in a supported IDE, saying a filename inserts a real editor `@`-reference. Spec: `FILE_TAGGING_SWARM.md`.
- **Impl:** `filetags.py` — detect IDE (`supported_ide`: Cursor, Windsurf, VS Code, Antigravity, Kiro via
  bundle-id sets + name match; `TAGGING_IDES`). Harvest open files via **macOS Accessibility**:
  **set `AXManualAccessibility`+`AXEnhancedUserInterface`** on the app element (Electron/Chromium hide
  their web AX tree otherwise), settle ~1.3 s (lazy tree), then a bounded BFS (≤4000 nodes, depth ≤40)
  reads `AXTitle`/`AXDescription` → `name.ext`. `harvest_async` runs the deep walk at record-start off the
  critical path. Seen files persisted (`config['filetag_files']`, LRU 200). `prompt_fragment` biases
  Whisper; `tag()` rewrites references in 4 passes (extension-present / strong-prefix / trailing-"file" /
  bare-multi-token-with-trigger), handling spoken separators ("dot"/"underscore") + extension homophones.
  Real `@`-chip insertion happens in `injector.py::_inject_with_mentions` (types `@`+name, Enter-selects
  the IDE picker).
- **Gated by** `config['filetag_enabled']`. **Not on mobile** (no IDEs).

## Text injection & target-app tracking (desktop)

- `injector.py`: `save_focused_app()` at record-start stores `_previous_app_{pid,name,bundle}` (the
  **dictation target**, not the live frontmost app which may be the overlay). `inject_text(text,
  allow_mentions=)` = `pyperclip` + `restore_focused_app` + Cmd+V CGEvent; when mentions are enabled and
  the text has an `@name.ext` in a tagging IDE, routes to `_inject_with_mentions` (falls back to plain
  paste on any failure). Windows equivalent: `win_injector.py` (clipboard + `pyautogui` Ctrl+V, `user32`
  foreground-window save/restore).

## Recordings — save / playback / retry

- **Desktop:** `recordings.py` — every capture saved as **16 kHz mono WAV** in `~/.verbal/recordings/{id}.wav`
  (LRU 60). `upload_cloud` → `recordings` bucket (`{user_id}/{id}.wav`), URL stored on the history entry.
  `DashboardApi.play_recording`/`get_audio` (base64 data-URI)/`retry_transcription`. Failed transcriptions
  saved `status:'failed'` for retry from History.
- **Mobile:** `lib/recordings.ts` mirror — `persist` (copy temp → `documentDirectory/recordings/`),
  `uploadCloud` (Storage binary upload), `ensureLocal` (download if needed); `historyStore.retryEntry`
  re-transcribes + `formatText`. Playback via `expo-audio`, prefers local then cloud.
- **Backend:** `recordings` bucket (public), path `<user_id>/<id>.<ext>`.

## Notes

- **What:** synced, voice-first notes.
- **Desktop:** `DashboardApi.fetch_notes/save_note/delete_note/toggle_note_pin` — local-first
  (`config['notes']`) merged with Supabase `notes` (newest `updated_at` wins). `note_dictate_start/stop`
  = in-note voice dictation; `format_note_with_ai` (Groq notes formatter).
- **Mobile:** `flume-ui/hooks/useNotes.ts` + `lib/notesStorage.ts` (AsyncStorage cache) + `notes` table.
  `NoteEditorScreen` appends dictation into the body (`useRecorder`); shows live `partialText`.
- **Backend:** `notes` table (`id,user_id,title,content,folder,is_pinned,device_name,created_at,updated_at`).
- **Known limit:** mobile `isVoice` flag isn't persisted (no `is_voice` column); mobile notes not auto-formatted.

## Canvas — shared clipboard

- **What:** a staging board to send text/links/images between your devices (one shared row per user).
- **Desktop:** `DashboardApi.fetch_canvas/save_canvas` + image support (`save_canvas_image_data`, native
  `NSOpenPanel`/`NSPasteboard` pickers → `canvas-images` bucket). `FlumeWebDashboard._canvas_listen_loop`
  = a `websocket` subscription to `postgres_changes` on `canvas`, emits `canvasRemote` to JS (ignores own
  writes). `canvas_window.py::CanvasWindow` is a standalone AppKit window but is effectively **legacy**
  (menu routes to the web dashboard tab instead).
- **Mobile:** `flume-ui/hooks/useCanvas.ts` — `canvas` table (upsert `on_conflict=user_id`) + `canvas-images`
  bucket + `expo-clipboard` + `expo-image-picker`; realtime channel `canvas_${userId}` (received text copied
  to clipboard, haptics, skips own writes).
- **Backend:** `canvas` table (one row/user: `content`, `image_url`, `device_name`, `updated_at`).

## Cross-device sync

- **What:** history/notes/canvas kept in sync across your signed-in devices; all keyed by `user_id`.
- **Desktop:** `sync.py::SyncClient` — Phoenix WebSocket to Supabase Realtime, subscribes to
  `transcriptions` INSERTs filtered by `user_id`, skips own inserts, honors `target_device_id`; `push()`
  inserts via REST; heartbeat upsert into `devices` every 60 s; `fetch_devices` = others seen in last 5 min.
  On receive, `main._on_sync_receive` copies+pastes into the focused app + overlay toast. Push targeting
  from `dashboard._target_device_id` (`__all__`/`__none__`/specific).
- **Mobile:** `flume-ui/hooks/historyStore.ts` — local AsyncStorage cache is source of truth; realtime
  channel `verbal_history_${userId}` merges remote INSERTs (skips own, respects `target_device_id`).
  `useDevices` heartbeats every 60 s; sync gated by `getSyncEnabled()`.
- **Backend:** `transcriptions`, `devices` tables + realtime. See `04-data-model.md` for the exact push
  shape differences (desktop push omits `audio_url`/`status`; mobile includes them).

## Device pairing

- QR-based, single-use token. Host (signed in) inserts a `pairings` row (`token`=`token_urlsafe(6)`,
  `expires_at`≈now+120 s), shows QR `flume://pair?t=<token>`. New device claims: SELECT unclaimed/unexpired
  row → atomic UPDATE `claimed_by` (guarded) → adopt host `user_id` → enable sync. Desktop `pairing.py`
  (`create_pairing`/`check_pairing`/`claim_pairing`, `qr_svg`); mobile `lib/pairing.ts`
  (`extractToken`/`claimPairing`), `PairDeviceScreen` (expo-camera), claim logic in `SettingsNavigator`.

## Google auth

- **Desktop:** `auth.py` — Supabase Auth **PKCE loopback**: browser → `/auth/v1/authorize?provider=google
  &redirect_to=http://localhost:8765/callback`; a dual-stack (IPv6+IPv4) loopback server on **port 8765**
  captures the code, exchange at `/token?grant_type=pkce`. Stores `config['auth']`
  (`user_id,email,name,avatar_url,access_token,refresh_token`) + sets `sync_user_id=user.id`. No Google
  secret in-app (Supabase holds it).
- **Mobile:** `lib/supabase.ts` + `flume-ui/hooks/useAuth.ts` — `signInWithOAuth({provider:'google',
  redirectTo:'verbal://auth-callback'})` + `WebBrowser.openAuthSessionAsync`; return URL parsed by
  `createSessionFromUrl` (PKCE `?code=` → `exchangeCodeForSession`, dedup via `_handledCodes`; implicit
  `#access_token` fallback); `Linking` listener for Android reopen. Only Google is real; Apple/email are
  stubs. Needs an EAS dev build (not Expo Go).
- **Setup facts:** `GOOGLE_AUTH_SETUP.md` (Web OAuth client, redirect
  `https://ovpcthjingugwvpxlsna.supabase.co/auth/v1/callback`; Supabase Redirect URLs include the loopback
  and the `verbal://` deep link). Details in `04-data-model.md`.

## Recording overlay / popover / hotkey / onboarding / updater / permissions / sounds (desktop)

- **Overlay** (`overlay.py`/`overlay_html.py`): non-activating pill (Recording → Transcribing → Done),
  bottom-center, `NSScreenSaverWindowLevel`, all-spaces; buttons via the bridge (`overlay_stop`/`_cancel`/
  `_pause`/`_copy`/`_dismiss`). iOS analog = the `Recording` modal screen.
- **Popover** (`flume_popover*.py`): macOS menubar `NSPopover` mini-dashboard; attached via a retrying timer.
- **Hotkey** (`hotkey.py`): `NSEvent` global monitor; default key **54 (Right Cmd)**, ESC cancels. Hold
  mode (down=start/up=stop) vs Toggle mode (debounced tap). Windows uses `pynput` (default `alt_r`).
- **Onboarding:** dashboard JS flow; `DashboardApi.complete_onboarding` sets `config['onboarded']`. Mobile:
  `OnboardingScreen` (3 slides) + AsyncStorage `flume_onboarded`.
- **Updater** (`updater.py`): polls Supabase `app_versions` per platform, downloads to temp with sha256
  verify, installs (`.dmg`/silent `.exe`) then exits. Binaries in `releases` bucket.
- **Permissions** (`permissions.py`): accessibility / microphone / system-audio / notifications status +
  request, surfaced via `DashboardApi.get_permissions/request_permission`.
- **Sounds** (`sounds.py`): `afplay` system AIFFs — `play_start`(Tink), `play_stop`(Pop), `play_done`(Glass),
  `play_added`(Hero, the auto-learn confirm chime).

---

For data shapes, tables, auth internals, and sync push-shape differences → `04-data-model.md`.
For conventions, gotchas, the design system, and dead/legacy modules → `05-conventions.md`.
