-- issue_reports — in-app "Report an issue" feedback (beta launch, 2026-09).
-- One row per report from any platform (mac/win/ios/android). Written ONLY by
-- the `report-issue` Edge Function with the service role; read by the founder
-- via the Supabase dashboard/SQL. RLS is enabled with NO policies on purpose:
-- clients never touch this table directly (the groq_rate_limits precedent),
-- so the anon key can neither read other users' reports nor spam inserts
-- without at least passing the function's validation.

create table if not exists public.issue_reports (
  id uuid primary key default gen_random_uuid(),
  user_id text not null default '',      -- auth uid; '' when signed out
  email text not null default '',        -- reporter's account email, if signed in
  platform text not null default '',     -- mac | win | ios | android
  app_version text not null default '',
  message text not null,
  meta jsonb not null default '{}'::jsonb, -- {device_name?, os_version?}
  status text not null default 'new',    -- new | seen | resolved (manual triage)
  created_at timestamptz not null default now()
);

create index if not exists issue_reports_created_at_idx
  on public.issue_reports (created_at desc);

alter table public.issue_reports enable row level security;
-- No policies: service-role-only access, fail closed for every client role.
