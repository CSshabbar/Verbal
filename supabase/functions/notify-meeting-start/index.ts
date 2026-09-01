// notify-meeting-start — sends an Expo push to a user's registered devices when a
// meeting begins on another device (the Mac). Called fire-and-forget by the desktop
// (meetings.py::_notify_start). Reads push_tokens via PostgREST with the service
// role, posts to the Expo Push API. Fails soft — a push failure never matters to
// the meeting itself.
//
// IDI-258: this function only ever notifies YOUR OWN other devices, so the target
// user is the JWT subject, never the request body. The gateway's `verify_jwt`
// accepts the project anon key (it ships in every client binary), so an anon-role
// caller is rejected here and a body `user_id` that isn't the JWT subject is
// refused — before this, anyone with the anon key could push-spam any user and
// use `sent: N` as a device-count oracle.
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

// Same local decode as groq-proxy/invite-member: the gateway already verified the
// signature, we only need role + sub. The anon key has role 'anon' and no sub.
function userIdFromJwt(authHeader: string): string | null {
  try {
    const t = authHeader.replace(/^[Bb]earer\s+/, "");
    const parts = t.split(".");
    if (parts.length < 2) return null;
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload.role === "authenticated" && typeof payload.sub === "string" ? payload.sub : null;
  } catch {
    return null;
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  const jwtUser = userIdFromJwt(req.headers.get("Authorization") ?? "");
  if (!jwtUser) return json({ ok: false, error: "not_authenticated" }, 401);
  try {
    const { user_id, meeting_id, title, source } = await req.json();
    // The body user_id is legacy (older desktops still send it) — it may only
    // ever confirm the JWT subject, never select a different target.
    if (user_id && String(user_id) !== jwtUser) {
      return json({ ok: false, error: "forbidden" }, 403);
    }

    // fetch this user's push tokens
    const r = await fetch(
      `${SUPABASE_URL}/rest/v1/push_tokens?user_id=eq.${encodeURIComponent(jwtUser)}&select=token`,
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
