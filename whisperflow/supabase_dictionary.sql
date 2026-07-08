-- Flume custom dictionary — vocabulary + replacement rules, one row per user.
-- Run once in the Supabase SQL editor (project ovpcthjingugwvpxlsna).

create table if not exists public.dictionary (
  user_id      text primary key,
  vocabulary   jsonb not null default '[]'::jsonb,   -- ["Lyft", "FigJam", ...]
  replacements jsonb not null default '[]'::jsonb,   -- [{"from":"shabar","to":"Shabbar"}]
  updated_at   timestamptz not null default now()
);

alter table public.dictionary enable row level security;

drop policy if exists "dictionary anon rw" on public.dictionary;
create policy "dictionary anon rw" on public.dictionary
  for all to anon using (true) with check (true);
