-- groq-proxy per-identity rate limiting (MER-30).
-- Run this once in the Supabase SQL editor (project ovpcthjingugwvpxlsna).
--
-- Design note: the first cut of this feature used an in-memory (in-isolate) counter
-- inside the groq-proxy Edge Function, to avoid a synchronous DB round-trip on the
-- hot path. Live testing during MER-30 disproved that: a 35-request sequential burst
-- from one identity showed 0 rejections from the in-memory limiter (confirmed via
-- groq_usage row counts — every request reached the upstream Groq call), meaning
-- Supabase's edge runtime does not reliably keep module-level state warm across
-- invocations for this traffic pattern. A DB-backed atomic counter is the only
-- available option that is actually correct, so this table + RPC replaces it.
--
-- Fixed epoch-aligned windows (not sliding), one row per (identity, window_start).
-- The `groq_check_rate_limit` RPC does a single indexed upsert + read in one round
-- trip, called with the service-role key from the Edge Function (same auth pattern
-- as the existing groq_usage insert) so no client-facing grants are needed.

create table if not exists public.groq_rate_limits (
  identity     text not null,
  window_start timestamptz not null,
  requests     int not null default 0,
  tokens       int not null default 0,
  primary key (identity, window_start)
);

create index if not exists groq_rate_limits_window_idx on public.groq_rate_limits (window_start);

alter table public.groq_rate_limits enable row level security;
-- No policies: only the service-role key (bypasses RLS) and the SECURITY DEFINER
-- RPC below ever touch this table. Never exposed to anon/authenticated clients.

create or replace function public.groq_check_rate_limit(
  p_identity text,
  p_window_seconds int,
  p_max_requests int,
  p_token_estimate int,
  p_max_tokens int
) returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  v_epoch numeric := extract(epoch from now());
  v_window_start timestamptz := to_timestamp(floor(v_epoch / p_window_seconds) * p_window_seconds);
  v_requests int;
  v_tokens int;
begin
  -- Opportunistic cleanup so this table doesn't grow unbounded — cheap, indexed,
  -- and run on ~1% of calls rather than every call.
  if random() < 0.01 then
    delete from public.groq_rate_limits where window_start < now() - interval '10 minutes';
  end if;

  insert into public.groq_rate_limits as g (identity, window_start, requests, tokens)
  values (p_identity, v_window_start, 1, p_token_estimate)
  on conflict (identity, window_start)
  do update set requests = g.requests + 1, tokens = g.tokens + p_token_estimate
  returning g.requests, g.tokens into v_requests, v_tokens;

  if v_requests > p_max_requests or v_tokens > p_max_tokens then
    return greatest(1, p_window_seconds - (v_epoch::bigint % p_window_seconds));
  end if;
  return null;
end;
$$;
