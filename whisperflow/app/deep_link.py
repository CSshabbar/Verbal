"""Deep links into the desktop app (2026-08-29).

`flume://invite?t=<token>` — a team invite. The e-mail links to the `invite`
Edge Function landing page, which tries this URL first and falls back to the
download page when nothing answers.

Platform plumbing delivers the URL here:
  * macOS: `main.py` registers an Apple Event handler (kInternetEventClass /
    kAEGetURL) — Launch Services routes the URL to the running instance or
    launches the app with it.
  * Windows: `win_main.py` reads it from argv (scheme registered by the
    installer) and hands it to the running instance through the second-launch
    signal — not wired yet; the parsing/handling below is shared.

`handle()` never raises and never touches the dictation path: the token is
parked in config (`pending_invite_token`), the dashboard is shown on the Team
screen and told about it (`inviteLink`); the page fetches the preview and asks
the user to join. Signed-out users see the sign-in wall first — the page
re-checks the parked token when `signed_in` flips, so nothing is lost.
"""
import logging
from urllib.parse import parse_qs, unquote, urlsplit

logger = logging.getLogger("verbal.deeplink")

SCHEME = "flume"
PENDING_KEY = "pending_invite_token"


def parse_invite_token(url) -> str:
    """Token from `flume://invite?t=…`, `flume://invite/<token>`, or an https
    claim/landing URL carrying `?t=`/`?token=`. '' when this is not an invite."""
    try:
        u = (url or "").strip()
        if not u:
            return ""
        parts = urlsplit(u)
        scheme = (parts.scheme or "").lower()
        host = (parts.netloc or "").lower()
        path = parts.path or ""
        if scheme == SCHEME:
            if host != "invite" and not path.startswith("/invite"):
                return ""
        elif scheme not in ("http", "https"):
            return ""
        q = parse_qs(parts.query or "")
        for key in ("t", "token"):
            if q.get(key) and q[key][0].strip():
                return unquote(q[key][0].strip())
        if scheme == SCHEME:
            tail = path.strip("/").split("/")[-1] if path.strip("/") else ""
            if tail and tail != "invite":
                return unquote(tail)
        return ""
    except Exception as e:
        logger.debug("deep link parse failed: %s", e)
        return ""


def handle(app, url) -> bool:
    """Route one incoming URL. Returns True if it was an invite we acted on."""
    try:
        token = parse_invite_token(url)
        if not token:
            logger.info("deep link ignored: %r", url)
            return False
        logger.info("deep link: team invite received")
        cfg = getattr(app, "config", None)
        if isinstance(cfg, dict):
            try:
                from app.config import save_config
                cfg[PENDING_KEY] = token
                save_config(cfg)
            except Exception as e:
                logger.debug("pending invite token not saved: %s", e)
        dash = getattr(app, "dashboard", None)
        if dash is not None:
            for step in (lambda: dash.show(), lambda: dash.show_tab("team"),
                         lambda: dash.emit("inviteLink", {"token": token})):
                try:
                    step()
                except Exception as e:
                    logger.debug("deep link dashboard step failed: %s", e)
        return True
    except Exception as e:
        logger.error("deep link handling failed: %s", e)
        return False
