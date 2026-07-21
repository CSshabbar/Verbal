// notify-meeting-start — sends an Expo push to a user's registered devices when a
// meeting begins on another device (the Mac). Called fire-and-forget by the desktop
// (meetings.py::_notify_start). Reads push_tokens via PostgREST with the service
// role, posts to the Expo Push API. Fails soft — a push failure never matters to
// the meeting itself.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const EXPO_PUSH = "https://exp.host/--/api/v2/push/send";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (o: unknown, s = 200) =>
  new Response(JSON.stringify(o), { status: s, headers: { ...CORS, "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  try {
    const { user_id, meeting_id, title, source } = await req.json();
    if (!user_id) return json({ ok: false, error: "user_id required" }, 400);

    // fetch this user's push tokens
    const r = await fetch(
      `${SUPABASE_URL}/rest/v1/push_tokens?user_id=eq.${encodeURIComponent(user_id)}&select=token`,
      { headers: { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}` } },
    );
    const rows: { token: string }[] = r.ok ? await r.json() : [];
    const tokens = rows.map((x) => x.token).filter((t) => t && t.startsWith("ExponentPushToken"));
    if (!tokens.length) return json({ ok: true, sent: 0 });

    const messages = tokens.map((to) => ({
      to,
      title: "Meeting started",
      body: `${title || "A meeting"} is recording on ${source || "your Mac"} — tap to follow live.`,
      sound: "default",
      priority: "high",
      data: { type: "meeting_start", meeting_id },
    }));

    const push = await fetch(EXPO_PUSH, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(messages),
    });
    return json({ ok: push.ok, sent: tokens.length });
  } catch (e) {
    return json({ ok: false, error: String(e) }, 200); // soft-fail
  }
});
