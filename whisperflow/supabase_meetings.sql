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
