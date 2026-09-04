// report-issue — receives an in-app "Report an issue" submission from any
// platform (mac/win/ios/android), saves it to `issue_reports`, then
// best-effort emails the report to the founder. Beta-launch feature (2026-09).
//
// `verify_jwt` is ON: the gateway requires a valid Supabase JWT — a signed-in
// user's session token OR the anon key (both apps hold one of the two), so no
// unauthenticated internet caller reaches this code. Identity is decoded from
// the JWT locally (same pattern as delete-account): an authenticated caller's
// user_id/email are recorded on the row, an anon-role caller is stored as an
// anonymous report — a signed-out beta tester must still be able to report.
//
// ORDER MATTERS: the DB insert happens FIRST and alone decides success. Email
// is strictly best-effort — a Resend outage, missing key, or unverified domain
// must never lose a report or surface an error to the tester. This inverts
// invite-member's posture (there the email IS the product; here the row is).
//
// SCREENSHOT (optional): `image_b64` (raw base64, no data: prefix) +
// `image_type` (png/jpg/jpeg/webp/gif, ≤5 MB decoded). Uploaded to the PRIVATE
// `issue-screenshots` bucket as `<report_id>.<ext>` (recorded in
// meta.screenshot) and attached to the notification email. Every image step
// fails SOFT — a bad/oversized/unuploadable image never blocks the text report.
//
// SECRETS (all optional, all shared with invite-member where they exist):
//   RESEND_API_KEY      — without it the email step is skipped, reports still save
//   INVITE_FROM_EMAIL   — the verified From address (bare or RFC-5322 wrapped)
//   ISSUE_REPORT_EMAIL  — recipient override; defaults to the founder's address

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY") ?? "";
const RAW_FROM = Deno.env.get("INVITE_FROM_EMAIL") ?? "invites@flume.app";
const FROM_EMAIL = RAW_FROM.includes("<") ? RAW_FROM : `Flume <${RAW_FROM}>`;
const REPORT_TO = Deno.env.get("ISSUE_REPORT_EMAIL") ?? "sraza@idiaz.io";

const MESSAGE_MAX = 4000;
const PLATFORMS = new Set(["mac", "win", "ios", "android"]);
const IMAGE_MAX_BYTES = 5 * 1024 * 1024;
// b64 is 4/3 the decoded size; +4 tolerates padding.
const IMAGE_MAX_B64 = Math.ceil(IMAGE_MAX_BYTES * 4 / 3) + 4;
const IMAGE_TYPES: Record<string, string> = {
  png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg",
  webp: "image/webp", gif: "image/gif",
};

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

function callerFromJwt(authHeader: string): { userId: string; email: string } {
  try {
    const t = authHeader.replace(/^[Bb]earer\s+/, "");
    const parts = t.split(".");
    if (parts.length < 2) return { userId: "", email: "" };
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (payload.role === "authenticated" && typeof payload.sub === "string") {
      return { userId: payload.sub, email: typeof payload.email === "string" ? payload.email : "" };
    }
  } catch { /* fall through to anonymous */ }
  return { userId: "", email: "" };
}

function clip(v: unknown, max: number): string {
  return typeof v === "string" ? v.trim().slice(0, max) : "";
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Decode + validate the optional screenshot. Returns null for anything off —
 * wrong type, oversized, or non-base64 — because an image must never sink the
 * text report it rides on. */
function parseImage(body: Record<string, unknown>):
  { b64: string; ext: string; contentType: string; bytes: Uint8Array } | null {
  const b64 = typeof body.image_b64 === "string" ? body.image_b64.trim() : "";
  if (!b64) return null;
  const ext = clip(body.image_type, 8).toLowerCase();
  const contentType = IMAGE_TYPES[ext];
  if (!contentType) return null;
  if (b64.length > IMAGE_MAX_B64) return null;
  try {
    const bin = atob(b64);
    if (bin.length > IMAGE_MAX_BYTES) return null;
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return { b64, ext: ext === "jpeg" ? "jpg" : ext, contentType, bytes };
  } catch {
    return null;
  }
}

async function uploadScreenshot(
  path: string,
  img: { contentType: string; bytes: Uint8Array },
): Promise<boolean> {
  try {
    const r = await fetch(`${SUPABASE_URL}/storage/v1/object/issue-screenshots/${path}`, {
      method: "POST",
      headers: {
        apikey: SERVICE_KEY,
        Authorization: `Bearer ${SERVICE_KEY}`,
        "Content-Type": img.contentType,
        "x-upsert": "true",
      },
      body: img.bytes,
      signal: AbortSignal.timeout(15000),
    });
    if (r.ok) return true;
    console.error(`report-issue: screenshot upload failed ${r.status} — ${(await r.text()).slice(0, 200)}`);
  } catch (e) {
    console.error(`report-issue: screenshot upload threw — ${String(e)}`);
  }
  return false;
}

async function sendEmail(report: {
  id: string; userId: string; email: string; platform: string;
  appVersion: string; message: string; deviceName: string; osVersion: string;
  image?: { b64: string; ext: string; contentType: string } | null;
}): Promise<boolean> {
  if (!RESEND_API_KEY) return false;
  const who = report.email || report.userId || "anonymous";
  const subject = `Flume issue report — ${report.platform || "unknown"} v${report.appVersion || "?"}`;
  const lines = [
    `From: ${who}`,
    `Platform: ${report.platform || "unknown"}  ·  App version: ${report.appVersion || "unknown"}`,
    report.deviceName ? `Device: ${report.deviceName}` : "",
    report.osVersion ? `OS: ${report.osVersion}` : "",
    report.image ? "Screenshot: attached" : "",
    `Report id: ${report.id}`,
    "",
    report.message,
  ].filter((l) => l !== "");
  const text = lines.join("\n");
  const html = `<div style="font-family:ui-monospace,Menlo,monospace;font-size:13px;line-height:1.6;white-space:pre-wrap">${escapeHtml(text)}</div>`;
  try {
    const payload: Record<string, unknown> = { from: FROM_EMAIL, to: [REPORT_TO], subject, html, text };
    if (report.image) {
      // content_type is required in practice — Resend's raw HTTP API tags an
      // attachment without one as application/octet-stream (the invite-member
      // inline-icon lesson, 2026-08-21), which many clients refuse to preview.
      payload.attachments = [{
        filename: `screenshot.${report.image.ext}`,
        content: report.image.b64,
        content_type: report.image.contentType,
      }];
    }
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${RESEND_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (r.ok) return true;
    // Log the real reason server-side (unverified domain, sandbox recipient,
    // bad key) — the client never sees email failures, so this log is the only
    // copy. Never logs the message body.
    console.error(`report-issue: resend rejected ${r.status} — ${(await r.text()).slice(0, 400)}`);
    console.error(`report-issue: from=${FROM_EMAIL} to=${REPORT_TO}`);
  } catch (e) {
    console.error(`report-issue: resend threw — ${String(e)}`);
  }
  return false;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ ok: false, error: "Method not allowed" }, 405);

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }

  const message = clip(body.message, MESSAGE_MAX);
  if (!message) return json({ ok: false, error: "empty_message" }, 400);

  // Metadata is best-effort: an unknown platform string is stored as '' rather
  // than rejecting the report — the message is the payload, the rest is garnish.
  const rawPlatform = clip(body.platform, 16).toLowerCase();
  const platform = PLATFORMS.has(rawPlatform) ? rawPlatform : "";
  const appVersion = clip(body.app_version, 40);
  const deviceName = clip(body.device_name, 120);
  const osVersion = clip(body.os_version, 120);

  const { userId, email } = callerFromJwt(req.headers.get("Authorization") ?? "");

  // The id is minted HERE (not by the DB default) so the screenshot can be
  // uploaded under its final `<id>.<ext>` name and referenced in meta within
  // the single row insert. Upload-before-insert is deliberate: the upload is
  // time-bounded (15 s) and fails soft, so the worst case is a text-only
  // report — never a lost one. (An insert failing after a successful upload
  // orphans one object; logged, rare, harmless.)
  const id = crypto.randomUUID();
  const image = parseImage(body);
  let screenshotPath = "";
  if (image) {
    const path = `${id}.${image.ext}`;
    if (await uploadScreenshot(path, image)) screenshotPath = path;
  }

  try {
    const r = await fetch(`${SUPABASE_URL}/rest/v1/issue_reports`, {
      method: "POST",
      headers: {
        apikey: SERVICE_KEY,
        Authorization: `Bearer ${SERVICE_KEY}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify({
        id,
        user_id: userId,
        email,
        platform,
        app_version: appVersion,
        message,
        meta: {
          device_name: deviceName,
          os_version: osVersion,
          ...(screenshotPath ? { screenshot: screenshotPath } : {}),
        },
      }),
    });
    if (!r.ok) {
      console.error(`report-issue: insert failed ${r.status} — ${(await r.text()).slice(0, 400)}`);
      if (screenshotPath) console.error(`report-issue: orphaned screenshot ${screenshotPath}`);
      return json({ ok: false, error: "save_failed" }, 500);
    }
  } catch (e) {
    console.error(`report-issue: insert threw — ${String(e)}`);
    return json({ ok: false, error: "save_failed" }, 500);
  }

  const emailed = await sendEmail({
    id, userId, email, platform, appVersion, message, deviceName, osVersion,
    image: screenshotPath ? image : null,
  });

  return json({ ok: true, id, emailed, screenshot: Boolean(screenshotPath) });
});
