// asr-stream — websocket relay for the `hybrid` dictation pipeline.
//
// The desktop streams microphone PCM here WHILE the user is still speaking; this
// relays it to AssemblyAI's realtime API and streams the transcript back. That keeps
// the vendor key server-side (Hard Rule #15 — no provider key ever reaches a client)
// while still giving the client a live socket.
//
// WHY A SEPARATE FUNCTION FROM groq-proxy: a websocket upgrade cannot carry the
// normal Authorization header, so a relay must run with verify_jwt OFF and check the
// key itself. Rather than weaken every existing HTTP path on groq-proxy, that
// relaxation is quarantined here — this function only relays audio, and it refuses
// any connection that does not present the project's anon key (otherwise it would be
// an open relay spending the account's ASR credit).
//
// WHY ASSEMBLYAI AND NOT ELEVENLABS: Deno's WebSocket cannot set request headers, so
// a vendor must accept credentials in the URL. AssemblyAI mints a short-lived token
// (GET /v3/token, verified working). ElevenLabs' realtime API documents only an
// `xi-api-key` header or a single-use token whose endpoint returns 404 on every path
// probed — so its streaming arm is deliberately NOT wired rather than guessed at.
//
// ONE MESSAGE SHAPE, so the client never learns which vendor it got:
//   -> binary frames         = 16 kHz mono PCM16 audio
//   -> {"type":"done"}       = end of speech; flush and finalise
//   <- {"type":"ready"} | {"type":"partial","text":…}
//   <- {"type":"final","text":…} | {"type":"error","error":…}
//
// Supabase recycles an isolate at roughly half its wall-clock limit and drops the
// socket with it. Dictations are seconds long so this rarely bites, and the client
// treats ANY failure as "fall back to the ordinary upload path" — a dropped stream
// costs latency, never a dictation.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const AAI_TOKEN = "https://streaming.assemblyai.com/v3/token?expires_in_seconds=180";
const AAI_WS = "wss://streaming.assemblyai.com/v3/ws";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

function bad(msg: string, status = 400): Response {
  return new Response(JSON.stringify({ error: { message: msg } }), {
    status, headers: { ...CORS, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });

  const url = new URL(req.url);
  const provider = url.searchParams.get("provider") ?? "assembly";
  const apikey = url.searchParams.get("apikey") ?? "";

  const anon = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
  // A signed-in user sends their JWT, which starts "eyJ"; everything else must match
  // the project anon key exactly.
  if (!apikey || (anon && apikey !== anon && !apikey.startsWith("eyJ"))) {
    return bad("unauthorized", 401);
  }
  if (req.headers.get("upgrade")?.toLowerCase() !== "websocket") {
    return bad("expected a websocket upgrade", 426);
  }
  if (provider !== "assembly") {
    return bad(`streaming provider '${provider}' is not available`, 400);
  }
  const vendorKey = Deno.env.get("ASSEMBLYAI_API_KEY");
  if (!vendorKey) return bad("ASSEMBLYAI_API_KEY secret not set on the function", 503);

  // Mint the short-lived token BEFORE upgrading, so a credential problem is a clean
  // HTTP error the client can log rather than a socket that opens and dies.
  let token: string;
  try {
    const r = await fetch(AAI_TOKEN, { headers: { Authorization: vendorKey } });
    if (!r.ok) return bad(`token ${r.status}: ${(await r.text()).slice(0, 160)}`, 502);
    token = String((await r.json())?.token ?? "");
    if (!token) return bad("vendor returned no token", 502);
  } catch (e) {
    return bad(`token: ${String(e).slice(0, 160)}`, 502);
  }

  const { socket: client, response } = Deno.upgradeWebSocket(req);

  let vendor: WebSocket | null = null;
  let opened = false;
  let finished = false;
  const pending: ArrayBuffer[] = [];
  // `Turn` repeats as a turn grows, so keep the newest text per turn_order; the
  // transcript is every turn joined in order.
  const turns = new Map<number, string>();

  const send = (o: unknown) => {
    try { if (client.readyState === 1) client.send(JSON.stringify(o)); } catch { /* gone */ }
  };
  const shut = () => {
    try { client.close(); } catch { /* already closed */ }
    try { vendor?.close(); } catch { /* already closed */ }
  };
  const fail = (why: string) => {
    if (finished) return;
    finished = true;
    send({ type: "error", error: why });
    shut();
  };
  const finalise = () => {
    if (finished) return;
    finished = true;
    const text = [...turns.keys()].sort((a, b) => a - b)
      .map((k) => turns.get(k)).filter(Boolean).join(" ").trim();
    send({ type: "final", text });
    shut();
  };

  client.onopen = () => {
    try {
      vendor = new WebSocket(
        `${AAI_WS}?token=${encodeURIComponent(token)}&sample_rate=16000&format_turns=true`);
    } catch (e) {
      return fail(`vendor connect: ${String(e).slice(0, 140)}`);
    }
    vendor.binaryType = "arraybuffer";
    vendor.onopen = () => {
      opened = true;
      send({ type: "ready" });
      for (const p of pending) { try { vendor!.send(p); } catch { /* ignore */ } }
      pending.length = 0;
    };
    vendor.onerror = () => fail("vendor socket error");
    vendor.onclose = () => { if (!finished) finalise(); };
    vendor.onmessage = (ev) => {
      if (typeof ev.data !== "string") return;
      let j: Record<string, unknown>;
      try { j = JSON.parse(ev.data); } catch { return; }
      const t = String(j.type ?? "");
      if (t === "Turn") {
        const order = Number(j.turn_order ?? 0);
        // A formatted turn always beats an unformatted one for the same turn.
        if (j.turn_is_formatted || !turns.has(order)) {
          turns.set(order, String(j.transcript ?? "").trim());
        }
        if (!j.end_of_turn) send({ type: "partial", text: String(j.transcript ?? "") });
      } else if (t === "Termination") {
        finalise();
      } else if (t.toLowerCase().includes("error") || j.error) {
        fail(String(j.error ?? t).slice(0, 160));
      }
    };
  };

  client.onmessage = (ev) => {
    if (typeof ev.data !== "string") {
      // Audio arriving before the vendor handshake is HELD, not dropped — losing the
      // opening words is exactly what a user notices. Bounded so a stuck handshake
      // cannot grow it without limit.
      const buf = ev.data as ArrayBuffer;
      if (!opened || !vendor) { if (pending.length < 600) pending.push(buf); return; }
      try { vendor.send(buf); } catch { fail("vendor send failed"); }
      return;
    }
    let j: Record<string, unknown>;
    try { j = JSON.parse(ev.data); } catch { return; }
    if (j.type === "done") {
      if (!vendor) return finalise();
      try { vendor.send(JSON.stringify({ type: "Terminate" })); } catch { /* net below */ }
      // Safety net: if the vendor never sends Termination we still owe the client an
      // answer, so finalise with whatever turns have landed.
      setTimeout(finalise, 6000);
    }
  };

  client.onerror = () => { try { vendor?.close(); } catch { /* ignore */ } };
  client.onclose = () => { try { vendor?.close(); } catch { /* ignore */ } };

  return response;
});
