// groq-proxy — Supabase Edge Function brokering AI access for every Flume client.
// Provider keys live ONLY here: GROQ_API_KEY (default) and OLLAMA_API_KEY (for the
// meeting-notes model). Clients never see them.
//
// Tuned for latency: no heavy SDK import (was supabase-js — a big cold-start cost),
// no getUser() round-trip (the gateway already verified the JWT, so we just decode
// the `sub` locally). Usage is logged fire-and-forget via a lightweight PostgREST
// call, and the upstream response is streamed straight back.
//
//   multipart/form-data with `file` ---------------> Groq  /audio/transcriptions (dictation)
//   application/json with `messages` --------------> Groq  /chat/completions      (cleanup/notes)
//   application/json + {"provider":"ollama"} ------> Ollama Cloud /v1/chat/completions (notes)
//
// The Ollama branch is OpenAI-compatible (same request/response shape as Groq), so it's
// a pure passthrough. It fails closed: if OLLAMA_API_KEY is unset the client gets an
// error and (by design) falls back to Groq — dictation is never affected.
//
// MER-30 (2026-07): per-identity rate limiting — the shared GROQ_API_KEY has a real
// tokens-per-minute budget (Groq returns 413 when a single request would exceed it,
// see meetings.py's ProxyPayloadTooLarge handling), and one heavy/abusive identity
// could otherwise exhaust it for everyone.
//
// First cut used an in-memory (in-isolate) counter to avoid a synchronous DB call on
// the hot path. Live testing disproved that: a 35-request sequential burst from one
// identity produced ZERO rejections from the in-memory limiter (every request reached
// the upstream Groq call, confirmed via groq_usage row counts) — Supabase's edge
// runtime does not reliably keep module-level state warm across invocations for this
// traffic pattern, so an in-isolate Map is not a functioning rate limiter here. This
// now calls a Postgres RPC (`groq_check_rate_limit`, see supabase_groq_rate_limits.sql)
// that does one indexed upsert+read per request — correctness over the latency
// micro-optimization, since a rate limiter that silently never triggers is worse than
// one that costs a few ms. Fails OPEN on any error (network, DB, malformed response) —
// Hard Rule #1: never take the dictation/meeting pipeline down because the limiter
// itself broke.

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

function json(obj: unknown, status = 200, extraHeaders?: Record<string, string>): Response {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...CORS, "Content-Type": "application/json", ...(extraHeaders ?? {}) },
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

// Same identity shape logged to `groq_usage` (user:<uuid> | device:<id> | ip:<addr>),
// shared by the rate limiter and the usage logger so they key off the same value.
function identityFromReq(req: Request): { identity: string; userId: string | null } {
  try {
    const userId = userIdFromJwt(req.headers.get("Authorization") ?? "");
    const deviceId = req.headers.get("x-flume-device");
    const ip = (req.headers.get("x-forwarded-for") ?? "").split(",")[0].trim();
    const identity = userId ? `user:${userId}` : deviceId ? `device:${deviceId}` : ip ? `ip:${ip}` : "anon";
    return { identity, userId };
  } catch {
    return { identity: "anon", userId: null };
  }
}

// Fire-and-forget usage row via PostgREST + the service role (no SDK, never blocks
// the response).
async function logUsage(identity: string, userId: string | null, kind: string): Promise<void> {
  const url = Deno.env.get("SUPABASE_URL");
  const svc = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !svc) return;
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

// ── Rate limiting (MER-30) ───────────────────────────────────────────────────
// Two independent per-identity fixed windows (60s): request count, and a COARSE
// token-equivalent estimate (we can't cheaply know real token usage before the
// upstream call, especially for audio — this is a safety-net proxy, not precise
// accounting). Both configurable via function secrets so limits can be tuned
// without a code change/redeploy.
const RATE_LIMIT_PER_MINUTE = Number(Deno.env.get("RATE_LIMIT_PER_MINUTE") ?? "30");
const RATE_LIMIT_TOKENS_PER_MINUTE = Number(Deno.env.get("RATE_LIMIT_TOKENS_PER_MINUTE") ?? "20000");
const WINDOW_SECONDS = 60;
// Flat per-request token-equivalent estimate, picked before the body is even
// parsed (transcription's real cost isn't token-shaped; chat's default
// max_tokens is 2048 across every caller in this codebase — see groq_proxy.py /
// lib/groq.ts / the keyboard extensions).
const TOKEN_ESTIMATE: Record<string, number> = { transcription: 500, chat: 2048 };

// Returns null if the request is allowed, or the seconds the caller should wait
// before retrying. Never throws — any internal error (network, DB, bad response)
// fails OPEN (returns null) so the limiter itself can never take the pipeline down.
async function checkRateLimit(identity: string, kindGuess: "transcription" | "chat"): Promise<number | null> {
  try {
    const url = Deno.env.get("SUPABASE_URL");
    const svc = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    if (!url || !svc) return null;
    const resp = await fetch(`${url}/rest/v1/rpc/groq_check_rate_limit`, {
      method: "POST",
      headers: { apikey: svc, Authorization: `Bearer ${svc}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        p_identity: identity,
        p_window_seconds: WINDOW_SECONDS,
        p_max_requests: RATE_LIMIT_PER_MINUTE,
        p_token_estimate: TOKEN_ESTIMATE[kindGuess],
        p_max_tokens: RATE_LIMIT_TOKENS_PER_MINUTE,
      }),
    });
    if (!resp.ok) {
      console.warn("groq-proxy rate limiter RPC error (failing open):", resp.status, await resp.text());
      return null;
    }
    const retryAfter = await resp.json();
    return typeof retryAfter === "number" ? retryAfter : null;
  } catch (e) {
    console.warn("groq-proxy rate limiter error (failing open):", e);
    return null;
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: { message: "Method not allowed" } }, 405);

  const groqKey = Deno.env.get("GROQ_API_KEY");
  if (!groqKey) return json({ error: { message: "GROQ_API_KEY secret not set on the function" } }, 500);

  const contentType = req.headers.get("content-type") || "";
  const isMultipart = contentType.includes("multipart/form-data");

  // Rate-limit check BEFORE touching the body — cheapest possible reject path,
  // and identity only needs headers (never transcription/chat content itself,
  // which must never appear in the limiter per the analytics-exclusion rule).
  const { identity, userId } = identityFromReq(req);
  const retryAfter = await checkRateLimit(identity, isMultipart ? "transcription" : "chat");
  if (retryAfter !== null) {
    return json(
      { error: { message: `Rate limit exceeded. Retry in ${retryAfter}s.` } },
      429,
      { "Retry-After": String(retryAfter) },
    );
  }

  let kind = "chat";
  let resp: Response;
  try {
    if (isMultipart) {
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

  logUsage(identity, userId, kind).catch(() => {}); // never blocks

  return new Response(resp.body, {
    status: resp.status,
    headers: { ...CORS, "Content-Type": resp.headers.get("content-type") ?? "application/json" },
  });
});
