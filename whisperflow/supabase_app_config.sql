-- app_config — small key/value store for app-wide settings we host centrally
-- (e.g. the shared Groq API key so users never have to paste one). Run once in the
-- Supabase SQL editor (project ovpcthjingugwvpxlsna). Idempotent — safe to re-run.
--
-- SECURITY POSTURE: the shared Groq key stored here is readable by the anon key
-- (that's the point — the app reads it). It is therefore extractable by anyone with
-- the app, same as the bundled anon Supabase key. RLS below makes it **read-only**
-- to clients (anon + authenticated); only the service role / SQL editor can write,
-- so a client can't overwrite or wipe the shared key.

create table if not exists public.app_config (
  name       text primary key,
  value      text,
  updated_at timestamptz default now()
);

alter table public.app_config enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'app_config' and policyname = 'app_config read'
  ) then
    -- Read-only to everyone; no insert/update/delete policy ⇒ clients cannot write.
    create policy "app_config read" on public.app_config
      for select to public using (true);
  end if;
end $$;
