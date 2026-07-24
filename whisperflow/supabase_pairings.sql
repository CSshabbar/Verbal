-- Flume device pairing — short-lived, single-use pairing tokens.
-- Run this once in the Supabase SQL editor (project ovpcthjingugwvpxlsna).
--
-- Flow: the host device (already has a sync user_id) inserts a row with a
-- random token + expiry and shows it as a QR. The new device scans the token,
-- looks the row up, adopts `user_id`, and stamps `claimed_by`. The host polls
-- the row and shows a confirmation once it's claimed. Tokens expire (~2 min)
-- and are single-use (claim only succeeds while claimed_by IS NULL).

create table if not exists public.pairings (
  id          uuid primary key default gen_random_uuid(),
  token       text unique not null,
  user_id     text not null,          -- the account the new device will join
  host_device text,                   -- name of the device showing the QR
  created_at  timestamptz not null default now(),
  expires_at  timestamptz not null,
  claimed_by  text,                   -- name of the device that scanned it
  claimed_at  timestamptz
);

create index if not exists pairings_token_idx on public.pairings (token);

alter table public.pairings enable row level security;

-- TO public, NOT TO anon (Hard Rule #10, MER-28 2026-07 fix) — desktop uses the
-- raw anon key (role `anon`); a signed-in mobile client sends the user's JWT
-- (role `authenticated`) and a TO anon policy would silently drop its rows, the
-- same trap that bit dictionary/notes/recordings. Tokens are random + short-lived
-- + single-use, so the permissive USING/WITH CHECK (true) is acceptable either way.
drop policy if exists "pairings anon insert" on public.pairings;
drop policy if exists "pairings anon select" on public.pairings;
drop policy if exists "pairings anon update" on public.pairings;

create policy "pairings insert" on public.pairings
  for insert to public with check (true);

create policy "pairings select" on public.pairings
  for select to public using (true);

create policy "pairings update" on public.pairings
  for update to public using (true) with check (true);
