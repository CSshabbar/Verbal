// Team-invite landing page (2026-08-29).
//
// The invite e-mail (invite-member) links here with `?t=<token>`. This page
// decides where the recipient lands:
//   * Flume installed  → the OS opens `flume://invite?t=<token>` and the running
//     (or freshly launched) app shows the "X invited you — Join" popup.
//   * Not installed    → after a short grace period, fall through to the
//     marketing download page, keeping the token in the URL so the first
//     sign-in after installing can still claim it.
//
// There is no reliable way for a web page to know whether a custom-scheme
// handler exists; the industry pattern (Slack/Zoom/Notion) is exactly this:
// try the scheme, and if the page is still the visible foreground document
// ~1.5 s later, nothing answered. The page also offers both actions as
// buttons, so a wrong guess costs one click, never the invite.
//
// Public endpoint (verify_jwt=false): the token is the only secret, and the
// page itself never reveals or redeems it — claiming happens inside the app
// against `org_claim_invite`.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const DOWNLOAD_PAGE = Deno.env.get("FLUME_DOWNLOAD_URL") ?? "https://idiaz.io/flume/download.html";
const SCHEME = "flume";
const OPEN_GRACE_MS = 1600;

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));
}

function isDesktop(ua: string): boolean {
  const s = ua.toLowerCase();
  if (/iphone|ipad|ipod|android/.test(s)) return false;
  return /windows|win32|win64|macintosh|mac os x/.test(s);
}

function page(token: string): string {
  const deep = `${SCHEME}://invite?t=${encodeURIComponent(token)}`;
  const dl = `${DOWNLOAD_PAGE}?t=${encodeURIComponent(token)}`;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>Join your team on Flume</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
  :root{color-scheme:dark}
  html,body{margin:0;height:100%;background:#0e1012;color:#f2efe9;font-family:Geist,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
  body{display:flex;align-items:center;justify-content:center;padding:24px}
  .card{max-width:440px;width:100%;text-align:center}
  .brand{color:#C85A3E;font-size:12px;letter-spacing:.2em;font-weight:600;margin-bottom:28px}
  h1{font-size:22px;font-weight:600;margin:0 0 10px;letter-spacing:-.01em}
  p{color:#a9a29c;font-size:14px;line-height:1.6;margin:0 0 22px}
  .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#e05049;margin-right:8px;
       animation:pulse 1.4s ease-in-out infinite;vertical-align:1px}
  @keyframes pulse{0%,100%{opacity:.35}50%{opacity:1}}
  .btn{display:inline-block;text-decoration:none;font-size:14px;font-weight:600;padding:12px 20px;border-radius:11px;margin:5px;
       background:#f2efe9;color:#0e1012}
  .btn.ghost{background:transparent;color:#f2efe9;border:1px solid rgba(240,240,240,.16)}
  .fine{color:#6f6a64;font-size:12px;margin-top:26px;font-family:'JetBrains Mono',ui-monospace,monospace}
  #fallback{display:none}
</style></head><body><div class="card">
  <div class="brand">&#10029;&nbsp;FLUME</div>
  <div id="opening"><h1><span class="dot"></span>Opening Flume…</h1>
    <p>Your team invite is being handed to the Flume app. If nothing happens in a moment, you'll be taken to the download page.</p></div>
  <div id="fallback"><h1>Join your team on Flume</h1>
    <p>Install Flume, sign in with the address the invite was sent to, and the team appears on your first launch.</p>
    <a class="btn" id="dl" href="${esc(dl)}">Download Flume</a>
    <a class="btn ghost" href="${esc(deep)}">I already have Flume</a></div>
  <div class="fine">Invite links are personal — don't forward this one.</div>
</div>
<script>
(function(){
  var deep=${JSON.stringify(deep)}, dl=${JSON.stringify(dl)}, grace=${OPEN_GRACE_MS};
  var answered=false;
  // If the OS switched to Flume, this document loses visibility/focus — that is
  // the only signal a page gets that the scheme was handled.
  function onAway(){ answered=true; }
  document.addEventListener('visibilitychange', function(){ if(document.hidden) onAway(); });
  window.addEventListener('blur', onAway);
  window.addEventListener('pagehide', onAway);
  try{ window.location.href=deep; }catch(e){}
  setTimeout(function(){
    document.getElementById('opening').style.display='none';
    document.getElementById('fallback').style.display='block';
    if(!answered){ window.location.replace(dl); }
  }, grace);
})();
</script></body></html>`;
}

Deno.serve((req: Request) => {
  const url = new URL(req.url);
  const token = (url.searchParams.get("t") || url.searchParams.get("token") || "").trim();
  const ua = req.headers.get("user-agent") || "";
  if (!token) return Response.redirect(DOWNLOAD_PAGE, 302);
  // Phones can't run Flume yet — send them to the download page (which
  // explains that) with the token intact.
  if (!isDesktop(ua)) return Response.redirect(`${DOWNLOAD_PAGE}?t=${encodeURIComponent(token)}`, 302);
  return new Response(page(token), {
    status: 200,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" },
  });
});
