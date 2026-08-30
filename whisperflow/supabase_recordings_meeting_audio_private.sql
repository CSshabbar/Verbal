-- Fix (MER-27): recordings and meeting-audio were fully public with deterministic,
-- guessable paths (<user_id>/<id>.<ext>) — the highest-sensitivity data this product
-- holds (raw dictation / meeting audio), downloadable by anyone with (or able to
-- construct) a URL, with zero authentication of any kind.
--
-- Flip both buckets private. Clients now generate short-lived signed URLs on demand
-- at playback/download time (Supabase Storage's POST /object/sign/{bucket}/{path})
-- instead of relying on a permanently-public URL. See recordings.py::sign_url /
-- lib/recordings.ts::signUrl.
update storage.buckets set public = false where id in ('recordings', 'meeting-audio');

-- Same class of bug as MER-26/dictionary: these policies were scoped TO anon only,
-- not TO public. Desktop's raw anon-key calls matched fine, but a signed-in mobile
-- client's storage call runs as `authenticated` and would be silently rejected —
-- which would have broken signed-in-mobile signed-URL generation for this exact fix.
-- Hard Rule #10 (context/05-conventions.md): any table/bucket both clients share
-- must be TO public, not TO anon.
drop policy if exists "recordings anon read" on storage.objects;
drop policy if exists "recordings anon insert" on storage.objects;
drop policy if exists "recordings anon update" on storage.objects;
create policy "recordings read" on storage.objects for select to public using (bucket_id = 'recordings');
create policy "recordings insert" on storage.objects for insert to public with check (bucket_id = 'recordings');
create policy "recordings update" on storage.objects for update to public using (bucket_id = 'recordings');

-- meeting-audio policies ("meeting-audio read/insert/update/delete") were already
-- TO public — left untouched.

-- canvas-images and releases are deliberately left public (canvas is lower-sensitivity
-- user-chosen shares; releases must stay public for app-update downloads).
