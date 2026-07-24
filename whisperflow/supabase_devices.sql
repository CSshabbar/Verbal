-- Device registry/presence (MER-28, 2026-07). Previously existed ONLY in the
-- live DB with no committed SQL. RLS + the "Users access own devices" policy
-- were already correctly enabled live (TO public) before this file was
-- written — committed here to close that gap, not to change behavior.
--
-- Idempotent — safe to run again.
create table if not exists public.devices (
  id            uuid primary key default gen_random_uuid(),
  user_id       text not null,
  device_id     text not null,
  device_name   text not null,
  device_type   text not null default 'mac',   -- 'mac' | 'win' | 'ios'
  last_seen     timestamptz default now(),
  sync_enabled  boolean not null default true   -- per-device sync gate (lib/deviceSync.ts)
);

create unique index if not exists devices_user_device_idx
  on public.devices (user_id, device_id);

alter table public.devices enable row level security;

-- TO public, NOT TO anon (Hard Rule #10) — same signed-in-mobile-JWT trap as
-- every other shared table.
drop policy if exists "Users access own devices" on public.devices;
create policy "Users access own devices" on public.devices
  for all to public using (true) with check (true);

-- In the supabase_realtime publication (already enabled live); if reproducing
-- this table from scratch, also run:
--   alter publication supabase_realtime add table public.devices;
