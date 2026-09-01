// Team-invite link target (2026-08-29).
//
// The invite e-mail (invite-member) links here with `?t=<token>`. This function is
// the STABLE address the e-mail points at; where it sends people is decided here.
//
// The landing page that tries `flume://invite?t=<token>` and falls back to the
// download page CANNOT be served from this function: the *.supabase.co functions
// gateway rewrites every response Content-Type (text/html AND
// application/xhtml+xml) to text/plain + nosniff, so browsers show the page as
// source. It is the static file idiaz.io/flume/invite.html (source of truth:
// Verbal repo site/flume/invite.html, published with the flume-site here.now
// slug). Desktop AND phone browsers are sent there — the page decides where a phone
// goes (a live store listing if the `download` function reports one, else the
// download page). Unrecognised user agents (link scanners, curl) and token-less
// hits skip the page and go straight to the download page, token preserved.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const DOWNLOAD_PAGE = Deno.env.get("FLUME_DOWNLOAD_URL") ?? "https://idiaz.io/flume/download.html";
// Static landing page (tries flume://, falls back to DOWNLOAD_PAGE). Set to "" to bypass.
const LANDING = Deno.env.get("INVITE_LANDING_URL") ?? "https://idiaz.io/flume/invite.html";

function isPhone(ua: string): boolean {
  return /iphone|ipad|ipod|android/.test(ua.toLowerCase());
}

function isDesktop(ua: string): boolean {
  const s = ua.toLowerCase();
  if (isPhone(s)) return false;
  return /windows|win32|win64|macintosh|mac os x/.test(s);
}

Deno.serve((req: Request) => {
  const url = new URL(req.url);
  const token = (url.searchParams.get("t") || url.searchParams.get("token") || "").trim();
  const ua = req.headers.get("user-agent") || "";
  if (!token) return Response.redirect(DOWNLOAD_PAGE, 302);
  const q = `?t=${encodeURIComponent(token)}`;
  // Recognised browser (desktop OR phone) with a hosted landing page → let the page
  // decide: desktop tries flume:// first, phones ask the download function for a
  // live store link (IDI-276). Unknown UAs skip the page and get the download link.
  if (LANDING && (isDesktop(ua) || isPhone(ua))) return Response.redirect(`${LANDING}${q}`, 302);
  return Response.redirect(`${DOWNLOAD_PAGE}${q}`, 302);
});
