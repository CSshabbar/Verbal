-- 2026-08-27: provenance of the meeting's speaker split (APPLIED LIVE 2026-08-27 as
-- migration `meetings_speakers_source`).
--   'diarized'  → AssemblyAI who-spoke-when turns were applied (desktop MeetingSession._diarize())
--   'estimated' → 90 s silence-gap heuristic only (diarization did not run / failed closed)
--   NULL        → meetings captured before this column existed (clients treat as estimated)
alter table public.meetings
  add column if not exists speakers_source text
  check (speakers_source is null or speakers_source in ('diarized', 'estimated'));
