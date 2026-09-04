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

RLS on; policy `dictionary owner`: `FOR ALL TO authenticated USING (user_id = auth.uid()::text)
WITH CHECK (…)` (tightened from the old permissive `dictionary rw` by `supabase_auth_uid_rls.sql`,
applied 2026-09-03 / IDI-268). **A shared table's policy must include `authenticated`, not be `TO anon`** — a
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
`is_pinned` bool `false` (LIVE since Notes v3, 2026-08: desktop `set_note_pinned` / mobile `notesStore.setPinned`.
**Pin writes NEVER bump `updated_at`** — a pin is a preference, not an edit, so it must not reorder the
recency-sorted lists or mint a conflict pair; both writers PATCH `{is_pinned}` alone, best-effort) ·
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

**`issue_reports`** — `whisperflow/supabase_issue_reports.sql` (applied live 2026-09-03, migration
`create_issue_reports`). In-app "Report an issue" feedback, one row per report from any platform.
`id` uuid PK · `user_id` text `''` (auth uid; `''` = anonymous/signed-out) · `email` text `''` ·
`platform` text `''` (`mac|win|ios|android`) · `app_version` text `''` · `message` text ·
`meta` jsonb `'{}'` (`{device_name?, os_version?}`) · `status` text `'new'` (`new|seen|resolved`,
manual triage) · `created_at`. Index `(created_at desc)`. **RLS on with NO policies on purpose**
(the `groq_rate_limits` pattern): written ONLY by the `report-issue` Edge Function with the service
role, read by the founder via dashboard/SQL — verified live that the anon key can neither SELECT nor
INSERT. See `03-features.md` §Report an issue.

`report-issue` (`supabase/functions/report-issue/index.ts`, 2026-09) — `verify_jwt` on; accepts a
session JWT **or the anon key** (anonymous reports allowed by design). Saves the row FIRST with the
service role, then best-effort emails the founder via Resend (reuses `RESEND_API_KEY` +
`INVITE_FROM_EMAIL`; recipient = optional `ISSUE_REPORT_EMAIL` secret, code-defaulted) — an email
failure never fails the request or reaches the client. Returns `{ok, id, emailed}`.

**`beta_signups`** — `whisperflow/supabase_beta_signups.sql` (applied live 2026-09-03, migration
`beta_signups_table`). One row per person who filled the public beta form (`idiaz.io/flume/beta.html`).
`id` uuid PK · `name` text · `email` text (stored lowercased; **unique index** — repeat submits are
idempotent) · `platform_hint` text `''` (`mac|win|ios|android`, visitor UA at signup) · `ip_hash` text
`''` (sha-256 of caller IP, rate limiting only — the raw IP is never stored) · `status` text `'new'`
(`new|active|churned`, manual triage) · `welcome_emailed` bool · `founder_notified` bool ·
`welcome_sends` int `0` + `last_welcome_at` timestamptz (migration
`beta_signups_welcome_resend_tracking`, 2026-09-04 — cap and space out duplicate re-sends) ·
`created_at`. Indexes `(created_at desc)`, `(ip_hash, created_at desc)`. **RLS on with NO policies**
(the `issue_reports` pattern): written ONLY by the `beta-signup` Edge Function with the service role.
Funnel joins: `beta_signups.email → auth.users.email` answers "did they install and create an
account"; from there the usage tables answer "are they active". See `03-features.md` §Beta signup.

`beta-signup` (`supabase/functions/beta-signup/index.ts`, 2026-09) — `verify_jwt` OFF (public form).
Honeypot `company` field (filled → fake success, nothing saved/sent), per-IP-hash rate limit
(8/hour, counted in-table, fails open), row-first, then best-effort Resend welcome email (light
site theme — see `03-features.md` §Beta signup — hosted logo `idiaz.io/flume/flume-mark-128.png`
(NOT cid; filename is versioned per icon change — Gmail proxy caches per-URL; 2026-09-04), Mac+Windows `download`-function
links, `reply_to` the founder) + founder notification (`Flume beta signup #N — {name}`, `reply_to`
the tester). Duplicate email → 409 → **welcome RE-SENT** using the stored name/hint (≤5 sends per
row via `welcome_sends`, ≥15 min apart via `last_welcome_at`; founder never re-notified) →
`{ok:true, already:true, emailed}`. Secrets shared with invite-member/report-issue
(`RESEND_API_KEY`, `INVITE_FROM_EMAIL`, `ISSUE_REPORT_EMAIL`); optional `FLUME_DOWNLOAD_FN` override.
Returns `{ok, already, emailed}`.

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
**Known gap (IDI-216):** `USER_TABLES` does not yet include the org layer, so deleting an account leaves
its `organization_members` row behind (and, if it owned a team, the org itself). The FK is
`on delete cascade` from `organizations`, not from `auth.users`, so nothing breaks — but a deleted
owner's team is orphaned. Add `organization_members` to the purge (and decide owner-transfer-vs-delete)
before Teams goes live.

`reap-meeting-audio` (`supabase/functions/reap-meeting-audio/index.ts`, MER-31, 2026-07) — invoked by the
daily `reap-meeting-audio-daily` `pg_cron` job (`supabase_meetings.sql`, via `pg_net.http_post`). Since the
IDI-258 hardening (2026-09) the call is gated on a dedicated `x-cron-secret` header, read by the cron job
from Vault (`reap_cron_secret`) and compared in constant time against the `REAP_CRON_SECRET` function
secret — the committed anon JWT that used to ride the call was a public client key, not a control (any
anon-key holder could trigger the cross-tenant service-role delete pass). Secret unset → every caller is
rejected (fail closed); the function must be deployed with `--no-verify-jwt` since no JWT is sent. The
function's own privileged work uses its internal service-role key like every other function here. See
`03-features.md`'s retention-reaper entry and the `meetings.audio_expired`/`retention_days` columns above.

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
| `speakers` | jsonb | `{speaker_id: display_name}` (`self` = the mic/user; since 2026-08-28 written as the signed-in user's name, "You" only when signed out — rows from before that hold the literal "You" and both clients substitute the account name at read time) |
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
| `speakers_source` | text | **vestigial since 2026-08-28** (two-speaker model: always written `estimated`, no UI reads it). nullable, CHECK ∈ `diarized`\|`estimated` — 2026-08-27 (`whisperflow/supabase_migration_2026-08-27_meetings_speakers_source.sql`, applied live). Provenance of the speaker split: `diarized` = AssemblyAI turns applied by desktop `_diarize()`, `estimated` = 90 s-gap heuristic only. `null` = pre-column meeting → clients render as estimated. Drives the SPEAKERS VERIFIED/ESTIMATED tag on both platforms |

Indexes `(user_id)`, `(user_id, started_at desc)`. **Realtime publication: yes** (mobile subscribes
INSERT+UPDATE on `verbal_meetings_<uid>` — the live-transcript stream). **`REPLICA IDENTITY FULL`**
(migration `meetings_replica_identity_full_for_realtime_updates`) — required so Realtime can match the
`user_id=eq` filter on UPDATE events; with the default (PK-only) identity INSERTs delivered but live
UPDATE chunks were silently dropped, so `MeetingLiveScreen` also polls every 3s while live as a fallback.
RLS on, policy `meetings owner` `FOR ALL TO authenticated USING (user_id = auth.uid()::text)`
(tightened from `meetings rw` by `supabase_auth_uid_rls.sql`, applied 2026-09-03 / IDI-268). Desktop also keeps a bounded metadata list
in `config['meetings']` (`MEETINGS_CAP=30`) and the mixed WAV at `~/.verbal/meetings/<id>.wav`.

**`app_versions_latest`** (view, 2026-08-20) — **the single definition of "newest build"**, read by
both `updater.py` and the public `download` Edge Function. `distinct on (platform)` ordered by
`public.semver_key(version) desc, released_at desc`.
**Why it exists:** `app_versions.released_at` is NOT monotonic — CI stamps whatever is convenient —
and live data had win `1.0.9` at `00:00:00` next to win `1.0.8` at `09:13:24` on the same day. The old
`order=released_at.desc&limit=1` therefore resolved "latest" to **1.0.8**, so a Windows user on 1.0.7
was offered 1.0.8 and could never reach 1.0.9. `semver_key()` sorts a version as an `int[]` (plain
text sort ranks `1.0.9` above `1.0.10`) and strips non-numeric suffixes so a `-beta` tag degrades
instead of erroring. **Never order `app_versions` by `released_at` again — read the view.**

**`app_versions`** — `supabase_migrations/001_app_versions.sql`. Auto-update manifest.
`id` bigserial PK · `platform` text (`mac`/`win`/`ios`) · `version` text · `changelog` · `file_url` ·
`file_hash` (sha256) · `file_size` · `released_at` · `UNIQUE(platform,version)`. RLS on; public SELECT;
inserts use **service_role** (release script) — no anon insert. **As of IDI-224 (2026-08-20),
`file_url` is always a GitHub Releases URL** (`github.com/<repo>/releases/download/vX.Y.Z/<file>`) —
never a Supabase Storage path; see `05-conventions.md` #50 for the release pipeline that writes these
rows. The 9 stale pre-IDI-224 rows (dead Storage links + mismatched GitHub asset filenames) are cleared
on ship.

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
publication (desktop subscribes to `*`, not just INSERT). `duration_ms` int nullable (**2026-08-16**,
live migration `transcriptions_duration_ms` + `supabase_transcriptions.sql`): the recording's real
duration, written by both desktops' `SyncClient.push` and mobile's `addTranscription` insert; feeds the
**account-wide WPM** on the Insights pages (mobile combines it with its local measured speech —
`lib/insights.ts::localSpeech` + the cache's `wpmW/wpmMs` accumulator, own-device rows excluded to avoid
double counting; insights cache is versioned `v:2` so existing installs re-read history once). Historic
desktop rows were backfilled from their stored 16 kHz mono PCM16 WAV sizes (32 bytes/ms); compressed
mobile uploads (m4a/caf) can't be size-derived and stayed NULL. (This replaced the old
"local-cache-only, never pushed" posture.)
`app` text nullable (**2026-08-21**, live migration `transcriptions_app_and_org_breakdown` +
`whisperflow/supabase_organizations_onboarding.sql`): the name of the frontmost application at the moment
the dictation was captured, written by both desktops' `SyncClient.push(..., app_name)` from the
**pre-injection** `target_app` (reading it after the paste would name whatever regained focus —
`05-conventions.md` #37). Partial index `(user_id, app) where app is not null`. **Mobile never writes
it** — a phone has no frontmost window to read — so these numbers describe desktop dictation only.
Historic rows are NULL and **cannot be backfilled**: the frontmost app was never recorded anywhere else,
so `org_app_breakdown` is empty until new dictations accumulate and every client that renders it says so
explicitly rather than showing a zero state.

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

### Organization layer (IDI-216, Aug 2026) — `whisperflow/supabase_organizations.sql`

The **first tables in this project with real `auth.uid()` RLS** — the working precedent for the model
IDI-29 extended to the six legacy shared tables on 2026-09-03 when `supabase_auth_uid_rls.sql` was applied
(IDI-268; before that they were `TO public USING (true)`). These four are `TO authenticated` and keyed on
`auth.uid()::text` from their first row. That is what let the team layer ship ahead of that migration:
nothing in the team feature reads another user's row in a legacy table, so the pairing trade-off that
gated that migration was not in the way here. Consequence to know: a paired-but-never-signed-in device
sends the anon key, reads **zero** org rows, and simply has no team — the correct fail-closed outcome.

**`organizations`** — `id` uuid PK · `name` text · `company_name` text `''` · `owner_user_id` text ·
`plan` text `'team'` · `seats` int `5` · `leaderboard_enabled` bool `false` (the OWNER's org-wide switch
for the member-visible ranking; never turns itself on) · `created_at` · `updated_at`.
Read by any active member; written by owner/admin; deleted by owner only.

**`organization_members`** — PK `(org_id, user_id)` · `email` · `display_name` · `role`
(`owner`|`admin`|`member`) · `status` (`active`|`invited`|`removed`) · `usage_consent` bool `false` ·
`leaderboard_opt_in` bool `false` · `joined_at` · `updated_at`. Partial unique index
`(user_id) where status='active'` enforces **one team per user** in the DB, so a racing invite claim
can't create a second membership. **SELECT-only over REST — there is no INSERT/UPDATE/DELETE policy on
purpose**: Postgres RLS cannot restrict which COLUMNS a policy lets you write, so a "members may update
their own row" policy would also let a member set their own `role` to `owner`. Every write goes through
an RPC. Removal is SOFT (`status='removed'`, consent flags cleared), which keeps the unique-active index
coherent and makes a re-invite a clean re-claim.

**`organization_invites`** — `id` uuid PK · `org_id` · `email` · **`token_hash`** text (sha256 hex —
the raw token exists only in the invite email and claim URL, so a leaked row cannot be replayed) ·
`role` · `invited_by` · `status` (`pending`|`claimed`|`expired`|`revoked`) · `expires_at` (default
now()+7 days) · `claimed_by` · `claimed_at` · `created_at`. Unique index on `token_hash`. Readable by
owner/admin only; INSERTed only by the `invite-member` Edge Function with the service role; claimed
through `org_claim_invite` (SECURITY DEFINER, because the claimer is by definition not a member yet).

**`organization_dictionary`** — `org_id` uuid PK · `vocabulary`/`replacements`/`snippets` jsonb `'[]'` ·
`updated_by` text · `updated_at`. **Deliberately the same SHAPE as `dictionary`** so both clients reuse
`normalize()`/`merge_dictionary()` verbatim rather than growing a second data model. Read by every
active member (they dictate with it), written by owner/admin, **CAS on `updated_at`** exactly like the
personal row (IDI-174's pattern): write filtered on the last-witnessed value, 0 rows → refetch, merge,
retry once, then report.

**RLS recursion note.** A policy on `organization_members` that answers "is the caller a member of this
org?" by selecting `organization_members` would recurse. Every policy instead calls
**`public.org_member_role(p_org uuid)`**, a SECURITY DEFINER function that reads the table with RLS
bypassed. It is the single definition of "who may see this org" — change it and every policy follows.

**RPCs** (all SECURITY DEFINER; each re-derives the caller from `auth.uid()` and checks its own
authorization, so the `authenticated` grant is the right to ASK, never the right to act on another org):
`org_create` (org + owner membership + empty shared dictionary, atomically) · `org_claim_invite` ·
`org_set_role` · `org_remove_member` · `org_set_consent` (the ONLY membership columns a non-admin can
move, and an admin cannot move them for someone else) · `org_usage_summary` · `org_leaderboard` ·
`org_usage_series` · `org_app_breakdown`.

**`org_usage_series(p_org, p_days)`** — per-member per-day word counts, backing the Team screen's roster
sparklines and per-member activity heatmap. One call for the whole org rather than one per member. Same
counts-only contract as the two above, with one difference worth knowing: **visibility is role-split** —
owner/admin get every consenting member's series, anyone else gets only their OWN row, so a member can
see their own sparkline without this becoming a way to read colleagues' activity.

**GRANT GOTCHA (learned applying this live).** `revoke all on function … from public` revokes from the
PUBLIC pseudo-role and does NOT undo Supabase's `ALTER DEFAULT PRIVILEGES` grant of `EXECUTE` to
**`anon`** on new functions in `public`. Every org RPC was briefly anon-callable because of it. Nothing
leaked — each derives its caller from `auth.uid()`, which is NULL for anon, so they returned
`not_authenticated` / `forbidden` / an empty set — but **revoke from `anon` BY NAME** on any future
SECURITY DEFINER function rather than relying on the `public` revoke.

**`org_app_breakdown(p_org, p_days)`** — per-member per-app dictation and word counts, one flat row per
`(member, app)`, ordered by member then count desc. Backs "Where the team writes" on the team overview and
"Where <name> writes" on each member page. Same role split as `org_usage_series` (owner/admin see every
consenting member, anyone else only themselves) and the same `usage_consent` gate — which here applies to
**everyone including a member asking about themselves**, so turning sharing off empties the panel rather
than leaving a private-looking row that is still being aggregated. Rows with a NULL/blank `app` or empty
`text` are excluded, so the counts are of *app-attributed* dictations, not of all of them.
**This RPC WIDENS the privacy contract.** Everything else in the team layer is counts and durations; an
app name is neither. It is still metadata — never the text, never the audio — but the product copy on
every Team surface had to change from "only counts and durations" to name app names explicitly, and it
did (team overview privacy card, member-page footnote, mobile usage footnote).

**`org_usage_summary` serves a plain member their OWN row** (live migration
`org_usage_summary_own_row_for_members`, 2026-08-21). It was originally hard admin-only, unlike
`org_usage_series` and `org_app_breakdown` which both already carried `or m.user_id = v_uid`. Since every
total on the Team overview is derived from these rows, a member's screen rendered zeroes across the board
and blamed them on consent — the "team insights are always empty" report. The clients had a matching gate
on the *request* (`organizations.usage_summary`'s `role not in (...)`, JS `if(teamAdmin())`), removed in
the same change: fixing one layer alone would not have changed a pixel. Nothing widened — a member still
gets exactly one row, their own, still `usage_consent`-gated.

**`org_usage_summary(p_org, p_days)` / `org_leaderboard(p_org, p_days)` — the privacy contract.** Both
read `transcriptions.text` to COUNT words and sum `duration_ms`, and return **only** aggregates
(`dictations`, `words`, `speech_ms`, `last_active`). There is no column in either return type that could
carry transcript content. A member without `usage_consent` is **absent from the result entirely** rather
than returned as zeroes, so their silence is not itself a signal. `org_leaderboard` additionally
requires `organizations.leaderboard_enabled` (the per-member `leaderboard_opt_in` stopped gating it on
2026-08-27 — the column remains, written by `org_set_consent`, but unused), and is readable
by every active member (not just admins) — that is the deliberate Phase-5b design, gated behind two
independent opt-ins.

**`groq_check_rate_limit_org`** — `groq_check_rate_limit` (MER-30) plus a `p_user_id` used to look up the
caller's org plan and RAISE their tier (`team` ×2, `enterprise` ×5; an unknown plan or no org leaves the
default). Folded into the round trip the limiter already makes, so Phase-3 entitlements cost the hot path
zero extra DB calls. A **separate name** rather than a replaced signature, so the original stays callable
as `groq-proxy`'s fallback (it latches the org RPC off after one 404) and a rollback is a one-line client
change. `EXECUTE` is revoked from `anon`/`authenticated` and granted only to `service_role` — the same
lockdown MER-30's security-advisor pass established, for the same reason.

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
- **`releases`** — **deprecated/unused as of IDI-224 (2026-08-20).** Was meant to hold auto-update
  binaries via a TUS upload from CI, but a live check found it had **zero objects, ever** — that upload
  path never worked. Release binaries now live entirely on **GitHub Releases** (see `05-conventions.md`
  #50); nothing writes to this bucket anymore. Left in place rather than deleted in case something else
  references it; do not resurrect the TUS-upload path without first explaining why the bucket was empty.
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
- **Latency flags** (`config.py::DEFAULT_CONFIG`, desktop-only, both **default `False`** so an existing
  install behaves exactly as before the 2026-08-14 latency pass; picked up by the `setdefault` backfill):
  `speed_mode` (skip the LLM under 8 words + lean prompt + `SPEED_CLEANUP_MODEL`, `openai/gpt-oss-20b` as
  of 2026-08-18 — `llama-3.1-8b-instant` before that, retired by Groq) and `chained_mode`
  (transcribe+format in ONE round trip via `groq-proxy` v10). Independent and composable — see
  03 §Models pane. Read through `config.feature_flag()`, never `config.get()` directly. Both are listed in
  `config.PIPELINE_FLAGS` and are the ONLY store for the Settings pipeline radio, which derives its
  position from them. Also `asr_model` (`"auto"` default; validated in `save_settings`).
- **`chain_*` multipart fields** (desktop → `groq-proxy`, only when `chained_mode` is on):
  `chain="1"`, `chain_model`, `chain_system`, `chain_user` (contains `{{TEXT}}`, the transcript slot),
  `chain_replace` (JSON `[{from,to}]`, the dictionary rules — applied server-side BEFORE formatting; capped
  at 500 rules server-side), `chain_reasoning_effort` (2026-08-22, optional — `"low"` for every current
  caller, since both gpt-oss tiers default to `"medium"` and burn hidden reasoning tokens on this
  mechanical task otherwise). All are deleted from the form before it is forwarded to Groq, which rejects
  unknown fields. Response gains `chain:{ok, formatted, model, fmt_ms, asr_ms, usage, error?}`.
- **`asr_provider` / `asr_alt_model`** (desktop → `groq-proxy`, only when `asr_model` picks a non-Groq
  model): `asr_provider` is `eleven` | `assembly`, `asr_alt_model` the provider's own model id
  (`scribe_v1`, `universal-2`, `universal-3-5-pro`). Also deleted before forwarding. The reply is
  normalized to `{text, provider, asr_ms}` — deliberately Groq's shape, so no client branches per provider
  and `chain=1` composes on top. On failure the function returns **502**, never 200-with-empty-text, which
  the client would misread as silence; the desktop then retries on Groq.
- **`asr-stream` Edge Function** (2026-08-15, **`verify_jwt: false`**) — the websocket relay for
  `hybrid_mode`. Connect to `wss://<proj>/functions/v1/asr-stream?provider=assembly&apikey=<anon>&device=<id>`.
  verify_jwt must be off because a WS upgrade cannot carry an Authorization header, so **the function checks
  the key itself** and refuses anything that is neither the anon key nor a `eyJ…` JWT — otherwise it is an
  open relay spending the account's ASR credit. That relaxation is quarantined in this function precisely so
  `groq-proxy` can keep verify_jwt on. Wire protocol: client sends binary PCM16 @16 kHz and
  `{"type":"done"}`; server sends `{"type":"ready"|"partial"|"final"|"error"}`. Needs `ASSEMBLYAI_API_KEY`.
- **`diarize` JSON action on `groq-proxy`** (2026-08-16; hardened IDI-259, 2026-09):
  `{"diarize":{"object":"<user>/<id>.wav"}}` → signs a 1h URL for the private `meeting-audio` object
  (service role) and submits to AssemblyAI with `speaker_labels: true`; returns `{id}`.
  `{"diarize":{"poll":"<id>"}}` → `{status}` or `{status:"completed", utterances:[{speaker,start,end}]}`
  in SECONDS. Usage logged as kind `diarize`. Needs `ASSEMBLYAI_API_KEY`; 503 without it and the desktop
  keeps gap labels (fail-closed, verified live). **Ownership is enforced since IDI-259**: diarize rejects
  anon-role callers (401 — the shape regex alone never proved ownership), submit requires the object's
  first path segment to equal the JWT `sub` (403 otherwise), and poll re-derives the binding statelessly
  from AssemblyAI's own stored `audio_url` (must start with the signed-URL prefix for the caller's user
  folder) — no durable submit→poll store needed. NOTE: desktop `groq_proxy._headers` still sends the anon
  key, so the (already-retired, `meetings_diarize_enabled` default OFF) desktop diarize path now 401s and
  fails soft to gap labels; a client that re-enables it must send the user's session JWT. The `asr_provider:
  "assembly"` transcription path also allowlists `asr_alt_model` (`universal-2`, `universal-3-5-pro`) —
  an unknown id gets 400 and the client falls back to Groq.
- **`groq-proxy` function secrets:** `GROQ_API_KEY`, `OLLAMA_API_KEY`, plus (2026-08-15)
  `ELEVENLABS_API_KEY` and `ASSEMBLYAI_API_KEY`. Set with `supabase secrets set` — there is **no MCP tool
  for secrets**. Without them the provider branch 502s naming the missing secret and dictation falls back
  to Groq, so a half-configured deploy degrades instead of breaking.
- **Insights stats (config-only, NO Supabase columns — Aug 2026):** desktop
  `config['stats_daily']` (per-day `{w,n,s,fx,apps,hh}` ledger, 800-day cap; `apps` values are
  `[words, dictations]` — bare ints from the first build are read-tolerated and upgraded on the next
  write to that app), `stats_total`,
  `stats_since`, and `stats_cloud` (incremental aggregate of `transcriptions` rows, high-water-marked on
  `created_at`; merge rule in `app/insights.py` prevents double counting). Mobile mirrors the cloud
  aggregate in AsyncStorage `verbal_insights_cache` (uid-stamped; in the `clearAccountData` teardown
  list). The Insights feature reads `transcriptions` but never writes it.
- **Device**: `{user_id, device_id, device_name, device_type, last_seen}`.
- **Canvas** (mobile UI item): `{id, state:'draft'|'sent', kind:'text'|'link'|'image', …}` → collapsed to the
  single shared `{content, image_url}` row on save.

## Auth flows

### Desktop — Google PKCE loopback (`app/auth.py`)
1. `_pkce()` verifier + S256 challenge.
2. Browser → `{URL}/auth/v1/authorize?provider=google&redirect_to=http://localhost:8765/callback&code_challenge=…`.
3. Loopback-only listeners on **port 8765** (IDI-265: `_make_servers()` binds BOTH `::1` and `127.0.0.1` —
   a loopback socket can't be dual-stack, and `localhost` resolves to either family); `_CallbackHandler`
   captures `?code=` (first code wins, `/callback` path only), serves a styled "Login successful" page,
   180 s timeout. No `state` param — GoTrue can't round-trip one (see `05-conventions.md` #82); PKCE binds
   the code.
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

- **History bootstrap on joining a device (2026-08-15):** `sync.bootstrap_history(config, save_config_fn)`
  seeds local history with the account's newest 50 non-tombstoned `transcriptions` when a device signs in
  (both desktops' after-sign-in paths) or starts sync with a near-empty local history (<5 entries). The
  SyncClient watermark is deliberately seeded to NOW, so without this a fresh install showed an empty
  History despite hundreds of cloud rows. QUIET merge (dedup by `sync_id`, then text+day as a backstop for
  entries that lost their sync_id to a config-reload race) — never touches the clipboard/overlay/paste
  path, which is `_on_sync_receive`'s job for LIVE rows only.
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
  device calls the `claim_pairing` RPC (atomic guarded claim, server-side expiry — IDI-157) → **verifies its
  own session already belongs to the host's account** (IDI-29; the old `user_id` adoption via the paired
  override is retired) → enables sync and registers the device. Host polls `pairing_status`, cancel revokes
  via `cancel_pairing`.

### Team dictionary in the sync model (IDI-216)

The shared dictionary is pulled by `organizations.fetch()` (desktop) / `fetchOrg()` (mobile) into a
LOCAL cache — `config['org']` and AsyncStorage `flume_org` respectively — and the dictation path reads
only that cache, so adding a team costs the hot path no network call. The **sync toggle gates the shared
dictionary but not team membership**: a user who turned sync off dictates with their personal dictionary
only, exactly as before joining, while still being a member with a visible roster and role. Both caches
are account-scoped and wiped on sign-out / account switch (`auth._clear_account_caches` sets
`config['org']`; `clearAccountData` removes `flume_org` and calls `clearOrgCache()` for the in-memory
mirror) — otherwise the next account on that machine would dictate with a team it was never in.

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
- **MER-29 (2026-07) — JWT forwarding shipped; `auth.uid()` enforcement APPLIED to prod 2026-09-03 (IDI-268).**
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
  - **The `auth.uid()` migration is APPLIED to prod (2026-09-03, IDI-268)**:
    `whisperflow/supabase_auth_uid_rls.sql` (drops each table's permissive policy, replaces with
    `FOR ALL TO authenticated USING (user_id = auth.uid()::text) WITH CHECK (...)` for
    `notes`/`transcriptions`/`devices`/`canvas`/`dictionary`/`meetings`). Re-verified live AFTER the apply
    (via role simulation, not a rolled-back transaction): an `anon`-role caller now sees **0** notes /
    meetings / transcriptions (was 26 / 54), and authenticated user `67962d98…` sees only their own 13
    notes / 10 meetings with **0** cross-user rows. Rollback if ever needed = re-create the prior
    permissive policies (the `DROP` lines in that file). `push_tokens` / `device_presence` were out of
    scope and still carry `USING(true)` — the documented next step.
  - **Both blockers were cleared before the apply:**
    1. **Pairing no longer adopts a `user_id`.** The paired-account override is **retired**. A claim now
       *confirms* an account instead of granting one: `pairing.ts::claimPairing` requires the scanning
       device to already hold a Supabase session whose `user.id` equals the host's `user_id`, and refuses
       the claim with an actionable message otherwise ("Sign in with the same account as the host device").
       `getCloudUserId()` returns the session id and nothing else; `getUserId()` lost its override step; the
       Settings **"Account ID" free-text field is now a read-only display** — as an editable field it was a
       plain IDOR primitive (type any user's id, read their data), which is exactly what these policies
       exist to stop. Desktop was never affected: it only ever HOSTS a pairing, and hosting already requires
       being signed in (Hard Rule #26). The accepted trade-off, chosen deliberately: **a device that hasn't
       signed in stays local-only.**
    2. **Rollout was no longer an outage risk.** JWT forwarding first shipped in **v1.0.11**; the
       `cloud_allowed()` `session_dead` gate (commit `dd01562`) shipped in **v1.0.47+**, and both had
       propagated (release **1.0.50**, 4-hour auto-update) before the 2026-09-03 apply — so no build old
       enough to lack the gate was still within the update horizon, and dead-session desktops surface the
       re-sign-in banner instead of silently reading zero rows. Mobile has no App Store installed base.
       (Hard Rule #24 / IDI-166 was the pre-gate behaviour: a dead refresh token kept syncing on the anon
       key; `cloud_allowed()` now fails closed on `session_dead`.)
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

- Transcript utterances may carry a transient `words: [[text, t0, t1]]` array **in memory only** during a
  live desktop meeting (per-word timestamps for turn splitting). The `transcript` jsonb shape above is
  unchanged: `_public_transcript()` strips `words` from every persisted/synced/emitted copy.

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
- **Security batch 2026-09 (IDI-258/267) — code committed, LIVE APPLY PENDING:**
  - `invite_rate_limits` table + `invite_check_rate_limit` SECURITY DEFINER RPC
    (`supabase/functions/invite-member/invite_rate_limits.sql`) back invite-member's new rate limiter
    (per-inviter/hour, per-org/day, per-recipient cooldown; identities only, recipient emails sha256-hashed).
    Until the SQL is applied the function fails OPEN (limiter off, latched per-isolate on RPC 404). EXECUTE
    must stay revoked from `anon`/`authenticated` (same rule as `groq_check_rate_limit`).
  - `reap-meeting-audio` now needs the `REAP_CRON_SECRET` function secret AND a matching Vault secret
    `reap_cron_secret` (read by the pg_cron job in `whisperflow/supabase_meetings.sql`), plus a redeploy
    with `--no-verify-jwt`. Until all three are done the daily reap rejects everything (fail closed — audio
    retention simply pauses; nothing user-facing breaks).
  - New optional function secrets on `invite-member`: `INVITE_LIMIT_USER_PER_HOUR` (15),
    `INVITE_LIMIT_ORG_PER_DAY` (50), `INVITE_RECIPIENT_COOLDOWN_SECONDS` (300).
