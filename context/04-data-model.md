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

RLS on; policy `dictionary anon rw`: `FOR ALL TO anon USING(true) WITH CHECK(true)`.

**`pairings`** — `supabase_pairings.sql`. Short-lived single-use device-pairing tokens.
`id` uuid PK · `token` text unique · `user_id` text · `host_device` text · `created_at` · `expires_at`
(~2 min TTL) · `claimed_by` text (null until claimed) · `claimed_at`. Index on `(token)`. RLS on;
anon insert/select/update all `true` (safe because tokens are random, short-lived, single-use).

**`notes`** — `notes_migration.sql`.
`id` uuid PK · `user_id` text · `title` text `''` · `content` text `''` · `folder` text `''` ·
`is_pinned` bool `false` · `device_name` text · `created_at` · `updated_at`. Indexes on `(user_id)` and
`(user_id, updated_at DESC)`. In the `supabase_realtime` publication. **No RLS statement in this file.**

**`app_versions`** — `supabase_migrations/001_app_versions.sql`. Auto-update manifest.
`id` bigserial PK · `platform` text (`mac`/`win`/`ios`) · `version` text · `changelog` · `file_url` ·
`file_hash` (sha256) · `file_size` · `released_at` · `UNIQUE(platform,version)`. RLS on; public SELECT;
inserts use **service_role** (release script) — no anon insert.

### Tables WITHOUT committed SQL (exist only in the live DB — inferred from code) ⚠️

**`transcriptions`** — the core dictation history / cross-device shared clipboard. Base DDL only written
down in `whisperflow/CROSSPLATFORM_SYNC_PLAN.md`:
```
id uuid PK default gen_random_uuid(), user_id text, device_id text, device_name text,
text text, created_at timestamptz default now()   -- index (user_id, created_at desc)
```
Columns added later (code writes/reads them, **no SQL anywhere**): `audio_url` text, `status` text
default `'done'`, `target_device_id` text, `edited_text` text (read as `edited_text ?? text`),
`is_pinned` bool. In the realtime publication.

**`devices`** — device registry/presence. Cols from upserts: `user_id`, `device_id`, `device_name`,
`device_type` (`mac`/`win`/`ios`), `last_seen` timestamptz. Upsert `on_conflict=user_id,device_id`.
"Online" = `last_seen` within 5 min.

**`canvas`** — one shared row/user. Cols: `user_id` (conflict key), `content` text, `image_url` text,
`device_name`, `updated_at`. In the realtime publication.

## Storage buckets (all public)

- **`recordings`** (`supabase_recordings.sql`) — audio. Object path **`<user_id>/<id>.<ext>`**
  (desktop 16 kHz WAV; mobile m4a/wav/caf). Public URL
  `…/storage/v1/object/public/recordings/<user_id>/<id>.<ext>`. Anon select/insert/update policies scoped
  to `bucket_id='recordings'`.
- **`canvas-images`** — canvas photo attachments, path `canvas/<userId>_<ts>.<ext>`. No committed SQL.
- **`releases`** — auto-update binaries, public SELECT.

## Exact data shapes in code

- **Desktop history entry** (`config.py::add_to_history`, in `~/.verbal/config.json` `history[]`, cap 50):
  `{id:<16-hex>, text, app, ts:"YYYY-MM-DD", audio:<local path>, audio_url:<cloud>, status:"done"|"failed"}`.
- **Mobile history entry** (`lib/storage.ts HistoryEntry`): `{id, text, device_name, device_id,
  is_pinned, created_at, source:'local'|'remote', audio_uri?, audio_url?, status?}`.
- **Replacement rule** (`dictionary.py`): `{from, to, auto?:true}` (`auto` = auto-learned, ✨ in UI).
- **Snippet** (`dictionary.py` / `lib/dictionary.ts`): `{id, trigger, expansion, label, used, created_at, updated_at}` (caps: trigger 40, expansion 500).
- **Dictionary**: `{vocabulary:[str], replacements:[{from,to,auto?}], snippets:[Snippet]}`.
- **Note** (matches `notes` table); mobile `NoteEntry` adds `source:'local'|'remote'`.
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
- **Notes:** desktop REST (`on_conflict=id`) + mobile SDK CRUD; both merge with a local cache; newest
  `updated_at` wins. (Table is in the realtime publication but code polls/merges here.)
- **Canvas:** one shared row/user, upsert `on_conflict=user_id`; mobile subscribes `channel('canvas_<uid>')`.
- **Recordings:** audio → `recordings` bucket under `<user_id>/`; `audio_url` on the row/entry. Failed
  transcriptions `status:'failed'`, retryable from saved audio.
- **Pairing:** host inserts `pairings` row (`token_urlsafe(6)`, +120 s), QR `flume://pair?t=<token>`; new
  device SELECTs unclaimed/unexpired → atomic UPDATE `claimed_by` (guarded) → adopts `user_id` → enables sync.

## Security posture (as implemented)

Pragmatic, matches code + `GOOGLE_AUTH_SETUP.md`:
- Both apps use the **anon key for all data requests**; users separated purely by the `user_id` value in
  the query/filter. The user's JWT/access_token is stored but **not** used to authorize REST/realtime.
- RLS: enabled with wide-open anon `true` on `dictionary`/`pairings`; `transcriptions`/`devices`/`canvas`/
  `notes` have **no committed RLS**. Any anon caller who knows a `user_id` could read that user's rows —
  data is scoped, not cryptographically enforced.
- Proper JWT + `auth.uid()` RLS is a **documented deferred** hardening (the setup doc has the migration).
- Storage buckets are public; `app_versions` inserts are service_role-gated.

## Schema gaps & stale docs (important) ⚠️

- **No committed SQL for `transcriptions`, `devices`, `canvas`** (nor the `canvas-images` bucket) — they
  exist only in the live DB. `transcriptions.target_device_id`, `edited_text`, `is_pinned` appear in **no**
  SQL/doc. **This is the biggest schema-vs-source gap** — treat `GOOGLE_AUTH_SETUP.md`'s table list +
  `CROSSPLATFORM_SYNC_PLAN.md`'s base DDL as the only written references, and re-derive columns from code.
- **`CROSSPLATFORM_SYNC_PLAN.md` is largely stale** (placeholder URL, a `sync_token` scheme that doesn't
  exist, `sync_listen()` as a stub) — its only current value is the base `transcriptions` DDL.
- `config.py DEFAULT_CONFIG` omits `sync_enabled` and `sync_target_device_id` though both are used —
  desktop sync must be turned on explicitly.
- Mobile `useNotes` note: `isVoice` isn't persisted (no `is_voice` column).
