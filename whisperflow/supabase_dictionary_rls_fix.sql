-- Fix: dictionary (vocabulary / replacements / snippets) not syncing to a
-- SIGNED-IN device.
--
-- The original policy "dictionary anon rw" was scoped `TO anon`. The desktop app
-- talks to Supabase with the raw anon key (role = anon), so it matched and synced
-- fine. But the mobile Supabase SDK, once the user signs in, sends the user's
-- authenticated JWT (role = authenticated) — which the `TO anon` policy does NOT
-- match, so RLS filtered the row out and the signed-in phone saw an empty
-- dictionary even though the data was in the cloud.
--
-- Broaden the policy to `public` (covers both anon and authenticated), matching
-- the app's pragmatic user_id-scoped model (see context/04-data-model.md §Security).
-- Idempotent — safe to run once in the Supabase SQL editor.

alter table public.dictionary enable row level security;
drop policy if exists "dictionary anon rw" on public.dictionary;
drop policy if exists "dictionary rw" on public.dictionary;
create policy "dictionary rw" on public.dictionary
  for all to public using (true) with check (true);

-- NOTE: public.pairings has the same `TO anon` pattern (supabase_pairings.sql). If
-- device pairing ever fails from a signed-in device, apply the identical broadening
-- there. Not changed here since pairing currently works for the reported flow.
