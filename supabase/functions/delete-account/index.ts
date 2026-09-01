// delete-account — permanently deletes a signed-in user's account and every
// row/object keyed by their user_id. MER-32 (2026-07), App Store Guideline
// 5.1.1(v) (apps with account creation must let users delete in-app).
//
// `verify_jwt` is ON: the gateway rejects anything without a valid Supabase
// JWT before this code ever runs. Identity is decoded from THAT JWT's `sub`
// locally (no getUser round-trip, same pattern as groq-proxy) — never from a
// body-supplied id, so a caller can only ever delete their OWN account.
//
// Order matters (see the ticket's "watch out for"): purge DB rows + storage
// objects FIRST, delete the auth user LAST. If anything fails partway, the
// auth user (and their session) still exists, so the client can retry rather
// than being left as an orphaned auth user with a live token but no data.
// Every step is a plain DELETE keyed by user_id, so retrying is safe — a
// second call for an already-deleted user just deletes zero rows/objects
// everywhere until the final admin-delete-user call, which itself 404s
// harmlessly (treated as success: the end state — no user, no data — is
// already achieved).
//
// Sign-in-with-Apple token revocation is INTENTIONALLY DEFERRED (Batch C —
// needs the Apple private key from the pending Developer account). See the
// revokeAppleToken() stub below — it's called and its TODO is the seam.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(obj: unknown, status = 200): Response {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...CORS, "Content-Type": "application/json" },
  });
}

// Every table keyed by user_id that a "delete my account" must clear.
// groq_usage is a usage/metering ledger, not user content — deleted rather
// than anonymized so no trace of the account remains, per the ticket's
// acceptance criteria ("no DB rows ... remain for that user_id").
const USER_TABLES = [
  "transcriptions", "notes", "dictionary", "canvas",
  "devices", "meetings", "push_tokens", "groq_usage",
] as const;

// Storage: recordings/meeting-audio are namespaced under `<user_id>/`;
// canvas-images is flat (`canvas/<user_id>_<ts>.<ext>`), so it needs a list +
// filter instead of a folder delete.
const NAMESPACED_BUCKETS = ["recordings", "meeting-audio"] as const;

function svcHeaders(json = false): Record<string, string> {
  const h: Record<string, string> = { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}` };
  if (json) h["Content-Type"] = "application/json";
  return h;
}

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

async function deleteTableRows(table: string, userId: string): Promise<{ ok: boolean; detail?: string }> {
  try {
    const r = await fetch(
      `${SUPABASE_URL}/rest/v1/${table}?user_id=eq.${encodeURIComponent(userId)}`,
      { method: "DELETE", headers: { ...svcHeaders(), Prefer: "return=minimal" } },
    );
    if (r.ok) return { ok: true };
    return { ok: false, detail: `${table}: ${r.status} ${await r.text()}` };
  } catch (e) {
    return { ok: false, detail: `${table}: ${String(e)}` };
  }
}

async function listObjects(bucket: string, prefix: string, search?: string): Promise<string[]> {
  const r = await fetch(`${SUPABASE_URL}/storage/v1/object/list/${bucket}`, {
    method: "POST",
    headers: svcHeaders(true),
    body: JSON.stringify({ prefix, limit: 1000, ...(search ? { search } : {}) }),
  });
  if (!r.ok) return [];
  const files = await r.json();
  return Array.isArray(files) ? files.map((f: { name: string }) => `${prefix}${f.name}`) : [];
}

async function deleteObjects(bucket: string, paths: string[]): Promise<{ ok: boolean; detail?: string }> {
  if (paths.length === 0) return { ok: true };
  try {
    const r = await fetch(`${SUPABASE_URL}/storage/v1/object/${bucket}`, {
      method: "DELETE",
      headers: svcHeaders(true),
      body: JSON.stringify({ prefixes: paths }),
    });
    if (r.ok) return { ok: true };
    return { ok: false, detail: `${bucket}: ${r.status} ${await r.text()}` };
  } catch (e) {
    return { ok: false, detail: `${bucket}: ${String(e)}` };
  }
}

async function deleteNamespacedBucket(bucket: string, userId: string): Promise<{ ok: boolean; detail?: string }> {
  const prefix = `${userId}/`;
  const paths = await listObjects(bucket, prefix);
  return deleteObjects(bucket, paths);
}

async function deleteCanvasImages(userId: string): Promise<{ ok: boolean; detail?: string }> {
  // Flat namespace: filenames are `<user_id>_<ts>.<ext>` under a shared
  // `canvas/` prefix — list then filter by filename prefix, not folder.
  const all = await listObjects("canvas-images", "canvas/");
  const mine = all.filter((p) => p.slice("canvas/".length).startsWith(`${userId}_`));
  return deleteObjects("canvas-images", mine);
}

// TODO(Batch C): call Apple's token-revocation endpoint here for accounts
// that signed in with Apple, using the Apple private key from the pending
// Developer account. Intentionally deferred — see MER-32. No-op for now so
// Google-only deletion (the only sign-in method live today) works fully.
async function revokeAppleToken(_userId: string): Promise<void> {
  return;
}

async function deleteAuthUser(userId: string): Promise<{ ok: boolean; detail?: string }> {
  try {
    const r = await fetch(`${SUPABASE_URL}/auth/v1/admin/users/${userId}`, {
      method: "DELETE",
      headers: svcHeaders(),
    });
    // 404 = already gone (idempotent retry) — treat as success either way.
    if (r.ok || r.status === 404) return { ok: true };
    return { ok: false, detail: `auth user: ${r.status} ${await r.text()}` };
  } catch (e) {
    return { ok: false, detail: `auth user: ${String(e)}` };
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ ok: false, error: "Method not allowed" }, 405);

  const userId = userIdFromJwt(req.headers.get("Authorization") ?? "");
  if (!userId) return json({ ok: false, error: "Not signed in" }, 401);

  const results = await Promise.all([
    ...USER_TABLES.map((t) => deleteTableRows(t, userId)),
    ...NAMESPACED_BUCKETS.map((b) => deleteNamespacedBucket(b, userId)),
    deleteCanvasImages(userId),
  ]);

  const failures = results.filter((r) => !r.ok).map((r) => r.detail);
  if (failures.length > 0) {
    // Data/storage purge incomplete — do NOT delete the auth user. Leaves a
    // recoverable state: the client can retry, and every step above is safe
    // to repeat (DELETE-by-user_id, list+delete-by-path).
    // IDI-267 batch: log the per-step details server-side, return an opaque error
    // — table/bucket names and raw PostgREST messages are internals (clients only
    // ever read `error`, verified against auth.py::delete_account_remote).
    console.error(`delete-account: partial failure — ${failures.join("; ")}`);
    return json({ ok: false, error: "Partial failure — auth user NOT deleted, safe to retry" }, 500);
  }

  await revokeAppleToken(userId);

  const authResult = await deleteAuthUser(userId);
  if (!authResult.ok) {
    console.error(`delete-account: auth user deletion failed — ${authResult.detail}`);
    return json({ ok: false, error: "Data purged, but auth user deletion failed — safe to retry" }, 500);
  }

  return json({ ok: true });
});
