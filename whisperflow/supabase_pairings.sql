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
-- (role `authenticated`) and a TO anon policy would silently drop its rows.
drop policy if exists "pairings anon insert" on public.pairings;
drop policy if exists "pairings anon select" on public.pairings;
drop policy if exists "pairings anon update" on public.pairings;
drop policy if exists "pairings select" on public.pairings;
drop policy if exists "pairings update" on public.pairings;

-- IDI-157 (migration `pairings_rpc_lockdown`, 2026-08): INSERT is the ONLY
-- direct REST access (the host creating a token). The old `for select using
-- (true)` let anyone with the anon key enumerate every user_id that ever
-- paired; select/update policies are gone — status, claim, and cancel go
-- through the token-gated SECURITY DEFINER RPCs below. Expiry is enforced
-- server-side and the claim RPC sweeps stale rows, so the table can never
-- become a user_id directory again.
create policy "pairings insert" on public.pairings
  for insert to public with check (true);

-- Host poll: status of a KNOWN token. Never returns user_id.
create or replace function public.pairing_status(p_token text)
returns table(claimed_by text, claimed_at timestamptz, expires_at timestamptz)
language sql stable security definer set search_path = public as $fn$
  select p.claimed_by, p.claimed_at, p.expires_at
  from public.pairings p where p.token = p_token
$fn$;

-- Claimer: atomic single-use claim with server-side expiry; returns the
-- account only on success; opportunistically deletes stale rows.
create or replace function public.claim_pairing(p_token text, p_device_name text)
returns table(user_id text, host_device text)
language plpgsql security definer set search_path = public as $fn$
begin
  delete from public.pairings where expires_at < now() - interval '10 minutes';
  return query
  update public.pairings p
     set claimed_by = coalesce(nullif(trim(p_device_name), ''), 'device'),
         claimed_at = now()
   where p.token = p_token
     and p.claimed_by is null
     and p.expires_at > now()
  returning p.user_id, p.host_device;
end $fn$;

-- Host cancel: server-side revoke of an unclaimed token (a photographed QR
-- must die the moment the host hits Cancel).
create or replace function public.cancel_pairing(p_token text)
returns void
language sql security definer set search_path = public as $fn$
  delete from public.pairings where token = p_token and claimed_by is null
$fn$;
