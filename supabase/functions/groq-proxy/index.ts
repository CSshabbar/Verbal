// groq-proxy — Supabase Edge Function brokering AI access for every Flume client.
// Provider keys live ONLY here: GROQ_API_KEY (default) and OLLAMA_API_KEY (for the
// meeting-notes model). Clients never see them.
//
// Tuned for latency: no heavy SDK import (was supabase-js — a big cold-start cost),
// no getUser() round-trip (the gateway already verified the JWT, so we just decode
// the `sub` locally), no blocking rate-limit query. Usage is logged fire-and-forget
// via a lightweight PostgREST call, and the upstream response is streamed straight back.
//
//   multipart/form-data with `file` ---------------> Groq  /audio/transcriptions (dictation)
//   application/json with `messages` --------------> Groq  /chat/completions      (cleanup/notes)
//   application/json + {"provider":"ollama"} ------> Ollama Cloud /v1/chat/completions (notes)
//
// The Ollama branch is OpenAI-compatible (same request/response shape as Groq), so it's
// a pure passthrough. It fails closed: if OLLAMA_API_KEY is unset the client gets an
// error and (by design) falls back to Groq — dictation is never affected.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const GROQ_BASE = "https://api.groq.com/openai/v1";
const OLLAMA_CHAT = "https://ollama.com/v1/chat/completions";
const DEFAULT_TRANSCRIBE_MODEL = "whisper-large-v3-turbo";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-flume-device",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(obj: unknown, status = 200): Response {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...CORS, "Content-Type": "application/json" },
  });
}

// Decode the user id from an already-gateway-verified JWT (no network call). The
// anon key has role 'anon' and no user; a signed-in user token has role
// 'authenticated' + a `sub`.
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

// Fire-and-forget usage row via PostgREST + the service role (no SDK, never blocks
// the response).
async function logUsage(req: Request, kind: string): Promise<void> {
  const url = Deno.env.get("SUPABASE_URL");
  const svc = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !svc) return;
  const userId = userIdFromJwt(req.headers.get("Authorization") ?? "");
  const deviceId = req.headers.get("x-flume-device");
  const ip = (req.headers.get("x-forwarded-for") ?? "").split(",")[0].trim();
  const identity = userId ? `user:${userId}` : deviceId ? `device:${deviceId}` : ip ? `ip:${ip}` : "anon";
  await fetch(`${url}/rest/v1/groq_usage`, {
    method: "POST",
    headers: {
      apikey: svc,
      Authorization: `Bearer ${svc}`,
      "Content-Type": "application/json",
      Prefer: "return=minimal",
    },
    body: JSON.stringify({ identity, user_id: userId, kind }),
  });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: { message: "Method not allowed" } }, 405);

  const groqKey = Deno.env.get("GROQ_API_KEY");
  if (!groqKey) return json({ error: { message: "GROQ_API_KEY secret not set on the function" } }, 500);

  const contentType = req.headers.get("content-type") || "";
  let kind = "chat";
  let resp: Response;
  try {
    if (contentType.includes("multipart/form-data")) {
      kind = "transcription";
      const form = await req.formData();
      if (!form.get("model")) form.set("model", DEFAULT_TRANSCRIBE_MODEL);
      resp = await fetch(`${GROQ_BASE}/audio/transcriptions`, {
        method: "POST",
        headers: { Authorization: `Bearer ${groqKey}` },
        body: form,
      });
    } else {
      const payload = await req.json();
      const provider = payload.provider;
      delete payload.provider; // not a valid upstream field — strip before forwarding
      if (provider === "ollama") {
        const ollamaKey = Deno.env.get("OLLAMA_API_KEY");
        if (!ollamaKey) {
          return json({ error: { message: "OLLAMA_API_KEY secret not set on the function" } }, 500);
        }
        kind = "chat-ollama";
        resp = await fetch(OLLAMA_CHAT, {
          method: "POST",
          headers: { Authorization: `Bearer ${ollamaKey}`, "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } else {
        resp = await fetch(`${GROQ_BASE}/chat/completions`, {
          method: "POST",
          headers: { Authorization: `Bearer ${groqKey}`, "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
    }
  } catch (e) {
    return json({ error: { message: `groq-proxy upstream error: ${String(e)}` } }, 502);
  }

  logUsage(req, kind).catch(() => {}); // never blocks

  return new Response(resp.body, {
    status: resp.status,
    headers: { ...CORS, "Content-Type": resp.headers.get("content-type") ?? "application/json" },
  });
});
