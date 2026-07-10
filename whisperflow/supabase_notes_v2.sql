-- Notes v2 — voice-native Notes enhancements (raw transcript + source-recording linkage).
-- Run once in the Supabase SQL editor (project ovpcthjingugwvpxlsna). Idempotent —
-- safe to re-run. See NOTES_ENHANCEMENT_SWARM.md and context/04-data-model.md §notes.

-- 1) raw_content: the untouched Whisper transcript for a voice-dictated note. The
--    user-visible `content` holds the AI-formatted version; "show original" reveals
--    this. NULL for pre-existing notes and for typed (non-dictated) notes.
alter table public.notes add column if not exists raw_content text;

-- 2) audio_segments: append-only list of the recordings behind a note, shape
--    [{ "id": text, "url": text, "created_at": iso8601 }]. A note accumulates
--    multiple segments over time; sync UNIONs this list (never overwrites), so a
--    segment added on one device is never lost to an edit on another.
alter table public.notes
  add column if not exists audio_segments jsonb not null default '[]'::jsonb;

comment on column public.notes.raw_content    is 'Raw Whisper transcript for a voice note; NULL for typed/pre-existing notes. content holds the AI-formatted version.';
comment on column public.notes.audio_segments is 'Append-only list of source recordings [{id,url,created_at}]; UNION-on-merge during sync.';

-- 3) RLS: match the dictionary/snippets lesson (see supabase_dictionary_rls_fix.sql
--    and context/04-data-model.md §Security). The desktop app talks to Supabase with
--    the raw anon key (role = anon); a signed-in mobile client sends an authenticated
--    JWT (role = authenticated). A policy scoped `TO anon` silently filters the row
--    out for the signed-in phone. If — and only if — `notes` already has RLS enabled
--    with an anon-only policy, broaden every such policy to `public`. If notes has no
--    RLS at all, this block does nothing (leaves it as-is).
do $$
declare
  pol record;
  has_rls boolean;
begin
  select relrowsecurity into has_rls
  from pg_class
  where oid = 'public.notes'::regclass;

  if has_rls then
    for pol in
      select polname
      from pg_policy
      where polrelid = 'public.notes'::regclass
        and polroles = array(select oid from pg_roles where rolname = 'anon')
    loop
      execute format('drop policy if exists %I on public.notes', pol.polname);
    end loop;

    -- Only (re)create a permissive public policy if we actually removed an anon-only
    -- one above, i.e. RLS is on but no policy now covers `public`.
    if not exists (
      select 1 from pg_policy
      where polrelid = 'public.notes'::regclass
    ) then
      create policy "notes rw" on public.notes
        for all to public using (true) with check (true);
    end if;
  end if;
end $$;
