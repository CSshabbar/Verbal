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
from app.sync import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger("verbal.auth")

REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
AUTH_BASE = f"{SUPABASE_URL}/auth/v1"

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
