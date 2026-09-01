-- Meetings — table + storage bucket for the Meetings feature (desktop capture,
-- mobile read-only). Idempotent: safe to run more than once.
--
-- Data shapes (see context/04-data-model.md):
--   transcript      jsonb  [{speaker, t0, t1, text}]           (utterances; t0/t1 = seconds from start)
--   speakers        jsonb  {"s1": "Sarah", "self": "You", ...} (speaker_id -> display name)
--   decisions       jsonb  ["We ship behind a flag", ...]
--   action_items    jsonb  [{owner, task, done}]               (owner = speaker_id or null)
--   marked_moments  jsonb  [{t, label}]                        (t = seconds from start)
--   hybrid_notes    jsonb  [{user_line, ai_addition}]          (scratchpad line + AI context; widget #21)
--
-- Idempotent upgrade for pre-existing installs:
--   alter table public.meetings add column if not exists hybrid_notes jsonb not null default '[]';
--
-- RLS: `TO public`, not `TO anon` — the desktop uses the raw anon key (role anon)
-- while a signed-in mobile client sends a JWT (role authenticated); a TO anon
-- policy silently hides rows from signed-in clients (context/05-conventions.md
-- Hard Rule #10). Scoping is by user_id in the query; JWT/auth.uid() RLS is the
-- documented deferred hardening (04-data-model.md §Security posture).

create table if not exists public.meetings (
  id               uuid primary key default gen_random_uuid(),
  user_id          text not null,
  title            text not null default '',
  started_at       timestamptz not null default now(),
  ended_at         timestamptz,
  duration_seconds integer not null default 0,
  audio_url        text,
  transcript       jsonb not null default '[]',
  speakers         jsonb not null default '{}',
  scratchpad       text not null default '',
  summary          text not null default '',
  decisions        jsonb not null default '[]',
  action_items     jsonb not null default '[]',
  marked_moments   jsonb not null default '[]',
  hybrid_notes     jsonb not null default '[]',
  device_id        text,
  device_name      text,
  status           text not null default 'processing',  -- processing | ready | failed
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create index if not exists meetings_user_idx        on public.meetings (user_id);
create index if not exists meetings_user_started_idx on public.meetings (user_id, started_at desc);

alter table public.meetings enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'meetings' and policyname = 'meetings rw'
  ) then
    create policy "meetings rw" on public.meetings
      for all to public using (true) with check (true);
  end if;
end $$;

-- Realtime: mobile subscribes to INSERT/UPDATE so a finished desktop meeting
-- appears within seconds.
do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'meetings'
  ) then
    alter publication supabase_realtime add table public.meetings;
  end if;
end $$;

-- Storage bucket for meeting audio (public, like `recordings`).
-- Object path: <user_id>/<meeting_id>.<ext>
insert into storage.buckets (id, name, public)
values ('meeting-audio', 'meeting-audio', true)
on conflict (id) do update set public = true;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'storage' and tablename = 'objects' and policyname = 'meeting-audio read'
  ) then
    create policy "meeting-audio read" on storage.objects
      for select to public using (bucket_id = 'meeting-audio');
  end if;
  if not exists (
    select 1 from pg_policies
    where schemaname = 'storage' and tablename = 'objects' and policyname = 'meeting-audio insert'
  ) then
    create policy "meeting-audio insert" on storage.objects
      for insert to public with check (bucket_id = 'meeting-audio');
  end if;
  if not exists (
    select 1 from pg_policies
    where schemaname = 'storage' and tablename = 'objects' and policyname = 'meeting-audio update'
  ) then
    create policy "meeting-audio update" on storage.objects
      for update to public using (bucket_id = 'meeting-audio');
  end if;
  if not exists (
    select 1 from pg_policies
    where schemaname = 'storage' and tablename = 'objects' and policyname = 'meeting-audio delete'
  ) then
    create policy "meeting-audio delete" on storage.objects
      for delete to public using (bucket_id = 'meeting-audio');
  end if;
end $$;

-- Widget kit v2 follow-ups (Jul 2026)
alter table public.meetings add column if not exists pinned boolean not null default false;
alter table public.meetings add column if not exists recognized jsonb not null default '{}'::jsonb;
alter table public.meetings add column if not exists notes_md text;  -- full AI meeting notes (markdown)
alter table public.meetings add column if not exists live boolean not null default false;  -- true while capturing (live mirror)
-- push_tokens: Expo push tokens per user (mobile meeting-start notifications)
create table if not exists public.push_tokens (
  user_id text not null, token text not null, platform text, device_name text,
  updated_at timestamptz not null default now(), primary key (user_id, token));
alter table public.push_tokens enable row level security;

-- Meeting-audio retention reaper (MER-31, 2026-07). OFF by default — a meeting
-- only gets `retention_days > 0` if the user explicitly changes
-- `meetings_keep_audio_days` from its default of 0 (never expire); desktop
-- stamps this per-meeting at capture time (app/meetings.py::row()), not a
-- retroactive global setting, so changing it only affects future recordings.
-- `audio_expired` is the single, authoritative "no audio left" signal clients
-- check — never inferred from a null `audio_url` (both fields go together).
alter table public.meetings add column if not exists audio_expired boolean not null default false;
alter table public.meetings add column if not exists retention_days int;  -- null/0 = never expire

create extension if not exists pg_cron;
create extension if not exists pg_net;

-- Calls the `reap-meeting-audio` Edge Function daily at 03:00 UTC (a low-traffic
-- window). The function does the actual work with the service-role key
-- internally (Deno.env, same pattern as every other Edge Function in this repo).
--
-- IDI-258: the call is authenticated by a DEDICATED cron secret, not a JWT. The
-- anon key that used to ride this call is a public client key and never gated
-- anything — anyone holding it could trigger (or probe) a cross-tenant
-- service-role delete pass. Setup, once, before (re)running this schedule:
--
--   1. Generate a long random value (e.g. `openssl rand -hex 32`).
--   2. Store it in Vault so the job below can read it without committing it:
--        select vault.create_secret('<that value>', 'reap_cron_secret');
--   3. Mirror the SAME value into the function's secrets:
--        supabase secrets set REAP_CRON_SECRET=<that value>
--   4. Deploy the function with the gateway JWT check OFF, so the secret header
--      is the sole (real) gate:
--        supabase functions deploy reap-meeting-audio --no-verify-jwt
--
-- The function rejects every caller whose x-cron-secret doesn't match (compared
-- in constant time), and rejects ALL callers while REAP_CRON_SECRET is unset.
select cron.schedule(
  'reap-meeting-audio-daily',
  '0 3 * * *',
  $$
  select net.http_post(
    url := 'https://ovpcthjingugwvpxlsna.supabase.co/functions/v1/reap-meeting-audio',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-cron-secret', (select decrypted_secret from vault.decrypted_secrets
                        where name = 'reap_cron_secret')
    ),
    body := '{}'::jsonb,
    timeout_milliseconds := 30000
  ) as request_id;
  $$
);
