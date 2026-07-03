-- Flume saved recordings + retry.
-- Run once in the Supabase SQL editor (project ovpcthjingugwvpxlsna).

-- 1) transcriptions: remember the audio URL + a status for failed/retryable rows
alter table public.transcriptions add column if not exists audio_url text;
alter table public.transcriptions add column if not exists status    text default 'done';

-- 2) a public Storage bucket for the audio files
insert into storage.buckets (id, name, public)
values ('recordings', 'recordings', true)
on conflict (id) do update set public = true;

-- 3) anon access to that bucket (same anon key the apps already use;
--    objects are namespaced under <user_id>/<recording_id>.wav)
drop policy if exists "recordings anon read"   on storage.objects;
create policy "recordings anon read"   on storage.objects
  for select to anon using (bucket_id = 'recordings');

drop policy if exists "recordings anon insert" on storage.objects;
create policy "recordings anon insert" on storage.objects
  for insert to anon with check (bucket_id = 'recordings');

drop policy if exists "recordings anon update" on storage.objects;
create policy "recordings anon update" on storage.objects
  for update to anon using (bucket_id = 'recordings') with check (bucket_id = 'recordings');
