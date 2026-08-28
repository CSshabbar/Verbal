// Team-invite link target (2026-08-29).
//
// The invite e-mail (invite-member) links here with `?t=<token>`. This function is
// the STABLE address the e-mail points at; where it sends people is decided here.
//
// The landing page that tries `flume://invite?t=<token>` and falls back to the
// download page CANNOT be served from this function: the *.supabase.co functions
// gateway rewrites every response Content-Type (text/html AND
// application/xhtml+xml) to text/plain + nosniff, so browsers show the page as
// source. It has to be hosted as a static file (idiaz.io/flume/invite.html —
// see the repo's site/ folder). Until INVITE_LANDING_URL points at it, this is
// a plain redirect to the download page with the token preserved, i.e. exactly
// the pre-2026-08-29 behaviour.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const DOWNLOAD_PAGE = Deno.env.get("FLUME_DOWNLOAD_URL") ?? "https://idiaz.io/flume/download.html";
// Static landing page (tries flume://, falls back to DOWNLOAD_PAGE). Empty = not hosted yet.
const LANDING = Deno.env.get("INVITE_LANDING_URL") ?? "";

function isDesktop(ua: string): boolean {
  const s = ua.toLowerCase();
  if (/iphone|ipad|ipod|android/.test(s)) return false;
  return /windows|win32|win64|macintosh|mac os x/.test(s);
}

Deno.serve((req: Request) => {
  const url = new URL(req.url);
  const token = (url.searchParams.get("t") || url.searchParams.get("token") || "").trim();
  const ua = req.headers.get("user-agent") || "";
  if (!token) return Response.redirect(DOWNLOAD_PAGE, 302);
  const q = `?t=${encodeURIComponent(token)}`;
  // Desktop with a hosted landing page → let the page try the app first.
  if (LANDING && isDesktop(ua)) return Response.redirect(`${LANDING}${q}`, 302);
  return Response.redirect(`${DOWNLOAD_PAGE}${q}`, 302);
});
