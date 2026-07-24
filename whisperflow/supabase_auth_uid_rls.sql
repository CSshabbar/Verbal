-- MER-29: tighten shared-table RLS from permissive `USING (true)` to real
-- per-user enforcement via `auth.uid()`.
--
-- ⚠️ NOT YET APPLIED TO PRODUCTION. This file is committed so the exact,
-- tested migration is ready to run — but it is intentionally NOT wired into
-- any auto-apply path, and was NOT run against the live project during
-- MER-29. It was verified correct live (2026-07) inside a transaction that
-- applied the `notes` policy above, inserted two disposable rows for two
-- fake users, and confirmed with simulated JWT claims: user A saw only its
-- own row and its attempt to overwrite user B's row affected 0 rows; user B
-- saw only its own row, unmodified; a plain `anon`-role request (no JWT —
-- i.e. today's real anon-key-only clients) saw ZERO rows, confirming the
-- `TO authenticated` scoping works as intended — then ROLLBACK, so
-- production's actual policy was never changed (re-verified after: `notes
-- rw` / `{public}` / `USING(true)` unchanged, 0 leftover test rows). See
-- context/04-data-model.md §Security posture and the MER-29 Linear comment
-- for why applying this for real is being held back:
--
--   1. Device pairing (`pairing.ts::claimPairing` / `app/pairing.py`) lets a
--      second device adopt the host's `user_id` WITHOUT ever creating its own
--      Supabase Auth session — it has no JWT at all, only the anon key. Every
--      policy below is `TO authenticated`, so a paired-but-never-signed-in
--      device would lose ALL cloud access (transcriptions, notes, dictionary,
--      canvas, devices, meetings) the instant this is applied. This is a
--      product decision, not just an engineering rollout question: either
--      accept that paired devices go local-only until they also sign in with
--      Google, or redesign pairing to mint the joining device a real session
--      for the host's account (not implemented anywhere today).
--   2. Desktop's REST/Realtime calls now forward the signed-in user's JWT
--      when available (MER-29, `app/auth.py::auth_header`/`get_access_token`),
--      falling back to the anon key otherwise — but that fallback is exactly
--      what makes today's anon-key-only *currently-installed* app builds keep
--      working. Applying this migration before those builds have actually
--      reached users would 401 every currently-running desktop app's sync
--      until it updates — a real outage, not a soft degrade.
--
-- Apply only once both of the above are resolved (see the Linear comment).

-- notes
drop policy if exists "notes rw" on public.notes;
create policy "notes owner" on public.notes
  for all to authenticated
  using (user_id = auth.uid()::text) with check (user_id = auth.uid()::text);

-- transcriptions
drop policy if exists "Users access own transcriptions" on public.transcriptions;
create policy "transcriptions owner" on public.transcriptions
  for all to authenticated
  using (user_id = auth.uid()::text) with check (user_id = auth.uid()::text);

-- devices
drop policy if exists "Users access own devices" on public.devices;
create policy "devices owner" on public.devices
  for all to authenticated
  using (user_id = auth.uid()::text) with check (user_id = auth.uid()::text);

-- canvas
drop policy if exists "Users access own canvas" on public.canvas;
create policy "canvas owner" on public.canvas
  for all to authenticated
  using (user_id = auth.uid()::text) with check (user_id = auth.uid()::text);

-- dictionary
drop policy if exists "dictionary rw" on public.dictionary;
create policy "dictionary owner" on public.dictionary
  for all to authenticated
  using (user_id = auth.uid()::text) with check (user_id = auth.uid()::text);

-- meetings
drop policy if exists "meetings rw" on public.meetings;
create policy "meetings owner" on public.meetings
  for all to authenticated
  using (user_id = auth.uid()::text) with check (user_id = auth.uid()::text);

-- pairings: deliberately UNCHANGED — the claiming device isn't signed in as
-- the host yet, so `user_id = auth.uid()` cannot apply to its own rows.
-- Kept on the existing safe model (random token, ~2 min TTL, single-use
-- claim), per the ticket's own guidance. See supabase_pairings.sql.

-- push_tokens / device_presence: NOT included — out of this ticket's listed
-- scope (acceptance criteria names transcriptions/notes/dictionary/canvas/
-- devices/meetings only). push_tokens has the same USING(true) pattern and
-- is a reasonable follow-up once the two blockers above are resolved.
