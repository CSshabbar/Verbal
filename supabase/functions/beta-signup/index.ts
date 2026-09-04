// beta-signup — receives the public beta form (idiaz.io/flume/beta.html):
// name + email. Saves a `beta_signups` row, sends the tester a branded
// welcome email with the download links, and notifies the founder that a
// new person signed up. Beta-launch feature (2026-09).
//
// `verify_jwt` is OFF (the `download`/`invite` posture): this is a public
// marketing form — a visitor has no Supabase session and the static page
// embeds no key. The abuse surface is bounded instead by:
//   - a hidden honeypot field (`company`) — bots that fill it get a fake OK,
//   - a per-IP rate limit (sha-256 of the caller IP, counted in-table),
//   - duplicate emails re-send the welcome but never re-notify the founder,
//     capped at 5 sends per row and 15 minutes apart (a silent duplicate
//     looked like "the email never sent" — 2026-09-04 user report),
//   - hard length caps + header sanitisation on everything user-controlled.
//
// ORDER MATTERS (the report-issue posture): the DB insert happens FIRST and
// alone decides success — the tester gets the download buttons on-screen
// either way, so BOTH emails are strictly best-effort. A Resend outage must
// never lose a signup or surface an error to the tester.
//
// EMAIL DESIGN (reworked 2026-09-04, user feedback): matches the LIGHT
// idiaz.io/flume marketing theme, same as beta.html — soft sky ground, paper
// card, lime #d9e7a4 hero band, dark #1d2312 pill buttons, the dark
// window-chrome before/after demo, JBM "///" mono meta. (The first version
// reused invite-member's cream/sky-band layout; the user disliked it.)
//
// SECRETS (all shared with invite-member / report-issue where they exist):
//   RESEND_API_KEY      — without it both email steps are skipped, signups still save
//   INVITE_FROM_EMAIL   — the verified From address (bare or RFC-5322 wrapped)
//   ISSUE_REPORT_EMAIL  — founder notification recipient; defaults to the founder
//   FLUME_DOWNLOAD_FN   — override for the download function base URL
//   FLUME_ICON_URL      — override for the hosted email logo

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY") ?? "";
const RAW_FROM = Deno.env.get("INVITE_FROM_EMAIL") ?? "invites@flume.app";
const FROM_EMAIL = RAW_FROM.includes("<") ? RAW_FROM : `Flume <${RAW_FROM}>`;
const FOUNDER_TO = Deno.env.get("ISSUE_REPORT_EMAIL") ?? "sraza@idiaz.io";
const DOWNLOAD_FN = Deno.env.get("FLUME_DOWNLOAD_FN") ??
  `${SUPABASE_URL}/functions/v1/download`;
// HOSTED image, not a cid: inline attachment (2026-09-04): the cid icon
// rendered as a broken image in the founder's own mail client even though the
// attachment and PNG were verified intact — cid handling is flaky per client,
// and Gmail/Apple Mail load (and proxy) https images by default. The PNG is
// published with the flume-site (source: Verbal repo site/flume/flume-mark-128.png —
// the 128px mascot-head app icon, resized from
// whisperflow/assets/brand/flume-mascot-head.png; user-picked).
// Bonus: no attachment means no paperclip indicator on the email.
// VERSIONED filename (2026-09-04): Gmail's image proxy caches per-URL, so when
// the icon changed under the old flume-icon.png URL, recipients who had opened
// an earlier email kept seeing the cached old mark. Any future icon change must
// ship as a NEW filename here, never by overwriting the current one.
const ICON_URL = Deno.env.get("FLUME_ICON_URL") ??
  "https://idiaz.io/flume/flume-mark-128.png";

const NAME_MAX = 80;
const EMAIL_MAX = 254;
const RATE_LIMIT_PER_HOUR = 8;
const WELCOME_SENDS_MAX = 5;
const WELCOME_RESEND_GAP_MS = 15 * 60_000;
const PLATFORMS = new Set(["mac", "win", "ios", "android"]);

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

function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));
}

// IDI-267 precedent: `name` reaches the Subject header of both emails. A CR/LF
// smuggled through it is RFC-5322 header injection, so strip every control
// character, collapse whitespace, and cap the length before any use.
function cleanHeaderText(s: string, max: number): string {
  return s.replace(/[\x00-\x1f\x7f]+/g, " ").replace(/\s{2,}/g, " ").trim().slice(0, max);
}

function isValidEmail(e: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e) && e.length <= EMAIL_MAX;
}

async function sha256Hex(s: string): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function svc(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    ...init,
    headers: {
      apikey: SERVICE_KEY,
      Authorization: `Bearer ${SERVICE_KEY}`,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
}

// ── Welcome email — the beta page's light theme, as bulletproof tables ──────
// Same components as beta.html: paper #fffdf8 card on a soft-sky ground, lime
// #d9e7a4 hero band with the "///" eyebrow, dark #1d2312 pill buttons, the
// dark #0a0c0e window-chrome before/after demo, 01/02/03 mono rows. Solid hex
// colors only (no rgba — Outlook), fonts inlined per element (email clients
// don't share <style>).

const FONT = "'Geist',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif";
const MONO = "'JetBrains Mono',ui-monospace,'SF Mono',SFMono-Regular,Menlo,Consolas,monospace";

// The mono meta signature: 10px, wide-tracked, uppercase — color per use.
function meta(color: string, text: string): string {
  return `<span style="font-family:${MONO};font-size:10px;letter-spacing:.14em;font-weight:600;text-transform:uppercase;color:${color}">${text}</span>`;
}

function welcomeEmail(
  name: string,
  platformHint: string,
): { subject: string; html: string; text: string } {
  const first = esc(name.split(/\s+/)[0] || "there");
  const subject = `You're in — here's Flume`;
  const preheader = `Your download links are inside. Install on your Mac or PC, sign in with this email, and talk.`;

  const macUrl = `${DOWNLOAD_FN}?platform=mac`;
  const winUrl = `${DOWNLOAD_FN}?platform=win`;
  const macFirst = platformHint !== "win";

  // The site's dark pill button + its quiet outlined sibling.
  const solidBtn = (href: string, label: string) => `
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="display:inline-table;margin:0 8px 8px 0">
  <tr><td align="center" bgcolor="#1d2312" style="border-radius:999px">
    <a href="${esc(href)}" style="display:inline-block;padding:13px 24px;font-family:${FONT};font-size:14px;font-weight:600;color:#f2f2f2;text-decoration:none;border-radius:999px">${label}&nbsp;&rarr;</a>
  </td></tr>
</table>`;
  const ghostBtn = (href: string, label: string) => `
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="display:inline-table;margin:0 0 8px">
  <tr><td align="center" bgcolor="#fffdf8" style="border-radius:999px;border:1px solid #cfc9bb">
    <a href="${esc(href)}" style="display:inline-block;padding:12px 22px;font-family:${FONT};font-size:14px;font-weight:600;color:#1d2312;text-decoration:none;border-radius:999px">${label}</a>
  </td></tr>
</table>`;
  const buttons = macFirst
    ? solidBtn(macUrl, "Download for Mac") + ghostBtn(winUrl, "Download for Windows")
    : solidBtn(winUrl, "Download for Windows") + ghostBtn(macUrl, "Download for Mac");

  // Lockup + lime "PRIVATE BETA" chip — the beta page's nav row.
  const headerRow = `
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
  <td>
    <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
      <td><img src="${ICON_URL}" width="26" height="26" alt="" style="display:block;border-radius:6px"></td>
      <td style="padding-left:9px;font-family:${FONT};font-size:15px;font-weight:700;color:#1d2312">flume</td>
    </tr></table>
  </td>
  <td align="right">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="display:inline-table"><tr>
      <td bgcolor="#d9e7a4" style="border-radius:999px;padding:6px 13px">${meta("#1d2312", "Private beta")}</td>
    </tr></table>
  </td>
</tr></table>`;

  // Lime hero band — the beta page's pitch panel.
  const limeBand = `
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#d9e7a4;border-radius:12px">
  <tr><td style="padding:22px 24px 24px">
    ${meta("#6b7248", "/// Early access")}
    <div style="font-family:${FONT};font-size:25px;line-height:1.25;font-weight:700;color:#1d2312;padding-top:9px">
      You're in, ${first}<span style="color:#C85A3E">.</span>
    </div>
    <div style="font-family:${FONT};font-size:14px;line-height:1.6;color:#3c4526;padding-top:8px">
      Flume turns your voice into clean, finished text in any app on your Mac or PC. Here are your links &mdash; also handy later, when you're back at your computer.
    </div>
  </td></tr>
</table>`;

  // The dark window-chrome demo, exactly as it appears on the beta page.
  const demo = `
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0a0c0e;border-radius:12px">
  <tr><td style="padding:10px 14px;border-bottom:1px solid #26282b">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
      <td><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#ff5f57"></span></td>
      <td style="padding-left:6px"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#febc2e"></span></td>
      <td style="padding-left:6px"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#28c840"></span></td>
      <td style="padding-left:11px">${meta("#8a8d90", "Flume &mdash; Dictation")}</td>
    </tr></table>
  </td></tr>
  <tr><td style="padding:13px 16px 15px">
    <div style="font-family:${FONT};font-size:14px;line-height:1.55;color:#7d8084;padding-bottom:5px">
      You say: &ldquo;um so basically can we uh move the standup to thursday&rdquo;
    </div>
    <div style="font-family:${FONT};font-size:14px;line-height:1.55;color:#f2f2f2">
      Flume types: &ldquo;<strong style="color:#f0b39a;font-weight:600">Can we move the standup to Thursday?</strong>&rdquo;
    </div>
  </td></tr>
</table>`;

  // 01/02/03 rows — terracotta numbers, mono labels (the site's index pattern).
  const stepRow = (n: string, label: string, body: string, firstRow = false) => `
<tr><td style="padding:${firstRow ? "0" : "11px"} 0 0">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
    <td valign="top" style="font-family:${MONO};font-size:11px;font-weight:700;color:#C85A3E;padding-right:10px;white-space:nowrap">${n}</td>
    <td style="font-family:${FONT};font-size:13.5px;line-height:1.55;color:#4a453c">
      ${meta("#948d7d", label)}<br>${body}
    </td>
  </tr></table>
</td></tr>`;

  const html = `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>${esc(subject)}</title>
</head>
<body style="margin:0;padding:0;background:#d6e8f4;">
<div style="display:none;font-size:1px;color:#d6e8f4;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden">${esc(preheader)}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#d6e8f4">
<tr><td align="center" style="padding:30px 14px">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:480px;border-radius:16px;background:#fffdf8">
  <tr><td style="padding:20px 22px 0">${headerRow}</td></tr>
  <tr><td style="padding:16px 22px 0">${limeBand}</td></tr>
  <tr><td align="left" style="padding:18px 22px 0">${buttons}</td></tr>
  <tr><td style="padding:10px 22px 0">${demo}</td></tr>
  <tr><td style="padding:18px 22px 0">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
      ${stepRow("01", "Install", "Open the download on your Mac or PC and drag it in &mdash; under a minute.", true)}
      ${stepRow("02", "Sign in", "Use <strong style=\"color:#1d2312\">this email address</strong> &mdash; it's how your dictionary and snippets follow you.")}
      ${stepRow("03", "Hold the hotkey &amp; talk", "Release, and clean text lands wherever your cursor is.")}
    </table>
  </td></tr>
  <tr><td style="padding:18px 22px 22px">
    <div style="font-family:${FONT};font-size:12px;line-height:1.65;color:#7a7060;border-top:1px solid #ece5d6;padding-top:14px">
      You're one of the first people using Flume, so your opinion carries real weight.
      <strong style="color:#4a453c">Reply to this email any time</strong> &mdash; it goes straight to the founder, not a ticket queue.
    </div>
  </td></tr>
</table>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:480px"><tr><td align="center" style="padding:20px 0 0">
  <img src="${ICON_URL}" width="30" height="30" alt="Flume" style="display:block;opacity:.55;border-radius:7px">
</td></tr></table>
<div style="text-align:center;padding:10px 10px 0;max-width:480px">${meta("#7e95a6", "&copy;&nbsp;2026 Flume &middot; Free during beta")}</div>

</td></tr></table>
</body></html>`;

  const text = [
    `PRIVATE BETA`,
    ``,
    `You're in, ${name.split(/\s+/)[0] || "there"}. Welcome to Flume.`,
    ``,
    `Flume turns your voice into clean, finished text - in any app on your`,
    `Mac or PC. Here are your links, so they're always one search away.`,
    ``,
    `Download for Mac:     ${macUrl}`,
    `Download for Windows: ${winUrl}`,
    ``,
    `FLUME — DICTATION`,
    `  You say:     "um so basically can we uh move the standup to thursday"`,
    `  Flume types: "Can we move the standup to Thursday?"`,
    ``,
    `01 INSTALL              - open the download and drag it in (under a minute).`,
    `02 SIGN IN              - use this email address; your dictionary follows you.`,
    `03 HOLD THE HOTKEY & TALK - release, and clean text lands at your cursor.`,
    ``,
    `You're one of the first people using Flume. Reply to this email any time -`,
    `it goes straight to the founder, not a ticket queue.`,
    ``,
    `© 2026 Flume · Free during beta`,
  ].join("\n");

  return { subject, html, text };
}

async function sendResend(payload: Record<string, unknown>, tag: string): Promise<boolean> {
  if (!RESEND_API_KEY) return false;
  try {
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${RESEND_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (r.ok) return true;
    // Log the real reason server-side (unverified domain, sandbox recipient,
    // bad key) — the tester never sees email failures, so this is the only copy.
    console.error(`beta-signup: resend(${tag}) rejected ${r.status} — ${(await r.text()).slice(0, 400)}`);
    console.error(`beta-signup: from=${FROM_EMAIL}`);
  } catch (e) {
    console.error(`beta-signup: resend(${tag}) threw — ${String(e)}`);
  }
  return false;
}

async function sendWelcome(to: string, name: string, platformHint: string): Promise<boolean> {
  const { subject, html, text } = welcomeEmail(name, platformHint);
  return await sendResend({
    from: FROM_EMAIL,
    to: [to],
    subject,
    html,
    text,
    // Replies land with the founder, not a no-reply void (invite-member precedent).
    reply_to: FOUNDER_TO,
  }, "welcome");
}

async function notifyFounder(row: {
  id: string; name: string; email: string; platformHint: string; count: number;
}): Promise<boolean> {
  const subject = `Flume beta signup #${row.count} — ${row.name}`;
  const lines = [
    `New beta signup through the form.`,
    ``,
    `Name:     ${row.name}`,
    `Email:    ${row.email}`,
    `Platform: ${row.platformHint || "unknown"}`,
    `Signup:   #${row.count}`,
    `Row id:   ${row.id}`,
  ];
  const text = lines.join("\n");
  const html = `<div style="font-family:ui-monospace,Menlo,monospace;font-size:13px;line-height:1.6;white-space:pre-wrap">${esc(text)}</div>`;
  return await sendResend({
    from: FROM_EMAIL, to: [FOUNDER_TO], subject, html, text, reply_to: row.email,
  }, "notify");
}

// ── Handler ─────────────────────────────────────────────────────────────────

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ ok: false, error: "method_not_allowed" }, 405);

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }

  // Honeypot: the form renders `company` off-screen and humans never fill it.
  // Bots that do get a convincing OK and no row, no email, no founder ping.
  if (typeof body.company === "string" && body.company.trim() !== "") {
    return json({ ok: true, already: false, emailed: true });
  }

  const name = cleanHeaderText(typeof body.name === "string" ? body.name : "", NAME_MAX);
  const email = (typeof body.email === "string" ? body.email : "").trim().toLowerCase().slice(0, EMAIL_MAX);
  if (!name) return json({ ok: false, error: "empty_name" }, 400);
  if (!isValidEmail(email)) return json({ ok: false, error: "invalid_email" }, 400);

  const rawHint = typeof body.platform_hint === "string" ? body.platform_hint.toLowerCase() : "";
  const platformHint = PLATFORMS.has(rawHint) ? rawHint : "";

  // Per-IP rate limit. Only a hash is stored; fails OPEN on any error — a
  // broken limiter must not turn away real testers (Hard Rule #1 posture).
  const ip = (req.headers.get("x-forwarded-for") ?? "").split(",")[0].trim();
  const ipHash = ip ? await sha256Hex(ip) : "";
  if (ipHash) {
    try {
      const since = new Date(Date.now() - 3600_000).toISOString();
      const r = await svc(
        `beta_signups?select=id&ip_hash=eq.${ipHash}&created_at=gte.${encodeURIComponent(since)}`,
        { method: "HEAD", headers: { Prefer: "count=exact" } },
      );
      const count = parseInt((r.headers.get("content-range") ?? "").split("/")[1] ?? "0", 10);
      if (Number.isFinite(count) && count >= RATE_LIMIT_PER_HOUR) {
        return json({ ok: false, error: "rate_limited" }, 429);
      }
    } catch (e) {
      console.error(`beta-signup: rate-limit check threw (failing open) — ${String(e)}`);
    }
  }

  // Insert. A duplicate email RE-SENDS the welcome (a silent duplicate looked
  // like "the email never sent" — 2026-09-04) but never re-notifies the
  // founder. Guards: the STORED name is used (a resubmit can't rewrite what
  // the email says), at most WELCOME_SENDS_MAX sends per row, and at least
  // WELCOME_RESEND_GAP_MS between sends — so the form can't be used to
  // mail-bomb an address someone else owns.
  let id = "";
  try {
    const r = await svc(`beta_signups`, {
      method: "POST",
      headers: { Prefer: "return=representation" },
      body: JSON.stringify({ name, email, platform_hint: platformHint, ip_hash: ipHash }),
    });
    if (r.status === 409) {
      try {
        const g = await svc(
          `beta_signups?email=eq.${encodeURIComponent(email)}&select=id,name,platform_hint,welcome_sends,last_welcome_at`,
        );
        const rows = g.ok ? await g.json() : [];
        const row = Array.isArray(rows) ? rows[0] : null;
        if (row) {
          const sends = Number(row.welcome_sends) || 0;
          const last = row.last_welcome_at ? Date.parse(String(row.last_welcome_at)) : 0;
          if (sends < WELCOME_SENDS_MAX && Date.now() - last > WELCOME_RESEND_GAP_MS) {
            const sent = await sendWelcome(
              email,
              String(row.name || name),
              String(row.platform_hint || platformHint),
            );
            if (sent) {
              await svc(`beta_signups?id=eq.${row.id}`, {
                method: "PATCH",
                body: JSON.stringify({
                  welcome_sends: sends + 1,
                  last_welcome_at: new Date().toISOString(),
                  welcome_emailed: true,
                }),
              });
            }
            return json({ ok: true, already: true, emailed: sent });
          }
        }
      } catch (e) {
        console.error(`beta-signup: duplicate re-send threw — ${String(e)}`);
      }
      return json({ ok: true, already: true, emailed: false });
    }
    if (!r.ok) {
      console.error(`beta-signup: insert failed ${r.status} — ${(await r.text()).slice(0, 400)}`);
      return json({ ok: false, error: "save_failed" }, 500);
    }
    const rows = await r.json();
    id = Array.isArray(rows) && rows[0]?.id ? String(rows[0].id) : "";
  } catch (e) {
    console.error(`beta-signup: insert threw — ${String(e)}`);
    return json({ ok: false, error: "save_failed" }, 500);
  }

  // Signup ordinal for the founder email ("signup #12"). Best-effort garnish.
  let count = 0;
  try {
    const r = await svc(`beta_signups?select=id`, {
      method: "HEAD", headers: { Prefer: "count=exact" },
    });
    count = parseInt((r.headers.get("content-range") ?? "").split("/")[1] ?? "0", 10) || 0;
  } catch { /* garnish only */ }

  const emailed = await sendWelcome(email, name, platformHint);
  const notified = await notifyFounder({ id, name, email, platformHint, count });

  // Record what actually went out — best-effort, the response is already decided.
  try {
    await svc(`beta_signups?id=eq.${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        welcome_emailed: emailed,
        founder_notified: notified,
        welcome_sends: emailed ? 1 : 0,
        last_welcome_at: emailed ? new Date().toISOString() : null,
      }),
    });
  } catch { /* row already saved; flags are triage aids */ }

  return json({ ok: true, already: false, emailed });
});
