"""
Flume device pairing over Supabase — short-lived, single-use tokens + QR.

Host side (this device already has a sync user_id):
    token, expires_at, ttl = create_pairing(user_id, host_device)
    ... show qr_svg("flume://pair?t=" + token) ...
    while not check_pairing(token)["claimed_by"]: poll

New device (scans the QR, extracts the token):
    info = claim_pairing(token, device_name)   # -> {"user_id", "host_device"}
    ... adopt info["user_id"], enable sync ...

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


def claim_pairing(token, device_name):
    """New device claims a token. Succeeds only while unclaimed and unexpired.
    Returns {"user_id", "host_device"} on success, else raises ValueError."""
    # find a valid, unclaimed row
    r = httpx.get(
        f"{REST_URL}/pairings",
        headers=_HEADERS,
        params={
            "token": f"eq.{token}",
            "claimed_by": "is.null",
            "expires_at": f"gt.{_iso(_now())}",
            "select": "id,user_id,host_device",
        },
        timeout=8,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise ValueError("This code is invalid, already used, or expired.")
    row = rows[0]
    # stamp it claimed (single-use: only rows still null match)
    u = httpx.patch(
        f"{REST_URL}/pairings",
        headers={**_HEADERS, "Prefer": "return=representation"},
        params={"id": f"eq.{row['id']}", "claimed_by": "is.null"},
        json={"claimed_by": device_name or "device", "claimed_at": _iso(_now())},
        timeout=8,
    )
    u.raise_for_status()
    if not u.json():  # someone else claimed it between select and patch
        raise ValueError("This code was just used by another device.")
    return {"user_id": row["user_id"], "host_device": row.get("host_device", "")}


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
