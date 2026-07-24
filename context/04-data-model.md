# 04 — Backend, Data Model, Auth & Sync

> Part of the `context/` knowledge set. See `context/README.md` for the maintenance rule.
> **Keep this current:** any schema change, new table/bucket, data-shape change, or auth/sync change
> must update this file. **When you add a column that only lives in the live DB, record it in §Schema gaps.**

## Supabase project

- **Ref:** `ovpcthjingugwvpxlsna` · **URL:** `https://ovpcthjingugwvpxlsna.supabase.co`
- One project shared by desktop + mobile. **Anon key hardcoded** in both:
  desktop `whisperflow/app/sync.py` (`SUPABASE_URL`/`SUPABASE_KEY`, reused via `from app.sync import …`
  by auth/recordings/dictionary/pairing/canvas_window/shared_dashboard); mobile
  `verbal-mobile/lib/supabase.ts` (`SUPABASE_URL`/`SUPABASE_ANON_KEY`).
- **Transport:** desktop uses raw `httpx` REST (`/rest/v1`) + a raw Phoenix WebSocket for realtime; mobile
  uses the `@supabase/supabase-js` SDK.

## Database schema

### Tables with committed SQL (in `whisperflow/`)

**`dictionary`** — `supabase_dictionary.sql` (+ `supabase_snippets.sql` for the `snippets` column). One row/user.
| col | type | notes |
|---|---|---|
| `user_id` | text | **PK** |
| `vocabulary` | jsonb | default `'[]'` |
| `replacements` | jsonb | default `'[]'` — `[{"from","to","auto"?}]` |
| `snippets` | jsonb | default `'[]'` — `[{id,trigger,expansion,label,used,created_at,updated_at}]` (spoken trigger → text expansion; caps 40/500) |
| `updated_at` | timestamptz | default `now()` |

RLS on; policy `dictionary rw`: `FOR ALL TO public USING(true) WITH CHECK(true)`
(`supabase_dictionary_rls_fix.sql`). **Must be `TO public`, not `TO anon`** — a
signed-in client (mobile SDK) sends an authenticated JWT (role `authenticated`), and a
`TO anon` policy would filter its rows out, silently breaking dictionary/snippet sync
to signed-in devices.

**`pairings`** — `supabase_pairings.sql`. Short-lived single-use device-pairing tokens.
`id` uuid PK · `token` text unique · `user_id` text · `host_device` text · `created_at` · `expires_at`
(~2 min TTL) · `claimed_by` text (null until claimed) · `claimed_at`. Index on `(token)`. RLS on;
anon insert/select/update all `true` (safe because tokens are random, short-lived, single-use).

**`notes`** — `notes_migration.sql` (base) + `supabase_notes_v2.sql` (self-contained: **creates the table if
missing** — it was never provisioned in the live DB, so Notes was local-only until 2026-07 — then adds v2 cols).
`id` **text** PK · `user_id` text · `title` text `''` · `content` text `''` (AI-formatted) · `folder` text `''` ·
`is_pinned` bool `false` · `device_name` text · `created_at` · `updated_at`. Indexes on `(user_id)` and
`(user_id, updated_at DESC)`. In the `supabase_realtime` publication.
**`id` is `text`, not uuid** (migration `fix_notes_id_type_to_text`, applied 2026-07 after a live-schema
audit found `supabase_notes_v2.sql`'s guarded `ALTER COLUMN id TYPE text` had never actually run against
this DB — the column was still `uuid` in production until then, verified fixed and default reset to
`gen_random_uuid()::text`): desktop writes `uuid4().hex`, mobile writes `note_<ts>` (not valid uuid syntax) — a
text column lets each client supply its **own** id so the note's local id === its cloud id. That equality
is load-bearing: mobile `updateNote` does `.update().eq('id', localId)`, and without it every edit matches
0 rows and the pulled-back row duplicates. Mobile `createNote` upserts **with** the id (gated on
`getSyncEnabled`), and `useNotes.load` **back-fills** any locally-cached note missing from the cloud
(notes created before the table existed never got pushed otherwise).
**v2 columns** (`supabase_notes_v2.sql`, idempotent): `raw_content` text nullable (raw Whisper transcript;
NULL for typed/pre-existing notes — `content` holds the formatted version, "show original" reveals this);
`audio_segments` jsonb `'[]'` (append-only list of source recordings, shape `[{id,url,created_at}]`,
**UNION-on-merge** during sync). **RLS:** enabled, `TO public` (`whisperflow/supabase_notes_rls.sql`,
MER-26, 2026-07) — the base file and `supabase_notes_v2.sql` wrote none (v2's guarded `DO` block only
broadens a *pre-existing* policy if RLS was already enabled, which it wasn't, so it was a silent no-op
until this fix landed).

**`groq_usage`** — `create_groq_usage` migration. Usage ledger (analytics only, not enforcement) for the
`groq-proxy` Edge Function: one row per request that reached the upstream call — `id`, `identity`
(`user:<uuid>`|`device:<id>`|`ip:<addr>`), `user_id?`, `kind` (`transcription`|`chat`|`chat-ollama` — the
`groq_usage_kind_check` constraint was fixed 2026-07 to actually allow `chat-ollama`; it silently rejected
every Ollama-routed usage-log insert before that, since `logUsage` is fire-and-forget with `.catch(()=>{})`,
so Ollama metering was a no-op in production until this migration), `created_at`. **RLS on**
(read-your-own for `authenticated`); only the function writes, via the service role (fire-and-forget).
Requests rejected by the rate limiter below never reach this table (they short-circuit before the upstream
call). Rate-limit *enforcement* itself now lives in `groq_rate_limits` (see below; MER-30, 2026-07 —
see `05-conventions` Hard Rule #15).

**`groq_rate_limits`** — `whisperflow/supabase_groq_rate_limits.sql` (MER-30, 2026-07). Per-identity
fixed-window (60s) request/token counters enforcing the `groq-proxy` rate limit. `identity` text ·
`window_start` timestamptz (epoch-aligned 60s bucket) · `requests` int · `tokens` int (coarse per-request
estimate, not real usage — see Hard Rule #15); PK `(identity, window_start)`. RLS on, **no policies** — the
table is only ever touched via the `groq_check_rate_limit` SECURITY DEFINER RPC, and `EXECUTE` on that RPC
is revoked from `anon`/`authenticated` and granted only to `service_role` (the Edge Function's own key) —
without that revoke, any client could call the RPC directly via PostgREST with an arbitrary `p_identity` to
tamper with another identity's counter; this was caught and fixed live via the security advisor during
MER-30 verification. Opportunistic cleanup (~1% of calls) deletes rows older than 10 minutes.

**`app_config` — referenced by code, does not exist in the live DB.** The provider-secret-key-table idea
(`GROQ_API_KEY` readable by clients) was correctly dropped — that must never exist; keys live only as the
`groq-proxy` function's own `GROQ_API_KEY`/`OLLAMA_API_KEY` secrets. But a *same-named*, different-purpose
table (general app-wide settings / cached shared Groq key, per `whisperflow/supabase_app_config.sql` and
mobile's `lib/remoteConfig.ts`, warmed in `RootNavigator.tsx` and read in `storage.ts`) is still actively
queried by mobile code — and a live-schema check found **no `app_config` table in the current `public`
schema at all**. Either the migration was never applied live, or this code path is currently dead/failing
silently. Needs verification, not just documentation, before relying on it.

**`push_tokens`** — `(user_id, token)` composite PK, `platform`, `device_name`, `updated_at`. RLS on.
Backs the meeting-start push-notification feature (`verbal-mobile/lib/notifications.ts::
registerForMeetingPush` upserts here) — undocumented until this pass.

**`device_presence`** — near-duplicate of `devices` (same columns minus `sync_enabled`). **Zero rows,
zero code references anywhere in `whisperflow/` or `verbal-mobile/`** — looks like an abandoned/orphaned
table (possibly an early false-started rename of `devices`). Flagging rather than documenting as a real
feature; worth confirming with whoever added it whether it's safe to drop.

**Edge Functions:** `groq-proxy` (`supabase/functions/groq-proxy/index.ts`) — the only holder of the
provider keys (`GROQ_API_KEY`, plus `OLLAMA_API_KEY` for the meeting-notes model `gpt-oss:120b`); brokers
all transcription + chat for every client. `verify_jwt` on. Per-identity rate limiting (MER-30, 2026-07)
enforced via the `groq_rate_limits` table + `groq_check_rate_limit` RPC, called with the service-role key
before any upstream fetch — see `groq_rate_limits` above and Hard Rule #15.

**`meetings`** — `supabase_meetings.sql` (applied live 2026-07 + follow-up `hybrid_notes` column). One row
per captured meeting.
| col | type | notes |
|---|---|---|
| `id` | uuid | **PK**, desktop-minted `uuid4` (mobile never creates) |
| `user_id` | text | scoping key |
| `title`, `scratchpad`, `summary` | text | scratchpad is the ONE mobile-writable field |
| `started_at`, `ended_at`, `created_at`, `updated_at` | timestamptz | |
| `duration_seconds` | int | elapsed excluding pauses |
| `audio_url` | text | public `meeting-audio` URL |
| `transcript` | jsonb | `[{speaker, t0, t1, text}]` — speaker ∈ `self`/`s<N>` |
| `speakers` | jsonb | `{speaker_id: display_name}` (`self` = "You") |
| `decisions` | jsonb | `["…"]` |
| `action_items` | jsonb | `[{owner: speaker_id\|null, task, done}]` |
| `marked_moments` | jsonb | `[{t, label}]` (t = secs from start) |
| `hybrid_notes` | jsonb | `[{user_line, ai_addition}]` — widget #21 (added after the base migration) |
| `device_id`, `device_name` | text | |
| `status` | text | `processing` \| `ready` \| `failed` (failed = summary failed, transcript intact) |
| `notes_md` | text | nullable — cached full AI meeting-notes markdown (`meetings.generate_meeting_notes`); see `03-features.md`'s Meeting Notes page. Mobile can now edit this directly, not just generate it |
| `live` | bool | default `false` — set while a meeting is actively being captured; surfaced to mobile as the live-transcript-in-progress flag |

Indexes `(user_id)`, `(user_id, started_at desc)`. **Realtime publication: yes** (mobile subscribes
INSERT+UPDATE on `verbal_meetings_<uid>` — the live-transcript stream). **`REPLICA IDENTITY FULL`**
(migration `meetings_replica_identity_full_for_realtime_updates`) — required so Realtime can match the
`user_id=eq` filter on UPDATE events; with the default (PK-only) identity INSERTs delivered but live
UPDATE chunks were silently dropped, so `MeetingLiveScreen` also polls every 3s while live as a fallback.
RLS on, policy "meetings rw" `FOR ALL TO public USING(true)`
(Hard Rule #10 — same deferred-hardening posture as the rest). Desktop also keeps a bounded metadata list
in `config['meetings']` (`MEETINGS_CAP=30`) and the mixed WAV at `~/.verbal/meetings/<id>.wav`.

**`app_versions`** — `supabase_migrations/001_app_versions.sql`. Auto-update manifest.
`id` bigserial PK · `platform` text (`mac`/`win`/`ios`) · `version` text · `changelog` · `file_url` ·
`file_hash` (sha256) · `file_size` · `released_at` · `UNIQUE(platform,version)`. RLS on; public SELECT;
inserts use **service_role** (release script) — no anon insert.

### `transcriptions`, `devices`, `canvas` (MER-28, 2026-07: now have committed SQL)

Previously existed only in the live DB, inferred from code, with no committed SQL — the single biggest
schema-vs-source gap this doc used to carry. Closed via `whisperflow/supabase_transcriptions.sql` /
`supabase_devices.sql` / `supabase_canvas.sql` (idempotent `CREATE TABLE IF NOT EXISTS` + RLS, written to
reproduce exactly what the live DB already had — **not** a behavior change; see the RLS note below).

**`transcriptions`** — the core dictation history / cross-device shared clipboard.
`id` uuid PK · `user_id` text · `device_id` text · `device_name` text default `''` · `text` text ·
`created_at` timestamptz default `now()` · `is_pinned` bool default `false` · `edited_text` text nullable
(read as `edited_text ?? text`) · `target_device_id` text nullable (Canvas-style targeting) ·
`audio_url` text nullable (private `recordings` bucket object path, see MER-27) · `status` text default
`'done'` (`'done'`\|`'failed'`, retryable). Indexes `(user_id, created_at desc)` and
`(user_id, is_pinned, created_at desc)`. In the realtime publication.

**`devices`** — device registry/presence. `id` uuid PK · `user_id` text · `device_id` text ·
`device_name` text · `device_type` text default `'mac'` (`mac`/`win`/`ios`) · `last_seen` timestamptz
default `now()` · **`sync_enabled`** bool default `true` (read/written by mobile `lib/deviceSync.ts` to
gate per-device sync). Unique index `(user_id, device_id)` (the upsert conflict target). "Online" =
`last_seen` within 5 min. In the realtime publication.

**`canvas`** — one shared row/user. `id` uuid PK (`gen_random_uuid()` default) · `user_id` text ·
`content` text default `''` · `device_name` text default `''` · `updated_at` timestamptz default `now()` ·
`image_url` text nullable. Unique index on `user_id` (the actual upsert conflict target — `id` is
informational, doesn't change upsert behavior). In the realtime publication.

## Storage buckets

- **`recordings`** (`supabase_recordings.sql` + `supabase_recordings_meeting_audio_private.sql`,
  MER-27, 2026-07) — audio. Object path **`<user_id>/<id>.<ext>`** (desktop 16 kHz WAV; mobile
  m4a/wav/caf). **Private** (was public — highest-sensitivity data the product holds, was downloadable by
  anyone with/able to construct a URL, zero auth). Consumers generate a short-lived signed URL on demand
  at playback/download time instead (`recordings.py::sign_url` / `lib/recordings.ts::signUrl`, ~180s TTL) —
  rows still store a value under `audio_url`, but it's now a **bare object path**, not a fetchable URL;
  a format-tolerant extractor (`extract_object_path`/`extractObjectPath`) accepts either a bare path (new
  writes) or a legacy `.../object/public/...` URL (rows written before this fix) so no backfill migration
  was needed. Policies widened from `TO anon` to **`TO public`** in the same fix (the exact
  `dictionary`/`notes` signed-in-mobile trap — see Hard Rule #10) — scoped to `bucket_id='recordings'`.
- **`canvas-images`** — canvas photo attachments, path `canvas/<userId>_<ts>.<ext>`. Still **public**
  (deliberately, per MER-27's scope — lower-sensitivity, user-chosen shares). Policy in
  `supabase_canvas_images_policy.sql` (idempotent: ensures the bucket exists + public, and read/insert/update
  `TO public` scoped to `bucket_id='canvas-images'`). A missing/blocked policy → mobile's anon upload fails
  silently → the shared photo never reaches the other device (now surfaced as an "Image upload failed" toast).
- **`releases`** — auto-update binaries, public SELECT. Stays public deliberately (app-update downloads).
- **`meeting-audio`** (`supabase_meetings.sql` + `supabase_recordings_meeting_audio_private.sql`,
  MER-27, 2026-07) — meeting recordings, path **`<user_id>/<meeting_id>.wav`** (16 kHz mono, mic+system
  mixed). **Private** (was public), same signed-URL mechanism as `recordings` but with a much longer TTL
  (~3600s, since a meeting can run long and the URL must stay valid for the whole playback+scrub session,
  not just the first byte) — see `meetings.py::_upload_audio` (stores a bare path) and
  `shared_dashboard.py::get_meeting_audio` / `MeetingPlaybackScreen.tsx` (sign at read time). Its
  read/insert/update/delete policies were already `TO public` — no role-scoping fix needed here.

## Exact data shapes in code

- **Desktop history entry** (`config.py::add_to_history`, in `~/.verbal/config.json` `history[]`, cap 50):
  `{id:<16-hex>, text, app, ts:"YYYY-MM-DD", audio:<local path>, audio_url:<cloud>, status:"done"|"failed"}`.
- **Mobile history entry** (`lib/storage.ts HistoryEntry`): `{id, text, device_name, device_id,
  is_pinned, created_at, source:'local'|'remote', audio_uri?, audio_url?, status?}`.
- **Replacement rule** (`dictionary.py`): `{from, to, auto?:true}` (`auto` = auto-learned, ✨ in UI).
- **Snippet** (`dictionary.py` / `lib/dictionary.ts`): `{id, trigger, expansion, label, used, created_at, updated_at}` (caps: trigger 40, expansion 500).
- **Dictionary**: `{vocabulary:[str], replacements:[{from,to,auto?}], snippets:[Snippet]}`.
- **Note** (matches `notes` table) — v2 shape: `{id, title, content, raw_content?:string|null,
  audio_segments?:[{id,url,created_at}], folder, is_pinned, device_name, created_at, updated_at}` plus
  sync markers `conflict?:bool` / `conflict_of?:string|null` (set on the two members of a conflict pair).
  Mobile `NoteEntry` adds `source:'local'|'remote'` and an index signature so **unknown/newer-client
  fields are preserved verbatim** (forward-compat). Mobile UI `Note` maps these to camelCase
  (`rawContent`, `audioSegments`, `conflict`, `conflictOf`).
- **Device**: `{user_id, device_id, device_name, device_type, last_seen}`.
- **Canvas** (mobile UI item): `{id, state:'draft'|'sent', kind:'text'|'link'|'image', …}` → collapsed to the
  single shared `{content, image_url}` row on save.

## Auth flows

### Desktop — Google PKCE loopback (`app/auth.py`)
1. `_pkce()` verifier + S256 challenge.
2. Browser → `{URL}/auth/v1/authorize?provider=google&redirect_to=http://localhost:8765/callback&code_challenge=…`.
3. `_DualStackServer` on **port 8765** (binds IPv6 `::` with `IPV6_V6ONLY=0` to catch `::1`/`127.0.0.1`,
   IPv4 fallback); `_CallbackHandler` captures `?code=`, serves a styled "Login successful" page, 180 s timeout.
4. Exchange `POST {AUTH}/token?grant_type=pkce` `{auth_code, code_verifier}`.
5. `_store_session` → `config['auth'] = {user_id,email,name,avatar_url,access_token,refresh_token}` and
   `config['sync_user_id']=user.id` (+ default `sync_device_name=platform.node()`).

### Mobile — Supabase OAuth + deep link (`lib/supabase.ts`, `flume-ui/hooks/useAuth.ts`)
- `signInWithOAuth({provider:'google', options:{redirectTo:'verbal://auth-callback', skipBrowserRedirect:true}})`
  → `WebBrowser.openAuthSessionAsync`. `redirectTo` **hardcoded** `verbal://auth-callback` (scheme in
  `app.json`; `makeRedirectUri()` returns `exp://` in Expo Go, so it only works in a dev/native build).
- `createSessionFromUrl`: PKCE `?code=` → `exchangeCodeForSession` (dedup via `_handledCodes`); implicit
  `#access_token`+`refresh_token` → `setSession`. `Linking` listener + `getInitialURL` for Android reopen.
- `afterSignIn`: `setUserId(session.user.id)`, `setSyncEnabled(true)`, upsert `devices`, "New device
  detected — Sync?" if other devices exist. Session in AsyncStorage, `autoRefreshToken:true`.
- Before sign-in, mobile uses a local guest id `user_<ts>_<rand>` (`storage.ts::getUserId`).

### Setup (`GOOGLE_AUTH_SETUP.md`)
Google OAuth client = **Web application**; sole Google redirect URI
`https://ovpcthjingugwvpxlsna.supabase.co/auth/v1/callback`. Supabase → Auth → Providers → Google
(Client ID+secret). URL Configuration → Redirect URLs include `http://localhost:8765/callback` (desktop)
and `verbal://auth-callback` (mobile). Consent screen in "Testing" mode. No separate mobile Google client.

## Sync model

**Everything keyed by the Supabase auth `user_id`.** After sign-in both platforms adopt `user.id`
(`sync_user_id` desktop / `setUserId` mobile). Device id: desktop `platform.node()`; mobile
`<deviceName>_<userId last6>`.

- **Transcriptions (history / shared clipboard):** push = INSERT into `transcriptions`. ⚠️ **Desktop push
  omits `audio_url`/`status`** (those live in local history) — **mobile push includes**
  `audio_url`+`status`+`target_device_id`. Receive: desktop Phoenix WS `postgres_changes` INSERT filtered
  `user_id=eq.<uid>`; mobile `channel('verbal_history_<uid>')` INSERT+UPDATE. Both **skip own inserts**
  (device_id) and honor **`target_device_id`** (broadcast when null, else targeted). Mobile local cache is
  source of truth; remote merges in (dedup by row id).
- **Dictionary:** REST pull/push, one row/user; `fetch_remote` writes config only on change; `_push_remote`
  upsert `on_conflict=user_id`, `resolution=merge-duplicates`. Last-write-wins on `updated_at`.
- **Notes:** desktop REST (`on_conflict=id`) + mobile SDK CRUD; both merge with a local cache.
  **v2 merge contract** (desktop `merge_remote_note` in `shared_dashboard.py`; mobile `mergeRemoteNote` in
  `lib/notesStorage.ts` — kept identical): (a) `audio_segments` **UNION** on every merge (de-dup by
  `id`→`url`, sorted by `created_at`) so an append on one device is never lost; (b) **conflict pair** — if
  local & remote edited the same note within **60 s** *and* diverge in `title`/`content`/`raw_content`,
  keep BOTH: the newer keeps the canonical id (`conflict=true, conflict_of=null`), the older is stored under
  a deterministic id `<id>::conflict::<updated_at>` (`conflict=true, conflict_of=<id>`) — idempotent across
  repeated fetches, editor shows a one-time "resolve" prompt, nothing silently discarded; (c) otherwise
  last-write-wins on known fields; (d) **forward-compat** — unknown/newer-client fields preserved verbatim
  through both merge and write-back (desktop `_NOTE_KNOWN_FIELDS` allowlist re-attaches them to the cloud
  upsert; mobile relies on the `NoteEntry` index signature + spread). Conflict copies (id contains
  `::conflict::`) are **local-only**, never pushed to cloud. (Table is in the realtime publication but code
  polls/merges here.)
- **Canvas:** one shared row/user, upsert `on_conflict=user_id`; mobile subscribes `channel('canvas_<uid>')`.
- **Recordings:** audio → `recordings` bucket under `<user_id>/`; `audio_url` on the row/entry. Failed
  transcriptions `status:'failed'`, retryable from saved audio.
- **Pairing:** host inserts `pairings` row (`token_urlsafe(6)`, +120 s), QR `flume://pair?t=<token>`; new
  device SELECTs unclaimed/unexpired → atomic UPDATE `claimed_by` (guarded) → adopts `user_id` → enables sync.

## Security posture (as implemented)

Pragmatic, matches code + `GOOGLE_AUTH_SETUP.md`:
- Both apps use the **anon key for all data requests**; users separated purely by the `user_id` value in
  the query/filter. The user's JWT/access_token is stored but **not** used to authorize REST/realtime.
- RLS: **every shared table now has RLS enabled with a wide-open `TO public` `true` policy** —
  `dictionary`, `pairings` (migrated off `TO anon`, MER-28 2026-07), `notes` (MER-26, 2026-07),
  `transcriptions`/`devices`/`canvas` (already correctly configured live when checked for MER-28; that
  ticket's real remaining work was `pairings`' role scoping + committing reproducible SQL for these three
  — see Schema gaps below). Any caller who knows a `user_id` could still read that user's rows — data is
  scoped, not cryptographically enforced; this is the accepted interim posture across the board now.
  True `auth.uid()`-based per-user isolation (so a caller who *knows* another `user_id` still can't read
  it) is a tracked follow-up (Linear MER-29), not yet done.
- **RLS role gotcha:** the desktop uses the raw anon key (role `anon`); a *signed-in* client (mobile SDK)
  sends the user's JWT (role `authenticated`). A policy scoped `TO anon` silently filters out the
  authenticated client's rows. So any table both clients share must use `TO public` (or include
  `authenticated`). This bit `dictionary` (fixed via `supabase_dictionary_rls_fix.sql`) and `pairings`
  (fixed via MER-28, 2026-07 — `supabase_pairings.sql` updated in place) — no table is known to still have
  this trap.
- Proper JWT + `auth.uid()` RLS is a **documented deferred** hardening (the setup doc has the migration).
- `recordings` and `meeting-audio` are **private** (MER-27, 2026-07) — signed URLs only, see Storage
  buckets above. `canvas-images` and `releases` remain public (lower-sensitivity / app binaries).
  `app_versions` inserts are service_role-gated.


### meetings — widget-kit-v2 columns (Jul 2026, applied live + in supabase_meetings.sql)
- `pinned boolean not null default false` — list pinning (33j).
- `recognized jsonb not null default '{}'` — `{sid:{name,meetings}}` voice-fingerprint hits for that meeting.
- `action_items[*].due` (inside the existing jsonb) — optional short deadline label from the summary LLM.
- `marked_moments[*].note` (inside the existing jsonb) — optional user note on a bookmark.
- Local-only config keys: `voice_prints` (per-name embeddings — NEVER synced), `meetings_opened` (read tracking).

## Schema gaps & stale docs (important) ⚠️

- ~~No committed SQL for `transcriptions`, `devices`, `canvas`~~ — **closed** (MER-28, 2026-07):
  `whisperflow/supabase_transcriptions.sql` / `supabase_devices.sql` / `supabase_canvas.sql` now reproduce
  the live schema (including `target_device_id`/`edited_text`/`is_pinned`, previously undocumented
  anywhere). The `canvas-images` **bucket** still has no committed SQL beyond its policy file
  (`supabase_canvas_images_policy.sql` doesn't create the bucket itself) — narrower remaining gap.
- **`CROSSPLATFORM_SYNC_PLAN.md` is largely stale** (placeholder URL, a `sync_token` scheme that doesn't
  exist, `sync_listen()` as a stub) — its only current value is the base `transcriptions` DDL.
- `config.py DEFAULT_CONFIG` omits `sync_enabled` and `sync_target_device_id` though both are used —
  desktop sync must be turned on explicitly.
- Mobile `useNotes` note: there's still no `is_voice` column, but v2 `toNote` now infers `isVoice` from the
  presence of `raw_content` or a non-empty `audio_segments` (a voice note has at least one), so it survives
  reloads for dictated notes without a dedicated column.
- **New from a 2026-07 live-schema audit (found via direct DB inspection, not code reading — re-verify
  periodically, code and live DB can and do drift):**
  - ~~`notes.id` was still `uuid` live despite the v2 migration's intent~~ — **fixed** (migration
    `fix_notes_id_type_to_text`, 2026-07): now `text`, default `gen_random_uuid()::text`, verified against
    the live table (no FKs/views depended on it; all 6 existing rows were valid uuid literals, cast cleanly).
  - ~~`groq_usage.kind`'s check constraint didn't allow `'chat-ollama'`~~ — **fixed** (migration
    `allow_chat_ollama_in_groq_usage_kind`, 2026-07): constraint now allows it, verified with a live
    insert+delete round-trip.
  - `app_config` is referenced by mobile code (`lib/remoteConfig.ts`) but doesn't exist in the live
    schema at all — see the `app_config` callout above.
  - Two more undocumented-until-now tables: `push_tokens` (real, in active use) and `device_presence`
    (appears orphaned/unused — flag for cleanup, don't treat as a feature).
  - Undocumented columns that do exist and are actively used: `meetings.notes_md`, `meetings.live`,
    `devices.id`, `devices.sync_enabled`, `canvas.id`.
