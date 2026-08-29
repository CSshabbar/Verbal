-- MER-29: tighten shared-table RLS from permissive `USING (true)` to real
-- per-user enforcement via `auth.uid()`.
--
-- ⚠️ READY TO APPLY — both original blockers were cleared by IDI-29 (see the
-- "Cutover" section at the bottom of this header). Still NOT wired into any
-- auto-apply path: run it by hand, in a transaction, against staging first.
--
-- It was verified correct live (2026-07) inside a transaction that
-- applied the `notes` policy above, inserted two disposable rows for two
-- fake users, and confirmed with simulated JWT claims: user A saw only its
-- own row and its attempt to overwrite user B's row affected 0 rows; user B
-- saw only its own row, unmodified; a plain `anon`-role request (no JWT —
-- i.e. today's real anon-key-only clients) saw ZERO rows, confirming the
-- `TO authenticated` scoping works as intended — then ROLLBACK, so
-- production's actual policy was never changed (re-verified after: `notes
-- rw` / `{public}` / `USING(true)` unchanged, 0 leftover test rows).
--
-- ── Why this was held back, and why it no longer is ────────────────────────
--
--   1. PAIRING (was: product decision). Device pairing let a second device
--      adopt the host's `user_id` WITHOUT ever creating its own Supabase Auth
--      session — no JWT, only the anon key. Every policy below is `TO
--      authenticated`, so such a device would lose ALL cloud access the
--      instant this applied.
--      RESOLVED: the override is retired. `claimPairing` now REQUIRES the
--      scanning device to already hold a session for the host's account and
--      refuses the claim with an actionable message otherwise
--      (`verbal-mobile/lib/pairing.ts`); `getCloudUserId()` returns the session
--      id and nothing else; the Settings "Account ID" free-text field — which
--      let anyone type another user's id and read their data — is now a
--      read-only display. Desktop was never affected: it only ever HOSTS a
--      pairing, and hosting already requires being signed in (Hard Rule #26).
--
--   2. ROLLOUT (was: would 401 every installed desktop build). This warning
--      was written on 2026-07-24, the same day JWT forwarding landed, when no
--      shipped build had it yet. That commit (a9ab560) first shipped in
--      v1.0.11; the current release is v1.0.42, ~31 releases later, and the
--      desktop auto-updates on a 4-hour check. Any build old enough to lack
--      JWT forwarding is long past the update horizon.
--      RESOLVED, with one behaviour change: a desktop whose refresh token has
--      died used to keep syncing via the anon key (Hard Rule #24 / IDI-166),
--      which under these policies would silently read zero rows instead.
--      `auth.py::cloud_allowed()` now fails closed on `session_dead`, so that
--      state surfaces the existing re-sign-in banner rather than pretending to
--      sync. This is why the client change MUST ship before the SQL.
--
-- ── Cutover order (do not reorder) ─────────────────────────────────────────
--
--   1. Ship the desktop build carrying the `cloud_allowed()` change and let it
--      propagate (>= one 4-hour update cycle; check `app_versions` adoption).
--   2. Apply this file to STAGING. Regression-test signed-in sync end to end:
--      dictation history, notes, dictionary/snippets, canvas, devices, and the
--      meetings live transcript — on desktop AND mobile.
--   3. Verify negative cases on staging: an anon-key request with a valid
--      `user_id` returns zero rows; an authenticated request for ANOTHER
--      user's `user_id` returns zero rows and writes affect 0 rows.
--   4. Apply to production inside a transaction, with the DROP/CREATE pairs
--      below kept together so no window exists where a table has no policy.
--
-- Realtime note: the desktop WS listeners authenticate via the `phx_join`
-- payload's `access_token`, and only `sync.py` refreshes that token on a timer
-- (20 min). The canvas listeners in dashboard.py / shared_dashboard.py /
-- flume_web_dashboard.py do NOT, so a long-lived canvas subscription can
-- outlive its JWT and go quiet. That is pre-existing, but these policies make
-- it user-visible — track it as follow-up, it is not a blocker for step 4.
--
-- Mobile note: the app has not shipped to the App Store, so there is no
-- installed base to migrate. Applying before launch is strictly cheaper than
-- after.

begin;

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
