# Verbal — End-to-End Flow & UI Audit

**Date:** 2026-08-06 · **Scope:** every user-facing workflow on macOS, Windows, iOS/Android (app + native keyboards), plus the Supabase-backed sync layer.
**Method:** 7 parallel code audits (auth/session, pairing+sync, desktop dashboard+popover, desktop aux surfaces, mobile UI wiring, mobile core flows, Windows parity), each cross-referencing UI → bridge/handler → backend code. Findings below are deduplicated and verified against code, not docs.

**Severity:** 🔴 P0 = broken flow / data loss / trust-breaking · 🟠 P1 = major gap or inconsistency · 🟡 P2 = polish / hygiene.

---

## 1. Executive summary

The core loop (hotkey → record → transcribe → inject) is solid on desktop, and the hard parts that are usually wrong — PKCE loopback, deep-link auth, atomic config writes, single-use pairing claim, notes merge contract, fail-closed peripherals — are **verified correct**. The problems cluster into seven systemic themes, not scattered one-offs:

| # | Theme | The pattern | Worst instances |
|---|-------|-------------|-----------------|
| T1 | **Two identity sources fight each other** | `sync_user_id` / stored id vs. the live Supabase session — each surface picks a different winner | Mobile pairing is a **silent no-op** (session id overwrites the adopted id ms later); desktop sign-out keeps writing to the ex-account's cloud; Settings "Account ID" field is dead UI |
| T2 | **UI lies about success** | Optimistic `_ok()` / unconditional success copy / swallowed promise rejections | Confirmation screen says "Pasted to MacBook" on a *failed* transcript; Windows toggles (Transform/auto-learn/file-tag) flip on and do nothing; "Saved & synced" shown unconditionally; delete-note hides the note even when the server delete failed |
| T3 | **Zero press feedback, app-wide** | No `:active` / pressed-state anywhere | 0 of ~107 desktop dashboard elements; all 5 aux surfaces; ~30 mobile tappables incl. the primary dictation controls |
| T4 | **Deletes don't propagate — some resurrect** | No tombstones, no DELETE subscriptions, additive merges | Deleted notes are **re-uploaded by the phone's back-fill** and come back; history deletes invisible cross-device; devices are immortal; storage audio orphans forever |
| T5 | **No sync lifecycle management** | Subscribe-once, no catch-up after sleep/reconnect, no teardown on account change | Zero `AppState` wiring on mobile (auth refresh + realtime both); canvas channel stays bound to the old account after sign-out |
| T6 | **"Sync" means something different on every surface** | Three mobile toggles, two backing stores, desktop gates a different feature set | Sync-off still uploads notes edits & the whole dictionary; per-device sync switch controls nothing on desktop |
| T7 | **The iOS keyboard skipped the pipeline contract** | `dictationPipeline.ts` is dead code; iOS calls the proxy raw | No dictionary bias, no replacements, no snippets on iOS keyboard dictation; every error path is silent (`flashMic` is an empty stub) |

**Totals:** ~15 P0 · ~55 P1 · ~60 P2 across 16 workflows (detail below).

---

## 2. The P0 list (fix before anything else)

| # | Workflow | Finding | Where |
|---|----------|---------|-------|
| 1 | Pairing | **Mobile pairing silently does nothing.** `claimPairing` adopts the host's `user_id`, but `getUserId()` treats the session id as authoritative and writes it back on the next call — the immediate `hist.refresh()` reverts the adoption within ms. Token burned, "Paired ✓" shown, nothing changed. Same root kills the Settings "Account ID" field. | `lib/storage.ts:46-53`, `lib/pairing.ts:59-60`, `RootNavigator.tsx:242-251` |
| 2 | Pairing / security | **`pairings` SELECT policy = `using(true)`** → anon key can enumerate every `user_id` ever paired; rows never deleted after claim/expiry. Under the user_id-scoped access model, a harvested id is full account access. | `whisperflow/supabase_pairings.sql:37-38` |
| 3 | Notes sync | **Deleted notes resurrect.** Mobile `load()` back-fills every cached note missing remotely → re-uploads notes the Mac deleted; desktop merge never prunes either. Deletion propagates in neither direction and is actively reverted in one. | `useNotes.ts:186-211`, `shared_dashboard.py:1333-1348` |
| 4 | Auth (desktop) | **Sign-in wall traps "Later" users.** First-run alert offers "Later" and anonymous dictation works, but the dashboard hard-gates on `signed_in` with no skip (the `.siSkip` CSS is orphaned — button was removed). Combined with #5, a canceled sign-in = stuck screen. | `flume_dashboard_html.py:1757-1766,453-466`, `main.py:300-309` |
| 5 | Mobile recording | **Recording modal can strand the user.** `handleStop`/`handleCancel` `await stop()` with no try/catch; `stop()` rethrows; modal has `gestureEnabled:false` → both buttons dead, no way out. Also: Cancel actually runs the **full pipeline** (uploads, burns quota, success haptic) instead of `cancel()`; no in-flight guard → double-tap = two history entries; unmount cleanup is a no-op (stale closure) so the mic can stay hot. | `RecordingScreen.tsx:30-46`, `useRecorder.ts:117-197` |
| 6 | Mobile dictation | **Groq-key gate can fail every in-app dictation.** `getGroqKey()` resolves from a user key (no UI sets one) or the `app_config` table (documented as absent from live schema); three call sites hard-fail on empty key — while `lib/groq.ts` states the key is IGNORED (proxy holds it). The gate can only produce false failures. ⚠️ Verify `app_config` in live DB; if present the severity drops, but the gate is still wrong-by-design. | `lib/storage.ts:108-114`, `useRecorder.ts:158`, `historyStore.ts:275`, `useNotes.ts:379` |
| 7 | Keyboard (iOS) | **iOS keyboard dictation skips 3 of 4 pipeline stages** — no vocabulary prompt, no replacements (written to the shared config but never read), no snippets, no language param. The documented main-app handoff doesn't exist; `dictationPipeline.ts` has zero callers repo-wide. | `KeyboardViewController.swift:1766-1804`, `lib/dictationPipeline.ts` |
| 8 | Keyboard (iOS) | **Every dictation error path is silent** — `flashMic` is an empty stub; HTTP status discarded (401/429/500 ≈ success); no timeout; mic-denial/empty-audio show nothing. | `KeyboardViewController.swift:1703-1790` |
| 9 | Keyboard (Android) | **One bad config file permanently kills dictation** — `readConfig()` caches the failed parse by mtime and keeps returning null; audio deleted, nothing committed, silently. | `FlumeInputMethodService.kt:1551-1561,1900` |
| 10 | Keyboard (both) | **Transcript lands in whatever field is focused when the network returns** — no field-identity token, no age check; `secure` only checked at tap time, so a dictation started in chat can be typed into a password field. | `FlumeInputMethodService.kt:1535-1541`, `KeyboardViewController.swift:1804` |
| 11 | Transform (both keyboards) | **Replace never re-validates the selection** → collapsed selection = document ends with original **and** rewrite. | `KeyboardViewController.swift:1625-1627`, `FlumeInputMethodService.kt:1829` |
| 12 | Transform (both keyboards) | **A failed transform permanently bricks the keyboard UI** — Android never restores `content` from the spinner; iOS's restore is guarded on a state it can't be in. | `FlumeInputMethodService.kt:1766-1791`, `KeyboardViewController.swift:1574-1578,1485` |
| 13 | Desktop dashboard | **`delNote()` ignores `r.ok`** — server-side delete failure still removes the note from the list. | `flume_dashboard_html.py:1100` |
| 14 | Desktop overlay | **Cancel while transcribing doesn't cancel** — `_cancel_flag` never set on this path; text still pastes into the focused app after the user pressed Cancel. | `overlay.py:246-250`, `main.py:947-952` |
| 15 | Contracts | **`useNotes.mock.ts` drift** — mock missing `flags`/`saveDictation`/`reformatNote`/`removeNotes` etc., all consumed by live screens (violates the "mocks are the design contract" rule; 3 more hooks drift at P1). | `useNotes.mock.ts` vs `useNotes.ts:477-489` |

---

## 3. Workflow-by-workflow findings

### 3.1 Sign-in / session

**Verdict:** the auth *mechanics* are excellent (PKCE loopback edge cases, deep-link dedup, refresh-lock concurrency all verified); the *UX around failure* is missing.

- 🔴 Desktop sign-in wall + no skip (P0 #4).
- 🟠 Desktop sign-in button latches forever on cancel/timeout — optimistic `_ok()`, failure only shows a rumps alert, static `#signin` pane never re-renders (`flume_dashboard_html.py:1768-1774`, `auth.py:139-140`, `main.py:404-406`).
- 🟠 Windows sign-in failure is 100% silent — `logger.error` only (`win_main.py:295-307`).
- 🟠 Mobile: no `AppState` wiring for `startAutoRefresh`/`stopAutoRefresh` → backgrounded >1 h can return with an expired token (`lib/supabase.ts:10-18`).
- 🟠 **Dead session is invisible** — desktop drops to anon but `get_state` still says `signed_in: true`; account deletion then returns "Not signed in" to a user the UI shows as signed in (`auth.py:43,192-195,325-334`, `shared_dashboard.py:464`).
- 🟠 Session death handled **oppositely**: desktop silently degrades to anon; mobile teleports to Welcome mid-use with no explanation (`useAuth.ts:143-145`, `RootNavigator.tsx:427`).
- 🟡 Loopback port 8765 collision paths opaque; Welcome button has no in-flight state; first-sign-in store refresh only patched for history.

### 3.2 Onboarding & permissions

- 🟠 **Windows renders the macOS permission wizard** — 4 "Grant" buttons that can never succeed (`permissions.py` is AppKit-only; every check → "unknown") (`shared_dashboard.py:469`, `flume_dashboard_html.py:1753-1801`).
- 🟡 Wizard step-2 "Sign in" branch is unreachable dead code (signin gate has priority).
- 🟡 Order inverted across platforms: desktop = sign-in→wizard; mobile = onboarding→sign-in.
- 🟡 Mobile "Skip for now" ≡ "Get started" (same callback, only rendered on last slide).
- 🟡 `completeOnboarding` calls `signOut()` unconditionally — if the onboarded flag is ever lost with a live session, finishing onboarding silently wipes local data (`RootNavigator.tsx:401-407`).
- 🟡 Mac fires the Accessibility prompt at startup, before any onboarding context, then asks again in the wizard (`main.py:283-287`).

### 3.3 Sign-out & account deletion

**Verdict:** the deletion *server contract* is right (JWT-scoped, two-step confirm, both clients). The local-teardown side leaks.

- 🟠 **Desktop sign-out keeps `sync_user_id`** → new meetings/notes/dictionary edits keep POSTing into the ex-account and appear on its other devices (`auth.py:198-203`; readers: `meetings.py`, `dictionary.py:339,364`, canvas, notes).
- 🟠 **Neither platform removes its `devices` row on sign-out**; the desktop presence heartbeat keeps upserting `last_seen` → the ex-account sees the device permanently "online" and pushes to it vanish.
- 🟠 **Keyboard config survives sign-out/deletion** (found independently by two audits): `flume_kbd_config.json` (last 15 dictations, vocab, snippets) stays in the App Group/`filesDir`; next phone user can read it from the keyboard's History panel (`keyboardBridge.ts:26-80`, `storage.ts:78-87`, `useAuth.ts:197-235`).
- 🟠 Mobile deletion leaves local audio on disk (`documentDirectory/recordings/` never removed); desktop `rmtree`s correctly — asymmetric.
- 🟡 Desktop lacks mobile's "different uid → wipe caches" guard: next account inherits the previous account's history/notes/dictionary (`auth.py:165-189` vs `useAuth.ts:92-96`).
- 🟡 Desktop deletion config-resurrection race (`wipe_local_account_data()` reloads from disk while the live in-memory config can re-save the deleted auth) (`shared_dashboard.py:972-986`).
- 🟡 Sign-out doesn't stop an in-progress meeting/recording; no "account deleted" confirmation on either platform.

### 3.4 Device pairing

- 🔴 Mobile claim is a no-op (P0 #1) · 🔴 `pairings` harvesting (P0 #2).
- 🟠 Claim skips the account-switch teardown sign-in performs → old cache re-uploaded **into the host's account** by the notes back-fill (`pairing.ts:58-62` vs `useAuth.ts:92-96`).
- 🟠 Flow is one-directional and desktop `claim_pairing()` is dead code — no Mac↔Mac, no phone-hosts path (`pairing.py:79-110` uncalled; not on the documented dead-code list).
- 🟠 Pairing requires the phone to already be signed in (PairDevice lives inside the auth-gated Main stack) — defeating pairing's stated purpose of joining without a second Google sign-in.
- 🟡 Cancel/expiry never revokes the token server-side; double-click `startPairing` orphans a claimable row; `start_pairing` failure shows no error; `pairing.py` is the one desktop call site not using `auth_header()`; pairing-while-signed-out mints a `uuid4` that a later sign-in orphans.

### 3.5 Devices list & presence

- 🟠 **No device can be removed on either platform** (`useDevices.unpair` never called; desktop has no control) — and the unwired `unpair` isn't user-scoped (would delete across tenants under `USING(true)`).
- 🟠 Per-device sync switch writes `devices.sync_enabled`, which **desktop never reads** — remote control that controls nothing (`deviceSync.ts:48-61` vs `sync.py:288-326`).
- 🟠 Presence heartbeat rides the *dashboard window's* refresh loop → close the window, go offline within 5 min (same bug class the "cross-device visibility" commit fixed) (`flume_web_dashboard.py:356-357`).
- 🟠 Five independent `useDevices()` instances, no shared store — target picked on Home never reaches the instance that routes dictations (`RootNavigator.tsx:450,458`).
- 🟡 Device identity unstable (name-derived id; rename = orphan row), `device_type` flip-flops `'ios'`/`'iphone'`, desktop renders a phone icon for every device, hostname collisions; Windows never restores the persisted sync target.

### 3.6 History / transcriptions sync

- 🟠 **Asymmetric receive:** Mac auto-pastes incoming dictations into the focused app and *discards* them — never queries the table, nothing lands in Mac history (`main.py:343-358`).
- 🟠 No DELETE subscription + additive union merge → deletes never propagate; desktop `clear_history` is local-only.
- 🟠 No catch-up after sleep/reconnect (zero `AppState` hits repo-wide); desktop reconnect has two overlapping retry paths that can stack connections (`sync.py:196-208`).
- 🟡 Desktop never pushes `audio_url` (audio never crosses devices from desktop); deleted entries orphan their storage objects; retry produces different text than the original attempt (retry adds AI cleanup, first pass doesn't — `historyStore.ts:278` vs `useRecorder.ts:161`); duration re-estimated as `words/2.5` on refresh; Confirmation screen P0 (#5-adjacent) claims "Pasted" unconditionally.

### 3.7 Notes

- 🔴 Resurrection via back-fill (P0 #3) · 🔴 desktop `delNote` ignores failure (P0 #13).
- 🟠 Conflict pairs are generated but **no screen renders `conflict`/`conflictOf`** — and the back-fill uploads the conflict copies as permanent duplicate notes.
- 🟠 Notes never refresh (no realtime despite being in the publication, no pull-to-refresh, `load` not exposed); mobile writes ignore the Sync toggle (only `createNote` checks it).
- 🟠 Un-debounced per-keystroke autosave (AsyncStorage + Supabase write per char) with a create-race that can **silently drop every edit** to a brand-new note (`useNotes.ts:285` + `:212`).
- 🟠 Failed/empty dictation into a note = silent no-op, audio never linked (`NoteEditorScreen.tsx:~85`).
- 🟡 `reloadFlags` has no callers (Settings toggles don't affect a mounted Notes tab); LWW on client clocks; conflict copies deliberately unpushed → divergent artifacts.

### 3.8 Canvas

- 🟠 Mobile never fetches on open (refresh is button-only → empty board despite data); subscribe effect captures `userId` once, never resubscribes on account change, never tears down on sign-out.
- 🟠 Clearing doesn't propagate (empty string is falsy → dropped by mobile and the Mac native window); mobile `discard` is local-only.
- 🟡 Origin filter compares device *names* (two "Mac"s drop each other; unset name = Mac re-applies its own writes); redelivered events duplicate cards; mobile text-send nulls the image; desktop canvas listener thread leaks past sign-out (`while True` with captured creds).

### 3.9 Dictionary & snippets

- 🟠 Whole-blob last-write-wins, `updated_at` written but never compared — two devices in one session silently drop each other's edits; a vocab edit rewrites snippets too (shared row).
- 🟠 **Edit-before-load wipes the row:** both mobile screens init state without a `snippets` key; an add tapped before `fetchRemote()` resolves pushes `snippets: []` over the cloud (`DictionaryScreen.tsx:19`, `SettingsScreen.tsx:42`).
- 🟡 No realtime on any platform; un-awaited push/fetch race can revert a just-saved edit locally; signed-out mobile writes junk `user_<ts>` rows (desktop correctly early-returns); errors swallowed → lost write ≈ success.

### 3.10 The Sync toggle (deserves its own heading)

- 🟠 Three mobile UIs, two backing stores (Menu/Settings → local flag; Devices row → local **and** cloud) that can disagree.
- 🟠 No live effect: toggling on doesn't subscribe/fetch (needs restart); toggling off doesn't unsubscribe (keeps receiving).
- 🟠 Gates a different feature set per platform (mobile: history/canvas/meetings/notes-create; desktop: SyncClient + notes; dictionary/meetings/recordings ungated everywhere) — none matching the UI copy "Sync history, notes & clipboard across devices."

### 3.11 Meetings (mobile read/edit side)

- 🟠 `fetchMeetings` returns `[]` on error → transient blip blanks the list (the keep-previous guard is dead).
- 🟠 Offline/failed scratchpad + notes edits are dropped silently (return value ignored, no local cache).
- 🟠 "Last-write-wins on `updated_at`" is claimed but not implemented — blind update, no `user_id` filter; the adopt-effect is `!notes`-guarded so a desktop regeneration is never shown once notes are loaded, and the next keystroke clobbers it.
- 🟠 Four independent `useMeetings()` instances share one channel topic — one screen's unmount can kill another's subscription; every keystroke echo triggers N× full refetch incl. transcripts; on-device notes generation has no timeout (spinner forever).
- 🟡 Debounce timers not flushed on unmount; action-item `done` toggles from desktop never re-sync (length-based dep); playback URL resolved once, no refresh/catch.

### 3.12 Desktop dashboard & popover (wiring)

**Verdict:** method-name wiring is clean — all ~107 `api()` calls resolve to real methods; zero literally-dead handlers. The problems are behavioral:

- 🟠 **"Resend" (dashboard) and "Paste again" (popover ×2) are fake** — all call `copy_text`, identical to Copy; the real injection path (`main.py::_paste_synced`) is never bridge-bound.
- 🟠 Windows/`SharedDashboard` emits a `devices` event the shared HTML has no case for (Mac path was fixed to re-emit `state`; Windows wasn't) → stale sidebar device list.
- 🟠 One-click irreversible deletes (note/meeting/snippet) — the good pattern (double-confirm + disable + error alert) exists on `deleteAccount` and was applied nowhere else.
- 🟠 Only 5 of ~107 elements have double-submit protection; toggles flip optimistically and never revert on `!r.ok`.
- 🟡 `saveCanvas` says "Saved & synced" unconditionally; `stop_meeting` fire-and-forget + `setTimeout`; 4 orphaned DashboardApi methods (`pin_text`, `toggle_note_pin`, `search_notes`, `clear_history`) with no UI callers; bootstrap rides a blind 400 ms timeout instead of a real ready event.

### 3.13 Desktop aux surfaces (overlay, meeting, auto-learn, transform, menubar)

- 🔴 Overlay Cancel-while-transcribing doesn't cancel (P0 #14).
- 🟠 Overlay + auto-learn widget use stock `WKWebView` — **first click from another app is swallowed** (missing the `acceptsFirstMouse` subclass both these focus-stealing surfaces need most).
- 🟠 Transform pill: Replace double-fires on fast clicks (pastes twice); failures during preview write to the *hidden* pill's error node → invisible errors; an escaped worker exception leaks `_busy=True` → stuck spinner.
- 🟠 Menubar checkmarks desync from dashboard Settings (`save_settings` never updates `mode_hold`/`mode_toggle`/model states).
- 🟡 Overlay: pause gives no feedback + timer drifts vs paused audio; error states render with success ✓ styling + a "Copy again" that copies stale text; retired accent `#E8522A`; no Stage-Manager opt-outs; no ready-handshake (record-at-launch shows no pill). Meeting: `preStart()` ignores start failure (stuck REC on empty screen); `MeetingHud` is confirmed dead code; bridge methods bypass the lazy accessor. Menu: "Reset Onboarding (dev)" ships to everyone; model default `"medium.en"` matches no option; orphaned `_manage_keys`; no manual "Check for Updates…".

### 3.14 Mobile UI wiring (screens/components)

**Verdict:** 21 screens, ~110 tappables — zero outright-dead buttons, zero TODO handlers, all routes exist. The gaps are feedback and contracts:

- 🔴 Recording modal stuck-state (P0 #5) · 🔴 `useNotes` mock drift (P0 #15).
- 🟠 Hook↔mock drift in 3 more pairs: `useAuth` (missing `deleteAccount`), `useCanvas` (missing `updateText`/`refresh`/`toast`), `useHistory` (missing `retryEntry`/`playEntry`/`refresh` + item-shape fields).
- 🟠 **Primary dictation controls have zero press feedback** (NoteEditor mic dock, cancel/pause, back, raw-edit toggle — all static-style Pressables).
- 🟠 Every screen's back chevron reimplements a raw Pressable instead of the shared `IconButton` (which handles pressed-state correctly) — the shared components are right, the screens bypass them.
- 🟡 ~25 more no-feedback tappables across 12 screens (list in appendix source); `PairDeviceScreen.onUseCode` orphaned prop; `MicButton` component built-and-never-used; `MeetingPlaybackScreen` empty state renders nothing; double-tap guards missing on Canvas Save→Device and History Retry.

### 3.15 Windows build

- 🟠 Settings → Hotkeys "Change" **raises `AttributeError`** and prints the raw Python exception into the UI (`capture_next_key` doesn't exist on `VerbalWinApp`).
- 🟠 "Start meeting" is a pure dead button (`open_meeting_launcher` → `{ok:false}`, no `.then` handler → literally nothing happens).
- 🟠 Transform/auto-learn/file-tag toggles return `_ok()` and persist, but nothing on Windows reads the flags — silent success for features that don't exist there; Transform row even shows a `⌘⇧T` chord. No platform flag is ever passed into the shared HTML — everything renders clickable.
- 🟡 Mac copy shown verbatim ("this Mac", "⌘V", "Right ⌘"); permission wizard unsatisfiable (see 3.2); tkinter fallback dashboard would silently replace Flume UI if pywebview import fails; overlay likely has DPI + colorkey-halo issues (needs a live-box visual QA); multiple concurrent Tk interpreters across threads (About + overlay) is fragile.
- (Meetings/auto-learn/file-tag being unported is *documented scope*, not flagged — the bug is the UI pretending otherwise.)

### 3.16 Mobile platform gaps (not keyboard)

- 🟠 No spoken-language setting: `flume_spoken_language` is read but never written; everything force-English (desktop has the setting).
- 🟡 Ollama fallback exists only for meeting notes — Groq's daily 429 kills mobile cleanup/Transform while desktop survives; local recordings never pruned (`recordings.remove()` uncalled); hardcoded `9:41` mock clock in the recording status bar.

### Keyboard extras (beyond the P0s)

- 🟠 iOS: no re-entrancy guard on `stopAndTranscribe` (double `AVAudioRecorder` on one URL); `deviceId` never sent → all iOS keyboards share one anonymous rate-limit bucket; host writes leak during transform-compose (space-swipe, emoji).
- 🟠 Android: snippet expansion **cascades** (spec says single-pass) and an empty expansion deletes its trigger; `buildPrompt` missing the 200-term slice + 896-char cap (Hard Rule #6); recorder not stopped on keyboard dismissal (mic held forever); `transformState` survives app switches → typing swallowed; mic during compose types the instruction into the host (iOS handles this right); Transform + clipboard not gated on secure fields (mic is).
- 🟠 Transform (both): silent 8 000-char truncation → Replace destroys the tail unrecoverably; soft Undo is positional/unscoped (can eat characters in a *different field*); iOS lacks a request token (cancelled-then-restarted transform applies the stale rewrite).
- 🟡 `theme`/`schemaVersion` written but read by no native (a v3 reshape would silently misparse); iOS audio never deleted after success; UTC timestamps; main-thread JSON serialization per word boundary on Android.

---

## 4. The "clicky feedback" plan (T3)

Feedback is not inconsistent — it is **absent by construction** on every surface. Three small, global fixes cover ~95% of it:

1. **Desktop (all 5 HTML surfaces):** one shared CSS block — `button:active, .btn:active, .chipbtn:active, .toggle:active, .qcard:active, .ctrl:active, .iconbtn:active { transform: scale(0.97); filter: brightness(0.92); }` (+ a `transition: transform 80ms`) — added to `flume_dashboard_html.py`, `flume_popover_html.py`, `overlay_html.py`, `meeting_html.py`, `autolearn_widget.py`, `transform_widget.py`. Consider extracting a `shared_css.py` so it's written once.
2. **Mobile:** make `IconButton`/`Button`/`Chip` (which already do pressed-state correctly) the only way to render a tappable — replace the ~30 raw static-style `Pressable`s, starting with the back chevrons and the NoteEditor mic dock. One mechanical sweep.
3. **First-click reliability (mac):** add the `acceptsFirstMouse` WKWebView subclass to the overlay and auto-learn panels — on those surfaces the "button feels dead" complaint is literal: the first click is swallowed.

---

## 5. Recommended fix batches

| Batch | Contents | Why this order |
|---|---|---|
| **B1 — Stop the bleeding (P0s)** | §2 items 1–15: identity/pairing fix (one `getUserId` precedence rule + route claim through the sign-in teardown), notes tombstones + back-fill scoping, RecordingScreen guards, overlay cancel flag, `delNote` ok-check, keyboard P0s (iOS pipeline stages + error surfacing, Android config cache, field-identity token, Transform revalidate + UI restore), pairings RLS, Groq-key gate removal | Broken flows & data loss; several are one-file fixes |
| **B2 — Truthful UI** | Kill optimistic success everywhere: Confirmation failure variant, Windows platform gating (pass a `platform` flag into `flume_html()`, disable/hide unsupported), toggle revert on `!r.ok`, error text on pairing/sign-in failure, dead-session banner, Resend/Paste-again → real injection or removal | Trust: every "the app lied to me" finding is in this bucket |
| **B3 — Press feedback sweep** | §4, all three items | Cheap, global, directly the user ask |
| **B4 — Sign-out/deletion hygiene** | Clear `sync_user_id`, delete own device row, stop heartbeat, wipe keyboard config + mobile audio, desktop uid-change cache wipe, deletion race fix | One coherent PR around `sign_out()`/`deleteAccount` |
| **B5 — Sync semantics** | Unify the Sync toggle (one store, live subscribe/unsubscribe, same gate-set on all platforms), catch-up fetch on reconnect/foreground (`AppState`), DELETE propagation (tombstones or DELETE subscriptions), dictionary CAS on `updated_at`, singleton `useDevices`/`useMeetings` stores | The deepest work; needs the small design decisions below first |
| **B6 — Cleanup** | Dead code (`claim_pairing` or wire it, `MeetingHud`, `MicButton`, orphaned DashboardApi methods, `_manage_keys`, `dictationPipeline.ts` decision), mock-contract sync, Mac-copy strings on Windows, `context/` doc corrections | Zero-risk deletions once the above land |

## 6. Decisions needed from you (they gate B1/B5)

1. **Anonymous mode: in or out?** Half-built today. In → restore the desktop skip button + signed-out pairing entry on mobile. Out → remove the "Later" alert, guest-id path, and empty-`sync_user_id` branches. (Affects P0 #4.)
2. **Pairing identity model:** should a paired device get a *real session* for the host account (edge function minting a token), or an explicit "paired override" key that outranks the session id? The override is quicker; the session is the only version that survives the planned `auth.uid()` RLS migration.
3. **Device removal: cosmetic or real?** Real revocation requires per-device credentials (the RLS migration again). Cosmetic is fine short-term but should say so in the UI.
4. **Deletes: tombstones or DELETE-event subscriptions?** Tombstones (`deleted_at`) are more robust (survive offline windows) and fix the notes-resurrection P0 and history/canvas propagation with one pattern.
5. **`dictationPipeline.ts`:** make it real (route `useRecorder` + retry through it, and treat it as the Kotlin/Swift reference) or delete it and fix the docs. Keeping it dead guarantees future drift like the iOS pipeline gap.

---

## 7. Verified solid (no action — for your confidence)

Desktop PKCE loopback details (dual-stack bind, drain, one-shot exchange) · mobile deep-link dedup + cold-start handling · token-refresh locking + anon degradation logic · atomic pairing claim (both platforms) · `target_device_id` routing end-to-end · notes v2 merge contract mirrored correctly (storage layer) · Android `applyReplacements` faithful to the TS reference · App-Group config plumbing + mtime invalidation on both keyboards · iOS `transformEnabled` fail-closed at all read sites · deletion server contract (JWT-scoped, no user_id param) · mobile account-switch cache wipe · dashboard/popover method wiring (every `api()` call resolves) · all mobile navigation routes + no stranding on tab-bar-hidden screens · meeting window double-fire guards + ready handshakes · fail-closed discipline on peripherals (record→transcribe→inject never blocked).
