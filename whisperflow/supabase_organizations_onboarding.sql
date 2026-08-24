-- Team onboarding layer — IDI-218 / 219 / 220 / 221 / 222 / 223.
-- Layers on `supabase_organizations.sql` (IDI-216). Idempotent; safe to re-run.
--
-- APPLIED LIVE 2026-08-20 as four migrations, in this order:
--   org_onboarding_idi218_223_schema
--   org_onboarding_idi218_223_rpcs
--   org_backfill_domain_classification
--   fix_org_set_auto_join_null_role_guard
--
-- WHAT CHANGED FROM THE IDI-216 BEHAVIOUR — three of these are reversals, not
-- additions, so read them before touching the claim path:
--
--  1. THE TOKEN IS THE SOURCE OF TRUTH, NOT THE EMAIL STRING (IDI-223 #2).
--     "Sign in with Apple" returns proxy…@privaterelay.appleid.com for someone
--     invited as jane@company.com. Under IDI-216's strict equality that person
--     could never join. So a mismatch is now a CONFIRMATION, not a refusal: the
--     first call returns `email_mismatch` carrying BOTH addresses so the UI can
--     ask "you're signed in as X, the invite went to Y — switch, or continue?",
--     and only an explicit p_confirm_mismatch := true proceeds. Nothing is ever
--     silently attached to the wrong account, which is what IDI-223 #1 actually
--     requires.
--  2. SEATS ARE CONSUMED AT ACCEPTANCE, NEVER AT DISPATCH (IDI-219). Pending
--     invites lock nothing — that is the fix for the seat-allocation deadlock in
--     IDI-223 #3, where an admin with 5 seats and 5 unaccepted invites could not
--     invite anyone else.
--  3. A DUPLICATE INVITE UPDATES THE EXISTING ROW (IDI-220). IDI-216 revoked and
--     re-inserted, which bloats the table. The partial unique index below makes
--     the new behaviour enforceable rather than merely intended.

-- ── IDI-219: seats ───────────────────────────────────────────────────────────
do $$
begin
  if exists (select 1 from information_schema.columns
              where table_schema='public' and table_name='organizations' and column_name='seats')
     and not exists (select 1 from information_schema.columns
              where table_schema='public' and table_name='organizations' and column_name='purchased_seats')
  then
    alter table public.organizations rename column seats to purchased_seats;
  end if;
end $$;

alter table public.organizations add column if not exists purchased_seats int not null default 5;

-- `active_members` is COMPUTED, never stored (IDI-219 left the choice open). A
-- stored counter drifts the moment one path forgets to decrement, and its failure
-- mode is OVER-provisioning — exactly what the fail-closed table forbids.
create or replace function public.org_active_members(p_org uuid)
returns int language sql stable security definer set search_path = public as $$
  select count(*)::int from public.organization_members
   where org_id = p_org and status = 'active'
$$;

-- ── IDI-218: domain rules ────────────────────────────────────────────────────
alter table public.organizations
  add column if not exists domain            text,
  add column if not exists is_generic_domain boolean not null default true,
  add column if not exists auto_join_enabled boolean not null default false;

-- A TABLE, not a hardcoded list: adding a consumer domain must not need a migration.
create table if not exists public.generic_email_domains (domain text primary key);

insert into public.generic_email_domains (domain) values
  ('gmail.com'), ('googlemail.com'), ('outlook.com'), ('hotmail.com'), ('live.com'),
  ('msn.com'), ('yahoo.com'), ('yahoo.co.uk'), ('ymail.com'), ('icloud.com'),
  ('me.com'), ('mac.com'), ('proton.me'), ('protonmail.com'), ('pm.me'),
  ('aol.com'), ('gmx.com'), ('gmx.de'), ('mail.com'), ('zoho.com'),
  ('yandex.com'), ('yandex.ru'), ('fastmail.com'), ('tutanota.com'), ('tuta.io'),
  ('hey.com'), ('duck.com'), ('privaterelay.appleid.com')
on conflict (domain) do nothing;

alter table public.generic_email_domains enable row level security;  -- no policies

create or replace function public.is_generic_email_domain(p_email text)
returns boolean language sql stable security definer set search_path = public as $$
  -- Fail-closed: an unparseable address is GENERIC, which forces invite-only.
  select case
    when p_email is null or position('@' in p_email) = 0 then true
    else exists (select 1 from public.generic_email_domains g
                  where g.domain = lower(split_part(p_email, '@', 2)))
  end
$$;

-- ── status lifecycles (IDI-221 decline, IDI-223 expiry, IDI-218 join requests) ─
alter table public.organization_invites drop constraint if exists organization_invites_status_check;
alter table public.organization_invites add constraint organization_invites_status_check
  check (status in ('pending', 'claimed', 'expired', 'revoked', 'rejected'));

-- 'requested' is a domain-discovery join request. It is NOT 'active', so it neither
-- collides with the one-active-org index nor consumes a seat.
alter table public.organization_members drop constraint if exists organization_members_status_check;
alter table public.organization_members add constraint organization_members_status_check
  check (status in ('active', 'invited', 'requested', 'removed'));

-- ── IDI-220: exactly one pending invite per (org, email) ─────────────────────
create unique index if not exists organization_invites_one_pending
  on public.organization_invites (org_id, lower(email)) where status = 'pending';

-- ── IDI-223 #3: soft expiry so pending invites never deadlock an admin ───────
create or replace function public.org_expire_invites()
returns int language sql security definer set search_path = public as $$
  with e as (
    update public.organization_invites set status = 'expired'
     where status = 'pending' and expires_at <= now()
    returning 1
  ) select count(*)::int from e
$$;

-- ── BACKFILL (one-shot, kept for reproducibility) ────────────────────────────
-- Orgs created before the IDI-218 columns took the DEFAULTS (generic = true,
-- domain = null). For a corporate owner that is wrong and is NOT self-correcting:
-- org_set_auto_join would refuse forever on a domain that isn't actually generic.
update public.organizations o
   set is_generic_domain = public.is_generic_email_domain(u.email),
       domain = case when public.is_generic_email_domain(u.email) then null
                     else lower(split_part(u.email, '@', 2)) end
  from auth.users u
 where u.id::text = o.owner_user_id and o.domain is null;

-- ── RPCs ─────────────────────────────────────────────────────────────────────
-- NOTE the guard shape in every one of these:
--     if v_role is null or v_role not in ('owner','admin')
-- The `is null` half is LOAD-BEARING. org_member_role() returns NULL for a
-- non-member, and `NULL not in (...)` evaluates to NULL — not true — so a bare
-- NOT IN never fires and execution falls straight through to the write. That
-- exact bug shipped in the first cut of org_set_auto_join and let any
-- authenticated caller who knew an org id flip auto_join_enabled on it. Caught by
-- the live role-gating test, fixed in fix_org_set_auto_join_null_role_guard.

-- org_create now records the domain + generic classification.
create or replace function public.org_create(p_name text, p_company text default '')
returns public.organizations language plpgsql security definer set search_path = public as $$
declare
  v_uid text := auth.uid()::text; v_email text; v_org public.organizations;
  v_name text := nullif(btrim(coalesce(p_name, '')), ''); v_domain text; v_generic boolean;
begin
  if v_uid is null then raise exception 'not_authenticated' using errcode = '28000'; end if;
  if v_name is null then raise exception 'name_required'    using errcode = '22023'; end if;
  if exists (select 1 from public.organization_members
              where user_id = v_uid and status = 'active') then
    raise exception 'already_in_org' using errcode = '23505';
  end if;
  select email into v_email from auth.users where id = auth.uid();
  v_generic := public.is_generic_email_domain(v_email);
  -- A generic domain records NO domain: storing 'gmail.com' invites a future bug
  -- where someone enables discovery on it.
  v_domain := case when v_generic then null
                   else lower(split_part(coalesce(v_email,''), '@', 2)) end;
  insert into public.organizations
    (name, company_name, owner_user_id, domain, is_generic_domain, auto_join_enabled)
  values (left(v_name, 80), left(btrim(coalesce(p_company, '')), 120), v_uid,
          v_domain, v_generic, false)
  returning * into v_org;
  insert into public.organization_members (org_id, user_id, email, display_name, role, status)
  values (v_org.id, v_uid, coalesce(v_email, ''),
          coalesce((select raw_user_meta_data ->> 'full_name' from auth.users where id = auth.uid()), ''),
          'owner', 'active');
  insert into public.organization_dictionary (org_id, updated_by) values (v_org.id, v_uid)
  on conflict (org_id) do nothing;
  return v_org;
end;
$$;

create or replace function public.org_set_auto_join(p_org uuid, p_enabled boolean)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_role text := public.org_member_role(p_org); v_generic boolean;
begin
  if v_role is null or v_role not in ('owner', 'admin') then
    return jsonb_build_object('ok', false, 'error', 'forbidden');
  end if;
  select is_generic_domain into v_generic from public.organizations where id = p_org;
  if v_generic is null then return jsonb_build_object('ok', false, 'error', 'no_such_org'); end if;
  -- Rejected at the DB, not merely hidden in the UI: a shared consumer domain must
  -- never become a discovery surface for strangers.
  if coalesce(p_enabled, false) and v_generic then
    return jsonb_build_object('ok', false, 'error', 'generic_domain');
  end if;
  update public.organizations
     set auto_join_enabled = coalesce(p_enabled, false), updated_at = now() where id = p_org;
  return jsonb_build_object('ok', true);
end;
$$;

-- Token-gated preview so the claim page can render BEFORE the recipient signs in.
-- Same posture as pairing_status: minimal fields, never exposes a user_id. This is
-- the one org function `anon` may call.
create or replace function public.org_invite_preview(p_token text)
returns jsonb language plpgsql stable security definer set search_path = public as $$
declare v_inv public.organization_invites; v_org public.organizations; v_by text;
begin
  select * into v_inv from public.organization_invites
   where token_hash = encode(sha256(convert_to(coalesce(p_token, ''), 'utf8')), 'hex');
  if not found then return jsonb_build_object('ok', false, 'error', 'invalid_token'); end if;
  if v_inv.status <> 'pending' then
    return jsonb_build_object('ok', false, 'error',
      case when v_inv.status = 'claimed' then 'already_used' else v_inv.status end);
  end if;
  if v_inv.expires_at <= now() then return jsonb_build_object('ok', false, 'error', 'expired'); end if;
  select * into v_org from public.organizations where id = v_inv.org_id;
  select coalesce(display_name, email) into v_by from public.organization_members
   where org_id = v_inv.org_id and user_id = v_inv.invited_by;
  return jsonb_build_object('ok', true, 'org_name', v_org.name,
    'company_name', v_org.company_name, 'invited_email', v_inv.email, 'role', v_inv.role,
    'invited_by', coalesce(v_by, ''), 'expires_at', v_inv.expires_at,
    'members', public.org_active_members(v_inv.org_id),
    'seats_left', greatest(0, v_org.purchased_seats - public.org_active_members(v_inv.org_id)));
end;
$$;

-- See the header for why the signature changed. The old single-arg version is
-- DROPPED rather than overloaded — a defaulted second arg would make a one-arg
-- call ambiguous.
drop function if exists public.org_claim_invite(text);

create or replace function public.org_claim_invite(p_token text, p_confirm_mismatch boolean default false)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_uid text := auth.uid()::text; v_email text; v_inv public.organization_invites;
  v_seats int; v_used int;
begin
  if v_uid is null then return jsonb_build_object('ok', false, 'error', 'not_authenticated'); end if;
  select email into v_email from auth.users where id = auth.uid();
  perform public.org_expire_invites();
  select * into v_inv from public.organization_invites
   where token_hash = encode(sha256(convert_to(coalesce(p_token, ''), 'utf8')), 'hex') for update;
  if not found then return jsonb_build_object('ok', false, 'error', 'invalid_token'); end if;
  -- Idempotent: re-claiming an invite this same user already used is a no-op, and
  -- cannot double-count a seat.
  if v_inv.status = 'claimed' and v_inv.claimed_by = v_uid then
    return jsonb_build_object('ok', true, 'org_id', v_inv.org_id, 'role', v_inv.role, 'already', true);
  end if;
  if v_inv.status <> 'pending' then
    return jsonb_build_object('ok', false, 'error',
      case when v_inv.status = 'claimed' then 'already_used' else v_inv.status end);
  end if;
  if v_inv.expires_at <= now() then
    update public.organization_invites set status = 'expired' where id = v_inv.id;
    return jsonb_build_object('ok', false, 'error', 'expired');
  end if;
  if exists (select 1 from public.organization_members
              where user_id = v_uid and status = 'active' and org_id <> v_inv.org_id) then
    return jsonb_build_object('ok', false, 'error', 'already_in_org');
  end if;
  if lower(coalesce(v_email, '')) <> lower(v_inv.email) and not coalesce(p_confirm_mismatch, false) then
    return jsonb_build_object('ok', false, 'error', 'email_mismatch',
                              'invited_email', v_inv.email, 'current_email', coalesce(v_email, ''));
  end if;
  select purchased_seats into v_seats from public.organizations where id = v_inv.org_id;
  v_used := public.org_active_members(v_inv.org_id);
  if v_used >= coalesce(v_seats, 0) then
    -- Invite deliberately STAYS pending so the admin can add a seat and the same
    -- link still works.
    return jsonb_build_object('ok', false, 'error', 'no_seats',
                              'purchased_seats', v_seats, 'active_members', v_used);
  end if;
  insert into public.organization_members (org_id, user_id, email, display_name, role, status)
  values (v_inv.org_id, v_uid, coalesce(v_email, ''),
          coalesce((select raw_user_meta_data ->> 'full_name' from auth.users where id = auth.uid()), ''),
          v_inv.role, 'active')
  on conflict (org_id, user_id) do update
    set status = 'active', role = excluded.role, email = excluded.email, updated_at = now();
  update public.organization_invites
     set status = 'claimed', claimed_by = v_uid, claimed_at = now() where id = v_inv.id;
  return jsonb_build_object('ok', true, 'org_id', v_inv.org_id, 'role', v_inv.role);
end;
$$;

create or replace function public.org_decline_invite(p_token text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_inv public.organization_invites;
begin
  if auth.uid() is null then return jsonb_build_object('ok', false, 'error', 'not_authenticated'); end if;
  update public.organization_invites set status = 'rejected'
   where token_hash = encode(sha256(convert_to(coalesce(p_token, ''), 'utf8')), 'hex')
     and status = 'pending'
  returning * into v_inv;
  if not found then return jsonb_build_object('ok', false, 'error', 'invalid_token'); end if;
  return jsonb_build_object('ok', true);
end;
$$;

-- IDI-222 fallback: when a deep link is eaten by an in-app browser and the person
-- installs manually, this recovers the invite after sign-in. Matches on the
-- SESSION's own email, so it can only return invites addressed to the caller, and
-- it returns NO token.
create or replace function public.org_pending_invites_for_me()
returns jsonb language plpgsql stable security definer set search_path = public as $$
declare v_email text; v_rows jsonb;
begin
  if auth.uid() is null then return jsonb_build_object('ok', true, 'invites', '[]'::jsonb); end if;
  select email into v_email from auth.users where id = auth.uid();
  if coalesce(v_email, '') = '' then return jsonb_build_object('ok', true, 'invites', '[]'::jsonb); end if;
  select coalesce(jsonb_agg(jsonb_build_object(
           'org_id', i.org_id, 'org_name', o.name, 'role', i.role, 'expires_at', i.expires_at)), '[]'::jsonb)
    into v_rows
    from public.organization_invites i join public.organizations o on o.id = i.org_id
   where lower(i.email) = lower(v_email) and i.status = 'pending' and i.expires_at > now();
  return jsonb_build_object('ok', true, 'invites', v_rows);
end;
$$;

-- Accepts an invite discovered by the lookup above. The email matched by
-- construction, so the mismatch prompt cannot apply here.
create or replace function public.org_accept_pending_invite(p_org uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_email text; v_tok text;
begin
  if auth.uid() is null then return jsonb_build_object('ok', false, 'error', 'not_authenticated'); end if;
  select email into v_email from auth.users where id = auth.uid();
  select token_hash into v_tok from public.organization_invites
   where org_id = p_org and lower(email) = lower(coalesce(v_email, ''))
     and status = 'pending' and expires_at > now() limit 1;
  if v_tok is null then return jsonb_build_object('ok', false, 'error', 'invalid_token'); end if;
  return public.org_claim_invite_by_hash(v_tok, true);
end;
$$;

-- Claim body addressed by HASH, so the email-lookup path needs no raw token it was
-- never given. Reachable only through org_accept_pending_invite (a SECURITY DEFINER
-- caller), never directly — otherwise a client could claim by guessing a hash.
create or replace function public.org_claim_invite_by_hash(p_hash text, p_confirm_mismatch boolean default false)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_uid text := auth.uid()::text; v_email text; v_inv public.organization_invites;
  v_seats int; v_used int;
begin
  if v_uid is null then return jsonb_build_object('ok', false, 'error', 'not_authenticated'); end if;
  select email into v_email from auth.users where id = auth.uid();
  select * into v_inv from public.organization_invites where token_hash = p_hash for update;
  if not found then return jsonb_build_object('ok', false, 'error', 'invalid_token'); end if;
  if v_inv.status = 'claimed' and v_inv.claimed_by = v_uid then
    return jsonb_build_object('ok', true, 'org_id', v_inv.org_id, 'role', v_inv.role, 'already', true);
  end if;
  if v_inv.status <> 'pending' then
    return jsonb_build_object('ok', false, 'error',
      case when v_inv.status = 'claimed' then 'already_used' else v_inv.status end);
  end if;
  if v_inv.expires_at <= now() then
    update public.organization_invites set status='expired' where id=v_inv.id;
    return jsonb_build_object('ok', false, 'error', 'expired');
  end if;
  if exists (select 1 from public.organization_members
              where user_id=v_uid and status='active' and org_id <> v_inv.org_id) then
    return jsonb_build_object('ok', false, 'error', 'already_in_org');
  end if;
  if lower(coalesce(v_email,'')) <> lower(v_inv.email) and not coalesce(p_confirm_mismatch,false) then
    return jsonb_build_object('ok', false, 'error', 'email_mismatch',
                              'invited_email', v_inv.email, 'current_email', coalesce(v_email,''));
  end if;
  select purchased_seats into v_seats from public.organizations where id = v_inv.org_id;
  v_used := public.org_active_members(v_inv.org_id);
  if v_used >= coalesce(v_seats,0) then
    return jsonb_build_object('ok', false, 'error', 'no_seats',
                              'purchased_seats', v_seats, 'active_members', v_used);
  end if;
  insert into public.organization_members (org_id, user_id, email, display_name, role, status)
  values (v_inv.org_id, v_uid, coalesce(v_email,''),
          coalesce((select raw_user_meta_data ->> 'full_name' from auth.users where id = auth.uid()), ''),
          v_inv.role, 'active')
  on conflict (org_id, user_id) do update
    set status='active', role=excluded.role, email=excluded.email, updated_at=now();
  update public.organization_invites
     set status='claimed', claimed_by=v_uid, claimed_at=now() where id=v_inv.id;
  return jsonb_build_object('ok', true, 'org_id', v_inv.org_id, 'role', v_inv.role);
end;
$$;

-- ── grants ───────────────────────────────────────────────────────────────────
revoke all on function public.org_expire_invites()                      from public;
revoke all on function public.org_active_members(uuid)                  from public;
revoke all on function public.is_generic_email_domain(text)             from public;
revoke all on function public.org_create(text, text)                    from public;
revoke all on function public.org_set_auto_join(uuid, boolean)          from public;
revoke all on function public.org_invite_preview(text)                  from public;
revoke all on function public.org_claim_invite(text, boolean)           from public;
revoke all on function public.org_claim_invite_by_hash(text, boolean)   from public;
revoke all on function public.org_decline_invite(text)                  from public;
revoke all on function public.org_pending_invites_for_me()              from public;
revoke all on function public.org_accept_pending_invite(uuid)           from public;

-- Revoke from `anon` BY NAME. `revoke … from public` hits only the PUBLIC
-- pseudo-role and does NOT undo Supabase's ALTER DEFAULT PRIVILEGES grant of
-- EXECUTE to anon on new functions in `public` (learned the hard way in IDI-216).
revoke execute on function public.org_expire_invites()                    from anon, authenticated;
revoke execute on function public.org_active_members(uuid)                from anon;
revoke execute on function public.is_generic_email_domain(text)           from anon;
revoke execute on function public.org_set_auto_join(uuid, boolean)        from anon;
revoke execute on function public.org_claim_invite(text, boolean)         from anon;
revoke execute on function public.org_decline_invite(text)                from anon;
revoke execute on function public.org_pending_invites_for_me()            from anon;
revoke execute on function public.org_accept_pending_invite(uuid)         from anon;
revoke execute on function public.org_claim_invite_by_hash(text, boolean) from anon, authenticated;

grant execute on function public.org_expire_invites()                    to service_role;
grant execute on function public.org_claim_invite_by_hash(text, boolean) to service_role;
grant execute on function public.org_active_members(uuid)                to authenticated, service_role;
grant execute on function public.is_generic_email_domain(text)           to authenticated, service_role;
grant execute on function public.org_create(text, text)                  to authenticated;
grant execute on function public.org_set_auto_join(uuid, boolean)        to authenticated;
grant execute on function public.org_claim_invite(text, boolean)         to authenticated;
grant execute on function public.org_decline_invite(text)                to authenticated;
grant execute on function public.org_pending_invites_for_me()            to authenticated;
grant execute on function public.org_accept_pending_invite(uuid)         to authenticated;

-- The claim page must render before the recipient authenticates.
grant execute on function public.org_invite_preview(text)                to anon, authenticated;


-- ═══════════════════════════════════════════════════════════════════════════
-- Migration: transcriptions_app_and_org_breakdown  (applied 2026-08-21)
--
-- "Which app is each person actually using Flume in?" — the question a team
-- admin asks first and the one we could not answer, because the only per-app
-- data we had lived in `config['stats_daily'].apps` on each user's own machine.
-- This records the frontmost app alongside the dictation so the team view can
-- aggregate it.
--
-- PRIVACY: this WIDENS what an admin can see. Everything else in the team layer
-- is counts and durations; an app name is neither. It is still metadata — never
-- the text, never the audio — but the product copy on the Team screen had to
-- change from "only counts and durations" to name it explicitly, and the same
-- `usage_consent` switch hides it. A member who turns sharing off disappears
-- from this RPC entirely, exactly as they do from org_usage_series.
--
-- NOT BACKFILLABLE: every row written before this shipped has app = NULL and
-- there is nowhere to recover it from. The client must say so rather than
-- rendering an empty panel that reads as a bug.
-- ═══════════════════════════════════════════════════════════════════════════

alter table public.transcriptions add column if not exists app text;

-- Partial: the vast majority of historic rows are NULL and indexing them buys
-- nothing. Ordered (user_id, app) because every read groups by member first.
create index if not exists transcriptions_user_app_idx
  on public.transcriptions using btree (user_id, app)
  where app is not null;

create or replace function public.org_app_breakdown(p_org uuid, p_days int default 30)
returns table (user_id text, display_name text, app text, dictations bigint, words bigint)
language plpgsql stable security definer set search_path to 'public' as $function$
declare
  v_role  text := public.org_member_role(p_org);
  v_uid   text := auth.uid()::text;
  v_since timestamptz := now() - (greatest(1, least(coalesce(p_days, 30), 365)) || ' days')::interval;
begin
  -- if v_role is null then return
  -- The `is null` check is LOAD-BEARING and must come first. org_member_role()
  -- returns NULL for a non-member, and a guard written as
  -- `v_role not in ('owner','admin')` evaluates to NULL — not true — so a
  -- stranger walks straight through it. That exact bug shipped once in
  -- org_set_auto_join; every role guard in this file keeps this shape.
  if v_role is null then
    return;
  end if;
  return query
    select m.user_id, m.display_name, tr.app,
           count(*)::bigint,
           coalesce(sum(array_length(regexp_split_to_array(btrim(tr.text), '\s+'), 1)), 0)::bigint
      from public.organization_members m
      join public.transcriptions tr on tr.user_id = m.user_id
     where m.org_id = p_org
       and m.status = 'active'
       -- usage_consent gates this for EVERYONE, including a member asking about
       -- themselves. Turning sharing off empties the panel rather than leaving a
       -- private-looking row that is in fact still being aggregated.
       and m.usage_consent
       -- Same role split as org_usage_series: an admin sees every consenting
       -- member, anyone else sees only themselves.
       and (v_role in ('owner', 'admin') or m.user_id = v_uid)
       and tr.created_at >= v_since
       and tr.deleted_at is null
       and tr.app is not null
       and btrim(tr.app) <> ''
       and btrim(coalesce(tr.text, '')) <> ''
     group by m.user_id, m.display_name, tr.app
     order by m.user_id, count(*) desc;
end;
$function$;

revoke all on function public.org_app_breakdown(uuid, int) from public;
revoke all on function public.org_app_breakdown(uuid, int) from anon;
grant execute on function public.org_app_breakdown(uuid, int) to authenticated;


-- ═══════════════════════════════════════════════════════════════════════════
-- Migration: org_usage_summary_own_row_for_members  (applied 2026-08-21)
--
-- org_usage_summary was the ONE team RPC that returned nothing at all to a plain
-- member, while org_usage_series and org_app_breakdown both already returned the
-- caller's own row ("an admin sees every consenting member, anyone else sees only
-- themselves"). Every total on the Team overview is computed from these rows, so
-- a member's screen rendered zeroes across the board — and then explained them
-- with "usage appears here as people turn sharing on", which was false: everyone
-- WAS sharing. That is the "team insights are always empty" report.
--
-- This makes the role split identical to its two siblings. It does NOT widen what
-- a member can see about anyone else: the added branch is `m.user_id = v_uid`, so
-- a member gets exactly one row, their own, and `usage_consent` still gates it.
-- The clients had a matching gate on the REQUEST (Python `role not in (...)`, JS
-- `if(teamAdmin())`), removed in the same change — fixing only one layer would
-- have changed nothing on screen.
-- ═══════════════════════════════════════════════════════════════════════════

create or replace function public.org_usage_summary(p_org uuid, p_days int default 30)
returns table (user_id text, email text, display_name text, role text,
               dictations bigint, words bigint, speech_ms bigint, last_active timestamptz)
language plpgsql stable security definer set search_path to 'public' as $function$
declare
  v_uid   text := auth.uid()::text;
  v_role  text := public.org_member_role(p_org);
  v_since timestamptz := now() - (greatest(1, least(coalesce(p_days, 30), 365)) || ' days')::interval;
begin
  -- `is null` first and on its own: org_member_role() returns NULL for a
  -- non-member and `NULL not in (...)` is NULL, not true, so a guard that skips
  -- this check lets a stranger through (the org_set_auto_join bug).
  if v_role is null then
    return;
  end if;
  return query
    select m.user_id, m.email, m.display_name, m.role,
           coalesce(t.dictations, 0), coalesce(t.words, 0), coalesce(t.speech_ms, 0), t.last_active
      from public.organization_members m
      left join lateral (
        select count(*)                                                                        as dictations,
               coalesce(sum(array_length(regexp_split_to_array(btrim(tr.text), '\s+'), 1)), 0) as words,
               coalesce(sum(coalesce(tr.duration_ms, 0)), 0)::bigint                           as speech_ms,
               max(tr.created_at)                                                              as last_active
          from public.transcriptions tr
         where tr.user_id = m.user_id
           and tr.created_at >= v_since
           and tr.deleted_at is null
           and btrim(coalesce(tr.text, '')) <> ''
      ) t on true
     where m.org_id = p_org
       and m.status = 'active'
       and m.usage_consent
       -- Same split as org_usage_series / org_app_breakdown.
       and (v_role in ('owner', 'admin') or m.user_id = v_uid)
     order by coalesce(t.words, 0) desc;
end;
$function$;

revoke all on function public.org_usage_summary(uuid, int) from public;
revoke all on function public.org_usage_summary(uuid, int) from anon;
grant execute on function public.org_usage_summary(uuid, int) to authenticated;
