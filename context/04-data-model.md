# 04 — Backend, Data Model, Auth & Sync

> Part of the `context/` knowledge set. See `context/README.md` for the maintenance rule.
> **Keep this current:** any schema change, new table/bucket, data-shape change, or auth/sync change
> must update this file. **When you add a column that only lives in the live DB, record it in §Schema gaps.**

## Supabase project

- **Ref:** `ovpcthjingugwvpxlsna` · **URL:** `https://ovpcthjingugwvpxlsna.supabase.co`
- One project shared by desktop + mobile. **Anon key hardcoded** in both:
  desktop `whisperflow/app/sync.py` (`SUPABASE_URL`/`SUPABASE_KEY`, reused via `from app.sync import …`
  by auth/recordings/dictionary/pairing/shared_dashboard); mobile
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
(~2 min TTL) · `claimed_by` text (null until claimed) · `claimed_at`. Index on `(token)`. RLS on.
**Locked down in IDI-157** (migration `pairings_rpc_lockdown`, 2026-08): INSERT (host creating a token) is
the ONLY direct REST access — the old `for select using(true)` let the anon key enumerate every user_id
that ever paired. Status/claim/cancel now go through token-gated SECURITY DEFINER RPCs
(`pairing_status`/`claim_pairing`/`cancel_pairing`): expiry enforced server-side (client clock skew
irrelevant), claim is one guarded UPDATE (no select-then-patch race), Cancel revokes the row server-side,
and the claim RPC sweeps rows >10 min past expiry so the table never re-accumulates. Verified live with
anon-key curl: select returns `[]`, double-claim rejected, status never exposes `user_id`.

**`notes`** — `notes_migration.sql` (base) + `supabase_notes_v2.sql` (self-contained: **creates the table if
missing** — it was never provisioned in the live DB, so Notes was local-only until 2026-07 — then adds v2 cols).
`id` **text** PK · `user_id` text · `title` text `''` · `content` text `''` (AI-formatted) · `folder` text `''` ·
`is_pinned` bool `false` (NB: no desktop writer since IDI-179 deleted the orphaned `toggle_note_pin`) ·
`device_name` text · `created_at` · `updated_at`. Indexes on `(user_id)` and
`(user_id, updated_at DESC)`. In the `supabase_realtime` publication.
**`id` is `text`, not uuid** (migration `fix_notes_id_type_to_text`, applied 2026-07 after a live-schema
audit found `supabase_notes_v2.sql`'s guarded `ALTER COLUMN id TYPE text` had never actually run against
this DB — the column was still `uuid` in production until then, verified fixed and default reset to
`gen_random_uuid()::text`): desktop writes `uuid4().hex`, mobile writes `note_<ts>` (not valid uuid syntax) — a
text column lets each client supply its **own** id so the note's local id === its cloud id. That equality
is load-bearing: mobile `updateNote` does `.update().eq('id', localId)`, and without it every edit matches
0 rows and the pulled-back row duplicates. Mobile `createNote` upserts **with** the id (gated on
`getSyncEnabled`), and `useNotes.load` **back-fills** locally-cached notes that have **never been
cloud-backed** — scoped in IDI-158 to `source === 'local'` entries only, excluding `::conflict::` copies
and tombstones (the old unscoped back-fill re-uploaded notes deleted on other devices, resurrecting them).
**v2 columns** (`supabase_notes_v2.sql`, idempotent): `raw_content` text nullable (raw Whisper transcript;
NULL for typed/pre-existing notes — `content` holds the formatted version, "show original" reveals this);
`audio_segments` jsonb `'[]'` (append-only list of source recordings, shape `[{id,url,created_at}]`,
**UNION-on-merge** during sync); `deleted_at` timestamptz nullable (**IDI-158 tombstone**, live migration
`notes_deleted_at_tombstone` 2026-08: deletion is a soft-delete — `deleted_at` + `updated_at` set, content
fields cleared, never a hard DELETE. Merges on both platforms treat a tombstone as **unconditionally
authoritative**: local copy + its `::conflict::` derivatives are dropped with no LWW comparison, so an
offline edit can never resurrect a deleted note. Desktop `delete_note` writes the cloud tombstone FIRST
and keeps the note + returns `ok:false` if that write fails while sync is on). **RLS:** enabled, `TO public` (`whisperflow/supabase_notes_rls.sql`,
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

**`app_config` — does not exist in the live DB, and no code references it anymore (resolved, IDI-160).**
The provider-secret-key-table idea (`GROQ_API_KEY` readable by clients) was correctly dropped — that must
never exist; keys live only as the `groq-proxy` function's own `GROQ_API_KEY`/`OLLAMA_API_KEY` secrets.
The mobile code that still queried a same-named settings table (`lib/remoteConfig.ts`, warmed in
`RootNavigator.tsx`, read via `storage.ts::getGroqKey`) was **removed in 2026-08**: the table had never
been provisioned live, so `getGroqKey()` returned `''` and its call-site gates falsely failed every in-app
dictation/retry/note-cleanup — while `lib/groq.ts` ignored the key parameter anyway (the proxy holds it).
`whisperflow/supabase_app_config.sql` remains in the repo as an unapplied historical file only.

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

`delete-account` (`supabase/functions/delete-account/index.ts`, MER-32, 2026-07) — `verify_jwt` on;
identity derived from the caller's JWT locally, never a body-supplied id. Service-role-only: purges every
row across `transcriptions`/`notes`/`dictionary`/`canvas`/`devices`/`meetings`/`push_tokens`/`groq_usage`
for that `user_id`, deletes storage objects under `recordings/<user_id>/` + `meeting-audio/<user_id>/` +
the matching flat-namespaced `canvas-images` objects, then deletes the Supabase auth user itself (always
last — a partial failure leaves a recoverable signed-in state). Idempotent; see `03-features.md`'s Account
deletion entry for the full design and live-verification notes. Apple-token revocation is an intentionally
deferred stub (`revokeAppleToken()`, Batch C).

`reap-meeting-audio` (`supabase/functions/reap-meeting-audio/index.ts`, MER-31, 2026-07) — invoked by the
daily `reap-meeting-audio-daily` `pg_cron` job (`supabase_meetings.sql`, via `pg_net.http_post` with the
anon key — only needs to pass the gateway's `verify_jwt`, the function's own privileged work uses its
internal service-role key like every other function here). See `03-features.md`'s retention-reaper entry
and the `meetings.audio_expired`/`retention_days` columns above for the full design.

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
| `audio_expired` | bool | default `false` — MER-31, 2026-07. Set by the `reap-meeting-audio` reaper once the audio object is actually deleted; the single authoritative "no audio left" signal (never inferred from `audio_url` alone) |
| `retention_days` | int | nullable, MER-31. `null`/`0` = never expire (default). Stamped **per meeting at capture time** from desktop's `meetings_keep_audio_days` setting — not a live/retroactive per-user lookup |

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
`audio_url` text nullable (private `recordings` bucket object path, see MER-27; since IDI-172 the DESKTOP
also writes it, via a row-scoped patch after the async WAV upload) · `status` text default
`'done'` (`'done'`\|`'failed'`, retryable) · `deleted_at` timestamptz nullable (**IDI-172 tombstone**,
live migration `transcriptions_deleted_at_tombstone` 2026-08: delete = UPDATE with `text` cleared /
`edited_text`+`audio_url` nulled, storage object removed — never a hard DELETE; merges drop + prune
tombstoned ids; reconnect backfill sweeps tombstones separately since an UPDATE never moves `created_at`).
Indexes `(user_id, created_at desc)` and `(user_id, is_pinned, created_at desc)`. In the realtime
publication (desktop subscribes to `*`, not just INSERT). Local-cache-only field with NO DB column:
`duration_ms` (mobile persists the real recording duration; never pushed).

**`devices`** — device registry/presence. `id` uuid PK · `user_id` text · `device_id` text (since IDI-177
a STABLE per-install uuid — desktop `config.get_device_id()`, mobile `verbal_device_uuid` — never derived
from hostname/name/account; one stale old-format row per upgraded device is expected and removable) ·
`device_name` text · `device_type` text default `'mac'` (`mac`/`win`/`ios`/`android` — mobile now sends
`Platform.OS`, the old `'iphone'` literal is gone) · `last_seen` timestamptz default `now()` ·
**`sync_enabled`** bool default `true` (SELF-only since IDI-177: each device mirrors its own toggle here;
nothing reads it as remote control). Unique index `(user_id, device_id)` (the upsert conflict target).
"Online" = `last_seen` within **`sync.PRESENCE_ONLINE_SEC` = 120 s** (2026-08; was 300 s, which let a
device that vanished four minutes ago still read "Online" — the dashboard promises "online right now", and
the heartbeat is 60 s, so 120 s tolerates exactly one missed beat). In the realtime publication. The
desktop device LIST reads `sync.fetch_account_devices` (ALL rows for the `user_id`, each tagged `online`,
`last_seen` passed through so the UI can say how stale a row is), not `fetch_devices` (live set only).
Presence heartbeats are APP-LEVEL 30 s daemons (`main._presence_loop`/`win_main`), gated on
being signed in — not on any window being open (IDI-177); mobile's is the device store's single 60 s
poll/upsert loop.
**Identity survives reinstall (2026-08):** mobile `getDeviceId()` reads/writes `verbal_device_uuid` in the
**Keychain** (`expo-secure-store`) first and AsyncStorage second, promoting a pre-Keychain AsyncStorage id
into the Keychain on first read (so existing installs keep their row). AsyncStorage is wiped by an app
reinstall or simulator reset, so before this every reinstall minted a fresh identity and orphaned its row:
one test account reached **16 rows — 14 of them identically-named dead "iPhone"s**, none seen in 3 weeks,
which buried the single device that was actually online. Those ids also record two dead schemes —
`iphone_dcf871` (name + *cloud* `userId.slice(-6)`) and `iphone_gyoco7` etc. (same shape but seeded from an
ephemeral **local** user id, hence one row per install) — plus `Shabbar-Windows` (desktop's old
hostname-as-id).
**There is NO TTL and nothing auto-prunes** — deliberate: a phone that is merely switched off is offline,
not gone, and must not vanish from the list on its own. Cleanup is manual via
`shared_dashboard.remove_offline_devices()` ("Remove all offline", user-confirmed, skips THIS device).
**Lifecycle:** sign-out DELETEs this device's row (IDI-170); both platforms offer
"Remove from list" for other devices (user_id+device_id-scoped, honestly labeled — removal doesn't revoke
anything until IDI-29's per-device credentials).

**`canvas`** — one shared row/user. `id` uuid PK (`gen_random_uuid()` default) · `user_id` text ·
`content` text default `''` · `device_name` text default `''` · `device_id` text nullable (**IDI-173**,
live migration `canvas_device_id_origin` 2026-08: origin filtering is by stable device id — name compare
only for rows written by old clients) · `updated_at` timestamptz default `now()` · `image_url` text
nullable. Unique index on `user_id` (the actual upsert conflict target — `id` is informational). In the
realtime publication. **Write contract (IDI-173):** every write stamps `device_id`+`device_name` and OMITS
columns it isn't changing (text edits never null the image); a clear is an explicit
`{content:'', image_url:null}` write that receivers apply — empty content is never falsy-dropped.

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
(`sync_user_id` desktop / `setUserId` mobile). Device id: STABLE per-install uuid on both (IDI-177 —
desktop `config.get_device_id()`, mobile `verbal_device_uuid`). **The sync toggle (one source per
platform: `lib/syncStore.ts` mobile / `sync_enabled` desktop) is LIVE and gates
history/notes/canvas/dictionary; meetings edits + recording uploads gate on being signed in only**
(`auth.cloud_allowed` / `getCloudUserId()`). Mobile stores are singletons with
`reset()`/`catchUp()`/channel-rejoin (see `05-conventions.md` #28); AppState foreground runs a catch-up;
desktop's `SyncClient` has a single reconnect loop with a bounded backfill (content since last-seen + a
separate tombstone sweep).

- **Transcriptions (history / shared clipboard):** push = INSERT into `transcriptions`; BOTH platforms
  include `audio_url`+`status`+`target_device_id` since IDI-172 (desktop patches `audio_url` row-scoped
  after the async upload; local↔cloud linkage via a local `sync_id`). Receive: desktop Phoenix WS
  `postgres_changes` `*` filtered `user_id=eq.<uid>` — received rows are APPENDED TO LOCAL HISTORY +
  clipboard, and auto-pasted ONLY when `target_device_id` equals this device (IDI-172; broadcasts no
  longer paste); mobile `channel('verbal_history_<uid>')` INSERT+UPDATE. Both skip own inserts
  (device_id), honor `target_device_id`, and treat `deleted_at` tombstones as authoritative (drop +
  prune). Desktop Settings has "Clear history" with an optional everywhere-tombstone sweep.
- **Dictionary:** REST pull/push, one row/user — **CAS on `updated_at`** since IDI-174 (write filtered on
  the last-witnessed value; 0 rows → refetch → pure merge — vocab case-insensitive union, snippets by
  trigger, replacements by `from` — → one retry; double failure surfaces "Couldn't sync — will retry").
  Mobile pushes are blocked until the first fetch resolves (edit-before-load used to wipe the row) and
  require a real identity (`getCloudUserId()` — no junk `user_<ts>` rows). Meetings notes/scratchpad
  writes use the same CAS pattern (freeze + Reload on conflict instead of merge).
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
  device calls the `claim_pairing` RPC (atomic guarded claim, server-side expiry — IDI-157) → adopts
  `user_id` via the paired override (IDI-156) → enables sync. Host polls `pairing_status`, cancel revokes
  via `cancel_pairing`.

## Security posture (as implemented)

Pragmatic, matches code + `GOOGLE_AUTH_SETUP.md`:
- RLS: **every shared table now has RLS enabled with a wide-open `TO public` `true` policy** —
  `dictionary`, `pairings` (migrated off `TO anon`, MER-28 2026-07), `notes` (MER-26, 2026-07),
  `transcriptions`/`devices`/`canvas` (already correctly configured live when checked for MER-28; that
  ticket's real remaining work was `pairings`' role scoping + committing reproducible SQL for these three
  — see Schema gaps below). Any caller who knows a `user_id` could still read that user's rows — data is
  scoped, not cryptographically enforced; this is the accepted **live** posture — see the MER-29 note
  immediately below for why the tightened version exists but hasn't been switched on.
- **RLS role gotcha:** the desktop uses the raw anon key (role `anon`); a *signed-in* client (mobile SDK)
  sends the user's JWT (role `authenticated`). A policy scoped `TO anon` silently filters out the
  authenticated client's rows. So any table both clients share must use `TO public` (or include
  `authenticated`). This bit `dictionary` (fixed via `supabase_dictionary_rls_fix.sql`) and `pairings`
  (fixed via MER-28, 2026-07 — `supabase_pairings.sql` updated in place) — no table is known to still have
  this trap.
- **MER-29 (2026-07) — JWT forwarding shipped, `auth.uid()` enforcement written but NOT applied.**
  - **Mobile** already sent the real session JWT for every table call (`@supabase/supabase-js` auto-attaches
    it once signed in) — no mobile code change was needed for `transcriptions`/`notes`/`dictionary`/`canvas`/
    `devices`/`meetings`. The two mobile call sites that use the raw anon key
    (`lib/recordings.ts::uploadCloud`, `flume-ui/hooks/useCanvas.ts` image upload) are **Storage** uploads,
    not table rows — both buckets (`recordings`, `canvas-images`) are `TO public` policies, out of this
    ticket's scope, left unchanged.
  - **Desktop** had zero JWT-forwarding plumbing before this — every REST/Realtime call used the shared
    anon key unconditionally. Added: `app/auth.py::get_access_token(cfg)` (refreshes the stored
    `refresh_token` via `POST {AUTH}/token?grant_type=refresh_token` when the cached `expires_at` is near,
    fails closed to `None`/the stale token on any error — never raises) and
    `app/auth.py::auth_header(cfg, json=False)` (returns `Authorization: Bearer <access_token>` when
    signed in and valid, else the anon key — **fully backward-compatible**, since RLS is still permissive
    either way). `_store_session` now also stores `expires_at`. Applied across every desktop REST call site
    for `meetings`/`notes`/`canvas`/`dictionary`/`devices` (`app/sync.py`, `app/meetings.py`,
    `app/shared_dashboard.py`, `app/dictionary.py`, `app/dashboard.py`) and to every
    Phoenix Realtime `phx_join` payload (`access_token` field) + WS handshake header
    (`app/flume_web_dashboard.py` too) — Realtime evaluates `postgres_changes` RLS off that field, so this
    was needed for Realtime to ever honor a future `auth.uid()` policy. Storage calls (`recordings.py`,
    the `meeting-audio`/`canvas-images` uploads inside `meetings.py`/`dashboard.py`) were deliberately left
    on the anon key — same reasoning as mobile, those buckets are `TO public`.
    `whisperflow/app/supabase_config.py` is a new zero-dependency module holding
    `SUPABASE_URL`/`SUPABASE_KEY`/`REST_URL` (split out of `sync.py`, which now re-exports them) so
    `auth.py` doesn't have to import `sync.py` and every call site can import `app.auth` without a cycle.
  - **The `auth.uid()` migration is written and live-verified, but intentionally NOT applied**:
    `whisperflow/supabase_auth_uid_rls.sql` (drops each table's permissive policy, replaces with
    `FOR ALL TO authenticated USING (user_id = auth.uid()::text) WITH CHECK (...)` for
    `notes`/`transcriptions`/`devices`/`canvas`/`dictionary`/`meetings`). Verified correct live (inside a
    transaction that applied it, tested with simulated JWT claims for two fake users, then `ROLLBACK` —
    prod's actual policies were never changed) — confirmed: each user sees only their own rows, cross-user
    writes affect 0 rows, and a plain anon-role request (no JWT — i.e. every *currently installed* app
    build) sees **zero** rows once the policy is `TO authenticated`.
  - **Why it's being held back — two real blockers, not just caution:**
    1. **Device pairing structurally can't satisfy `auth.uid()`.** `pairing.ts::claimPairing` /
       `app/pairing.py` let a second device adopt the host's `user_id` **without ever creating a Supabase
       Auth session** — it has no JWT at all, ever, by design (that's the point of pairing without a second
       Google sign-in). The moment any of the six tables above requires `TO authenticated`, every
       paired-but-never-signed-in device loses ALL cloud access instantly and permanently, not just until an
       app update — there's no client fix that restores it under the current pairing design. This needs a
       **product decision**: accept that trade-off (paired devices become local-only unless they also sign
       in with Google), or redesign pairing to mint the joining device a real session for the host's account
       (not implemented anywhere today) — before this migration can ever be applied.
    2. **Client rollout coordination.** Even once (1) is resolved, applying this migration instantly 401s
       every *currently-running* desktop/mobile build that hasn't yet received the JWT-forwarding code above
       (old builds only ever send the anon key) — a real outage, not a soft degrade, until users update.
       This must be sequenced behind an actual release + adoption window, which is outside what a single
       backend change can control.
  - `pairings` keeps its random/short-lived/single-use token model (the claiming device isn't signed in
    as the host yet, so `auth.uid()` can't apply to its own rows) — but is no longer wide-open: since
    IDI-157 the table is INSERT-only over REST and everything else is token-gated RPC (see the `pairings`
    entry above), which closed the user_id-enumeration hole without needing the JWT migration.
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
  - ~~`app_config` referenced by mobile code but absent from the live schema~~ — **resolved** (IDI-160,
    2026-08): the referencing code was removed entirely; see the `app_config` callout above.
  - Two more undocumented-until-now tables: `push_tokens` (real, in active use) and `device_presence`
    (appears orphaned/unused — flag for cleanup, don't treat as a feature).
  - Undocumented columns that do exist and are actively used: `meetings.notes_md`, `meetings.live`,
    `devices.id`, `devices.sync_enabled`, `canvas.id`.
