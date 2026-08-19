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
const ELEVEN_STT = "https://api.elevenlabs.io/v1/speech-to-text";
const AAI_BASE = "https://api.assemblyai.com/v2";

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
const TOKEN_ESTIMATE: Record<string, number> = { transcription: 500, chat: 2048, chained: 2548 };

// Returns null if the request is allowed, or the seconds the caller should wait
// before retrying. Never throws — any internal error (network, DB, bad response)
// fails OPEN (returns null) so the limiter itself can never take the pipeline down.
async function checkRateLimit(identity: string, kindGuess: "transcription" | "chat" | "chained"): Promise<number | null> {
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

// ── Chained transcribe -> format (2026-08-14) ────────────────────────────────
// Dictation used to cost the client TWO round trips: one to transcribe, one to format.
// Measurement showed each round trip is a ~0.5-0.9s FIXED cost regardless of payload
// (a 12-token prompt is no faster than a 677-token one), so halving the number of trips
// is the only lever that actually moves total latency. Chaining them here means the
// second hop is edge->Groq instead of client->edge->Groq.
//
// Strictly OPT-IN: activated only by a `chain=1` field in the multipart form. Every
// existing client (desktop groq_proxy.py, mobile lib/groq.ts, both keyboard extensions)
// sends no such field and takes the untouched streaming path below.
//
// FAILS CLOSED: any error formatting returns the transcription anyway with
// chain.ok=false, so the client can format locally and dictation is never lost to this.
// ── Alternate ASR providers (2026-08-15) ─────────────────────────────────────
// Settings can pick a non-Groq transcription model. Their keys live HERE as function
// secrets (ELEVENLABS_API_KEY / ASSEMBLYAI_API_KEY) for the same reason the Groq key
// does — Hard Rule #15, no provider key ever reaches a client.
//
// Both return the SAME `{text}` shape Groq does, so the desktop/mobile clients need no
// per-provider response handling; only the request grows one field. Both fail with a
// non-200 so the caller can retry on Groq — a provider being down or unpaid must never
// cost a dictation.
//
// Honest expectation: these are BATCH APIs and are slower than Groq on this audio
// (measured on the user's own clips: Groq ~1.0s, ElevenLabs ~1.75s, AssemblyAI ~5s
// because it is upload-then-poll). They are offered for accuracy, not speed.
async function transcribeEleven(file: File, language: string): Promise<Record<string, unknown>> {
  const key = Deno.env.get("ELEVENLABS_API_KEY");
  if (!key) return { ok: false, error: "ELEVENLABS_API_KEY secret not set on the function" };
  const fd = new FormData();
  fd.set("file", file);
  fd.set("model_id", "scribe_v1");
  // ElevenLabs wants ISO-639-3 ("eng"), not the ISO-639-1 the rest of the app speaks.
  if (language) fd.set("language_code", language === "en" ? "eng" : language);
  const r = await fetch(ELEVEN_STT, { method: "POST", headers: { "xi-api-key": key }, body: fd });
  if (!r.ok) return { ok: false, error: `eleven ${r.status}: ${(await r.text()).slice(0, 200)}` };
  const j = await r.json();
  return { ok: true, text: String(j?.text ?? "").trim() };
}

async function transcribeAssembly(
  file: File, language: string, model: string,
): Promise<Record<string, unknown>> {
  const key = Deno.env.get("ASSEMBLYAI_API_KEY");
  if (!key) return { ok: false, error: "ASSEMBLYAI_API_KEY secret not set on the function" };
  const h = { Authorization: key };            // no Bearer prefix
  const up = await fetch(`${AAI_BASE}/upload`, {
    method: "POST", headers: h, body: await file.arrayBuffer(),
  });
  if (!up.ok) return { ok: false, error: `aai upload ${up.status}: ${(await up.text()).slice(0, 160)}` };
  const uploadUrl = (await up.json())?.upload_url;
  // `speech_models` is a LIST; the singular `speech_model` is rejected as deprecated.
  // One entry pins the model instead of letting the service walk its default priority
  // list and silently transcribe with something else.
  const sub = await fetch(`${AAI_BASE}/transcript`, {
    method: "POST", headers: { ...h, "Content-Type": "application/json" },
    body: JSON.stringify({ audio_url: uploadUrl, speech_models: [model],
                           language_code: language || "en" }),
  });
  if (!sub.ok) return { ok: false, error: `aai submit ${sub.status}: ${(await sub.text()).slice(0, 160)}` };
  const id = (await sub.json())?.id;
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    const g = await fetch(`${AAI_BASE}/transcript/${id}`, { headers: h });
    const j = await g.json();
    if (j?.status === "completed") return { ok: true, text: String(j?.text ?? "").trim() };
    if (j?.status === "error") return { ok: false, error: `aai: ${String(j?.error).slice(0, 160)}` };
    await new Promise((r) => setTimeout(r, 400));
  }
  return { ok: false, error: "aai timed out waiting for completion" };
}

// Mirror of dictionary.apply_replacements() (whisperflow/app/dictionary.py): the
// user's find->replace rules, word-boundary and case-insensitive.
//
// This has to run HERE, before the formatter, not on its output. Unchained, the
// client applies these in transcriber.finalize() before it ever calls the formatter.
// Chained, the server holds the transcript first — so skipping this let the model
// read an uncorrected word and then "fix" the grammar around it: "so ideas needs a
// new one" came back as "so ideas need a new one", and correcting ideas->Idiaz
// afterwards could not restore "needs".
//
// Only the RULES cross the wire (the dictionary itself stays on the client). The
// replacement is passed as a function so `to` is always literal — $1/$& in a
// user-typed word can never be read as a backreference.
function applyReplacements(text: string, rules: Array<{ from: string; to: string }>): string {
  let out = text;
  for (const r of rules) {
    if (!r?.from || typeof r.to !== "string") continue;
    try {
      const esc = r.from.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      out = out.replace(new RegExp(`\\b${esc}\\b`, "gi"), () => r.to);
    } catch {
      // A rule that will not compile is skipped, never fatal — same posture as the
      // Python side, which falls back rather than raising.
    }
  }
  return out;
}

async function chainFormat(
  groqKey: string,
  transcript: string,
  model: string,
  systemPrompt: string,
  userTemplate: string,
  replaceRules: Array<{ from: string; to: string }> = [],
): Promise<Record<string, unknown>> {
  const t0 = Date.now();
  try {
    if (!transcript.trim()) return { ok: false, error: "empty transcript", fmt_ms: 0 };
    if (replaceRules.length) transcript = applyReplacements(transcript, replaceRules);
    // The client supplies the prompt so prompt logic stays versioned with the app and
    // never drifts between here and ai_cleanup.py. {{TEXT}} is the transcript slot.
    const userMsg = userTemplate.includes("{{TEXT}}")
      ? userTemplate.replace("{{TEXT}}", transcript)
      : `${userTemplate}\n\n${transcript}`;
    const r = await fetch(`${GROQ_BASE}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${groqKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model,
        temperature: 0,
        max_tokens: 2048,
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userMsg },
        ],
      }),
    });
    const fmt_ms = Date.now() - t0;
    if (!r.ok) {
      return { ok: false, error: `chat ${r.status}: ${(await r.text()).slice(0, 200)}`, fmt_ms };
    }
    const j = await r.json();
    const formatted = j?.choices?.[0]?.message?.content ?? null;
    return { ok: !!formatted, formatted, model, fmt_ms, usage: j?.usage ?? null };
  } catch (e) {
    return { ok: false, error: String(e).slice(0, 200), fmt_ms: Date.now() - t0 };
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
      // Pull the chain fields out BEFORE forwarding — Groq would reject unknown fields.
      const wantChain = String(form.get("chain") ?? "") === "1";
      // Default only matters when a client omits chain_model (they all send it).
      // llama-3.1-8b was retired by Groq (2026-08) — gpt-oss-20b is the fast tier now.
      const chainModel = String(form.get("chain_model") ?? "openai/gpt-oss-20b");
      const chainSystem = String(form.get("chain_system") ?? "");
      const chainUser = String(form.get("chain_user") ?? "{{TEXT}}");
      // Dictionary rules as JSON. Malformed -> no rules, never an error: losing a
      // name correction is bad, failing the dictation is worse.
      let chainReplace: Array<{ from: string; to: string }> = [];
      try {
        const rawRules = String(form.get("chain_replace") ?? "");
        if (rawRules) {
          const parsed = JSON.parse(rawRules);
          if (Array.isArray(parsed)) chainReplace = parsed.slice(0, 500);
        }
      } catch {
        chainReplace = [];
      }
      // Alternate ASR provider (Settings → Transcription model). Pulled out and
      // deleted before forwarding, like the chain fields — Groq rejects unknown fields.
      const asrProvider = String(form.get("asr_provider") ?? "groq");
      const asrAltModel = String(form.get("asr_alt_model") ?? "universal-2");
      for (const k of ["chain", "chain_model", "chain_system", "chain_user", "chain_replace",
                       "asr_provider", "asr_alt_model"]) {
        form.delete(k);
      }

      if (asrProvider === "eleven" || asrProvider === "assembly") {
        kind = `transcription-${asrProvider}`;
        const file = form.get("file");
        if (!(file instanceof File)) {
          return json({ error: { message: "no audio file in request" } }, 400);
        }
        const language = String(form.get("language") ?? "");
        const t_alt = Date.now();
        let res: Record<string, unknown>;
        try {
          res = asrProvider === "eleven"
            ? await transcribeEleven(file, language)
            : await transcribeAssembly(file, language, asrAltModel);
        } catch (e) {
          res = { ok: false, error: `${asrProvider}: ${String(e).slice(0, 180)}` };
        }
        const asr_ms = Date.now() - t_alt;
        logUsage(identity, userId, kind).catch(() => {});
        if (!res.ok || !res.text) {
          // 502 (not 200-with-empty-text) so the client can tell "provider broke" from
          // "you said nothing" and retry on Groq instead of treating it as silence.
          return json({ error: { message: String(res.error ?? "no transcript") },
                        provider: asrProvider }, 502);
        }
        // Same `{text}` shape as Groq, so the chain below and every client are unchanged.
        const alt: Record<string, unknown> = { text: res.text, provider: asrProvider, asr_ms };
        if (wantChain && chainSystem) {
          const chain = await chainFormat(
            groqKey, String(res.text).trim(), chainModel, chainSystem, chainUser, chainReplace,
          );
          return json({ ...alt, chain: { ...chain, asr_ms } });
        }
        return json(alt);
      }

      const t_asr = Date.now();
      resp = await fetch(`${GROQ_BASE}/audio/transcriptions`, {
        method: "POST",
        headers: { Authorization: `Bearer ${groqKey}` },
        body: form,
      });
      if (wantChain && chainSystem) {
        kind = "chained";
        // Buffer instead of streaming — we need the transcript to feed the second hop.
        const asrBody = await resp.text();
        const asr_ms = Date.now() - t_asr;
        if (!resp.ok) {
          logUsage(identity, userId, kind).catch(() => {});
          return new Response(asrBody, {
            status: resp.status,
            headers: { ...CORS, "Content-Type": "application/json" },
          });
        }
        let asrJson: Record<string, unknown> = {};
        try {
          asrJson = JSON.parse(asrBody);
        } catch {
          asrJson = { text: "" };
        }
        // .trim() is REQUIRED, not cosmetic. Whisper always returns its transcript
        // with a leading space, and every client strips it before formatting
        // (groq_proxy.py, lib/groq.ts). Passing the untrimmed string here fed the
        // formatter one extra leading token, which re-tokenizes the first line and
        // deterministically changed the output — measured: the chained path lost a
        // dictionary name fix ("Subhan" -> "Siobhan") 3/3 times that the local path
        // made 3/3 times, on a byte-identical prompt. Trimming makes chained and
        // unchained formatting see exactly the same input.
        const chain = await chainFormat(
          groqKey, String(asrJson.text ?? "").trim(), chainModel, chainSystem, chainUser,
          chainReplace,
        );
        logUsage(identity, userId, kind).catch(() => {});
        return json({ ...asrJson, chain: { ...chain, asr_ms } });
      }
    } else {
      const payload = await req.json();

      // ── Speaker diarization for meetings (2026-08-16) ─────────────────────
      // Who-spoke-when for the meeting transcript. The audio NEVER passes through
      // this function: the meeting WAV is already in the private `meeting-audio`
      // bucket, so we sign a short-lived URL with the service role and hand THAT to
      // AssemblyAI, which fetches the file itself. Submit and poll are separate
      // actions so no isolate ever sits in a poll loop against its wall clock —
      // the desktop polls, one cheap request at a time.
      //
      // Only speaker labels + times are consumed client-side; the transcript text
      // stays Groq's. Fails closed at every step: any error keeps the meeting's
      // gap-heuristic labels exactly as they are today.
      if (payload.diarize) {
        const d = payload.diarize;
        const aaiKey = Deno.env.get("ASSEMBLYAI_API_KEY");
        if (!aaiKey) {
          return json({ error: { message: "ASSEMBLYAI_API_KEY secret not set on the function" } }, 503);
        }
        kind = "diarize";
        if (typeof d.poll === "string" && /^[\w-]{8,64}$/.test(d.poll)) {
          const g = await fetch(`${AAI_BASE}/transcript/${d.poll}`, {
            headers: { Authorization: aaiKey },
          });
          if (!g.ok) return json({ error: { message: `poll ${g.status}` } }, 502);
          const j = await g.json();
          logUsage(identity, userId, kind).catch(() => {});
          if (j?.status === "completed") {
            // ms → seconds here, once, so the client never worries about units.
            const utts = (j?.utterances ?? []).map((u: Record<string, unknown>) => ({
              speaker: String(u.speaker ?? "?"),
              start: Number(u.start ?? 0) / 1000,
              end: Number(u.end ?? 0) / 1000,
            }));
            return json({ status: "completed", utterances: utts });
          }
          if (j?.status === "error") {
            return json({ status: "error", error: String(j?.error).slice(0, 200) });
          }
          return json({ status: String(j?.status ?? "processing") });
        }
        // Submit: object path is constrained to the caller-shaped layout
        // (<user>/<meeting>.wav) so this cannot be used to sign arbitrary bucket paths.
        const obj = String(d.object ?? "");
        if (!/^[\w-]{1,64}\/[\w-]{1,64}\.wav$/.test(obj)) {
          return json({ error: { message: "bad object path" } }, 400);
        }
        const svcUrl = Deno.env.get("SUPABASE_URL"), svc = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
        if (!svcUrl || !svc) return json({ error: { message: "service role unavailable" } }, 503);
        const sig = await fetch(`${svcUrl}/storage/v1/object/sign/meeting-audio/${obj}`, {
          method: "POST",
          headers: { apikey: svc, Authorization: `Bearer ${svc}`, "Content-Type": "application/json" },
          body: JSON.stringify({ expiresIn: 3600 }),
        });
        if (!sig.ok) return json({ error: { message: `sign ${sig.status}: ${(await sig.text()).slice(0, 120)}` } }, 502);
        const signedPath = (await sig.json())?.signedURL;
        if (!signedPath) return json({ error: { message: "no signed URL" } }, 502);
        const sub = await fetch(`${AAI_BASE}/transcript`, {
          method: "POST",
          headers: { Authorization: aaiKey, "Content-Type": "application/json" },
          body: JSON.stringify({
            audio_url: `${svcUrl}/storage/v1${signedPath}`,
            // universal-2, not 3.5-pro: measured better on this user's code-switched
            // speech, and diarization only needs turns + times anyway.
            speech_models: ["universal-2"],
            speaker_labels: true,
            language_code: "en",
          }),
        });
        if (!sub.ok) return json({ error: { message: `submit ${sub.status}: ${(await sub.text()).slice(0, 160)}` } }, 502);
        const id = (await sub.json())?.id;
        logUsage(identity, userId, kind).catch(() => {});
        return json({ id: String(id ?? "") });
      }

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
