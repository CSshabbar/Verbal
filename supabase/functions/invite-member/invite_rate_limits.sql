-- invite-member rate limiting (IDI-267).
-- Run this once in the Supabase SQL editor (project ovpcthjingugwvpxlsna) — the
-- Edge Function fails OPEN (limiter off) until it is applied, and latches the
-- limiter off per-isolate after a 404, so deploy order doesn't matter.
--
-- Same design as groq_rate_limits (whisperflow/supabase_groq_rate_limits.sql):
-- fixed epoch-aligned windows, one row per (identity, window_start), a single
-- SECURITY DEFINER RPC doing one indexed upsert+read per check, called only with
-- the service-role key. It gets its OWN table + RPC because groq_check_rate_limit's
-- opportunistic cleanup deletes rows older than 10 minutes — correct for its 60s
-- windows, but it would silently reset the hour/day windows invites need. This
-- one's cleanup horizon is 2 days (longest window is the per-org day cap).
--
-- Identities used by the function (emails are sha256-hashed before they get here —
-- this table never stores an address):
--   invite:user:<user_id>              — per-inviter, hourly
--   invite:org:<org_id>                — per-org, daily
--   invite:rcpt:<org_id>:<sha256(email)> — per-recipient cooldown

create table if not exists public.invite_rate_limits (
  identity     text not null,
  window_start timestamptz not null,
  requests     int not null default 0,
  primary key (identity, window_start)
);

create index if not exists invite_rate_limits_window_idx on public.invite_rate_limits (window_start);

alter table public.invite_rate_limits enable row level security;
-- No policies: only the service-role key (bypasses RLS) and the SECURITY DEFINER
-- RPC below ever touch this table. Never exposed to anon/authenticated clients.

create or replace function public.invite_check_rate_limit(
  p_identity text,
  p_window_seconds int,
  p_max_requests int
) returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  v_epoch numeric := extract(epoch from now());
  v_window_start timestamptz := to_timestamp(floor(v_epoch / p_window_seconds) * p_window_seconds);
  v_requests int;
begin
  -- Opportunistic cleanup so this table doesn't grow unbounded — cheap, indexed,
  -- run on ~1% of calls. Horizon must exceed the longest window in use (1 day).
  if random() < 0.01 then
    delete from public.invite_rate_limits where window_start < now() - interval '2 days';
  end if;

  insert into public.invite_rate_limits as g (identity, window_start, requests)
  values (p_identity, v_window_start, 1)
  on conflict (identity, window_start)
  do update set requests = g.requests + 1
  returning g.requests into v_requests;

  if v_requests > p_max_requests then
    return greatest(1, p_window_seconds - (v_epoch::bigint % p_window_seconds));
  end if;
  return null;
end;
$$;

-- MER-30's hard-won rule (context/05-conventions.md Hard Rule #15): a SECURITY
-- DEFINER RPC reachable via PostgREST MUST NOT be executable by clients, or any
-- anon-key holder can tamper with another identity's counter.
revoke execute on function public.invite_check_rate_limit(text, int, int) from public;
revoke execute on function public.invite_check_rate_limit(text, int, int) from anon;
revoke execute on function public.invite_check_rate_limit(text, int, int) from authenticated;
grant execute on function public.invite_check_rate_limit(text, int, int) to service_role;
