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
- **Backend:** all Groq calls (transcription + cleanup) now route through the **`groq-proxy` Edge Function**
  — the Groq key is server-side only, clients hold none, and the **in-app API-key entry has been removed**
  on macOS/mobile **and Windows** (mobile Settings card + desktop dashboard field + the menu-bar "Groq/Gemini
  API Key…" items are gone on all three platforms — macOS's `main.py::_manage_groq_keys` is dead code,
  unattached to any `rumps.MenuItem`; Windows's `win_main.py::_tray_manage_groq`/`_tray_manage_gemini` and
  their tray `MenuItem`s were removed MER-34, 2026-07, closing the one platform that still exposed reachable
  key entry). A user's pre-existing local Groq/Gemini key still works as a silent *fallback* (the read path
  in `transcriber.py`/`ai_cleanup.py` was untouched — only the management UI is gone) — the proxy is always
  tried first. Audio → `recordings` bucket. See `05-conventions` Hard Rule #15.
- **Status:** solid. Local Whisper is a desktop-only offline fallback (`faster_whisper` bundled).

## AI cleanup / formatting

- **What:** turn a raw transcript into clean, correctly-formatted text without adding content.
- **Desktop:** `ai_cleanup.py::process_text` — ① `clean_raw_transcript` (regex: strip hallucinations,
  fillers, doubled words; capitalize; terminal punctuation), ② LLM format via Groq
  `llama-3.3-70b-versatile` (`cleanup_with_groq`) → Gemini fallback with key rotation. `SYSTEM_PROMPT` =
  17 rules ("you are a TEXT FORMATTER, not an assistant"). Separate `NOTES_FORMATTER_SYSTEM_PROMPT`;
  `build_notes_system_prompt(structure_detection, autotitle)` appends the checklist/structure-detection
  and `TITLE:` rules only when those flags are on (see §Notes). `format_note(text, cfg, …)` returns
  `{title, formatted_content}`; `_parse_note_response` peels a leading `TITLE:` line.
- **Mobile:** `lib/groq.ts::formatText` (same `llama-3.3-70b-versatile`) — used on **retry** and where
  screens call it. `formatNotes` / `formatNoteWithTitle(text, apiKey, {timeoutMs, detectStructure,
  withTitle})` are now **wired into the note editor** via `useNotes.saveDictation` (see §Notes) — mobile
  notes are no longer stored raw-only.
- **Status:** desktop runs cleanup on every dictation. Notes cleanup (both platforms) runs **once** per
  dictated save, not on every edit (Decision 2 — see §Notes).

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
  (LRU 60). `upload_cloud` → `recordings` bucket (`{user_id}/{id}.wav`), the bare **object path** (not a
  URL — bucket is private, MER-27) stored on the history entry. `DashboardApi._ensure_local_audio` signs a
  short-lived URL (`recordings.sign_url`) before downloading — the one choke point for
  `play_recording`/`get_audio` (base64 data-URI)/`retry_transcription`. Failed transcriptions saved
  `status:'failed'` for retry from History.
- **Mobile:** `lib/recordings.ts` mirror — `persist` (copy temp → `documentDirectory/recordings/`),
  `uploadCloud` (Storage binary upload, returns a bare object path), `ensureLocal` (signs via
  `signUrl`/`resolvePlaybackUrl` then downloads if needed); `historyStore.retryEntry`/`playEntry` both
  delegate to `ensureLocal`. Playback via `expo-audio`, prefers local then cloud.
- **Backend:** `recordings` bucket, **private** (MER-27, 2026-07 — was public), path `<user_id>/<id>.<ext>`.
  Signed URLs generated on demand (~180s TTL); a format-tolerant path extractor
  (`extract_object_path`/`extractObjectPath`) handles both new bare-path writes and legacy public-URL rows,
  so no backfill migration was needed.

## Notes

- **What:** synced, voice-first notes. **v2** (spec `NOTES_ENHANCEMENT_SWARM.md`) adds full-text search,
  auto-titling, structure detection (voice → interactive checklists), note ↔ source-recording linkage,
  raw+formatted dual storage, cost-controlled cleanup, four per-user feature flags, and conflict-pair sync.
- **Raw + formatted (Decision 1):** a dictated note stores **both** the raw transcript (`raw_content`) and
  the AI-formatted `content`; the toolbar's **"show original"** reveals the raw text. Pre-existing/typed
  notes have `raw_content` null → the affordance is hidden.
- **Cost control (Decision 2):** cleanup runs **once**, on the initial dictated save (creates formatted
  content + title). Typed edits never auto-format. Appended dictation cleans **only the new segment** and
  concatenates it. Re-running cleanup is explicit only: toolbar **"Reformat"** (or **"Retry formatting"**
  when the first cleanup failed/timed out — 8 s hard timeout → save raw + set the retry affordance).
- **Auto-title (Decision/Feature 2):** fires only on the first save of a note whose title is still empty;
  **never overwrites a manually-set title**.
- **Structure detection (Feature 3):** enumerable speech becomes markdown task-list items (`- [ ]`);
  checkboxes are interactive (toggle `- [ ]`↔`- [x]` in the underlying content, persisted immediately) and
  carry a real checkbox role/label. Flag-off still formats but keeps prose/plain bullets.
- **Audio linkage (Feature 4):** each dictation persists its recording and appends `{id,url,created_at}` to
  the note's `audio_segments`; a labeled per-segment play control appears (typed notes show none).
- **Feature flags (Decision 4, default on):** `notes_search_enabled`, `notes_autotitle_enabled`,
  `notes_structure_detection_enabled`, `notes_audio_linkage_enabled` — toggled in Settings; desktop reads
  via `feature_flag(cfg,…)` (`config`), mobile via `getNotesFeatureFlags`/`setNotesFeatureFlag`
  (AsyncStorage). First-run does **not** backfill existing notes (Decision 5); only new notes get v2
  behaviors, but search covers everything.
- **Desktop:** `DashboardApi.fetch_notes/save_note/delete_note/toggle_note_pin` — local-first
  (`config['notes']`) merged with Supabase `notes` via `merge_remote_note` (union + conflict-pair, see
  `04-data-model.md`). `note_dictate_start/stop` = in-note dictation (stop persists the recording +
  appends to `audio_segments` when linkage is on); `format_note_with_ai(text)` returns
  `{title, formatted_content}` in one LLM call; `search_notes(query)` = case-insensitive substring,
  title-over-content ranked, recency tiebreak. Dashboard UI (`flume_dashboard_html.py`): search field,
  hand-rolled markdown/checklist renderer (`role="checkbox"`), per-segment playback, show-original/reformat/
  retry affordances, and Notes feature-flag toggles in Settings.
- **Mobile:** `flume-ui/hooks/useNotes.ts` + `lib/notesStorage.ts` (AsyncStorage cache, `mergeRemoteNote`)
  + `notes` table. `useNotes.saveDictation` wires `formatNoteWithTitle` into the save path (first-vs-append,
  8 s timeout → `format_failed`); `reformatNote` = explicit Reformat/Retry. Search via
  `lib/notesSearch.ts::searchNotes` (same ranking). `NoteEditorScreen` renders markdown/checklists through
  the fresh `flume-ui/components/MarkdownNote.tsx` (NOT the legacy `lib/MarkdownText.tsx`), with
  show-original, reformat/retry chips, and per-segment playback (`expo-audio` via `lib/recordings.ts`).
- **Backend:** `notes` table — base cols `id,user_id,title,content,folder,is_pinned,device_name,created_at,
  updated_at` **plus v2** `raw_content text` (nullable) and `audio_segments jsonb '[]'` (see
  `supabase_notes_v2.sql`; details + conflict-pair/union/unknown-field sync in `04-data-model.md`).
- **Multi-select delete (mobile):** long-press a note card in `NotesListScreen` enters selection mode
  (checkmark affordances, count in the header); tap toggles, the header trash icon deletes the selection
  after a `confirm()` dialog. Backed by `useNotes.removeNotes(ids)` (one `.in('id',…)` cloud delete +
  per-id cache eviction). Opening a note is suppressed while selecting.
- **Sync identity (fixed 2026-07):** notes sync was broken by two bugs — (1) mobile inserted **without** an
  id so its local `note_<ts>` never matched the server-minted uuid (edits lost, rows duplicated), and (2) no
  back-fill of notes created before the `notes` table existed. Fixed by the **text `id`** column
  (`04-data-model.md`), mobile upsert-with-id (gated on sync), and a load-time back-fill. Notes have **no
  realtime subscription** on either platform (only `transcriptions` do) — they reconcile on notes-tab open
  (desktop `fetch_notes`) / screen mount (mobile `useNotes.load`), not live.
- **Known limit:** still no `is_voice` column — `isVoice` is inferred from `raw_content`/non-empty
  `audio_segments` (survives reloads for dictated notes).

## Canvas — shared clipboard

- **What:** a staging board to send text/links/images between your devices (one shared row per user).
- **Desktop:** `DashboardApi.fetch_canvas/save_canvas` + image support (`save_canvas_image_data`, native
  `NSOpenPanel`/`NSPasteboard` pickers → `canvas-images` bucket). `FlumeWebDashboard._canvas_listen_loop`
  = a `websocket` subscription to `postgres_changes` on `canvas`, emits `canvasRemote` to JS (ignores own
  writes). On receive it copies **text OR the image URL** to the clipboard and fires a macOS banner
  (`_notify_native` → `osascript`, fail-closed) — **regardless of the active tab**; the `canvasRemote` JS
  handler now updates the (always-present, hidden) canvas DOM without gating on `active==="canvas"`, so a
  photo received in the background is there when you open Canvas. `canvas_window.py::CanvasWindow` is legacy.
- **Mobile:** `flume-ui/hooks/useCanvas.ts` — `canvas` table (upsert `on_conflict=user_id`) + `canvas-images`
  bucket + `expo-clipboard` + `expo-image-picker`; realtime channel `canvas_${userId}`. On receive it copies
  text/image-URL to the clipboard and shows a transient **"Received from X — copied to clipboard"** toast
  (`toast`/`dismissToast`, rendered by `CanvasScreen`); a failed image upload now shows an explicit toast
  instead of silently no-op'ing. Skips own writes, haptics on receive.
- **Backend:** `canvas` table (one row/user: `content`, `image_url`, `device_name`, `updated_at`);
  `canvas-images` bucket policy in `supabase_canvas_images_policy.sql`.

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

## Account deletion (MER-32, 2026-07)

In-app "Delete account" — App Store Guideline 5.1.1(v) requires apps with account creation to let users
initiate deletion in-app. **Server-side:** `supabase/functions/delete-account/index.ts`, `verify_jwt` on,
identity derived from the caller's JWT locally (never a body-supplied id — the function can only ever
delete the signed-in caller's own account). Order: purge DB rows across every `user_id`-keyed table
(`transcriptions`, `notes`, `dictionary`, `canvas`, `devices`, `meetings`, `push_tokens`, `groq_usage`) +
storage objects (`recordings/<user_id>/`, `meeting-audio/<user_id>/`, and a list+filter over `canvas-images`
since that bucket's namespace is flat, `canvas/<user_id>_<ts>.<ext>`, not folder-per-user) **first**, then
the Supabase auth user itself **last** — a partial failure leaves a recoverable signed-in state instead of
an orphaned auth user. Idempotent (retrying after a partial failure is safe: every delete is either
by-`user_id` or by-listed-path, and a repeat admin-delete-user call 404s harmlessly, treated as success).
Sign-in-with-Apple token revocation is an intentional deferred TODO (`revokeAppleToken()` stub — needs the
Apple Developer account, not available yet); Google-only deletion (the only live sign-in method) works
fully without it.

**Clients:** both call the same edge function with the real session JWT (not the anon key — the function
401s without one) via `app.auth.delete_account_remote(cfg)` (desktop, `whisperflow/app/auth.py`) /
`useAuth().deleteAccount()` (mobile, `flume-ui/hooks/useAuth.ts`), then wipe every local trace on success:
desktop `app.auth.wipe_local_account_data()` (clears `config['auth']`/history/pinned/notes/meetings/
dictionary, deletes the local `recordings/`+`meetings/` directories — a strict superset of `sign_out()`,
which deliberately preserves local caches for a same-user re-sign-in); mobile reuses `clearAccountData()` +
`historyStore.reset()` (the same sign-out teardown, Hard Rule #13). Two-step destructive confirm on both
platforms: desktop uses two sequential JS `confirm()` dialogs in the Settings "Account" card
(`flume_dashboard_html.py`); mobile uses two sequential native `Alert.alert` calls in `SettingsScreen.tsx`
(Hard Rule #14 — this screen is a native-stack modal, so the custom `ConfirmDialog` wouldn't reliably
receive touches here, same reasoning as the existing sign-out confirm).

Live-verified end-to-end (2026-07) with a disposable test auth user: seeded one row in every table + one
object in every bucket, called the function with a real JWT, confirmed all rows/objects/the auth user were
gone, confirmed a repeat call with the same token still returned success (idempotency), and confirmed a
request bearing only the anon key (no user JWT) was rejected with 401. The desktop Python client wrapper
(`delete_account_remote`) was also exercised directly against the live function, not just the edge function
itself via curl. `wipe_local_account_data()` was verified by code review only, not live execution — it
deletes real files under `~/.verbal/` and this development machine has a real, in-use installation.

## Meetings — capture, live transcript, hybrid summary


> **UI: widget kit v2 — COMPLETE** (`MEETINGS_WIDGETS_HANDOFF.md`, Jul 2026). Dot+label speaker chips,
> single-parent-card rows with faint dividers, glyph icon buttons (1.4 stroke), ↳ hybrid-note AI additions
> with Yours/Merged/AI tabs, v2 meeting list on the dashboard AND mobile (compact rows in one parent card,
> `MeetingListScreen.tsx`). Summary fully editable: transcript hover copy/inline-edit (`edited` flag),
> action items inline edit/delete/done + **due labels** (extracted by the summary LLM, `due` key), marked
> moments get **user notes** (`set_mark_note`), jump-to-transcript + delete. Per-row **AI regenerate** on
> hybrid notes (`regenerate_hybrid` → one focused LLM call). Meeting list: **pinned** (cloud `pinned`
> column, PINNED group first) and **NEW/unread** (local `meetings_opened`, cleared by `open_meeting`).
> **Voice fingerprinting** (`app/voiceprint.py`): at meeting end each non-self speaker gets a numpy log-mel
> mean+std embedding from the meeting WAV; named speakers update rolling prints in `config['voice_prints']`
> (LOCAL-ONLY, never synced); unnamed speakers auto-name on a decisive cosine match (≥0.92 + 0.02 margin)
> BEFORE the summary runs; hits land in the `recognized` jsonb column and render the fingerprint banner +
> avatar corner dot. Speakers are renameable from the SUMMARY too (double-click the header avatar chip
> or a transcript chip → `set_speaker_name`), which also feeds the fingerprint learner from the local WAV
> ("⚡ Voice print saved" toast). Scratchpad is a contenteditable with markdown-lite (⌘B/⌘I native, `- `→em-dash bullets
> with Enter continuation, numbered continuation, `# `→heading) — stored as plain text (`innerText`), and
> freshly-dictated text flashes accent. All list writes go load-then-patch (never write a list you didn't load).
- **What:** record a live meeting ON the Mac (system audio + mic — no bot joins the call), see a live
  transcript beside a personal scratchpad, and get a post-meeting hybrid summary: AI summary + decisions +
  action items + the user's own notes enhanced with transcript context. Spec: `MEETINGS_DESIGN_HANDOFF.md`
  (screens 31a–31h); availability: macOS full, iOS read-only (+ scratchpad edit), Windows none.
- **Desktop:** `meetings.py` (`MeetingManager`/`MeetingSession` state machine: idle→preparing→recording⇄
  paused→stopping→processing→ready|failed) + `system_audio.py` (SCK audio capture) + `meeting_window.py`/
  `meeting_html.py` (ONE morphing WKWebView panel: an ambient glassy **bar** top-center — live dot, title,
  timer, waveform, star/pause/stop, click-to-expand — that fluidly grows into the full window via native
  frame animation; content modes `permissions` 31h / `premeeting` 31b / `live` 31c / `summary` 31e; while
  recording, losing focus or closing collapses back to the bar. The separate `meeting_hud.py` is superseded).
  Dashboard (31a/31f/31g): Home `MeetingLauncherCard`/`ActiveMeetingCard`, a **dedicated "Meetings"
  sidebar destination** (`scr-meetings`: count header, New-meeting button, active-recording bar, search,
  Today/This-week/Earlier groups, delete, empty state — user preference; it originally shipped as a folder
  inside Notes), and a Settings group; popover gets a "Start meeting" row; menubar gets
  "Start Meeting"/"Return to Meeting". (Mobile keeps its Meetings entry inside the Notes tab — there is no
  sidebar on mobile.) Bridge methods on `DashboardApi`: `start/stop/pause_meeting`,
  `mark_moment`, `save_meeting_scratchpad`, `set_meeting_title`, `rename_speaker`, `list_meetings`,
  `get_meeting`, `open_meeting(_launcher)`, `delete_meeting`, `retry_meeting_summary`, `get_meeting_audio`,
  `get_meeting_permissions`, `test_meeting_capture`, `get/set_meeting_setting(s)`. Scratchpad dictation
  reuses the standard dictation path (paste lands in the focused scratchpad).
- **Summary generation:** `meetings.generate_meeting_summary` — strict-JSON contract
  `{summary, decisions[], action_items[{owner,task,done}], hybrid_notes[{user_line, ai_addition}]}` via
  `chat_via_proxy` (2 attempts, 45 s, 24k-char transcript budget head+tail). Failure → status `failed`
  with explicit Retry (31e); silent meeting → `ready` with empty summary. Runs ONCE per meeting;
  regenerate is explicit (Notes cleanup cost-control philosophy).
- **Mobile:** read-only by design (empty states, not errors): `lib/meetings.ts` (fetch/map/realtime/
  scratchpad update) + `flume-ui/hooks/useMeetings.ts` (+`.mock.ts` contract) + `MeetingListScreen` /
  `MeetingDetailScreen` / `MeetingPlaybackScreen` (expo-audio playback with transcript highlight + tap-to-
  seek), reached from a "Meetings" folder row in `NotesListScreen` (routes on the Notes stack). The ONE
  mobile write: scratchpad edits (optimistic + debounced, last-write-wins).
- **Export:** the summary header has `TXT`/`MD` buttons → `DashboardApi.export_meeting(id, fmt)` → pure
  builders `meetings.export_transcript_txt/_md` (txt: header + `[m:ss] Name: text`; md: summary, decisions,
  checkbox action items, marks, notes, transcript) → native `NSSavePanel` (main thread), fallback
  `~/Downloads`. **Mark feedback:** pressing ★ pops the button, shows a "★ Marked m:ss" toast (expanded) or
  flashes the bar title (collapsed) — the marks footer alone was invisible feedback ("star isn't working").
- **Ask your meetings (chat Q&A):** the dashboard Meetings page has a chat panel → `DashboardApi.ask_meetings`
  → `meetings.ask_meetings`: fetches the ~25 latest cloud rows, keyword-ranks them against the question
  (title×4 / summary×2 / transcript×0.5), builds context from the top 3 (summary+decisions+actions + the
  question-relevant transcript lines ±1 neighbor, ~3.2k chars each), answers via `chat_via_proxy` with a
  grounded-only system prompt, and cites source meeting titles. Client keeps a 6-turn thread (Q bubbles /
  A cards / typing dots). Desktop-only for now.
- **Open/delete:** clicking a row opens the meeting in the summary window — the meeting window buffers
  events until the page's `meeting_page_ready` handshake (a fresh window used to lose the mode/meeting
  events → "click does nothing"). Delete: ✕ on each row, plus a two-step confirm trash button in the
  summary header; deletes emit `meetingsUpdated` so the dashboard list refreshes everywhere.
- **Backend:** `meetings` table + `meeting-audio` bucket (`supabase_meetings.sql`, realtime on, RLS
  `TO public`). Bucket is **private** (MER-27, 2026-07 — was public); `meetings.audio_url` stores a bare
  object path, and both `shared_dashboard.py::get_meeting_audio` (desktop) and
  `MeetingPlaybackScreen.tsx` (mobile) generate a signed URL (~3600s TTL — long enough for a full
  playback+scrub session) before playing. See `04-data-model.md`.
- **Status/limitations:** system audio requires macOS 13+ and the Screen & System Audio Recording
  permission (31h checklist + 3 s capture self-test). Speaker identity is source-based v1 (no diarization);
  meeting text NEVER goes to analytics; `meetings_max_minutes` (capture-length cap) is still stored but not
  enforced — a separate, not-yet-built concern from the reaper below.
- **Meeting-audio retention reaper (MER-31, 2026-07):** audio-only deletion, **off by default**. A daily
  `pg_cron` job (`reap-meeting-audio-daily`, 03:00 UTC) POSTs to the `reap-meeting-audio` Edge Function,
  which deletes the `meeting-audio/<user_id>/<meeting_id>.wav` object for meetings where `pinned = false`,
  `audio_expired = false`, `retention_days > 0`, and `now() - started_at > retention_days` — **never**
  touching `transcript`/`summary`/`decisions`/`action_items`/`hybrid_notes`/`notes_md`; the readable record
  survives, only the heavy audio goes. Fail-closed ordering: storage delete happens first, `audio_expired`
  (+ clearing `audio_url`) is only set if that actually succeeded, and rows still `status = 'processing'`
  are never touched (avoids the zombie-row race). `retention_days` is stamped **per meeting at capture
  time** from the desktop setting `meetings_keep_audio_days` (default **0 = never expire** — changing the
  setting only affects meetings captured afterward, not retroactively; a future billing tier would write
  this same column instead of it being user-editable — the seam is already there, no schema change needed).
  Clients: desktop's meeting summary screen shows "Audio expired — notes and transcript kept" and clicks on
  the transcript no-op instead of erroring (`meeting_html.py`); mobile's `MeetingPlaybackScreen`/
  `MeetingDetailScreen` already degraded gracefully on a missing `audioUrl` (hide the player bar / show
  "View transcript" instead of "Play with transcript") — that same path now also covers the expired case,
  plus a small "Audio expired — transcript kept" line where the player bar would be.

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


## Notes — Granola-style note-maker (Jul 2026 upgrade)

The notes LLM prompt (`ai_cleanup.NOTES_FORMATTER_SYSTEM_PROMPT`, mirrored VERBATIM in mobile
`lib/groq.ts::NOTES_FORMATTER_PROMPT`) is a **world-class note-maker** engineered against six
explicit criteria and tuned over four live eval iterations (v1 formatter → v4):
(1) completeness floor — compression removes WORDS never INFORMATION (every fact/number/name/
commitment/reason/open-question survives; reasons stay ATTACHED to their bullet); (2)
proportionality — tiny thought = 1–2 clean lines with zero scaffolding, dense debrief = full note;
(3) 3-second scannability — decisions/dates/owners bolded, consequential line first; (4) scenario
shapes — debrief (Decisions/Next steps/Open questions/Notes), tasks (owner+due inline), idea dumps
(rationale on the same bullet, speaker's own ranking kept), journal (prose in the speaker's voice,
NO bullets/headings), technical (steps+backticks); (5) truth discipline — self-corrections resolve
to final, "maybe" never upgrades, zero invention; (6) writer-not-stenographer — polished
capitalization/punctuation, spoken meta-preambles ("remind me…") stripped. Known failure modes each
rule guards: v1 over-summarized (bare noun-phrase bullets, rationales lost), v3 went verbatim-
lowercase. Checklist syntax ("- [ ]") stays exclusively in the flag-gated structure-detection
appendix. Eval harness: scratchpad `notes_eval.py` pattern (4 scenario transcripts); fixtures
`notes_fixtures.py` 66/66.

## Live meeting on mobile + meeting-start push (Jul 2026)

Follow a meeting LIVE from the phone while the Mac captures it. Desktop
(`meetings.py`): `row()` carries a `live` bool (true while preparing/recording/paused);
`_cloud_push_live` PATCHes ONLY transcript/speakers/duration/live every ≥4s during the
meeting (never scratchpad — mobile owns that live), so the phone streams the transcript
in via the existing realtime UPDATE subscription. On stop the final write flips `live`
false. Mobile `MeetingLiveScreen.tsx`: REC pill + locally-ticking elapsed, auto-scrolling
live transcript with speaker dots, and a sliding segmented control to a synced Notes pad
(debounced `updateScratchpadRemote`). `lib/meetings.isLiveNow` guards a 90s staleness
window (desktop crash → stale `live` never traps the UI). The list shows a LIVE banner
that routes to the live screen; when the meeting ends the live screen `replace()`s to the
finished detail. New column `meetings.live`.

**Meeting-start push:** desktop `_notify_start` fires the `notify-meeting-start` edge
function on meeting start → reads `push_tokens` (new table) → Expo Push API. Mobile
`lib/notifications.ts` registers an Expo push token on launch and is DEFENSIVE — every
expo-notifications call is a lazy `require` in try/catch, so a dev client built before the
native module was added never crashes (remote push lights up on the next native build; the
`expo-notifications` config plugin is in app.json). Local-notification + foreground handler
paths also present. Simulators can't receive real push (needs a device + APNs).

## Meeting Notes page (Jul 2026)

Full AI notes of a meeting — a dedicated PAGE inside the meeting window (MODE `notes`), not a new
window. Generated by `meetings.generate_meeting_notes` (`MEETING_NOTES_SYSTEM`: **analyst-grade**
notes matching a top human write-up — `## TL;DR` (3–6 bullets, skipped for a trivial note), `##
<Topic>` sections with nested sub-bullets and **bold** load-bearing facts, **Markdown TABLES**
(mandatory whenever 3+ items share fields — cost breakdowns, option comparisons, pros/cons,
schedules; derived values computed, never invented), `## Decisions` with reasons, `## Action items`
as checkboxes with owner/due and a `### Phase N` PHASED ROADMAP for multi-step plans, `## Open
questions`; proportional — rich when the call is rich, two lines when it's thin; written in the
deterministically computed OUTPUT LANGUAGE). ONE LLM call per meeting (`max_tokens=4000`,
`timeout=60s`), LAZY: generated on first open of the page, cached in the new `meetings.notes_md`
column (cloud-persisted), Regenerate button re-runs it. Rendered by a self-contained markdown
renderer in `meeting_html.js::mdRender` (##/###, - and 1. lists, - [ ] checklists, **bold**,
`code`, **GitHub-style tables** → `.ntTable`; first paragraph styled as an accent-bordered context
callout). Entry points: "Open notes ↗"
in the hybrid-notes card header; when the user took no scratchpad notes the card body previews the
first lines of the AI notes (or offers "Generate meeting notes"). Copy button exports the raw
markdown to the clipboard.

**Mobile parity (iOS, Jul 2026):** `MeetingNotesScreen.tsx` renders the same `notes_md` with a
self-contained RN markdown view (context callout, ## sections, bullets, 1. lists, - [ ] tasks,
**bold**, `code`, **tables** via flex-column `MdView` rows); when `notes_md` is absent the phone
generates it on-device via `lib/groq.ts::generateMeetingNotes` (same `MEETING_NOTES_SYSTEM` prompt,
`max_tokens=4000`, + deterministic output language) and persists via `updateNotesRemote` so every
device gets it. `MeetingDetailScreen` gained
a Notes entry row, tappable action-item checkboxes (`updateActionItemsRemote`, full-list write),
due-date labels, and marked-moment user notes. New cloud column `notes_md`; mobile Meeting type +
`toMeeting` carry `notesMd`/`pinned`/`recognized`.

**Notes are now editable on mobile (Jul 2026):** a pencil toggle in the header swaps the rendered
`MdView` for a raw-markdown `TextInput` (edits are plain markdown source, not WYSIWYG); a checkmark
returns to the rendered view. Wiring mirrors the scratchpad's optimistic-update + 600ms-debounced-write
shape (`useMeetings.ts::updateNotes`, both the real hook and `useMeetings.mock.ts` — the two must stay
contract-identical) → `lib/meetings.ts::updateNotesRemote` (pre-existing, previously only called after
AI regeneration). The screen also hides the bottom tab bar (`RootNavigator.tsx`'s
`getFocusedRouteNameFromRoute` check, same mechanism `NoteEditor` already used) and now has its own
"Play with transcript" button (previously only on `MeetingDetailScreen`) linking to
`MeetingPlaybackScreen` — see the tap-to-seek/highlight sync described just above.

## Meeting auto-detection (Granola-style, desktop, Jul 2026)

Flume notices a call in progress and pops a floating **"Meeting detected · <source>"** pill with a
one-click **Take notes** button — no more manually hitting Start Meeting. macOS-only, meetings-only,
fails closed.

- **Detection** (`app/meeting_detect.py`): a `rumps.Timer` (5 s) runs `detect()` **on a background
  thread** (the scan can block ~1 s) and applies the result on the main thread. It enumerates windows
  via **`SCShareableContent`** (ScreenCaptureKit) — the reliable title source: with the Screen-Recording
  permission Flume already holds it returns EVERY on-screen window's title, including background windows.
  `CGWindowListCopyWindowInfo` is only a **fallback** (on macOS 14/15 `kCGWindowName` is empty for all but
  the frontmost window, so it alone misses a Meet call you've tabbed away from — this was the "not
  detecting" bug). It looks for an *in-call* window, not just an open app: a **Zoom Meeting** window, a
  **Google Meet** call in any browser (code `xxx-yyyy-zzz` / `meet.google.com` / `Meet - ` prefix),
  **Zoom web**, **Teams**/**Webex** meeting windows, FaceTime. Returns `{source,key,app}`; the friendly
  `source` (e.g. "Chrome", "Zoom") shows in the pill. `_BROWSERS`/provider matchers are easily extended.
  Conservative on purpose (an idle Zoom / a doc titled "Meet…" must not trigger — see the fixture matrix
  in the detect test).
- **Prompt** (`app/meeting_prompt.py`): a non-activating NSPanel + WKWebView pill (same recipe as
  `autolearn_widget.py` — never steals focus from the call), near-black Flume design with a sage accent.
  Buttons post `md_take`/`md_dismiss` through the shared `_Bridge`.
- **Wiring** (`main.py`): `_detect_meeting_tick` asks **once per call** (`_md_handled` keyed by call),
  skips when a meeting is already recording, and resets after ~2 empty polls so the *next* call re-prompts
  (also hides a stale pill). `_meeting_detect_result(True)` → `meetings.start(use_mic,use_system,lang)` +
  open the live window; if capture isn't ready (permissions) it falls back to `_toggle_meeting` (the
  permission/pre-meeting flow). Menubar **"Auto-detect meetings"** checkbox toggles `meeting_autodetect`
  (config, default **on**).

## Mobile audit pass (Jul 2026): onboarding, buttons, per-device sync, keyboard

- **Onboarding** trimmed to 2 slides (`OnboardingScreen.tsx`) — the "Connect a computer /
  pair a device" slide was removed (pairing happens post-sign-in, not in onboarding).
- **Dead buttons fixed**: Home feature cards → Devices / Notes (`useNavigation`), Home +
  Notes "See all" wired/removed, Home notifications bell removed; History search field +
  overflow menu (Copy/Delete via `remove`) wired, misleading Edit==Copy button dropped;
  Pairing "Enter code instead" now a real code field (reuses `pairing.extractToken`).
- **Per-device sync** (replaces the single global yes/no popup): new cloud column
  `devices.sync_enabled`; shared helper `lib/deviceSync.ts` (`fetchAccountDevices`,
  `setDeviceSync`, `isDeviceOnline`); a root-mounted `DevicesSyncHost` sheet
  (`showDevicesSheet()`, mounted beside `ConfirmHost`) shown from `useAuth.afterSignIn`
  when other devices exist; each device has its own Switch; toggling THIS device mirrors to
  local `verbal_sync_enabled` (drives `lib/useSync`); on sign-in this device reconciles its
  flag from its own cloud row. Ongoing management via the rebuilt `DevicesScreen` (native
  Switches — avoids the JS-modal-in-modal touch issue).
- **Keyboard fast-typing (dropped letters) fixed** on BOTH platforms
  (`plugins/keyboard/FlumeInputMethodService.kt`, `targets/keyboard/KeyboardViewController.swift`):
  (1) config cached by file-mtime (was disk-read+JSON-parse per keystroke); (2) suggestions
  DEBOUNCED ~70ms off the commit path (was a 25k-word scan + IPC per keystroke); (3) shift/
  auto-cap now update key labels IN PLACE (`refreshLetterCaps`) instead of a full
  `showKeyboard()` rebuild — the rebuild was the primary cause, racing the next rapid tap
  (esp. the letter after a space); (4) on-device learning writes moved off the main thread.
  Verified via the EAS Android APK (native can't hot-reload).

## Multilingual transcription (Jul 2026)

Whisper was hard-pinned to `language="en"` in four places — the model itself is multilingual (~99
languages). Now: `config['spoken_language']` (ISO-639-1 or `auto`; default `en` preserves old
behavior) applies to dictation AND meetings; a per-meeting **Language** picker in the pre-meeting
modal overrides it (`start_meeting(..., language)` → `MeetingSession.language` → every chunk).
Resolution + routing live in `transcriber.resolve_language` / `transcribe_with_status(language=…)`:
`auto` → omit the param (Whisper detects); non-English pins route Groq to full **whisper-large-v3**
(turbo is weaker on low-resource languages); the English dictionary-glossary bias prompt is attached
ONLY when the language is English (a Whisper prompt also hints the language). The dictation formatter
carries a "same language, never translate" rule. Options list: `shared_dashboard.SPOKEN_LANGUAGES`.
Mobile: `lib/groq.ts` honors `flume_spoken_language` (default `en`; no picker UI yet). Known limit:
code-switched meetings resolve per 8–22s chunk in auto mode.

**Meeting notes/summary output language is a separate setting from transcription language**
(`config['meetings_notes_language']`, Settings → Meetings): default `"en"` always writes the
summary/decisions/action items/notes in English, regardless of what language (or script) the
meeting was recorded in — e.g. a meeting transcribed in Roman-script Urdu still gets English notes.
Set it to `"auto"` to fall back to the old behavior: per-meeting `MeetingSession.language` pin >
global `spoken_language` pin > script detection over the transcript > English. Resolution lives in
`meetings._summary_output_language`, used by both `generate_meeting_summary` and
`generate_meeting_notes`.

## Custom keyboard — core features (mobile, iOS + Android)

Verbal ships a real system-level keyboard on both platforms (iOS extension
`targets/keyboard/KeyboardViewController.swift`, Android IME `plugins/keyboard/
FlumeInputMethodService.kt`) — a from-scratch QWERTY/numbers/symbols keyboard, not a wrapper around the
system one. The "Flume bar" above the keys has icon buttons that toggle in-keyboard overlays (tap-to-insert
rows), a pattern every subsequent keyboard feature (clipboard history, Transform) has reused rather than
inventing new UI:

- **Snippets** — spoken/typed trigger phrases expand to full text, browsable and tap-to-insert directly
  from the keyboard (not just via dictation).
- **Canvas** — the cross-device shared-clipboard feature, reachable from the keyboard too.
- **History** — recent dictations, tap to re-insert.
- **Vocabulary** — the user's custom dictionary words, with phonetics shown if present.
- **On-device word suggestions**: prefix completions AND next-word prediction from a personal
  word/bigram model (`learnWord`/`learnBigram`, bundled `flume_words.txt`/`flume_bigrams.txt` seed data),
  persisted per-keyboard (see `05-conventions.md` Hard Rule #16 for the exact storage/caps). Suggestions
  can also surface an emoji for an exact word match.
- **Emoji picker**: a full bundled library (~1900 emoji, 9 groups + Recents) with keyword search
  (`flume_emoji_kw.txt`) mapping typed words to relevant emoji.
- **Dictation via mic**: records and transcribes through the same `groq-proxy` pipeline as the in-app
  recorder; on iOS (which can't run JS in an extension) this hands off to `lib/dictationPipeline.ts` in
  the main app — see `02-architecture.md`'s "Shared dictation pipeline contract" note. Android's IME
  mirrors the same transcribe → cleanup → replacements → snippets sequence natively in Kotlin.

All of the above predates and is extended by the clipboard-history and Transform features below, which
reuse the identical bar-icon → overlay → tap-to-insert (or bar-icon → live-action) shape. Deep
implementation gotchas (fonts, sounds, typing feel, theming, the app→keyboard config bridge) live in
`05-conventions.md` Hard Rule #16 — this section is deliberately the "what," not the "how."

## Keyboard clipboard history (mobile, Jul 2026)

A 5th Flume-bar icon (clipboard glyph) on both custom keyboards opens a clipboard-history
overlay (same bar-icon → overlay → tap-to-insert pattern as dictation history), plus an ephemeral
"quick paste" chip near the bar that appears once per new copy with an 8-char preview — tap either
to insert the full text.

**Entirely self-contained in each keyboard target — not part of the `flume_kbd_config.json`
app→keyboard bridge.** Neither the main app nor JS ever sees clipboard content; only the extension
observes and persists it, to a NEW file `flume_kbd_clipboard.json` (iOS: same App Group container as
the config bridge; Android: the IME's own `filesDir`), capped at 15 entries (mirrors the existing
dictation-history wire cap). One preference IS threaded through the existing bridge:
`clipboardHistoryEnabled` (`lib/storage.ts::getClipboardHistoryEnabled`/`setClipboardHistoryEnabled`,
default ON, Settings → Keyboard) — gates the feature without carrying any clipboard content itself.

- **iOS** (`KeyboardViewController.swift`): clipboard access needs the keyboard's "Full Access"
  permission. The quick-paste chip simply doesn't render without it (ambient, not naggy); the
  clipboard overlay always shows the icon, but tapping it without Full Access shows an explicit
  "tap to open Settings" row (`extensionContext?.open(...)`) instead of the list — informative,
  never silently broken. Detection happens in `viewWillAppear` (the only reliable moment an
  extension can notice a clipboard change — extensions don't run in the background) by comparing
  `UIPasteboard.general.changeCount` against a persisted value.
- **Android** (`FlumeInputMethodService.kt`): no permission gate needed. A
  `ClipboardManager.OnPrimaryClipChangedListener` registered in `onCreate()` can catch a clipboard
  change made in another app before the keyboard reopens (Android IMEs stay resident more readily
  than iOS extensions); `onStartInputView` re-checks once as a fallback.
- **Privacy — respected on both platforms, not optional:** content flagged by the password-manager
  "don't capture this" convention is skipped for both the chip and history — Android's
  `ClipDescription.EXTRA_IS_SENSITIVE` (API 33+) and iOS's de facto `org.nspasteboard.ConcealedType`
  UTI (set by 1Password/Bitwarden etc). Clipboard content is never synced to Supabase or any cloud
  store — device-local only, always.

## Transform — voice/prompt-driven text reshaping (TRANSFORM_SWARM.md, Jul 2026)

**What:** reshape text with an instruction instead of just dictating it. Master switch
`transform_enabled` (default OFF) + per-mode flags, in Settings → Transform.

- **Mode A — inline (Capture):** end a dictation with *“…so Flume, make this formal”*. A free
  tail-gate (`transform.detect_trailing_instruction` — trigger homophones `transform_trigger_words`,
  ≥3-word body, instruction must START with an editing verb from `INSTRUCTION_VERBS`) splits body from
  instruction; `apply_instruction` (TRANSFORM_SYSTEM_PROMPT via groq-proxy) rewrites the body; the
  overlay shows *“✦ Transformed · <instruction>”* so a wrong split is catchable. ANY failure falls
  back to the untouched `process_text` path (Rule #1). Hook lives in `main`'s transcribe worker,
  BEFORE `process_text`.
- **Mode B — selection (Agentic):** select text anywhere → **⌘⇧T** → `transform.capture_selection`
  (save clipboard → synth ⌘C → read → ALWAYS restore) → `transform_widget.TransformWidget` cream pill
  (non-activating, bottom-center): **Improvise** (IMPROVISE_SYSTEM_PROMPT clarity pass), typed
  instruction, or SPOKEN instruction (reuses Recorder+transcriber; blocked while a meeting holds the
  mic). Result is a **preview** — Replace pastes over the still-highlighted selection
  (`injector.inject_text`), then a 6-s **Undo** (target-app ⌘Z). Cancel/no-selection/too-long
  (>12k chars) are all no-ops.
- **Mobile — Mode B on the keyboard (Jul 2026):** a dedicated Transform button (iOS SF Symbol
  `wand.and.stars`, Android Ionicons `sparkles-outline`) on both custom keyboards
  (`targets/keyboard/KeyboardViewController.swift`, `plugins/keyboard/FlumeInputMethodService.kt`),
  gated by `transformEnabled` (default OFF, bridged like `clipboardHistoryEnabled` — Settings →
  Keyboard). No Accessibility-style universal selection API exists on mobile, so selection is read
  through the focused field's own proxy instead: iOS `textDocumentProxy.selectedText`, Android
  `currentInputConnection.getSelectedText(0)` (the same call already used for the existing
  delete-over-selection backspace logic). Empty/unreadable selection shows an inline "Select some
  text first" message rather than silently doing nothing. **Typing the instruction reuses the
  physical keyboard itself**: both files already funnel every keystroke through one centralized
  `commit()`/`onSpace()`/`onBackspace()` — a compose-mode flag redirects these to a local instruction
  buffer instead of the host app, so the letters layer stays fully usable while the original
  selection is left untouched (critical: nothing touches the host proxy until the final Replace,
  which is what keeps the selection alive through the whole flow). The existing mic button is
  repurposed (same button, mode-dependent meaning) to speak the instruction via the already-built
  recording→transcribe pipeline; a horizontally-scrollable preset row (Improvise + Formal/Casual/
  Shorten/Fix grammar) covers the one-tap case. Same verbatim `TRANSFORM_SYSTEM_PROMPT`/
  `IMPROVISE_SYSTEM_PROMPT` and de-wrapping logic as desktop, called directly from the extension via
  a new JSON chat-completions call (`chatViaProxy`/`proxyChat`) — a sibling of the multipart
  transcription call each file already makes, same `groq-proxy` endpoint (it already routes JSON→chat
  vs multipart→transcription), no backend changes needed. Selection sent to the LLM is capped at 8000
  chars (smaller than desktop's 12000 — mobile selections are shorter, and the shared Groq key has a
  real tokens-per-minute ceiling, see the 413-handling note in `05-conventions.md`). **No OS-level undo
  exists on mobile** (no "send ⌘Z to the host app" equivalent) — Undo is a soft implementation: delete
  exactly as many characters as the rewrite inserted, then re-insert the original captured text; correct
  only if nothing else was typed/moved since Replace, shown as a ~6s bar chip (shared with the clipboard
  quick-paste chip — whichever ephemeral affordance is most recent wins; the two never show at once).
  Mode A (trailing "…so Flume, …" trigger) is not implemented on mobile.
- **Fixtures:** `whisperflow/transform_fixtures.py` (16 gate cases + output unwrapping, offline).
