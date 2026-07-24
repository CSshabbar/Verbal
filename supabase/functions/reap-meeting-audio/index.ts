// reap-meeting-audio — MER-31 scheduled reaper: deletes old meeting AUDIO
// only (never the meeting row's text — transcript/summary/decisions/
// action_items/hybrid_notes/notes_md all survive) for meetings whose owner
// has opted into a retention window (`retention_days > 0`, OFF by default —
// see supabase_meetings.sql) and are not pinned. Invoked by a daily pg_cron
// job (see supabase_meetings.sql's `reap-meeting-audio-daily` schedule).
//
// Fail-closed ordering, per the ticket's own "watch out for": delete the
// storage object FIRST, only flag `audio_expired = true` (and clear
// `audio_url`) if that delete actually succeeded — a storage failure must
// never corrupt a row or mark audio as gone when it isn't. Never touches
// `pinned = true` rows or rows still `status = 'processing'` (a live capture
// could still be writing its audio — the exact zombie-row race called out).

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(obj: unknown, status = 200): Response {
  return new Response(JSON.stringify(obj), { status, headers: { ...CORS, "Content-Type": "application/json" } });
}

function svcHeaders(withJson = false): Record<string, string> {
  const h: Record<string, string> = { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}` };
  if (withJson) h["Content-Type"] = "application/json";
  return h;
}

type Candidate = { id: string; user_id: string; started_at: string; retention_days: number };

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });

  try {
    // Candidates: not pinned, not already expired, retention explicitly
    // enabled (>0 — OFF is the default), has an audio object, not mid-pipeline.
    const query = new URLSearchParams({
      pinned: "eq.false",
      audio_expired: "eq.false",
      retention_days: "gt.0",
      audio_url: "not.is.null",
      status: "neq.processing",
      select: "id,user_id,started_at,retention_days",
    });
    const listResp = await fetch(`${SUPABASE_URL}/rest/v1/meetings?${query}`, { headers: svcHeaders() });
    if (!listResp.ok) {
      return json({ ok: false, error: `candidate query failed: ${listResp.status} ${await listResp.text()}` }, 500);
    }
    const candidates: Candidate[] = await listResp.json();

    // retention_days is per-row (stamped at capture time from the user's
    // setting then), so the cutoff differs per meeting — filter here rather
    // than trying to express it as a single PostgREST comparison.
    const now = Date.now();
    const expired = candidates.filter((m) => {
      const startedAt = new Date(m.started_at).getTime();
      const windowMs = m.retention_days * 24 * 60 * 60 * 1000;
      return Number.isFinite(startedAt) && now - startedAt > windowMs;
    });

    let deleted = 0;
    let failed = 0;
    for (const m of expired) {
      const objectPath = `${m.user_id}/${m.id}.wav`;
      try {
        const delResp = await fetch(`${SUPABASE_URL}/storage/v1/object/meeting-audio`, {
          method: "DELETE",
          headers: svcHeaders(true),
          body: JSON.stringify({ prefixes: [objectPath] }),
        });
        if (!delResp.ok) {
          console.warn(`reap-meeting-audio: storage delete failed for ${objectPath}: ${delResp.status}`);
          failed++;
          continue; // do NOT mark audio_expired — leave it recoverable/retryable
        }
        const patchResp = await fetch(`${SUPABASE_URL}/rest/v1/meetings?id=eq.${m.id}`, {
          method: "PATCH",
          headers: { ...svcHeaders(true), Prefer: "return=minimal" },
          body: JSON.stringify({ audio_expired: true, audio_url: null }),
        });
        if (!patchResp.ok) {
          console.warn(`reap-meeting-audio: flag update failed for ${m.id}: ${patchResp.status}`);
          failed++;
          continue;
        }
        deleted++;
      } catch (e) {
        console.warn(`reap-meeting-audio: error processing ${m.id}: ${e}`);
        failed++;
      }
    }

    return json({ ok: true, candidates: candidates.length, deleted, failed });
  } catch (e) {
    return json({ ok: false, error: String(e) }, 500);
  }
});
