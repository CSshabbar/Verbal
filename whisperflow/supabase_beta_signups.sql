-- beta_signups — public beta signup form (idiaz.io/flume/beta.html, 2026-09).
-- One row per person who filled the form. Written ONLY by the `beta-signup`
-- Edge Function with the service role; read by the founder via SQL/dashboard.
-- RLS is enabled with NO policies on purpose (the issue_reports precedent):
-- clients never touch this table directly, so the anon key can neither read
-- the tester list nor insert rows without passing the function's validation.
--
-- Funnel joins: beta_signups.email → auth.users.email answers "did they
-- install and create an account", and from there the usage tables answer
-- "are they active".

create table if not exists public.beta_signups (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  email text not null,                     -- stored lowercased by the function
  platform_hint text not null default '',  -- mac | win | ios | android | '' (visitor UA at signup)
  ip_hash text not null default '',        -- sha-256 hex of caller IP — rate limiting only, never the raw IP
  status text not null default 'new',      -- new | active | churned (manual triage)
  welcome_emailed boolean not null default false,
  founder_notified boolean not null default false,
  -- Duplicate submits RE-SEND the welcome (migration beta_signups_welcome_resend_tracking,
  -- 2026-09-04): a silent duplicate looked like "the email never sent". Caps: at most
  -- 5 sends per row, minimum 15 minutes apart — enforced by the function via these two.
  welcome_sends int not null default 0,
  last_welcome_at timestamptz,
  created_at timestamptz not null default now()
);

-- One row per person: the function lowercases email before insert (so a plain
-- column index is enough — PostgREST's on_conflict can't target an expression
-- index) and treats a conflict as "already signed up" — idempotent success,
-- no duplicate founder email.
create unique index if not exists beta_signups_email_uidx
  on public.beta_signups (email);

create index if not exists beta_signups_created_at_idx
  on public.beta_signups (created_at desc);

-- Rate limiting: the function counts recent rows per ip_hash before inserting.
create index if not exists beta_signups_ip_hash_created_idx
  on public.beta_signups (ip_hash, created_at desc);

alter table public.beta_signups enable row level security;
-- No policies: service-role-only access, fail closed for every client role.
