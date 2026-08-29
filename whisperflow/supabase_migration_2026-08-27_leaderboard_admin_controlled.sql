-- Run once against the live Verbal project (ovpcthjingugwvpxlsna).
-- Leaderboard becomes owner-controlled, all-or-nothing: drops the per-member
-- leaderboard_opt_in gate from org_leaderboard. usage_consent still applies.

create or replace function public.org_leaderboard(p_org uuid, p_days int default 7)
returns table (
  user_id      text,
  display_name text,
  words        bigint,
  speech_ms    bigint
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  v_since timestamptz := now() - (greatest(1, least(coalesce(p_days, 7), 365)) || ' days')::interval;
begin
  if public.org_member_role(p_org) is null then
    return;
  end if;
  if not exists (select 1 from public.organizations
                  where id = p_org and leaderboard_enabled) then
    return;
  end if;
  return query
    select m.user_id, m.display_name,
           coalesce(t.words, 0), coalesce(t.speech_ms, 0)
      from public.organization_members m
      left join lateral (
        select coalesce(sum(array_length(regexp_split_to_array(btrim(tr.text), '\s+'), 1)), 0) as words,
               coalesce(sum(coalesce(tr.duration_ms, 0)), 0)::bigint                           as speech_ms
          from public.transcriptions tr
         where tr.user_id = m.user_id
           and tr.created_at >= v_since
           and tr.deleted_at is null
           and btrim(coalesce(tr.text, '')) <> ''
      ) t on true
     where m.org_id = p_org and m.status = 'active'
       and m.usage_consent
     order by coalesce(t.words, 0) desc;
end;
$$;
