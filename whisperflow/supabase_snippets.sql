-- Flume snippets — spoken trigger phrase → longer text expansion.
-- Snippets live on the existing per-user dictionary row (a third array beside
-- vocabulary + replacements), so they inherit its sync path (one row/user,
-- last-write-wins on updated_at). Idempotent; run once in the Supabase SQL
-- editor (project ovpcthjingugwvpxlsna).
-- Shape: [{id, trigger, expansion, label, used, created_at, updated_at}]
alter table public.dictionary add column if not exists snippets jsonb not null default '[]'::jsonb;
