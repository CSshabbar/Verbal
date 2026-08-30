// download — the ONE stable URL your website links to, for every platform and
// every future release.
//
//     https://<project>.supabase.co/functions/v1/download            (sniffs the OS)
//     https://<project>.supabase.co/functions/v1/download?platform=mac
//     https://<project>.supabase.co/functions/v1/download?platform=win
//     https://<project>.supabase.co/functions/v1/download?json=1     (metadata, no redirect)
//
// It 302-redirects to whatever `app_versions_latest` currently says is newest for
// that platform. Nothing here needs touching when you ship a release: CI inserts
// the new `app_versions` row and this endpoint follows it on the next request.
// Point flume.app/download at this and the website never needs updating either.
//
// WHY A REDIRECT AND NOT A FIXED BUCKET PATH: a stable path like
// `releases/latest/Verbal.dmg` means overwriting the same object every release,
// which (a) loses the version in the filename people download, (b) fights CDN
// caching, and (c) makes rollback a re-upload instead of a row change. A redirect
// keeps every build immutable and addressable while the ENTRY POINT stays fixed.
//
// `verify_jwt` is OFF, deliberately. This is a public download link printed on a
// marketing page — requiring a Supabase JWT would defeat its only purpose. The
// relaxation is safe and quarantined: the function performs a single read of a
// view over `app_versions` (already public-SELECT, it is a release manifest), holds
// no secrets, writes nothing, and can only ever emit a redirect to a URL that is
// already public. It uses the ANON key, not the service role, so it cannot reach
// anything the anon key couldn't.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;

// Short, not zero. Long enough that a burst of downloads doesn't hammer the DB,
// short enough that a fresh release is live within a minute rather than whenever a
// CDN feels like expiring.
const CACHE_SECONDS = 60;

type Row = {
  platform: string;
  version: string;
  file_url: string;
  file_size: number | null;
  file_hash: string | null;
  changelog: string | null;
  released_at: string | null;
};

/** Guess the platform from the User-Agent so one link works for everyone.
 *  Deliberately conservative: anything unrecognised returns null and gets the
 *  chooser page rather than a wrong download. */
function sniff(ua: string): "mac" | "win" | "ios" | "android" | null {
  const s = ua.toLowerCase();
  // iPad reports as Macintosh on modern iPadOS, so test touch hints first.
  if (/iphone|ipad|ipod/.test(s)) return "ios";
  if (/android/.test(s)) return "android";
  if (/windows|win32|win64/.test(s)) return "win";
  if (/macintosh|mac os x/.test(s)) return "mac";
  return null;
}

async function latest(platform: string): Promise<Row | null> {
  const url = `${SUPABASE_URL}/rest/v1/app_versions_latest` +
    `?platform=eq.${encodeURIComponent(platform)}` +
    `&select=platform,version,file_url,file_size,file_hash,changelog,released_at&limit=1`;
  const r = await fetch(url, { headers: { apikey: ANON_KEY, Authorization: `Bearer ${ANON_KEY}` } });
  if (!r.ok) return null;
  const rows = await r.json();
  return Array.isArray(rows) && rows.length ? rows[0] as Row : null;
}

function esc(t: string): string {
  return t.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));
}

function page(body: string, status = 200): Response {
  return new Response(
    `<!doctype html><html><head><meta charset="utf-8"><title>Download Flume</title>
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#0e1012;color:#f2f2f2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
display:flex;align-items:center;justify-content:center;min-height:100vh;padding:28px">
<div style="max-width:420px;text-align:center">
<div style="color:#C85A3E;font-size:13px;letter-spacing:.18em;font-weight:600;margin-bottom:26px">&#10029;&nbsp;FLUME</div>
${body}
</div></body></html>`,
    { status, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } },
  );
}

const BTN = "display:inline-block;background:#f2f2f2;color:#0e1012;text-decoration:none;" +
  "font-size:14px;font-weight:600;padding:13px 22px;border-radius:11px;margin:6px";

Deno.serve(async (req) => {
  const u = new URL(req.url);
  const asked = (u.searchParams.get("platform") ?? "").toLowerCase().trim();
  const wantJson = u.searchParams.get("json") === "1";

  // Normalise the aliases a website will realistically link with.
  const alias: Record<string, string> = {
    mac: "mac", macos: "mac", osx: "mac", darwin: "mac",
    win: "win", windows: "win", win64: "win",
    ios: "ios", iphone: "ios", android: "android",
  };
  const platform = alias[asked] ?? (asked ? "" : sniff(req.headers.get("user-agent") ?? "") ?? "");

  if (!platform) {
    if (wantJson) {
      return new Response(JSON.stringify({ ok: false, error: "unknown_platform" }), {
        status: 400, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
      });
    }
    // Never guess wrong — offer the choice instead.
    return page(
      `<div style="font-size:21px;font-weight:600;margin-bottom:10px">Pick your platform</div>
       <p style="color:#a9a29c;font-size:14px;line-height:1.6;margin:0 0 20px">We couldn't tell which device you're on.</p>
       <a style="${BTN}" href="?platform=mac">Download for Mac</a>
       <a style="${BTN}" href="?platform=win">Download for Windows</a>`,
    );
  }

  // Mobile isn't distributed through this endpoint — say so plainly rather than
  // 404ing, since a phone visiting the marketing page is a normal thing to happen.
  if (platform === "ios" || platform === "android") {
    const store = platform === "ios" ? "the App Store" : "Google Play";
    if (wantJson) {
      return new Response(JSON.stringify({ ok: false, error: "not_distributed", platform }), {
        status: 404, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
      });
    }
    return page(
      `<div style="font-size:21px;font-weight:600;margin-bottom:10px">Flume for ${platform === "ios" ? "iPhone" : "Android"} is on its way</div>
       <p style="color:#a9a29c;font-size:14px;line-height:1.6;margin:0 0 20px">It isn't on ${store} yet. Flume runs on Mac and Windows today.</p>
       <a style="${BTN}" href="?platform=mac">Download for Mac</a>
       <a style="${BTN}" href="?platform=win">Download for Windows</a>`,
      404,
    );
  }

  const row = await latest(platform);
  if (!row || !row.file_url) {
    // A missing row is a RELEASE-PIPELINE problem, not a user problem. Fail loudly
    // enough to be noticed, without dead-ending the visitor.
    console.error(`download: no app_versions row for platform=${platform}`);
    if (wantJson) {
      return new Response(JSON.stringify({ ok: false, error: "no_release", platform }), {
        status: 503, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
      });
    }
    return page(
      `<div style="font-size:21px;font-weight:600;margin-bottom:10px">No ${platform === "mac" ? "Mac" : "Windows"} build published yet</div>
       <p style="color:#a9a29c;font-size:14px;line-height:1.6;margin:0 0 20px">This is on us, not you. Try the other platform meanwhile.</p>
       <a style="${BTN}" href="?platform=${platform === "mac" ? "win" : "mac"}">Download for ${platform === "mac" ? "Windows" : "Mac"}</a>`,
      503,
    );
  }

  // VERIFY THE TARGET BEFORE REDIRECTING.
  //
  // app_versions rows outlive their artifacts. Production had 9 rows and an
  // entirely EMPTY releases bucket, so this endpoint faithfully 302'd people into
  // `{"error":"not_found","code":"NoSuchKey"}` — a raw storage error is the worst
  // possible thing to hand someone who just clicked "Download for Mac". A dead
  // release is a pipeline failure and should read as one.
  //
  // Costs one HEAD per uncached click. Worth it: the 302 carries a 60s
  // Cache-Control so repeat traffic never reaches this code, and a wrong answer
  // here is far more expensive than 200ms.
  let reachable = true;
  try {
    const probe = await fetch(row.file_url, {
      method: "HEAD", redirect: "follow", signal: AbortSignal.timeout(4000),
    });
    reachable = probe.ok;
    if (!reachable) {
      console.error(`download: ${platform} ${row.version} target is ${probe.status} — ${row.file_url}`);
    }
  } catch (e) {
    // A probe that times out is NOT proof the file is gone — some hosts refuse
    // HEAD. Fail OPEN there and let the browser try; only a definite non-OK
    // status counts as broken.
    console.warn(`download: could not probe ${row.file_url}: ${String(e)}`);
    reachable = true;
  }

  if (!reachable && !wantJson) {
    return page(
      `<div style="font-size:21px;font-weight:600;margin-bottom:10px">This build has gone missing</div>
       <p style="color:#a9a29c;font-size:14px;line-height:1.6;margin:0 0 20px">
         ${platform === "mac" ? "Mac" : "Windows"} ${esc(row.version)} is listed, but its file is no longer
         where it should be. That's on us, not you.</p>
       <a style="${BTN}" href="?platform=${platform === "mac" ? "win" : "mac"}">Try ${platform === "mac" ? "Windows" : "Mac"}</a>`,
      503,
    );
  }

  if (wantJson) {
    // Lets the website render "v1.0.10 · 124 MB" next to the button without
    // hardcoding a version anywhere. `reachable` is surfaced so a status page or a
    // CI smoke test can catch a stale row without a human clicking the button.
    return new Response(JSON.stringify({
      ok: true, platform: row.platform, version: row.version, url: row.file_url,
      reachable,
      size: row.file_size, sha256: row.file_hash, changelog: row.changelog,
      released_at: row.released_at,
    }), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": `public, max-age=${CACHE_SECONDS}`,
        "Access-Control-Allow-Origin": "*",
      },
    });
  }

  return new Response(null, {
    status: 302,
    headers: {
      Location: row.file_url,
      // 302 + a short max-age: browsers must re-ask often enough to pick up the
      // next release. A 301 here would be cached ~forever and pin people to an old
      // build with no way to fix it short of a new URL.
      "Cache-Control": `public, max-age=${CACHE_SECONDS}`,
      "X-Flume-Version": row.version,
    },
  });
});
