// invite-member — creates an organization invite and emails the claim link.
// IDI-216 Phase 2 (2026-08).
//
// Modelled on `delete-account`: `verify_jwt` is ON, so the gateway rejects anything
// without a valid Supabase JWT before this code runs, and the caller's identity is
// decoded from THAT JWT locally (no getUser round-trip) — never from the body. A
// caller can therefore only ever invite into an org they are already an owner/admin
// of, which this function re-checks against the DB rather than trusting the client.
//
// FAIL-CLOSED, and in particular NO PARTIAL INVITE: the invite row is written first
// and DELETED again if the email send fails, so an admin never sees a "pending"
// invite for a mail that was never delivered. The raw token is returned to the
// caller only so the desktop/mobile UI can offer "copy invite link" — the DB stores
// nothing but its sha256, so a leaked row cannot be replayed (see
// whisperflow/supabase_organizations.sql).
//
// SECRETS: RESEND_API_KEY + INVITE_FROM_EMAIL (a verified sending domain — invites
// will NOT deliver until that domain is verified in Resend). Handled exactly like
// GROQ_API_KEY/OLLAMA_API_KEY: `supabase secrets set`, never in a client bundle.
// Without RESEND_API_KEY the function refuses with `email_not_configured` rather
// than silently creating invites nobody receives.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { FLUME_ICON_B64 } from "./flume-icon.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY") ?? "";
// Normalise the From header. INVITE_FROM_EMAIL is currently a BARE address
// (sraza@idiaz.io), which every client renders as the raw address — an invite that
// appears to come from a person's mailbox rather than the product reads like a
// mistake, and looks worse in a crowded inbox. Wrapping a bare value in a display
// name fixes it here so nobody has to remember the RFC-5322 shape when setting the
// secret. Already-wrapped values ("Flume <x@y>") pass through untouched.
const RAW_FROM = Deno.env.get("INVITE_FROM_EMAIL") ?? "invites@flume.app";
const FROM_EMAIL = RAW_FROM.includes("<") ? RAW_FROM : `Flume <${RAW_FROM}>`;
// Where the claim link points.
//
// INTERIM DESTINATION: `idiaz.io/flume/download.html` is the real, live marketing
// download page — it does NOT yet consume `?t=<token>` to auto-claim into
// `verbal://team-invite?t=<token>` (the mobile app's REGISTERED scheme is `verbal`,
// app.json — `flume://` appears only in the pairing QR payload, parsed by the app
// itself rather than the OS). The token still rides the query string so a future
// version of that page can pick it up with no email/function change. Until then,
// invites still work end to end: the recipient downloads the app from the page they
// land on, then pastes the same link (or bare token) into the "Have an invite?"
// field on the desktop dashboard's Team screen or the mobile Team screen.
// 2026-08-29: the link now lands on the `invite` Edge Function, which opens the
// installed app via `flume://invite?t=…` and falls back to the download page
// (token preserved) when nothing answers — see supabase/functions/invite.
const CLAIM_BASE = Deno.env.get("INVITE_CLAIM_URL") ??
  `${Deno.env.get("SUPABASE_URL") ?? "https://ovpcthjingugwvpxlsna.supabase.co"}/functions/v1/invite`;

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

function svcHeaders(withJson = false): Record<string, string> {
  const h: Record<string, string> = { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}` };
  if (withJson) h["Content-Type"] = "application/json";
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

// RFC-shaped enough to reject the mistakes people actually make in an invite box.
// Deliberately not a full grammar — the real validation is whether the mail lands.
const EMAIL_RE = /^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]{2,}$/;

function randomToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function sha256Hex(s: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function rest(path: string, init: RequestInit = {}): Promise<Response> {
  return await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    ...init,
    headers: { ...svcHeaders(init.body !== undefined), ...(init.headers ?? {}) },
  });
}

function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));
}

// Shared font stacks — inlined into every styled element below (email clients
// don't resolve external/registered fonts), but centralised here so the brand's
// two-typeface system (Geist for UI, JetBrains Mono for numerics/meta —
// context/05-conventions.md) reads as one deliberate choice instead of copy-pasted
// stacks that could quietly drift apart across the ~20 elements that use them.
const FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif";
const MONO = "ui-monospace,'SF Mono',SFMono-Regular,Menlo,Consolas,monospace";

function inviteEmail(
  orgName: string,
  inviterName: string,
  link: string,
  resend: boolean,
): { subject: string; html: string; text: string } {
  const org = esc(orgName);
  const who = esc(inviterName || "A teammate");
  const subject = resend
    ? `Reminder: ${inviterName || "someone"} invited you to ${orgName}`
    : `${inviterName || "Someone"} invited you to ${orgName} on Flume`;

  // PREHEADER: the grey line Gmail/Apple Mail show next to the subject. With no
  // preheader, clients scrape the first text in the body — which was the "✳ FLUME"
  // wordmark, so the inbox preview read "✳ FLUME ✳ FLUME". This is the single
  // highest-leverage line in the whole email and it is invisible once opened.
  const preheader = resend
    ? `Your invite to ${orgName} is still open — it expires in 7 days.`
    : `Join ${orgName} and your first dictation already knows their names and jargon.`;

  // Wordmark lockup: the actual mascot mark (rasterized from the same vector as
  // idiaz.io/flume's nav, sent as a `cid:` inline attachment — see `sendEmail` —
  // not a hosted URL, so there's no new bucket/CDN and it still survives strict
  // remote-image blocking) next to the lowercase "flume" wordmark, the same
  // pairing as the site nav.
  const logo = `
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
  <td><img src="cid:flume-icon" width="26" height="28" alt="" style="display:block"></td>
  <td style="padding-left:10px;font-family:${FONT};font-size:15px;font-weight:700;color:#201d17">flume</td>
</tr></table>`;

  // Eyebrow pill — a white chip on the blue header band, echoing the dotted tags
  // on the site's hero ("VOICE-FIRST WRITING", "LIVE") but built to sit on a
  // colour panel instead of a dark one.
  const eyebrow = `
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
  <td bgcolor="#fffdf8" style="border-radius:999px;padding:6px 14px;font-family:${MONO};font-size:10px;letter-spacing:.16em;font-weight:600;color:#C85A3E">&#9679;&nbsp;&nbsp;TEAM INVITE</td>
</tr></table>`;

  // Window-chrome mockup: the same three-dot titlebar as the site's actual
  // macOS/Windows screenshots (download.html's light "Flume — macOS" panels),
  // wrapped around the one thing worth showing rather than describing — a single
  // ambiguous line, and the same line once Flume knows the team's names and
  // jargon. This is the whole reason to join a team, and (being text, not a
  // screenshot image) it survives image blocking.
  //
  // FIXED (2026-08-20, user feedback): the previous example read "On {org}:
  // Idiaz needs a new one" — Idiaz is OUR company name, hardcoded into the
  // example copy, so any org name next to it looked like a typo or a leaked
  // placeholder rather than a deliberate before/after. The fix disambiguates a
  // PERSON (a first name that could be anyone) and a THING (a vague "the
  // deploy") — neither string is a stray proper noun, so the point ("Flume
  // fills in the specifics your team already knows") reads clearly no matter
  // what {org} actually is.
  // NO traffic-light dots here (user feedback, 2026-08-21): three red/yellow/
  // green circles next to a titlebar label reads as macOS window chrome — i.e.
  // "this is a native app", which Flume's marketing screenshots can afford to
  // imply and an EMAIL cannot (nobody should think they're looking at a live
  // window). The mono label alone still gives the "this is showing you the
  // product" cue without the close/minimize/zoom implication.
  const whatChanges = `
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#fffdf8;border-radius:10px;border:1px solid #ecdfc4">
  <tr><td style="padding:12px 16px;border-bottom:1px solid #ecdfc4">
    <div style="font-family:${MONO};font-size:9.5px;letter-spacing:.14em;font-weight:600;color:#9a8f78">FLUME &mdash; DICTIONARY</div>
  </td></tr>
  <tr><td style="padding:14px 18px 16px">
    <div style="font-family:${FONT};font-size:15px;line-height:1.55;color:#9a8f78;padding-bottom:5px">
      Alone: &ldquo;Ping Sam about the deploy.&rdquo;
    </div>
    <div style="font-family:${FONT};font-size:15px;line-height:1.55;color:#201d17">
      On ${org}: &ldquo;Ping <strong style="color:#C85A3E">Sam Okafor</strong> about the <strong style="color:#C85A3E">auth&#8209;service</strong> deploy.&rdquo;
    </div>
  </td></tr>
</table>`;

  // Two-line mono index, echoing the hero's numbered "01 / 02 / 03" feature rows.
  const featureRow = (n: string, label: string, body: string) => `
<tr><td style="padding:${n === "01" ? "0" : "12px"} 0 0">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
    <td valign="top" style="font-family:${MONO};font-size:11px;font-weight:700;color:#C85A3E;padding-right:10px;white-space:nowrap">${n}</td>
    <td style="font-family:${FONT};font-size:14px;line-height:1.55;color:#5b5346">
      <span style="font-family:${MONO};font-size:10px;letter-spacing:.1em;font-weight:600;color:#9a8f78">${esc(label)}</span><br>${body}
    </td>
  </tr></table>
</td></tr>`;

  // Table-based button, not a padded <a>. Outlook for Windows ignores padding on
  // an anchor and collapses it to bare underlined text, which is the difference
  // between a call to action and a link nobody clicks.
  const button = `
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 10px">
  <tr><td align="center" bgcolor="#C85A3E" style="border-radius:10px">
    <a href="${esc(link)}" style="display:inline-block;padding:14px 30px;font-family:${FONT};font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:10px">Accept invitation&nbsp;&rarr;</a>
  </td></tr>
</table>`;

  // LIGHT THEME (2026-08-20, user feedback): the dark card read as generic SaaS
  // chrome and didn't match idiaz.io — specifically the soft sky-blue the site's
  // OWN light surfaces use (download.html's hero). The header band below reuses
  // that exact blue; the body below it drops to a warm paper cream rather than
  // white, so the card still has the site's "printed on something," not
  // "rendered in a browser," warmth.
  const html = `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<!-- Tell clients we have designed both, so they stop auto-inverting our palette. -->
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>${subject}</title>
</head>
<body style="margin:0;padding:0;background:#f3ecdd;">
<!-- preheader: shown in the inbox list, hidden in the opened mail -->
<div style="display:none;font-size:1px;color:#f3ecdd;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden">${esc(preheader)}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f3ecdd">
<tr><td align="center" style="padding:32px 16px">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:480px;border-radius:16px;background:#fffdf8">
  <tr><td bgcolor="#d3e6f0" style="background-color:#d3e6f0;background-image:radial-gradient(circle 34px at 372px 34px,rgba(255,255,255,.92) 0%,rgba(255,255,255,.92) 65%,rgba(255,255,255,0) 100%),radial-gradient(circle 26px at 404px 22px,rgba(255,255,255,.92) 0%,rgba(255,255,255,.92) 65%,rgba(255,255,255,0) 100%),radial-gradient(circle 22px at 428px 40px,rgba(255,255,255,.88) 0%,rgba(255,255,255,.88) 65%,rgba(255,255,255,0) 100%),radial-gradient(circle 20px at 350px 46px,rgba(255,255,255,.8) 0%,rgba(255,255,255,.8) 65%,rgba(255,255,255,0) 100%),radial-gradient(circle 16px at 58px 148px,rgba(255,255,255,.8) 0%,rgba(255,255,255,.8) 65%,rgba(255,255,255,0) 100%),radial-gradient(circle 12px at 78px 140px,rgba(255,255,255,.75) 0%,rgba(255,255,255,.75) 65%,rgba(255,255,255,0) 100%),radial-gradient(circle 13px at 192px 20px,rgba(255,255,255,.85) 0%,rgba(255,255,255,.85) 65%,rgba(255,255,255,0) 100%),radial-gradient(circle 9px at 207px 13px,rgba(255,255,255,.85) 0%,rgba(255,255,255,.85) 65%,rgba(255,255,255,0) 100%),radial-gradient(circle 11px at 458px 112px,rgba(255,255,255,.75) 0%,rgba(255,255,255,.75) 65%,rgba(255,255,255,0) 100%),radial-gradient(circle 8px at 468px 104px,rgba(255,255,255,.75) 0%,rgba(255,255,255,.75) 65%,rgba(255,255,255,0) 100%);border-radius:16px 16px 0 0;padding:28px 32px 24px">
    <!-- A handful of small clouds on the sky-blue band — each one is 2-4
         overlapping radial-gradient circles (not a single blob, or it reads as
         a light leak rather than a cloud), CSS not an image. Solid through ~65%
         of each circle's radius then a short fade (not a fade from the very
         center) so they read as puffs with an edge, not a blur/glow — user
         feedback, 2026-08-21. Outlook falls back to the plain bgcolor above;
         everyone else gets a little sky. Still sparse: small clouds, not a
         pattern. -->
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr><td>${logo}</td></tr>
      <tr><td style="padding-top:20px">${eyebrow}</td></tr>
      <tr><td style="padding-top:16px">
        <div style="font-family:${FONT};font-size:24px;line-height:1.3;font-weight:700;color:#201d17">
          ${who} invited you to<br><span style="color:#C85A3E">${org}.</span>
        </div>
      </td></tr>
      <tr><td style="padding-top:12px">
        <div style="font-family:${FONT};font-size:15px;line-height:1.6;color:#3c4a52">
          Flume turns your voice into clean text &mdash; and on ${org}, it already knows the names and jargon you use every day.
        </div>
      </td></tr>
    </table>
  </td></tr>

  <tr><td style="padding:24px 32px 0">${whatChanges}</td></tr>

  <tr><td style="padding:20px 32px 0">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
      ${featureRow("01", "SHARED DICTIONARY", `${org}&rsquo;s names, tools, and jargon &mdash; already agreed on.`)}
      ${featureRow("02", "STILL YOURS", "Your own words win if the two ever disagree.")}
    </table>
  </td></tr>

  <tr><td align="left" style="padding:26px 32px 0">${button}</td></tr>

  <tr><td style="padding:0 32px 8px">
    <div style="font-family:${MONO};font-size:10px;letter-spacing:.12em;font-weight:600;color:#9a8f78">EXPIRES IN 7 DAYS &middot; WORKS ONCE</div>
  </td></tr>

  <tr><td style="padding:18px 32px 28px">
    <div style="font-family:${FONT};font-size:12px;line-height:1.65;color:#7a7060;border-top:1px solid #ecdfc4;padding-top:16px">
      This link only works for <strong style="color:#5b5346">this email address</strong>.
      Nothing is shared until you accept, and what you dictate is never shared with your team.
    </div>
  </td></tr>
</table>

<div style="font-family:${FONT};font-size:11px;color:#a49a86;padding:18px 10px 0;max-width:480px">
  Not expecting this? You can ignore it &mdash; no account is created and nothing is shared.
</div>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:480px"><tr><td align="center" style="padding:22px 0 0">
  <img src="cid:flume-icon" width="30" height="33" alt="Flume" style="display:block;opacity:.6">
</td></tr></table>
<div style="font-family:${MONO};font-size:9.5px;letter-spacing:.14em;color:#b5ab97;text-align:center;padding:10px 10px 0;max-width:480px">&copy;&nbsp;2026 FLUME</div>

</td></tr></table>
</body></html>`;

  // Plain text is not a throwaway: spam filters weight it, and some clients show it
  // by default. It mirrors the same structure rather than being a bare URL dump.
  const text = [
    `TEAM INVITE`,
    ``,
    `${inviterName || "Someone"} invited you to join ${orgName} on Flume.`,
    ``,
    `Flume turns your voice into clean text - and on ${orgName}, it already knows`,
    `the names and jargon you use every day.`,
    ``,
    `FLUME — DICTIONARY`,
    `  Alone:        "Ping Sam about the deploy."`,
    `  On ${orgName}: "Ping Sam Okafor about the auth-service deploy."`,
    ``,
    `01 SHARED DICTIONARY - ${orgName}'s names, tools, and jargon, already agreed on.`,
    `02 STILL YOURS        - your own words win if the two ever disagree.`,
    ``,
    `Accept your invitation:`,
    link,
    ``,
    `Expires in 7 days - works once.`,
    `This link only works for this email address. Nothing is shared until you`,
    `accept, and what you dictate is never shared with your team.`,
    ``,
    `Not expecting this? Ignore it - no account is created and nothing is shared.`,
    ``,
    `© 2026 Flume`,
  ].join("\n");

  return { subject, html, text };
}

async function sendEmail(to: string, orgName: string, inviterName: string, link: string, resend: boolean, replyTo?: string): Promise<{ ok: boolean; detail?: string }> {
  const { subject, html, text } = inviteEmail(orgName, inviterName, link, resend);
  try {
    const payload: Record<string, unknown> = {
      from: FROM_EMAIL, to: [to], subject, html, text,
      // The mascot mark travels WITH the email as a `cid:` inline attachment
      // (referenced twice in the HTML above) rather than a hosted <img src>
      // pointing at some bucket/CDN — no new public storage surface to stand up
      // or secure, and it renders even for recipients who block remote images
      // (only their client's own inline-image gate applies, same as any image).
      //
      // content_type is NOT optional in practice (2026-08-21 bug): Resend's docs
      // say it's "auto-derived from filename if not set", but calling the raw
      // POST /emails HTTP API directly (as this function does) left the
      // attachment tagged `application/octet-stream` — mail clients won't render
      // an octet-stream attachment inline via `cid:` even with a matching
      // content_id, so the icon showed as a blank/broken image. Set explicitly.
      attachments: [{
        filename: "flume-icon.png", content: FLUME_ICON_B64, content_id: "flume-icon",
        content_type: "image/png",
      }],
    };
    // Reply-To the person who actually invited them. "Who is this?" is the first
    // reaction to an unexpected invite, and a reply that reaches a colleague beats
    // one that bounces off a no-reply mailbox. Also a mild deliverability positive.
    if (replyTo && /^[^\s@]+@[^\s@]+$/.test(replyTo)) payload.reply_to = replyTo;
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${RESEND_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (r.ok) return { ok: true };
    const body = (await r.text()).slice(0, 400);
    // LOG IT SERVER-SIDE. The detail is returned to the caller too, but both
    // clients collapse a failed invite into a friendly one-liner, so without this
    // the only copy of the actual reason (unverified domain, sandbox recipient
    // restriction, bad key) is discarded and the failure is undiagnosable.
    // Logs the FROM address too, since a misconfigured INVITE_FROM_EMAIL is the
    // likeliest cause. Never logs the token or the recipient's address.
    console.error(`invite-member: resend rejected ${r.status} — ${body}`);
    console.error(`invite-member: from=${FROM_EMAIL}`);
    return { ok: false, detail: `resend: ${r.status} ${body}` };
  } catch (e) {
    console.error(`invite-member: resend threw — ${String(e)}`);
    return { ok: false, detail: `resend: ${String(e)}` };
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ ok: false, error: "Method not allowed" }, 405);

  const inviterId = userIdFromJwt(req.headers.get("Authorization") ?? "");
  if (!inviterId) return json({ ok: false, error: "not_authenticated" }, 401);

  let body: { org_id?: string; email?: string; role?: string };
  try {
    body = await req.json();
  } catch {
    return json({ ok: false, error: "bad_request" }, 400);
  }

  const orgId = String(body.org_id ?? "").trim();
  const email = String(body.email ?? "").trim().toLowerCase();
  const role = body.role === "admin" ? "admin" : "member";
  if (!orgId) return json({ ok: false, error: "org_required" }, 400);
  if (!EMAIL_RE.test(email)) return json({ ok: false, error: "bad_email" }, 400);
  if (!RESEND_API_KEY) {
    console.error("invite-member: RESEND_API_KEY is not set");
    return json({ ok: false, error: "email_not_configured" }, 503);
  }

  // Authorization: the caller must be an ACTIVE owner/admin of this org. Checked
  // against the DB with the service role — the JWT proves who they are, not what
  // they may do.
  const meRes = await rest(
    `organization_members?select=role,display_name,email&org_id=eq.${encodeURIComponent(orgId)}` +
      `&user_id=eq.${encodeURIComponent(inviterId)}&status=eq.active`,
  );
  if (!meRes.ok) return json({ ok: false, error: "lookup_failed" }, 500);
  const me = (await meRes.json())[0];
  if (!me || (me.role !== "owner" && me.role !== "admin")) {
    return json({ ok: false, error: "forbidden" }, 403);
  }

  const orgRes = await rest(`organizations?select=name,purchased_seats&id=eq.${encodeURIComponent(orgId)}`);
  if (!orgRes.ok) return json({ ok: false, error: "lookup_failed" }, 500);
  const org = (await orgRes.json())[0];
  if (!org) return json({ ok: false, error: "no_such_org" }, 404);

  // SEATS ARE NOT CHECKED HERE (IDI-219 + IDI-223 #3). The first cut counted
  // active members PLUS pending invites against the plan and refused at dispatch —
  // which is precisely the seat-allocation deadlock IDI-223 forbids: an admin with
  // 5 seats and 5 unaccepted invites could not invite anybody else, even though not
  // one of those invites had consumed a seat.
  //
  // Enforcement moved to ACCEPTANCE (org_claim_invite), where a seat is actually
  // taken. Dispatch only reports the numbers so the UI can warn.
  //
  // Accepted trade-off: an admin may now send more invites than they have seats,
  // and the surplus acceptors hit `no_seats` with an upgrade prompt. That is the
  // behaviour the tickets specify, and it is the lesser evil — a blocked admin is
  // worse than a late upsell.
  const seatRes = await rest(
    `organization_members?select=user_id&org_id=eq.${encodeURIComponent(orgId)}&status=eq.active`,
    { headers: { Prefer: "count=exact", Range: "0-0" } },
  );
  const countOf = (r: Response) => Number((r.headers.get("content-range") ?? "").split("/")[1] ?? "0");
  const activeMembers = countOf(seatRes);
  const purchasedSeats = Number(org.purchased_seats ?? 0);

  // Already a member, or already invited and still pending? Both are no-ops rather
  // than errors the admin has to interpret — but they must not mint a second token.
  const dupeRes = await rest(
    `organization_members?select=user_id&org_id=eq.${encodeURIComponent(orgId)}` +
      `&email=eq.${encodeURIComponent(email)}&status=eq.active`,
  );
  if (dupeRes.ok && (await dupeRes.json()).length > 0) {
    return json({ ok: false, error: "already_member" }, 409);
  }

  // IDI-220: a repeat invite UPDATES the existing pending row — new token, pushed
  // expiry — and resends. The first cut revoked and inserted, which grows the table
  // by one dead row per nudge. A partial unique index on
  // (org_id, lower(email)) WHERE status='pending' makes this enforceable rather
  // than merely intended, so a racing double-submit cannot mint two live tokens.
  const token = randomToken();
  const tokenHash = await sha256Hex(token);
  const expiresAt = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString();

  const existingRes = await rest(
    `organization_invites?select=id&org_id=eq.${encodeURIComponent(orgId)}` +
      `&email=eq.${encodeURIComponent(email)}&status=eq.pending&limit=1`,
  );
  const existing = existingRes.ok ? (await existingRes.json())[0] : null;

  let invite: { id: string; expires_at: string } | null = null;
  let reissued = false;
  if (existing) {
    reissued = true;
    const patchRes = await rest(`organization_invites?id=eq.${encodeURIComponent(existing.id)}`, {
      method: "PATCH",
      headers: { Prefer: "return=representation" },
      body: JSON.stringify({ token_hash: tokenHash, role, expires_at: expiresAt, invited_by: inviterId }),
    });
    if (!patchRes.ok) {
      return json({ ok: false, error: "insert_failed", detail: (await patchRes.text()).slice(0, 300) }, 500);
    }
    invite = (await patchRes.json())[0];
  } else {
    const insertRes = await rest("organization_invites", {
      method: "POST",
      headers: { Prefer: "return=representation" },
      body: JSON.stringify({
        org_id: orgId, email, token_hash: tokenHash, role,
        invited_by: inviterId, status: "pending", expires_at: expiresAt,
      }),
    });
    if (!insertRes.ok) {
      return json({ ok: false, error: "insert_failed", detail: (await insertRes.text()).slice(0, 300) }, 500);
    }
    invite = (await insertRes.json())[0];
  }

  const link = `${CLAIM_BASE}?t=${encodeURIComponent(token)}`;
  const sent = await sendEmail(email, String(org.name ?? "your team"),
                               String(me.display_name || me.email || ""), link, reissued,
                               String(me.email || ""));
  if (!sent.ok) {
    // No partial invite: roll back so the roster never shows a pending invite for a
    // mail that was never sent (IDI-216's failure table).
    //
    // But only delete a row WE created. A re-issued invite existed before this
    // request — destroying it because a resend bounced would revoke a perfectly
    // good outstanding invite the recipient may already be holding.
    if (!reissued) {
      await rest(`organization_invites?id=eq.${encodeURIComponent(invite!.id)}`, { method: "DELETE" });
    }
    return json({ ok: false, error: "email_failed", detail: sent.detail, reissued }, 502);
  }

  return json({
    ok: true,
    invite: { id: invite!.id, email, role, expires_at: invite!.expires_at },
    // True when this nudged an existing invite rather than creating one, so the UI
    // can say "invite resent" instead of "invite sent".
    reissued,
    // Reported, not enforced (see the seat comment above) — the dashboard warns
    // when invites outnumber seats.
    seats: { purchased: purchasedSeats, active: activeMembers },
    // For "copy invite link" in the admin UI. Never stored in this form.
    link,
  });
});
