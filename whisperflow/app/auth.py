"""
Google sign-in for the Mac app via Supabase Auth (PKCE loopback flow).

Flow:
  1. Generate a PKCE verifier/challenge.
  2. Open the browser to Supabase's /authorize?provider=google with a localhost
     redirect. Supabase runs the Google consent, then redirects back to
     http://localhost:<PORT>/callback?code=...
  3. A tiny local HTTP server captures the code; we exchange it for a Supabase
     session (which contains the user's stable id + email).
  4. We store that identity and use the user's id as the data key (sync_user_id),
     so every signed-in user gets their own cloud data.

No Google client secret lives in the app — Supabase holds the Google credentials.
Data requests still use the anon key keyed by the user id (see SETUP guide for the
optional RLS-hardening step).
"""
import base64
import hashlib
import http.server
import logging
import secrets
import socket
import threading
import time
import urllib.parse
import webbrowser

import httpx

from app.config import load_config, save_config
from app.supabase_config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger("verbal.auth")

REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
AUTH_BASE = f"{SUPABASE_URL}/auth/v1"
_refresh_lock = threading.Lock()
# Set once a refresh definitively fails (dead refresh token) so we stop firing a
# doomed refresh before every authed call — even when a caller passes an in-memory
# config that still holds the stale tokens. Reset on a fresh sign-in.
_dead_session = False

_DONE_PAGE = (
    "<!doctype html><html><head><meta charset='utf-8'><title>Flume</title></head>"
    "<body style='font-family:-apple-system,system-ui,sans-serif;background:#0e1012;"
    "color:#f2f2f2;display:flex;align-items:center;justify-content:center;height:100vh;margin:0'>"
    "<div style='text-align:center;max-width:340px'>"
    "<div style='font-size:44px;margin-bottom:10px'>%s</div>"
    "<h2 style='font-weight:600;margin:0 0 6px'>%s</h2>"
    "<p style='color:#9a9a9a;margin:0;font-size:14px'>You can close this tab and return to Flume.</p>"
    "</div></body></html>"
)


def _pkce():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    code = None
    error = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _CallbackHandler.code = params["code"][0]
        if "error_description" in params or "error" in params:
            _CallbackHandler.error = (params.get("error_description") or params.get("error"))[0]
        ok = _CallbackHandler.code is not None
        body = (_DONE_PAGE % (("✓", "Login successful") if ok
                              else ("⚠", "Sign-in failed"))).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        try:
            self.wfile.flush()
        except Exception:
            pass

    def log_message(self, *args):
        pass


class _DualStackServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    """Bind IPv6 + IPv4 so it catches localhost however the browser resolves it
    (localhost → ::1 on many macs, → 127.0.0.1 on others)."""
    address_family = socket.AF_INET6

    def server_bind(self):
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except Exception:
            pass
        http.server.HTTPServer.server_bind(self)


def _make_server():
    try:
        return _DualStackServer(("::", REDIRECT_PORT), _CallbackHandler)
    except Exception as e:
        logger.warning("dual-stack bind failed (%s); falling back to IPv4", e)
        return http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler)


def sign_in_with_google(timeout=180):
    """Blocking. Opens the browser and returns the stored auth dict, or raises."""
    verifier, challenge = _pkce()
    authorize_url = (
        f"{AUTH_BASE}/authorize?provider=google"
        f"&redirect_to={urllib.parse.quote(REDIRECT_URI, safe='')}"
        f"&code_challenge={challenge}&code_challenge_method=s256"
    )
    _CallbackHandler.code = None
    _CallbackHandler.error = None

    server = _make_server()
    logger.info("Opening browser for Google sign-in")
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    webbrowser.open(authorize_url)

    try:
        start = time.time()
        while _CallbackHandler.code is None and _CallbackHandler.error is None:
            if time.time() - start > timeout:
                raise TimeoutError("Sign-in timed out")
            time.sleep(0.2)
    finally:
        # let the browser fully receive the success page before we tear down
        time.sleep(1.2)
        try:
            server.shutdown()
        except Exception:
            pass
        server.server_close()

    if _CallbackHandler.error:
        raise RuntimeError(_CallbackHandler.error)

    resp = httpx.post(
        f"{AUTH_BASE}/token?grant_type=pkce",
        headers={"apikey": SUPABASE_KEY, "Content-Type": "application/json"},
        json={"auth_code": _CallbackHandler.code, "code_verifier": verifier},
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text[:200]}")
    return _store_session(resp.json())


def _store_session(session):
    user = session.get("user", {}) or {}
    meta = user.get("user_metadata", {}) or {}
    auth = {
        "user_id": user.get("id", ""),
        "email": user.get("email", ""),
        "name": meta.get("full_name") or meta.get("name") or user.get("email", ""),
        "avatar_url": meta.get("avatar_url", ""),
        "access_token": session.get("access_token", ""),
        "refresh_token": session.get("refresh_token", ""),
        "expires_at": time.time() + session.get("expires_in", 3600),
    }
    cfg = load_config()
    cfg["auth"] = auth
    # key all synced data by the real user id
    if auth["user_id"]:
        cfg["sync_user_id"] = auth["user_id"]
        if not cfg.get("sync_device_name"):
            import platform
            cfg["sync_device_name"] = platform.node()
    save_config(cfg)
    global _dead_session
    _dead_session = False   # a fresh session revives authed calls
    logger.info("Signed in as %s", auth.get("email"))
    return auth


def current_user():
    """Return the stored auth dict, or None if signed out."""
    auth = load_config().get("auth")
    return auth if (auth and auth.get("user_id")) else None


def sign_out():
    cfg = load_config()
    cfg.pop("auth", None)
    cfg["sync_enabled"] = False
    save_config(cfg)
    logger.info("Signed out")


# ── Account deletion (MER-32) ────────────────────────────────────────────────
def delete_account_remote(cfg: dict | None = None) -> dict:
    """Call the `delete-account` Edge Function using the signed-in user's JWT.
    Returns {"ok": True} or {"ok": False, "error": "..."}. There is no
    user_id parameter — the function derives identity from the JWT itself,
    so this can only ever delete the CURRENTLY signed-in account. Requires
    being signed in with a real session (the anon key alone can't authorize
    this — the function 401s without a valid authenticated JWT)."""
    cfg = cfg if cfg is not None else load_config()
    token = get_access_token(cfg)
    if not token:
        return {"ok": False, "error": "Not signed in"}
    try:
        resp = httpx.post(
            f"{SUPABASE_URL}/functions/v1/delete-account",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {token}"},
            timeout=30,
        )
        data = resp.json() if resp.content else {}
    except Exception as e:
        return {"ok": False, "error": f"Network error: {e}"}
    if resp.status_code == 200 and data.get("ok"):
        return {"ok": True}
    return {"ok": False, "error": data.get("error") or f"HTTP {resp.status_code}"}


def wipe_local_account_data(cfg: dict | None = None) -> None:
    """Full local teardown after a successful account deletion. Deliberately
    goes further than `sign_out()` (which keeps local caches so re-signing in
    as the same user finds their data still there) — MER-32 requires nothing
    of the deleted account surviving on-device: history, pinned items, local
    notes/meetings cache, the local dictionary, and cached recording/meeting
    audio files all go."""
    cfg = cfg if cfg is not None else load_config()
    cfg.pop("auth", None)
    cfg["sync_enabled"] = False
    cfg["sync_user_id"] = ""
    cfg["history"] = []
    cfg["pinned"] = []
    cfg["notes"] = []
    cfg["meetings"] = []
    cfg["dictionary"] = {}
    save_config(cfg)
    try:
        import shutil
        from app.recordings import RECORDINGS_DIR
        if RECORDINGS_DIR.exists():
            shutil.rmtree(RECORDINGS_DIR, ignore_errors=True)
    except Exception as e:
        logger.debug("wipe_local_account_data: recordings cleanup skipped: %s", e)
    try:
        import os
        import shutil
        meetings_dir = os.path.expanduser("~/.verbal/meetings")
        if os.path.isdir(meetings_dir):
            shutil.rmtree(meetings_dir, ignore_errors=True)
    except Exception as e:
        logger.debug("wipe_local_account_data: meetings cleanup skipped: %s", e)
    logger.info("Local account data wiped")


# ── Per-user JWT forwarding (MER-29) ─────────────────────────────────────────
# Every Supabase REST/Realtime call historically used the shared anon key only,
# scoping data purely by the `user_id` *value* in the query/filter — not
# cryptographically enforced. This adds real Supabase-session auth: when
# signed in (with a fresh-enough access_token, refreshing via the stored
# refresh_token when needed), REST calls carry `Authorization: Bearer
# <access_token>`; otherwise they fall back to the anon key exactly as before.
# This is deliberately backward-compatible and additive — RLS policies remain
# `USING (true)` for now (see context/04-data-model.md §Security posture), so
# sending the anon key still works identically. It's shipped ahead of any RLS
# tightening specifically so that a future cutover to `auth.uid()`-scoped
# policies doesn't ALSO require a client code change at the same time.
def _refresh_access_token(cfg: dict) -> str | None:
    """Return a valid access_token for the signed-in user, refreshing via the
    stored refresh_token if the cached one is expired/near-expiry. Returns
    None if signed out. Never raises — falls back to the last-known token (or
    None) on any refresh error, so a network hiccup degrades to "try the old
    token" rather than breaking the caller."""
    global _dead_session
    if _dead_session:
        return None   # refresh token already proven dead this session → use anon
    auth = cfg.get("auth") or {}
    access_token = auth.get("access_token")
    if not access_token:
        return None
    if time.time() < auth.get("expires_at", 0) - 60:
        return access_token  # still valid (60s safety margin)
    refresh_token = auth.get("refresh_token")
    if not refresh_token:
        return access_token  # no refresh_token on record; use what we have
    with _refresh_lock:
        # Re-read + re-check under the lock — another thread may have already
        # refreshed while we were waiting.
        cfg2 = load_config()
        auth2 = cfg2.get("auth") or {}
        if time.time() < auth2.get("expires_at", 0) - 60:
            return auth2.get("access_token")
        try:
            resp = httpx.post(
                f"{AUTH_BASE}/token?grant_type=refresh_token",
                headers={"apikey": SUPABASE_KEY, "Content-Type": "application/json"},
                json={"refresh_token": auth2.get("refresh_token", refresh_token)},
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning("Token refresh failed (%s): %s", resp.status_code, resp.text[:200])
                # A 400/401/403 means the refresh token is permanently dead
                # (invalid_grant / refresh_token_not_found) — the session is
                # unrecoverable. DROP the unusable tokens and return None so
                # auth_header() falls back to the anon key (which works under the
                # current permissive `USING (true)` RLS) instead of sending a
                # KNOWN-EXPIRED JWT that 401s every authed read — which silently
                # broke opening meeting notes (cloud row fetch 401 → local
                # metadata has no notes_md/transcript → "can't open notes"), the
                # device list, and dictionary sync. Dropping the tokens also stops
                # a failing 10s refresh from firing before EVERY authed call.
                # sync_user_id is kept, so user_id-keyed reads/writes keep working;
                # the user can re-sign-in for a fresh session.
                if resp.status_code in (400, 401, 403):
                    _dead_session = True
                    try:
                        for k in ("access_token", "refresh_token", "expires_at"):
                            auth2.pop(k, None)
                        cfg2["auth"] = auth2
                        save_config(cfg2)
                    except Exception:
                        pass
                    return None
                return auth2.get("access_token", access_token)
            session = resp.json()
            auth2["access_token"] = session.get("access_token", auth2.get("access_token"))
            auth2["refresh_token"] = session.get("refresh_token", auth2.get("refresh_token"))
            auth2["expires_at"] = time.time() + session.get("expires_in", 3600)
            cfg2["auth"] = auth2
            save_config(cfg2)
            return auth2["access_token"]
        except Exception as e:
            logger.warning("Token refresh error: %s", e)
            return auth2.get("access_token", access_token)


def get_access_token(cfg: dict | None = None) -> str | None:
    """Public helper: a valid access_token if signed in (refreshing as
    needed), else None. Fails closed to None on any error."""
    try:
        return _refresh_access_token(cfg if cfg is not None else load_config())
    except Exception as e:
        logger.warning("get_access_token error (falling back to anon): %s", e)
        return None


def auth_header(cfg: dict | None = None, json: bool = False) -> dict:
    """REST headers for any Supabase call: the signed-in user's JWT when
    available and valid, else the shared anon key (signed-out desktop, or a
    paired device that adopted a user_id without ever signing in itself —
    see the `pairings` note in context/04-data-model.md §Security posture).
    `apikey` is always the project's anon key regardless — that's the
    project identifier, not the caller's identity; `Authorization` is what
    Supabase's RLS actually evaluates."""
    token = get_access_token(cfg) or SUPABASE_KEY
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {token}"}
    if json:
        h["Content-Type"] = "application/json"
    return h
