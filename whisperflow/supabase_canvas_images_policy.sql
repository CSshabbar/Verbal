-- Canvas images — ensure the `canvas-images` storage bucket exists, is public,
-- and accepts uploads/reads from the anon role. Both apps talk to storage with the
-- anon key (desktop always; mobile when signed in the JWT is also fine because the
-- policies below are TO public). Run once in the Supabase SQL editor
-- (project ovpcthjingugwvpxlsna). Idempotent — safe to re-run.
--
-- Why: mobile uploads a canvas photo to this bucket, then shares only the public
-- URL via the `canvas` row. If the bucket rejects the anonymous upload, the URL is
-- never produced and the picture silently never reaches the other device.

-- 1) Bucket exists + is public (public read via the object URL).
insert into storage.buckets (id, name, public)
values ('canvas-images', 'canvas-images', true)
on conflict (id) do update set public = true;

-- 2) Read / insert / update policies scoped to this bucket, TO public (covers both
--    the anon key and a signed-in JWT). Guarded so re-runs don't error.
do $$
begin
  if not exists (select 1 from pg_policies
      where schemaname='storage' and tablename='objects' and policyname='canvas-images read') then
    create policy "canvas-images read" on storage.objects
      for select to public using (bucket_id = 'canvas-images');
  end if;

  if not exists (select 1 from pg_policies
      where schemaname='storage' and tablename='objects' and policyname='canvas-images insert') then
    create policy "canvas-images insert" on storage.objects
      for insert to public with check (bucket_id = 'canvas-images');
  end if;

  -- The mobile upload sends x-upsert:true, which can perform an UPDATE.
  if not exists (select 1 from pg_policies
      where schemaname='storage' and tablename='objects' and policyname='canvas-images update') then
    create policy "canvas-images update" on storage.objects
      for update to public using (bucket_id = 'canvas-images') with check (bucket_id = 'canvas-images');
  end if;
end $$;
