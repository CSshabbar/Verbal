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
import hmac
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
# Set while an interactive sign-in is waiting on the browser round-trip so the
# dashboard's "Cancel" affordance can end it (IDI-166): without this the local
# callback server stays bound to REDIRECT_PORT for the full 180 s timeout and a
# retry fails to bind.
_signin_cancel = threading.Event()

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
    # CSRF binding (IDI-265): when set (non-None), a callback is honored ONLY
    # if it carries a matching `state` — absent or mismatched state is
    # rejected without touching `code`/`error`. Currently always None: see
    # the state note in sign_in_with_google() for why Supabase GoTrue cannot
    # round-trip a client state today. PKCE meanwhile binds the code to this
    # flow — a code minted for any other code_challenge fails our token
    # exchange, so an injected foreign code cannot complete a sign-in.
    expected_state = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        state_ok = True
        if _CallbackHandler.expected_state is not None:
            got = (params.get("state") or [""])[0]
            state_ok = hmac.compare_digest(got, _CallbackHandler.expected_state)
            if not state_ok:
                logger.warning("Sign-in callback rejected: missing/mismatched state")
        if state_ok and "code" in params and _CallbackHandler.code is None:
            # First code wins — a later request must not replace a code the
            # real redirect already delivered.
            _CallbackHandler.code = params["code"][0]
        if state_ok and ("error_description" in params or "error" in params):
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


class _LoopbackV6Server(http.server.ThreadingHTTPServer):
    """IPv6 loopback (`::1`) listener for the sign-in callback."""
    daemon_threads = True
    address_family = socket.AF_INET6


def _make_servers():
    """Loopback-ONLY listeners (IDI-265). The old server bound `::` — every
    interface, dual-stack — exposing the OAuth callback to the whole LAN; the
    redirect URI is http://localhost:8765/callback, so loopback suffices.

    `localhost` resolves to ::1 on some machines and 127.0.0.1 on others, and
    a loopback socket cannot be dual-stack (IPV6_V6ONLY=0 only maps IPv4 into
    a wildcard `::` bind, never into `::1`) — so bind BOTH loopback addresses
    and let the browser connect on whichever family it picked. One family may
    be unavailable (e.g. IPv6 disabled): that alone is fine; only both binds
    failing is an error. Returns a non-empty list of servers."""
    servers = []
    try:
        servers.append(_LoopbackV6Server(("::1", REDIRECT_PORT), _CallbackHandler))
    except Exception as e:
        logger.warning("IPv6 loopback bind failed (%s); trying IPv4 only", e)
    try:
        servers.append(http.server.ThreadingHTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler))
    except Exception as e:
        logger.warning("IPv4 loopback bind failed (%s)", e)
        if not servers:
            raise
    return servers


class SignInCancelled(RuntimeError):
    """The user cancelled the interactive sign-in (not an error to report)."""


def cancel_sign_in():
    """Ask an in-flight `sign_in_with_google` to give up now (IDI-166).
    Safe to call when nothing is running."""
    _signin_cancel.set()


def sign_in_with_google(timeout=180):
    """Blocking. Opens the browser and returns the stored auth dict, or raises."""
    _signin_cancel.clear()
    verifier, challenge = _pkce()
    # STATE (IDI-265): deliberately NOT sent. Supabase GoTrue cannot
    # round-trip a client `state` through the provider PKCE flow — verified
    # live (2026-09-01) against our project: `&state=X` on /authorize
    # REPLACES GoTrue's own flow-state id in the Google round-trip (breaking
    # the flow at Google→Supabase), and GoTrue matches `redirect_to` against
    # the redirect allowlist INCLUDING its query string, so smuggling state
    # as `/callback?state=X` silently falls back to SITE_URL unless the
    # dashboard allowlist carries a `http://localhost:8765/callback*` glob.
    # To activate enforcement once that glob is configured: append the state
    # to REDIRECT_URI's query here and set _CallbackHandler.expected_state =
    # secrets.token_urlsafe(32); the handler then rejects absent/mismatched
    # state. Until then PKCE is the binding: an injected foreign code fails
    # the token exchange below (wrong code_challenge), so it cannot sign the
    # user into another account.
    _CallbackHandler.expected_state = None
    authorize_url = (
        f"{AUTH_BASE}/authorize?provider=google"
        f"&redirect_to={urllib.parse.quote(REDIRECT_URI, safe='')}"
        f"&code_challenge={challenge}&code_challenge_method=s256"
    )
    _CallbackHandler.code = None
    _CallbackHandler.error = None

    servers = _make_servers()
    logger.info("Opening browser for Google sign-in")
    for s in servers:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    webbrowser.open(authorize_url)

    try:
        start = time.time()
        while _CallbackHandler.code is None and _CallbackHandler.error is None:
            if _signin_cancel.is_set():
                raise SignInCancelled("Sign-in cancelled")
            if time.time() - start > timeout:
                raise TimeoutError("Sign-in timed out — the browser never came back.")
            time.sleep(0.2)
    finally:
        # let the browser fully receive the success page before we tear down
        # (skip the wait when cancelled — the point is to free the port fast)
        if not _signin_cancel.is_set():
            time.sleep(1.2)
        _CallbackHandler.expected_state = None   # clear after use
        for s in servers:
            try:
                s.shutdown()
            except Exception:
                pass
            try:
                s.server_close()
            except Exception:
                pass

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
    # ── Account switch → wipe the previous account's local caches (IDI-170) ──
    # Mobile has had this guard since MER (Hard Rule #13); desktop did not, so a
    # SECOND Google account signing in on the same Mac inherited the first
    # account's history/pinned/notes/meetings/dictionary/voice-prints (and then
    # re-uploaded them under the new user_id). Everything account-scoped goes —
    # including the on-disk recordings/meeting audio of the OLD account — while
    # device-level config (Groq keys, hotkeys, device name, feature prefs) stays.
    prev_uid = ((cfg.get("auth") or {}).get("user_id") or ""
                or (cfg.get("sync_user_id") or ""))
    if auth["user_id"] and prev_uid and prev_uid != auth["user_id"]:
        logger.info("Account switch detected (%s… → %s…) — wiping local caches",
                    prev_uid[:8], auth["user_id"][:8])
        try:
            _clear_account_caches(cfg)
        except Exception as e:
            logger.warning("account-switch wipe failed: %s", e)
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


SESSION_EXPIRED_MSG = "Your session expired — sign in again, then retry."


def session_dead(cfg: dict | None = None) -> bool:
    """True when we still know WHO the user is (`auth.user_id` survives) but the
    Supabase session is unrecoverable — the refresh token was rejected and the
    tokens were dropped (see `_refresh_access_token` / Hard Rule #24).

    `signed_in` alone can't express this: the app keeps working (anon key +
    `sync_user_id` under the current permissive RLS) but anything that needs a
    REAL JWT — account deletion above all — will fail until the user re-auths.
    The in-process flag is mirrored into `config['auth']['session_dead']` so the
    state survives a restart; a fresh `_store_session` writes a clean auth dict
    and therefore clears it.

    Pass the already-loaded config when you have one (get_state does) — this is
    called on every state refresh and shouldn't re-read the config file.
    """
    if _dead_session:
        return True
    try:
        cfg = cfg if cfg is not None else load_config()
        auth = cfg.get("auth") or {}
        return bool(auth.get("user_id")) and bool(auth.get("session_dead"))
    except Exception:
        return False


def cloud_allowed(cfg: dict | None = None) -> bool:
    """True when this desktop may talk to the cloud ON BEHALF OF AN ACCOUNT
    (IDI-170).

    Every cloud path here historically gated on `sync_user_id` alone, which
    SURVIVED sign-out — so post-sign-out edits kept POSTing into the account
    the user had just left. `sign_out()` now clears that id; this helper is the
    belt-and-braces second gate, ANDed in at each call site.

    Identity is taken from `current_user()` (a real stored session), not from
    `sync_user_id`: the paired-desktop case that used to have an adopted
    `sync_user_id` without an `auth` dict no longer exists — desktop only ever
    HOSTS a pairing, and hosting requires being signed in (Hard Rule #26).

    Gated on `session_dead` (IDI-268 / IDI-29): once shared-table RLS is
    `TO authenticated` on `auth.uid()`, a dead refresh token can no longer limp
    along on the anon-key fallback — those requests read ZERO rows silently, so
    the app would look healthy while showing nothing. A dead session must deny
    cloud access here and let the re-sign-in banner (IDI-166) surface instead.
    This deliberately reverses the pre-RLS Hard Rule #24 fallback; the desktop
    build carrying this gate MUST ship (and propagate to installs) before
    `supabase_auth_uid_rls.sql` is applied, or dead-session clients silently go
    blank the moment the policies tighten.
    """
    try:
        cfg = cfg if cfg is not None else load_config()
        return bool((cfg.get("auth") or {}).get("user_id")) and not session_dead(cfg)
    except Exception:
        return False


def _delete_device_row_async(user_id: str, headers: dict | None) -> None:
    """Best-effort: remove THIS device's `devices` row so the account's other
    devices stop showing a signed-out Mac (IDI-170). Runs off-thread — sign-out
    must never block on the network. Headers are captured by the caller while
    the session still exists."""
    def work():
        try:
            from app.sync import delete_device_presence
            delete_device_presence(user_id, headers=headers)
        except Exception as e:
            logger.debug("device row delete skipped: %s", e)
    try:
        threading.Thread(target=work, daemon=True).start()
    except Exception as e:
        logger.debug("device row delete dispatch failed: %s", e)


def sign_out():
    """Sign out: drop the session AND stop acting as this account's device.

    Clearing `sync_user_id` is load-bearing, not cosmetic — see
    `cloud_allowed()`. Local caches are deliberately KEPT (re-signing in as the
    same user finds their data intact); the account-switch case is handled in
    `_store_session`, full destruction in `wipe_local_account_data`."""
    cfg = load_config()
    prev = cfg.get("auth") or {}
    user_id = prev.get("user_id") or cfg.get("sync_user_id") or ""
    # Grab REST headers while we still hold a session — the DELETE below runs
    # after the local teardown has already dropped the tokens.
    try:
        headers = auth_header(cfg) if user_id else None
    except Exception:
        headers = None
    cfg.pop("auth", None)
    cfg["sync_enabled"] = False
    cfg["sync_user_id"] = ""
    save_config(cfg)
    global _dead_session
    _dead_session = False   # no session at all now; a re-sign-in starts clean
    if user_id:
        _delete_device_row_async(user_id, headers)
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
        # Distinguish "never signed in" from "session died under you" — the
        # second is the common case (a dead refresh token drops the tokens but
        # keeps the identity) and "Not signed in" was an unactionable lie there
        # while the sidebar still showed the account (IDI-166).
        if session_dead(cfg):
            return {"ok": False, "error": SESSION_EXPIRED_MSG, "session_dead": True}
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


def _clear_account_caches(cfg: dict) -> None:
    """Drop every ACCOUNT-SCOPED local cache, mutating `cfg` IN PLACE and
    without saving. Auth/identity keys are deliberately left alone so the
    caller decides whether this is a sign-out, a deletion, or an account
    switch. Also removes the on-disk recording/meeting audio.

    Device-level config (Groq/Gemini keys, hotkeys, device name, feature
    flags) is preserved — same split as mobile's `clearAccountData()`
    (Hard Rule #13)."""
    cfg["history"] = []
    cfg["pinned"] = []
    cfg["notes"] = []
    cfg["meetings"] = []
    cfg["meetings_opened"] = []
    cfg["dictionary"] = {}
    # The team cache carries another organization's shared vocabulary, snippets and
    # roster (IDI-216). It is account-scoped in the strongest sense — leaving it
    # behind would let the next account signed in on this machine dictate with a
    # team they were never in, and read its member list out of the dashboard.
    cfg["org"] = {}
    # …and the per-device onboarding nudge, so the next account that creates a
    # team gets the setup screen rather than inheriting "already done".
    cfg["org_setup_done"] = False
    # Voice fingerprints are local-only biometric-adjacent data (Hard Rule #18)
    # keyed to the people in THIS account's meetings — they must not survive
    # into another account, or past a deletion.
    cfg["voice_prints"] = {}
    try:
        import shutil
        from app.recordings import RECORDINGS_DIR
        if RECORDINGS_DIR.exists():
            shutil.rmtree(RECORDINGS_DIR, ignore_errors=True)
    except Exception as e:
        logger.debug("account wipe: recordings cleanup skipped: %s", e)
    try:
        import os
        import shutil
        meetings_dir = os.path.expanduser("~/.verbal/meetings")
        if os.path.isdir(meetings_dir):
            shutil.rmtree(meetings_dir, ignore_errors=True)
    except Exception as e:
        logger.debug("account wipe: meetings cleanup skipped: %s", e)


def wipe_local_account_data(cfg: dict | None = None) -> None:
    """Full local teardown after a successful account deletion. Deliberately
    goes further than `sign_out()` (which keeps local caches so re-signing in
    as the same user finds their data still there) — MER-32 requires nothing
    of the deleted account surviving on-device: history, pinned items, local
    notes/meetings cache, the local dictionary, voice prints, and cached
    recording/meeting audio files all go.

    **Pass the LIVE config object** when the caller has one (IDI-170). With no
    argument this re-reads from disk, and the caller's in-memory
    `app.config` — which still holds auth + history — resurrects everything
    the moment any other thread fires `save_config(app.config)`. Given a live
    dict we mutate it in place, so a concurrent save writes the WIPED state.
    """
    cfg = cfg if cfg is not None else load_config()
    cfg.pop("auth", None)
    cfg["sync_enabled"] = False
    cfg["sync_user_id"] = ""
    _clear_account_caches(cfg)
    save_config(cfg)
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
                        # Persist it too — the dashboard/Settings banner and
                        # delete_account must still know the session is dead
                        # after a restart (IDI-166). Cleared by _store_session.
                        auth2["session_dead"] = True
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
