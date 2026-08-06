-- Canvas — shared staging clipboard, one row per user (MER-28, 2026-07).
-- Previously existed ONLY in the live DB with no committed SQL. RLS + the
-- "Users access own canvas" policy were already correctly enabled live
-- (TO public) before this file was written — committed here to close that
-- gap, not to change behavior.
--
-- Idempotent — safe to run again.
create table if not exists public.canvas (
  id           uuid primary key default gen_random_uuid(),
  user_id      text not null,
  content      text not null default '',
  device_name  text not null default '',
  updated_at   timestamptz default now(),
  image_url    text
);

-- One row per user — upserts target user_id as the conflict key.
create unique index if not exists canvas_user_id_idx on public.canvas (user_id);

alter table public.canvas enable row level security;

-- TO public, NOT TO anon (Hard Rule #10) — same signed-in-mobile-JWT trap as
-- every other shared table.
drop policy if exists "Users access own canvas" on public.canvas;
create policy "Users access own canvas" on public.canvas
  for all to public using (true) with check (true);

-- In the supabase_realtime publication (already enabled live); if reproducing
-- this table from scratch, also run:
--   alter publication supabase_realtime add table public.canvas;

-- IDI-173 (2026-08, live migration `canvas_device_id_origin`): origin filtering
-- by stable device_id instead of display name (same-name devices used to drop
-- each other's updates). Old-client rows without it fall back to name-compare.
alter table public.canvas add column if not exists device_id text;
