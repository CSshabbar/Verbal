-- Dictation history / cross-device "shared clipboard" (MER-28, 2026-07).
-- This table previously existed ONLY in the live DB with no committed SQL —
-- the base shape was written down informally in CROSSPLATFORM_SYNC_PLAN.md and
-- the later columns (audio_url, status, target_device_id, edited_text,
-- is_pinned) only ever existed as code that reads/writes them. This file makes
-- the live schema reproducible. RLS + the "Users access own transcriptions"
-- policy were already correctly enabled live (TO public) before this file was
-- written — it's committed here to close that gap, not to change behavior.
--
-- Idempotent — safe to run again.
create table if not exists public.transcriptions (
  id                uuid primary key default gen_random_uuid(),
  user_id           text not null,
  device_id         text not null,
  device_name       text not null default '',
  text              text not null,
  created_at        timestamptz default now(),
  is_pinned         boolean not null default false,
  edited_text       text,
  target_device_id  text,   -- Canvas-style device-to-device targeting
  audio_url         text,   -- private `recordings` bucket object path (see MER-27)
  status            text default 'done'  -- 'done' | 'failed' (retryable)
);

create index if not exists idx_transcriptions_user_created
  on public.transcriptions (user_id, created_at desc);
create index if not exists idx_transcriptions_pinned
  on public.transcriptions (user_id, is_pinned, created_at desc);

alter table public.transcriptions enable row level security;

-- TO public, NOT TO anon (Hard Rule #10) — desktop uses the anon key, a
-- signed-in mobile client sends a JWT (role `authenticated`); a TO anon policy
-- would silently drop the authenticated client's rows.
drop policy if exists "Users access own transcriptions" on public.transcriptions;
create policy "Users access own transcriptions" on public.transcriptions
  for all to public using (true) with check (true);

-- In the supabase_realtime publication — mobile/desktop subscribe to
-- INSERT/UPDATE filtered by user_id (verbal_history_<uid>). Already enabled
-- live; if reproducing this table from scratch, also run:
--   alter publication supabase_realtime add table public.transcriptions;

-- IDI-172 (2026-08, live migration `transcriptions_deleted_at_tombstone`):
-- history deletes are soft — deleted_at set + text cleared, never a hard
-- DELETE — so every device's merge removes its copy and nothing resurrects.
alter table public.transcriptions add column if not exists deleted_at timestamptz;
