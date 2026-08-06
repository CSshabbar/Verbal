"""
Flume device pairing over Supabase — short-lived, single-use tokens + QR.

Host side (this device already has a sync user_id):
    token, expires_at, ttl = create_pairing(user_id, host_device)
    ... show qr_svg("flume://pair?t=" + token) ...
    while not check_pairing(token)["claimed_by"]: poll

New device (scans the QR, extracts the token):
    the MOBILE app claims it — verbal-mobile/lib/pairing.ts::claimPairing.
    (Desktop only ever hosts; the old desktop claim_pairing was dead code and
    was removed in IDI-156 — see context/05-conventions.md dead-code list.)

Reuses the same Supabase project + anon key + REST pattern as sync.py.
"""
import datetime as _dt
import logging
import secrets

import httpx

from app.sync import REST_URL, SUPABASE_KEY

logger = logging.getLogger("verbal.pairing")

TTL_SECONDS = 120  # tokens live 2 minutes

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def _now():
    return _dt.datetime.now(_dt.timezone.utc)


def _iso(dt):
    return dt.isoformat()


def new_token():
    # ~8 url-safe chars — enough entropy for a 2-minute single-use code
    return secrets.token_urlsafe(6)


def create_pairing(user_id, host_device, ttl=TTL_SECONDS):
    """Insert a pairing row and return (token, expires_at_iso, ttl_seconds)."""
    token = new_token()
    expires_at = _now() + _dt.timedelta(seconds=ttl)
    r = httpx.post(
        f"{REST_URL}/pairings",
        headers={**_HEADERS, "Prefer": "return=minimal"},
        json={
            "token": token,
            "user_id": user_id,
            "host_device": host_device or "",
            "expires_at": _iso(expires_at),
        },
        timeout=8,
    )
    r.raise_for_status()
    return token, _iso(expires_at), ttl


def check_pairing(token):
    """Host polls: returns the row (with claimed_by/claimed_at) or {} if gone."""
    r = httpx.get(
        f"{REST_URL}/pairings",
        headers=_HEADERS,
        params={"token": f"eq.{token}", "select": "claimed_by,claimed_at,expires_at"},
        timeout=8,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else {}


def qr_svg(data, module=7, quiet=2, dark="#0e1012", light="#ffffff"):
    """Render `data` as a QR-code SVG string (dark modules on a light ground)."""
    import qrcode

    qr = qrcode.QRCode(border=quiet, box_size=1,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    size = n * module
    rects = []
    for y, row in enumerate(matrix):
        for x, cell in enumerate(row):
            if cell:
                rects.append(
                    '<rect x="%d" y="%d" width="%d" height="%d"/>'
                    % (x * module, y * module, module, module))
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" shape-rendering="crispEdges">'
        '<rect width="%d" height="%d" fill="%s"/>'
        '<g fill="%s">%s</g></svg>'
        % (size, size, size, size, size, size, light, dark, "".join(rects))
    )
