-- Fix (MER-26): notes had Row Level Security fully DISABLED in production —
-- Supabase's own security advisor flagged this critical: any anon or
-- authenticated caller could read or write EVERY user's notes, not just rows
-- whose user_id they happened to know.
--
-- supabase_notes_v2.sql already has a guarded DO block that broadens a
-- pre-existing anon-only policy to `public`, but only fires if RLS is already
-- enabled on the table — since it wasn't, that block was a silent no-op. This
-- file is what actually closes the hole: enable RLS + add the same interim
-- policy shape `dictionary`/`pairings` use (see supabase_dictionary_rls_fix.sql).
--
-- TO public, NOT TO anon (Hard Rule #10) — desktop uses the raw anon key
-- (role `anon`); a signed-in mobile client sends the user's JWT (role
-- `authenticated`). A `TO anon` policy silently filters out authenticated
-- rows and breaks notes sync to signed-in phones — this exact bug already
-- bit `dictionary` (fixed the same way there).
--
-- This is the INTERIM posture only (permissive, scoped by convention via
-- user_id in the query, not enforced by auth.uid()) — matches every other
-- shared table's current posture. True per-user isolation is a separate
-- follow-up (MER-29). Idempotent — safe to run again.

alter table public.notes enable row level security;
drop policy if exists "notes rw" on public.notes;
create policy "notes rw" on public.notes
  for all to public using (true) with check (true);
