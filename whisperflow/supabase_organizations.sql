-- Team / Organization layer (IDI-216, Phases 1/3/4/5). Idempotent — safe to re-run.
-- Run once in the Supabase SQL editor (project ovpcthjingugwvpxlsna).
--
-- SEQUENCING DECISION (IDI-216 open decision #1, resolved 2026-08-19):
-- this migration deliberately does NOT touch the six legacy tables that
-- `whisperflow/supabase_auth_uid_rls.sql` (IDI-29) rewrites, and does not depend on
-- that migration having been applied. Everything the team layer needs is either
--   (a) a NEW table created here, which is `TO authenticated` + `auth.uid()`-scoped
--       from the very first row, or
--   (b) a cross-member read (usage insights, leaderboard), which goes through a
--       SECURITY DEFINER RPC that checks org membership ITSELF rather than leaning
--       on the caller's row-level access to someone else's data.
-- So Teams needs no cross-account access to `dictionary`/`transcriptions`/etc, and
-- shipping it does not require the pairing-vs-auth.uid() product decision or the
-- client-rollout window that hold IDI-29 back. The shared dictionary lives in its
-- own org-scoped table (`organization_dictionary`), NOT in a widened `dictionary`.
--
-- RLS RECURSION NOTE: a policy on `organization_members` that answers "is the caller
-- a member of this org?" by selecting `organization_members` would recurse. Every
-- policy below therefore asks `public.org_member_role(org_id)`, a SECURITY DEFINER
-- function that reads the table with RLS bypassed. That function is the single
-- definition of "who may see this org" — change it and every policy follows.
--
-- WRITE MODEL: membership and invites are read-mostly over REST and written ONLY
-- through the RPCs at the bottom of this file (or the `invite-member` Edge Function
-- with the service-role key). There is no direct INSERT/UPDATE/DELETE policy on
-- `organization_members` on purpose: Postgres RLS cannot restrict which COLUMNS a
-- policy lets you write, so a "members may update their own row" policy would also
-- let a member set their own `role` to 'owner'. Consent flags are changed via
-- `org_set_consent`, which writes exactly those two columns and nothing else.

-- ── tables ───────────────────────────────────────────────────────────────────

create table if not exists public.organizations (
  id                  uuid primary key default gen_random_uuid(),
  name                text not null,
  company_name        text not null default '',
  owner_user_id       text not null,
  -- Phase 3 entitlements. Kept as columns on the org rather than a separate
  -- org_entitlements table: there is exactly one row per org either way, and the
  -- existing billing seams (meetings.retention_days) are already column-shaped.
  plan                text not null default 'team',
  seats               int  not null default 5,
  -- Phase 5b. The owner's org-wide switch for the member-visible leaderboard.
  -- Default OFF (IDI-216 open decision #4): a visible ranking of teammates by
  -- activity is more surveillance-adjacent than a private admin dashboard, so it
  -- never turns itself on. When it IS on, every ACTIVE MEMBER can read the board
  -- (not just admins) — but only members who individually opted in appear on it.
  leaderboard_enabled boolean not null default false,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

create table if not exists public.organization_members (
  org_id             uuid not null references public.organizations(id) on delete cascade,
  user_id            text not null,
  email              text not null default '',
  display_name       text not null default '',
  role               text not null default 'member',
  status             text not null default 'active',
  -- Phase 5 consent. `usage_consent` gates whether this member's aggregates are
  -- visible to org admins at all; `leaderboard_opt_in` additionally gates the
  -- team-visible ranking. Both default FALSE and are set by the member alone
  -- (org_set_consent) — an admin can never grant consent on someone's behalf.
  usage_consent      boolean not null default false,
  leaderboard_opt_in boolean not null default false,
  joined_at          timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  primary key (org_id, user_id),
  constraint organization_members_role_check   check (role   in ('owner', 'admin', 'member')),
  constraint organization_members_status_check check (status in ('active', 'invited', 'removed'))
);

-- One org per user is the shipped model (the clients assume `my org` is singular).
-- Enforced here rather than in app code so a second membership cannot be created
-- by a racing invite claim.
create unique index if not exists organization_members_one_active_org
  on public.organization_members (user_id) where status = 'active';
create index if not exists organization_members_org_idx on public.organization_members (org_id);

create table if not exists public.organization_invites (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references public.organizations(id) on delete cascade,
  email       text not null,
  -- sha256 hex of the token. The raw token exists only in the invite email and in
  -- the claim URL — a leaked DB row cannot be replayed into a membership.
  token_hash  text not null,
  role        text not null default 'member',
  invited_by  text not null,
  status      text not null default 'pending',
  expires_at  timestamptz not null default (now() + interval '7 days'),
  claimed_by  text,
  claimed_at  timestamptz,
  created_at  timestamptz not null default now(),
  constraint organization_invites_role_check   check (role   in ('admin', 'member')),
  constraint organization_invites_status_check check (status in ('pending', 'claimed', 'expired', 'revoked'))
);

create unique index if not exists organization_invites_token_idx on public.organization_invites (token_hash);
create index if not exists organization_invites_org_idx on public.organization_invites (org_id, status);

-- Phase 4 — the shared dictionary/snippets, one row per org. Deliberately the same
-- SHAPE as public.dictionary so the desktop/mobile merge code can reuse
-- normalize()/mergeDictionary() verbatim instead of growing a second data model.
create table if not exists public.organization_dictionary (
  org_id       uuid primary key references public.organizations(id) on delete cascade,
  vocabulary   jsonb not null default '[]'::jsonb,
  replacements jsonb not null default '[]'::jsonb,
  snippets     jsonb not null default '[]'::jsonb,
  updated_by   text not null default '',
  updated_at   timestamptz not null default now()
);

-- ── the single definition of "who may see this org" ──────────────────────────

create or replace function public.org_member_role(p_org uuid)
returns text
language sql
stable
security definer
set search_path = public
as $$
  select m.role
    from public.organization_members m
   where m.org_id = p_org
     and m.user_id = auth.uid()::text
     and m.status = 'active'
   limit 1
$$;

revoke all on function public.org_member_role(uuid) from public;
grant execute on function public.org_member_role(uuid) to authenticated, service_role;

-- ── RLS ──────────────────────────────────────────────────────────────────────
-- All policies are `TO authenticated` and keyed on auth.uid(). Unlike the legacy
-- tables (Hard Rule #10's TO public compromise) there is no signed-out client that
-- ever needs to read these: a device that never signed in has no org, by design.

alter table public.organizations          enable row level security;
alter table public.organization_members   enable row level security;
alter table public.organization_invites   enable row level security;
alter table public.organization_dictionary enable row level security;

drop policy if exists "organizations read"   on public.organizations;
drop policy if exists "organizations insert" on public.organizations;
drop policy if exists "organizations update" on public.organizations;
drop policy if exists "organizations delete" on public.organizations;

create policy "organizations read" on public.organizations
  for select to authenticated
  using (public.org_member_role(id) is not null);

-- The creator must be the owner named on the row. Membership itself is created by
-- org_create (which inserts the org AND the owner's member row in one transaction);
-- this policy exists so a hand-rolled insert can't hand an org to someone else.
create policy "organizations insert" on public.organizations
  for insert to authenticated
  with check (owner_user_id = auth.uid()::text);

create policy "organizations update" on public.organizations
  for update to authenticated
  using (public.org_member_role(id) in ('owner', 'admin'))
  with check (public.org_member_role(id) in ('owner', 'admin'));

create policy "organizations delete" on public.organizations
  for delete to authenticated
  using (public.org_member_role(id) = 'owner');

drop policy if exists "organization_members read" on public.organization_members;

-- Read-only to clients; every write goes through an RPC (see WRITE MODEL above).
create policy "organization_members read" on public.organization_members
  for select to authenticated
  using (public.org_member_role(org_id) is not null);

drop policy if exists "organization_invites read" on public.organization_invites;

-- Only owners/admins can see who has been invited. Claiming does NOT read through
-- this policy — org_claim_invite is SECURITY DEFINER, because the claimer is by
-- definition not a member yet.
create policy "organization_invites read" on public.organization_invites
  for select to authenticated
  using (public.org_member_role(org_id) in ('owner', 'admin'));

drop policy if exists "organization_dictionary read"  on public.organization_dictionary;
drop policy if exists "organization_dictionary write" on public.organization_dictionary;
drop policy if exists "organization_dictionary edit"  on public.organization_dictionary;

-- Every active member READS the shared dictionary (they dictate with it);
-- only owners/admins write it.
create policy "organization_dictionary read" on public.organization_dictionary
  for select to authenticated
  using (public.org_member_role(org_id) is not null);

create policy "organization_dictionary write" on public.organization_dictionary
  for insert to authenticated
  with check (public.org_member_role(org_id) in ('owner', 'admin'));

create policy "organization_dictionary edit" on public.organization_dictionary
  for update to authenticated
  using (public.org_member_role(org_id) in ('owner', 'admin'))
  with check (public.org_member_role(org_id) in ('owner', 'admin'));

-- ── RPCs ─────────────────────────────────────────────────────────────────────

-- Create an org and make the caller its owner, atomically. Returns the org row.
create or replace function public.org_create(p_name text, p_company text default '')
returns public.organizations
language plpgsql
security definer
set search_path = public
as $$
declare
  v_uid  text := auth.uid()::text;
  v_org  public.organizations;
  v_name text := nullif(btrim(coalesce(p_name, '')), '');
begin
  if v_uid is null then
    raise exception 'not_authenticated' using errcode = '28000';
  end if;
  if v_name is null then
    raise exception 'name_required' using errcode = '22023';
  end if;
  if exists (select 1 from public.organization_members
              where user_id = v_uid and status = 'active') then
    raise exception 'already_in_org' using errcode = '23505';
  end if;

  insert into public.organizations (name, company_name, owner_user_id)
  values (left(v_name, 80), left(btrim(coalesce(p_company, '')), 120), v_uid)
  returning * into v_org;

  insert into public.organization_members (org_id, user_id, email, display_name, role, status)
  values (v_org.id, v_uid,
          coalesce((select email from auth.users where id = auth.uid()), ''),
          coalesce((select raw_user_meta_data ->> 'full_name' from auth.users where id = auth.uid()), ''),
          'owner', 'active');

  insert into public.organization_dictionary (org_id, updated_by) values (v_org.id, v_uid)
  on conflict (org_id) do nothing;

  return v_org;
end;
$$;

-- Claim an invite. SECURITY DEFINER because the caller is not a member yet and so
-- cannot read `organization_invites` through its policy.
--
-- FAIL-CLOSED, in this order: unknown token, expired, already claimed/revoked, the
-- caller already belongs to an org, the org is out of seats, and finally the email
-- guard — the signed-in account's email must match the address the invite was sent
-- to (case-insensitive). Without that last check a forwarded or leaked invite link
-- would grant membership to whoever opened it first.
create or replace function public.org_claim_invite(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_uid   text := auth.uid()::text;
  v_email text;
  v_inv   public.organization_invites;
  v_seats int;
  v_used  int;
begin
  if v_uid is null then
    return jsonb_build_object('ok', false, 'error', 'not_authenticated');
  end if;
  select email into v_email from auth.users where id = auth.uid();

  select * into v_inv from public.organization_invites
   where token_hash = encode(sha256(convert_to(coalesce(p_token, ''), 'utf8')), 'hex')
   for update;

  if not found then
    return jsonb_build_object('ok', false, 'error', 'invalid_token');
  end if;
  if v_inv.status <> 'pending' then
    return jsonb_build_object('ok', false, 'error', 'already_used');
  end if;
  if v_inv.expires_at <= now() then
    update public.organization_invites set status = 'expired' where id = v_inv.id;
    return jsonb_build_object('ok', false, 'error', 'expired');
  end if;
  if exists (select 1 from public.organization_members
              where user_id = v_uid and status = 'active') then
    return jsonb_build_object('ok', false, 'error', 'already_in_org');
  end if;
  if lower(coalesce(v_email, '')) <> lower(v_inv.email) then
    return jsonb_build_object('ok', false, 'error', 'email_mismatch',
                              'invited_email', v_inv.email);
  end if;

  select seats into v_seats from public.organizations where id = v_inv.org_id;
  select count(*) into v_used from public.organization_members
   where org_id = v_inv.org_id and status = 'active';
  if v_used >= coalesce(v_seats, 0) then
    return jsonb_build_object('ok', false, 'error', 'no_seats');
  end if;

  insert into public.organization_members (org_id, user_id, email, display_name, role, status)
  values (v_inv.org_id, v_uid, coalesce(v_email, ''),
          coalesce((select raw_user_meta_data ->> 'full_name' from auth.users where id = auth.uid()), ''),
          v_inv.role, 'active')
  on conflict (org_id, user_id) do update
    set status = 'active', role = excluded.role, email = excluded.email,
        updated_at = now();

  update public.organization_invites
     set status = 'claimed', claimed_by = v_uid, claimed_at = now()
   where id = v_inv.id;

  return jsonb_build_object('ok', true, 'org_id', v_inv.org_id, 'role', v_inv.role);
end;
$$;

-- Change a member's role. Owner/admin only; the owner's own role is immovable
-- (an org must always have exactly one owner) and nobody may promote to 'owner'.
create or replace function public.org_set_role(p_org uuid, p_user text, p_role text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_actor text := public.org_member_role(p_org);
begin
  if v_actor not in ('owner', 'admin') then
    return jsonb_build_object('ok', false, 'error', 'forbidden');
  end if;
  if p_role not in ('admin', 'member') then
    return jsonb_build_object('ok', false, 'error', 'bad_role');
  end if;
  if exists (select 1 from public.organizations
              where id = p_org and owner_user_id = p_user) then
    return jsonb_build_object('ok', false, 'error', 'cannot_change_owner');
  end if;
  update public.organization_members
     set role = p_role, updated_at = now()
   where org_id = p_org and user_id = p_user and status = 'active';
  if not found then
    return jsonb_build_object('ok', false, 'error', 'not_a_member');
  end if;
  return jsonb_build_object('ok', true);
end;
$$;

-- Remove a member (soft — status 'removed', so the row's consent history and the
-- unique-active-org index both stay coherent and a re-invite is a clean re-claim).
-- Admins cannot remove the owner or each other's superiors; the owner cannot be
-- removed at all. A member may always remove THEMSELVES (leave the team).
create or replace function public.org_remove_member(p_org uuid, p_user text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_uid    text := auth.uid()::text;
  v_actor  text := public.org_member_role(p_org);
  v_target text;
begin
  if v_actor is null then
    return jsonb_build_object('ok', false, 'error', 'forbidden');
  end if;
  if p_user <> v_uid and v_actor not in ('owner', 'admin') then
    return jsonb_build_object('ok', false, 'error', 'forbidden');
  end if;
  if exists (select 1 from public.organizations
              where id = p_org and owner_user_id = p_user) then
    return jsonb_build_object('ok', false, 'error', 'cannot_remove_owner');
  end if;
  select role into v_target from public.organization_members
   where org_id = p_org and user_id = p_user and status = 'active';
  if v_target is null then
    return jsonb_build_object('ok', false, 'error', 'not_a_member');
  end if;
  if v_actor = 'admin' and v_target = 'admin' and p_user <> v_uid then
    return jsonb_build_object('ok', false, 'error', 'forbidden');
  end if;

  update public.organization_members
     set status = 'removed', usage_consent = false, leaderboard_opt_in = false,
         updated_at = now()
   where org_id = p_org and user_id = p_user;
  return jsonb_build_object('ok', true);
end;
$$;

-- A member's own consent flags — the ONLY membership columns a non-admin can move,
-- and an admin cannot move them for someone else. Turning usage_consent off also
-- drops the member off the leaderboard: you cannot be ranked on data you just
-- withdrew.
create or replace function public.org_set_consent(p_org uuid, p_usage boolean, p_leaderboard boolean)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_uid text := auth.uid()::text;
begin
  if public.org_member_role(p_org) is null then
    return jsonb_build_object('ok', false, 'error', 'forbidden');
  end if;
  update public.organization_members
     set usage_consent      = coalesce(p_usage, false),
         leaderboard_opt_in = coalesce(p_usage, false) and coalesce(p_leaderboard, false),
         updated_at         = now()
   where org_id = p_org and user_id = v_uid and status = 'active';
  return jsonb_build_object('ok', true);
end;
$$;

-- Phase 5 — per-member usage. Every active member can call this (an owner/admin
-- gets every consenting member, anyone else gets exactly their own row) — see
-- app/flume_dashboard_html.py's loadTeamExtras comment: the frontend always
-- requests this for everyone, and used to be gated on teamAdmin() client-side,
-- which is why a plain member's Team screen was all zeroes.
--
-- FIXED 2026-08-25 (fix_org_usage_summary_member_own_row): this originally
-- hard-gated the entire function to `role in ('owner','admin')`, silently
-- returning empty for a plain member — contradicting the contract above and
-- leaving a member's own Team screen blank even after the frontend fix landed,
-- since usage_consent gates visibility TO ADMINS, not to yourself.
--
-- PRIVACY CONTRACT (IDI-216 open decision #2, and the reason this is an RPC rather
-- than a view): the function reads `transcriptions.text` to COUNT words, and returns
-- only counts. No transcript, title, note or audio reference can leave through it —
-- there is no column in the return type that could carry one. A member who has not
-- set usage_consent is absent from an ADMIN's result entirely (not zeroed), so an
-- admin cannot infer activity from a row of zeroes either — but every member can
-- still see their own row regardless of their own consent flag.
create or replace function public.org_usage_summary(p_org uuid, p_days int default 30)
returns table (
  user_id      text,
  email        text,
  display_name text,
  role         text,
  dictations   bigint,
  words        bigint,
  speech_ms    bigint,
  last_active  timestamptz
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  v_uid   text := auth.uid()::text;
  v_role  text := public.org_member_role(p_org);
  v_since timestamptz := now() - (greatest(1, least(coalesce(p_days, 30), 365)) || ' days')::interval;
begin
  if v_role is null then
    return;
  end if;
  return query
    select m.user_id, m.email, m.display_name, m.role,
           coalesce(t.dictations, 0), coalesce(t.words, 0), coalesce(t.speech_ms, 0), t.last_active
      from public.organization_members m
      left join lateral (
        select count(*)                                              as dictations,
               coalesce(sum(array_length(regexp_split_to_array(btrim(tr.text), '\s+'), 1)), 0) as words,
               coalesce(sum(coalesce(tr.duration_ms, 0)), 0)::bigint as speech_ms,
               max(tr.created_at)                                    as last_active
          from public.transcriptions tr
         where tr.user_id = m.user_id
           and tr.created_at >= v_since
           and tr.deleted_at is null
           and btrim(coalesce(tr.text, '')) <> ''
      ) t on true
     where m.org_id = p_org and m.status = 'active'
       and (m.user_id = v_uid or (v_role in ('owner', 'admin') and m.usage_consent))
     order by coalesce(t.words, 0) desc;
end;
$$;

-- Phase 5b — the team-visible leaderboard. Readable by EVERY active member (not
-- just admins) once the owner has switched it on org-wide, and listing only the
-- members who individually opted in. Same counts-only return shape as above.
create or replace function public.org_leaderboard(p_org uuid, p_days int default 7)
returns table (
  user_id      text,
  display_name text,
  words        bigint,
  speech_ms    bigint
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  v_since timestamptz := now() - (greatest(1, least(coalesce(p_days, 7), 365)) || ' days')::interval;
begin
  if public.org_member_role(p_org) is null then
    return;
  end if;
  if not exists (select 1 from public.organizations
                  where id = p_org and leaderboard_enabled) then
    return;
  end if;
  return query
    select m.user_id, m.display_name,
           coalesce(t.words, 0), coalesce(t.speech_ms, 0)
      from public.organization_members m
      left join lateral (
        select coalesce(sum(array_length(regexp_split_to_array(btrim(tr.text), '\s+'), 1)), 0) as words,
               coalesce(sum(coalesce(tr.duration_ms, 0)), 0)::bigint                           as speech_ms
          from public.transcriptions tr
         where tr.user_id = m.user_id
           and tr.created_at >= v_since
           and tr.deleted_at is null
           and btrim(coalesce(tr.text, '')) <> ''
      ) t on true
     where m.org_id = p_org and m.status = 'active'
       and m.usage_consent and m.leaderboard_opt_in
     order by coalesce(t.words, 0) desc;
end;
$$;

-- Phase 3 — the entitlement lookup the groq-proxy rate limiter folds into its
-- EXISTING round trip. This is a superset of `groq_check_rate_limit` (MER-30) with
-- one extra argument; it is a separate name rather than a replaced signature so
-- the old function stays callable as the Edge Function's fallback and a rollback
-- is a one-line client change, not a migration.
--
-- Team members get the org's tier limits instead of the per-identity defaults. The
-- lookup is one indexed read inside a function that was already doing a write, so
-- Phase 3 costs the hot path ZERO extra round trips (Hard Rule #15's whole reason
-- for existing). p_user_id null → behaves exactly like groq_check_rate_limit.
create or replace function public.groq_check_rate_limit_org(
  p_identity       text,
  p_window_seconds int,
  p_max_requests   int,
  p_token_estimate int,
  p_max_tokens     int,
  p_user_id        text default null
) returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  v_epoch        numeric      := extract(epoch from now());
  v_window_start timestamptz  := to_timestamp(floor(v_epoch / p_window_seconds) * p_window_seconds);
  v_requests     int;
  v_tokens       int;
  v_plan         text;
  v_max_req      int := p_max_requests;
  v_max_tok      int := p_max_tokens;
begin
  if p_user_id is not null then
    select o.plan into v_plan
      from public.organization_members m
      join public.organizations o on o.id = m.org_id
     where m.user_id = p_user_id and m.status = 'active'
     limit 1;
    -- Only ever RAISES a limit. An org lookup that returns nothing, or a plan name
    -- this function doesn't know, leaves the caller on the default tier.
    if v_plan = 'team' then
      v_max_req := greatest(v_max_req, p_max_requests * 2);
      v_max_tok := greatest(v_max_tok, p_max_tokens * 2);
    elsif v_plan = 'enterprise' then
      v_max_req := greatest(v_max_req, p_max_requests * 5);
      v_max_tok := greatest(v_max_tok, p_max_tokens * 5);
    end if;
  end if;

  if random() < 0.01 then
    delete from public.groq_rate_limits where window_start < now() - interval '10 minutes';
  end if;

  insert into public.groq_rate_limits as g (identity, window_start, requests, tokens)
  values (p_identity, v_window_start, 1, p_token_estimate)
  on conflict (identity, window_start)
  do update set requests = g.requests + 1, tokens = g.tokens + p_token_estimate
  returning g.requests, g.tokens into v_requests, v_tokens;

  if v_requests > v_max_req or v_tokens > v_max_tok then
    return greatest(1, p_window_seconds - (v_epoch::bigint % p_window_seconds));
  end if;
  return null;
end;
$$;

-- ── grants ───────────────────────────────────────────────────────────────────
-- Member-facing RPCs are callable by signed-in users only; each one re-derives the
-- caller from auth.uid() and checks its own authorization, so `authenticated` here
-- grants the right to ASK, never the right to act on another org.

revoke all on function public.org_create(text, text)                    from public;
revoke all on function public.org_claim_invite(text)                    from public;
revoke all on function public.org_set_role(uuid, text, text)            from public;
revoke all on function public.org_remove_member(uuid, text)             from public;
revoke all on function public.org_set_consent(uuid, boolean, boolean)   from public;
revoke all on function public.org_usage_summary(uuid, int)              from public;
revoke all on function public.org_leaderboard(uuid, int)                from public;

grant execute on function public.org_create(text, text)                  to authenticated;
grant execute on function public.org_claim_invite(text)                  to authenticated;
grant execute on function public.org_set_role(uuid, text, text)          to authenticated;
grant execute on function public.org_remove_member(uuid, text)           to authenticated;
grant execute on function public.org_set_consent(uuid, boolean, boolean) to authenticated;
grant execute on function public.org_usage_summary(uuid, int)            to authenticated;
grant execute on function public.org_leaderboard(uuid, int)              to authenticated;

-- The rate-limit RPC must stay service-role only, for the same reason MER-30's
-- security-advisor pass locked down groq_check_rate_limit: a client that can call
-- it directly can tamper with another identity's counter.
revoke all on function public.groq_check_rate_limit_org(text, int, int, int, int, text) from public;
revoke execute on function public.groq_check_rate_limit_org(text, int, int, int, int, text) from anon, authenticated;
grant execute on function public.groq_check_rate_limit_org(text, int, int, int, int, text) to service_role;

-- ── daily series (IDI-216 Phase 5, added for the redesigned Team screen) ─────
--
-- org_usage_summary returns TOTALS, which is all a table needs. The Team screen's
-- roster sparklines and the per-member activity heatmap need the same numbers
-- broken down BY DAY, and doing that with N round trips (one per member) would be
-- silly — this is one call for the whole org.
--
-- Same privacy contract as org_usage_summary, and the same reason it is an RPC:
-- it reads `transcriptions.text` to COUNT words and returns only counts. There is
-- no column in the return type that could carry transcript content.
--
-- Visibility differs by role ON PURPOSE: an owner/admin gets every consented
-- member's series (that is the roster view), while a plain member gets ONLY their
-- own row — so a member can still see their own sparkline without the screen
-- becoming a way to read colleagues' activity.
create or replace function public.org_usage_series(p_org uuid, p_days int default 98)
returns table (
  user_id text,
  day     date,
  words   bigint
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  v_uid   text := auth.uid()::text;
  v_role  text := public.org_member_role(p_org);
  v_since timestamptz := now() - (greatest(1, least(coalesce(p_days, 98), 365)) || ' days')::interval;
begin
  if v_role is null then
    return;
  end if;
  return query
    select m.user_id,
           (tr.created_at at time zone 'UTC')::date as day,
           coalesce(sum(array_length(regexp_split_to_array(btrim(tr.text), '\s+'), 1)), 0)::bigint
      from public.organization_members m
      join public.transcriptions tr on tr.user_id = m.user_id
     where m.org_id = p_org
       and m.status = 'active'
       and m.usage_consent
       -- an admin sees every consenting member; anyone else sees only themselves
       and (v_role in ('owner', 'admin') or m.user_id = v_uid)
       and tr.created_at >= v_since
       and tr.deleted_at is null
       and btrim(coalesce(tr.text, '')) <> ''
     group by m.user_id, (tr.created_at at time zone 'UTC')::date
     order by m.user_id, day;
end;
$$;

revoke all     on function public.org_usage_series(uuid, int) from public;
revoke execute on function public.org_usage_series(uuid, int) from anon;
grant  execute on function public.org_usage_series(uuid, int) to authenticated;

-- ── Team-wide stats visibility (applied live 2026-08-25 as
--    `org_stats_visible_to_members`) ─────────────────────────────────────────
-- The owner can open the per-member stats to EVERY active member, not just
-- owner/admin ("either everyone can see each other's stats, or no" — user
-- request). A member's own usage_consent still gates whether THEY appear: the
-- org-wide switch widens the audience, never overrides an individual opt-out
-- (same contract as leaderboard_enabled vs leaderboard_opt_in). These three
-- CREATE OR REPLACEs supersede the earlier definitions above (this file is
-- append-ordered and idempotent — the last definition wins on a re-run).

alter table public.organizations
  add column if not exists stats_visible_to_members boolean not null default false;

create or replace function public.org_usage_summary(p_org uuid, p_days int default 30)
returns table (
  user_id text, email text, display_name text, role text,
  dictations bigint, words bigint, speech_ms bigint, last_active timestamptz
)
language plpgsql stable security definer set search_path = public as $$
declare
  v_uid   text := auth.uid()::text;
  v_role  text := public.org_member_role(p_org);
  v_all   boolean;
  v_since timestamptz := now() - (greatest(1, least(coalesce(p_days, 30), 365)) || ' days')::interval;
begin
  if v_role is null then return; end if;
  select o.stats_visible_to_members into v_all from public.organizations o where o.id = p_org;
  return query
    select m.user_id, m.email, m.display_name, m.role,
           coalesce(t.dictations, 0), coalesce(t.words, 0), coalesce(t.speech_ms, 0), t.last_active
      from public.organization_members m
      left join lateral (
        select count(*) as dictations,
               coalesce(sum(array_length(regexp_split_to_array(btrim(tr.text), '\s+'), 1)), 0) as words,
               coalesce(sum(coalesce(tr.duration_ms, 0)), 0)::bigint as speech_ms,
               max(tr.created_at) as last_active
          from public.transcriptions tr
         where tr.user_id = m.user_id and tr.created_at >= v_since
           and tr.deleted_at is null and btrim(coalesce(tr.text, '')) <> ''
      ) t on true
     where m.org_id = p_org and m.status = 'active'
       and (m.user_id = v_uid
            or ((v_role in ('owner','admin') or coalesce(v_all, false)) and m.usage_consent))
     order by coalesce(t.words, 0) desc;
end; $$;

create or replace function public.org_usage_series(p_org uuid, p_days int default 98)
returns table (user_id text, day date, words bigint)
language plpgsql stable security definer set search_path = public as $$
declare
  v_uid   text := auth.uid()::text;
  v_role  text := public.org_member_role(p_org);
  v_all   boolean;
  v_since timestamptz := now() - (greatest(1, least(coalesce(p_days, 98), 365)) || ' days')::interval;
begin
  if v_role is null then return; end if;
  select o.stats_visible_to_members into v_all from public.organizations o where o.id = p_org;
  return query
    select m.user_id, (tr.created_at at time zone 'UTC')::date as day,
           coalesce(sum(array_length(regexp_split_to_array(btrim(tr.text), '\s+'), 1)), 0)::bigint
      from public.organization_members m
      join public.transcriptions tr on tr.user_id = m.user_id
     where m.org_id = p_org and m.status = 'active' and m.usage_consent
       and (v_role in ('owner','admin') or m.user_id = v_uid or coalesce(v_all, false))
       and tr.created_at >= v_since and tr.deleted_at is null
       and btrim(coalesce(tr.text, '')) <> ''
     group by m.user_id, (tr.created_at at time zone 'UTC')::date
     order by m.user_id, day;
end; $$;

create or replace function public.org_app_breakdown(p_org uuid, p_days int default 30)
returns table (user_id text, display_name text, app text, dictations bigint, words bigint)
language plpgsql stable security definer set search_path = public as $$
declare
  v_role  text := public.org_member_role(p_org);
  v_uid   text := auth.uid()::text;
  v_all   boolean;
  v_since timestamptz := now() - (greatest(1, least(coalesce(p_days, 30), 365)) || ' days')::interval;
begin
  if v_role is null then return; end if;
  select o.stats_visible_to_members into v_all from public.organizations o where o.id = p_org;
  return query
    select m.user_id, m.display_name, tr.app, count(*)::bigint,
           coalesce(sum(array_length(regexp_split_to_array(btrim(tr.text), '\s+'), 1)), 0)::bigint
      from public.organization_members m
      join public.transcriptions tr on tr.user_id = m.user_id
     where m.org_id = p_org and m.status = 'active' and m.usage_consent
       and (v_role in ('owner','admin') or m.user_id = v_uid or coalesce(v_all, false))
       and tr.created_at >= v_since and tr.deleted_at is null
       and tr.app is not null and btrim(tr.app) <> ''
       and btrim(coalesce(tr.text, '')) <> ''
     group by m.user_id, m.display_name, tr.app
     order by m.user_id, count(*) desc;
end; $$;
