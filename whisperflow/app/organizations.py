"""
Team / Organization layer — desktop client (IDI-216).

One org per user. This module owns everything the desktop knows about that org:
the membership row, the roster, the SHARED dictionary/snippets, invites, and the
usage/leaderboard aggregates. It is the desktop mirror of
`verbal-mobile/lib/organizations.ts` — edit one, edit the other.

THREE THINGS THAT ARE LOAD-BEARING HERE:

1. **Everything fails closed to "no team".** Every public function is wrapped and
   returns the no-org shape on any error. A user with no org, a network blip, a
   403, or an unapplied migration all look identical from the caller's side: no
   team, personal dictionary only, dictation completely unaffected (Hard Rule #1).

2. **Team features need a REAL session, not the anon key.** Unlike every other
   table in this codebase (Hard Rule #10's `TO public` compromise), the four
   `organization*` tables are `TO authenticated` with `auth.uid()` policies. A
   paired-but-never-signed-in device sends the anon key, so it reads zero org rows
   and simply has no team — which is the correct, fail-closed outcome, not a bug to
   work around. This is exactly why the org layer could ship without waiting on
   IDI-29's pairing decision: it never needs cross-account access to a legacy table.

3. **The cached copy in `config['org']` is what the dictation path reads.** The
   pipeline must never make a network call to find out what the team dictionary is
   (Hard Rule #1 + the latency rules): `fetch()` refreshes the cache off the hot
   path, and `team_dictionary()` is a pure local read. Writes to config go through
   save_config and ONLY when something actually changed (Hard Rule #3).
"""
import logging

logger = logging.getLogger("verbal.organizations")

# Shape returned whenever there is no team, for any reason. Callers branch on
# `org_id` being falsy and never have to distinguish "no org" from "couldn't ask".
NO_ORG = {
    "org_id": "",
    "name": "",
    "company_name": "",
    "role": "",
    "plan": "",
    "seats": 0,
    "leaderboard_enabled": False,
    "stats_visible_to_members": False,
    # IDI-218 domain governance. `is_generic_domain` defaults TRUE so an unknown or
    # unfetched org is treated as invite-only — the fail-closed direction.
    "domain": "",
    "is_generic_domain": True,
    "auto_join_enabled": False,
    "usage_consent": False,
    "leaderboard_opt_in": False,
    "members": [],
    "dictionary": {"vocabulary": [], "replacements": [], "snippets": []},
    "dictionary_updated_at": "",
}

_MEMBER_FIELDS = ("user_id", "email", "display_name", "role", "status",
                  "usage_consent", "leaderboard_opt_in", "joined_at")

# Last cloud-write outcome, so the dashboard can TELL the user a team edit didn't
# reach the account rather than silently pretending it did (same contract as
# dictionary.last_sync_error()).
_LAST_ERROR = {"ok": True, "error": ""}


def last_error() -> str:
    return "" if _LAST_ERROR.get("ok") else (_LAST_ERROR.get("error") or "")


def _mark(ok: bool, error: str = "") -> None:
    _LAST_ERROR["ok"] = bool(ok)
    _LAST_ERROR["error"] = "" if ok else (error or "Couldn't reach your team")


def _gate(config) -> bool:
    """May this device talk to the org tables at all?

    Requires a real signed-in session — not merely a `sync_user_id`, which a
    paired device also has (see the module docstring, point 2). Deliberately does
    NOT consult `sync_enabled`: the team roster/roles are account membership, not
    synced user content, and an admin turning sync off on one machine shouldn't
    make them stop being an admin. The shared DICTIONARY is gated separately,
    where it is applied."""
    try:
        cfg = config or {}
        if not cfg.get("sync_user_id"):
            return False
        from app import auth
        return bool(auth.cloud_allowed(cfg))
    except Exception:
        return False


def _headers(config, json=False):
    from app.auth import auth_header
    return auth_header(config, json=json)


def _rest(config, method, path, *, params=None, body=None, timeout=10.0, headers=None):
    """One guarded REST/RPC call. Returns the parsed body, or None on any failure."""
    import httpx
    from app.supabase_config import REST_URL
    h = _headers(config, json=(body is not None))
    if headers:
        h.update(headers)
    resp = httpx.request(method, f"{REST_URL}/{path}", params=params, json=body,
                         headers=h, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"{resp.status_code} {resp.text[:200]}")
    if not resp.content:
        return None
    return resp.json()


def _rpc(config, name, args, timeout=10.0):
    return _rest(config, "POST", f"rpc/{name}", body=args, timeout=timeout)


# ── local cache ───────────────────────────────────────────────────────────────

def get(config) -> dict:
    """The cached org, or NO_ORG. Pure local read — safe on the dictation path."""
    try:
        o = (config or {}).get("org")
        if not isinstance(o, dict) or not o.get("org_id"):
            return dict(NO_ORG)
        merged = dict(NO_ORG)
        merged.update(o)
        return merged
    except Exception:
        return dict(NO_ORG)


def is_admin(config) -> bool:
    return get(config).get("role") in ("owner", "admin")


def _store(config, org: dict, save_config_fn) -> dict:
    """Persist the org cache, writing config ONLY when the content changed."""
    try:
        current = (config or {}).get("org")
        if current == org:
            return org
        config["org"] = org
        save_config_fn(config)
    except Exception as e:
        logger.debug("org cache write failed: %s", e)
    return org


def clear(config, save_config_fn) -> None:
    """Drop the cached org — called from the sign-out / account-switch teardown
    (Hard Rule #13's desktop equivalent). A team's shared vocabulary must not
    survive into the next account signed in on this machine."""
    try:
        if (config or {}).get("org"):
            config["org"] = dict(NO_ORG)
            save_config_fn(config)
    except Exception as e:
        logger.debug("org clear failed: %s", e)


# ── fetch ─────────────────────────────────────────────────────────────────────

def fetch(config, save_config_fn) -> dict:
    """Pull membership + org + roster + shared dictionary and refresh the cache.

    Network. Never call from the dictation path — call it when the dashboard opens,
    after sign-in, and on an explicit refresh. Returns the same shape as get()."""
    if not _gate(config):
        return get(config)
    user_id = (config or {}).get("sync_user_id", "")
    try:
        rows = _rest(config, "GET", "organization_members", params={
            "select": "org_id,role,status,usage_consent,leaderboard_opt_in,"
                      # IDI-219 renamed the column to `purchased_seats`. Aliased back to `seats` in
            # the SELECT so the cached shape and every UI reference stay put — the
            # client word for it is unchanged, only the DB column moved.
            "organizations(id,name,company_name,owner_user_id,plan,"
            "seats:purchased_seats,leaderboard_enabled,stats_visible_to_members,"
            "domain,is_generic_domain,auto_join_enabled)",
            "user_id": f"eq.{user_id}",
            "status": "eq.active",
            "limit": "1",
        }) or []
        if not rows:
            _mark(True)
            return _store(config, dict(NO_ORG), save_config_fn)

        me = rows[0]
        org_row = me.get("organizations") or {}
        org_id = org_row.get("id") or me.get("org_id") or ""
        if not org_id:
            _mark(True)
            return _store(config, dict(NO_ORG), save_config_fn)

        org = dict(NO_ORG)
        org.update({
            "org_id": org_id,
            "name": org_row.get("name") or "",
            "company_name": org_row.get("company_name") or "",
            "role": me.get("role") or "member",
            "plan": org_row.get("plan") or "team",
            "seats": int(org_row.get("seats") or 0),
            "leaderboard_enabled": bool(org_row.get("leaderboard_enabled")),
            "stats_visible_to_members": bool(org_row.get("stats_visible_to_members")),
            "domain": org_row.get("domain") or "",
            # Absent column -> True, matching NO_ORG: never assume a domain is
            # corporate just because the read came back thin.
            "is_generic_domain": bool(org_row.get("is_generic_domain", True)),
            "auto_join_enabled": bool(org_row.get("auto_join_enabled")),
            "usage_consent": bool(me.get("usage_consent")),
            "leaderboard_opt_in": bool(me.get("leaderboard_opt_in")),
            "members": _fetch_members(config, org_id),
        })
        d, updated_at = _fetch_team_dictionary(config, org_id)
        org["dictionary"] = d
        org["dictionary_updated_at"] = updated_at
        _mark(True)
        return _store(config, org, save_config_fn)
    except Exception as e:
        logger.debug("org fetch failed: %s", e)
        _mark(False, str(e))
        return get(config)


def _fetch_members(config, org_id) -> list:
    try:
        rows = _rest(config, "GET", "organization_members", params={
            "select": ",".join(_MEMBER_FIELDS),
            "org_id": f"eq.{org_id}",
            "status": "eq.active",
            "order": "joined_at.asc",
        }) or []
        return [{k: r.get(k) for k in _MEMBER_FIELDS} for r in rows if isinstance(r, dict)]
    except Exception as e:
        logger.debug("org members fetch failed: %s", e)
        return []


def _fetch_team_dictionary(config, org_id):
    """The shared dictionary row, normalized through the SAME normalize() the
    personal dictionary uses — the org table is deliberately the same shape."""
    from app import dictionary
    try:
        rows = _rest(config, "GET", "organization_dictionary", params={
            "select": "vocabulary,replacements,snippets,updated_at",
            "org_id": f"eq.{org_id}",
            "limit": "1",
        }) or []
        if not rows:
            return dict(NO_ORG["dictionary"]), ""
        row = rows[0]
        return dictionary.normalize(row), str(row.get("updated_at") or "")
    except Exception as e:
        logger.debug("team dictionary fetch failed: %s", e)
        return dict(NO_ORG["dictionary"]), ""


def team_dictionary(config) -> dict:
    """The cached shared dictionary — pure local read, safe on the dictation path.

    Returns the empty dictionary when there is no team, when the user's sync
    toggle is off, or on any error. The sync gate applies HERE (and not in _gate)
    because the shared vocabulary IS synced user content: a user who turned sync
    off should dictate with their local dictionary only, exactly as before."""
    try:
        cfg = config or {}
        if not cfg.get("sync_enabled"):
            return dict(NO_ORG["dictionary"])
        d = get(cfg).get("dictionary")
        from app import dictionary
        return dictionary.normalize(d)
    except Exception:
        return dict(NO_ORG["dictionary"])


# ── membership ────────────────────────────────────────────────────────────────

def create(config, name, company, save_config_fn) -> dict:
    """Create an org with this user as owner (atomic, server-side)."""
    if not _gate(config):
        return {"ok": False, "error": "Sign in to create a team"}
    try:
        _rpc(config, "org_create", {"p_name": name or "", "p_company": company or ""})
        _mark(True)
        return {"ok": True, "org": fetch(config, save_config_fn)}
    except Exception as e:
        msg = str(e)
        logger.debug("org create failed: %s", msg)
        _mark(False, msg)
        if "already_in_org" in msg:
            return {"ok": False, "error": "You're already in a team"}
        if "name_required" in msg:
            return {"ok": False, "error": "Give the team a name"}
        return {"ok": False, "error": "Couldn't create the team"}


def invite(config, email, role="member") -> dict:
    """Invite by email via the `invite-member` Edge Function.

    The EF holds the provider key and does its own owner/admin re-check — this is
    a thin caller, deliberately: an invite must never be constructible client-side."""
    if not _gate(config):
        return {"ok": False, "error": "Sign in first"}
    org = get(config)
    if not org["org_id"]:
        return {"ok": False, "error": "No team yet"}
    if org["role"] not in ("owner", "admin"):
        return {"ok": False, "error": "Only owners and admins can invite"}
    try:
        import httpx
        from app.supabase_config import SUPABASE_URL
        resp = httpx.post(
            f"{SUPABASE_URL}/functions/v1/invite-member",
            json={"org_id": org["org_id"], "email": (email or "").strip(), "role": role},
            headers=_headers(config, json=True), timeout=20.0,
        )
        data = resp.json() if resp.content else {}
        if resp.status_code < 400 and data.get("ok"):
            _mark(True)
            return {"ok": True, "invite": data.get("invite") or {}, "link": data.get("link") or "",
                    "reissued": bool(data.get("reissued")), "seats": data.get("seats") or {}}
        code = data.get("error") or ""
        detail = str(data.get("detail") or "")[:300]
        # The friendly line is what the UI shows; `detail` is the provider's own
        # words. Keep BOTH — a mail failure is undiagnosable without the reason,
        # and it is the one error here the user can't infer from context.
        _mark(False, detail or str(code or resp.status_code))
        msg = _INVITE_ERRORS.get(code, "Couldn't send the invite")
        logger.warning("invite failed: %s %s", code, detail)
        return {"ok": False, "error": msg, "detail": detail}
    except Exception as e:
        logger.debug("invite failed: %s", e)
        _mark(False, str(e))
        return {"ok": False, "error": "Couldn't send the invite"}


_INVITE_ERRORS = {
    "bad_email": "That doesn't look like an email address",
    "no_seats": "No seats left on this plan",
    "already_member": "They're already on the team",
    "forbidden": "Only owners and admins can invite",
    "email_not_configured": "Email isn't configured yet — invites can't be sent",
    "email_failed": "The invite email didn't send",
}


def list_invites(config) -> list:
    """Pending invites, for the admin roster. Owner/admin only (enforced by RLS —
    a member's read simply returns nothing)."""
    org = get(config)
    if not org["org_id"] or not _gate(config):
        return []
    try:
        return _rest(config, "GET", "organization_invites", params={
            "select": "id,email,role,status,expires_at,created_at",
            "org_id": f"eq.{org['org_id']}",
            "status": "eq.pending",
            "order": "created_at.desc",
        }) or []
    except Exception as e:
        logger.debug("invite list failed: %s", e)
        return []


def revoke_invite(config, invite_id) -> dict:
    org = get(config)
    if not org["org_id"] or org["role"] not in ("owner", "admin"):
        return {"ok": False, "error": "Only owners and admins can do that"}
    try:
        _rest(config, "PATCH", "organization_invites",
              params={"id": f"eq.{invite_id}", "org_id": f"eq.{org['org_id']}"},
              body={"status": "revoked"})
        _mark(True)
        return {"ok": True}
    except Exception as e:
        logger.debug("revoke invite failed: %s", e)
        _mark(False, str(e))
        return {"ok": False, "error": "Couldn't revoke that invite"}


def invite_preview(config, token) -> dict:
    """Read an invite by token WITHOUT claiming it, so the join UI can name the
    team before the user commits. Works signed-out (the RPC is the one org
    function `anon` may call), so this is also what a paired-only device sees."""
    try:
        res = _rpc(config, "org_invite_preview", {"p_token": _token_of(token)}) or {}
        if res.get("ok"):
            return {"ok": True, **{k: v for k, v in res.items() if k != "ok"}}
        return {"ok": False, "error": _CLAIM_ERRORS.get(res.get("error"), "That invite link isn't valid")}
    except Exception as e:
        logger.debug("invite_preview failed: %s", e)
        return {"ok": False, "error": "Couldn't reach the team service"}


def _token_of(v) -> str:
    """Accept a bare token or the whole link as pasted out of the email."""
    import re as _re
    v = (v or "").strip()
    m = _re.search(r"[?&]t(?:oken)?=([^&\s]+)", v)
    if m:
        from urllib.parse import unquote
        return unquote(m.group(1))
    return v


def claim_invite(config, token, save_config_fn, confirm_mismatch=False) -> dict:
    """Redeem an invite for the signed-in account.

    IDI-223: the TOKEN is the source of truth, not the email string — "Sign in with
    Apple" hands back a privaterelay address for someone invited under their work
    email, and strict equality would lock them out forever. So a mismatch comes back
    as `needs_confirm` carrying BOTH addresses, and the caller re-invokes with
    confirm_mismatch=True once the user has said yes. Nothing is ever silently
    attached to the wrong account."""
    if not _gate(config):
        return {"ok": False, "error": "Sign in first"}
    try:
        res = _rpc(config, "org_claim_invite", {
            "p_token": _token_of(token),
            "p_confirm_mismatch": bool(confirm_mismatch),
        }) or {}
        if res.get("ok"):
            _mark(True)
            return {"ok": True, "already": bool(res.get("already")),
                    "org": fetch(config, save_config_fn)}
        code = res.get("error") or ""
        if code == "email_mismatch":
            return {"ok": False, "needs_confirm": True,
                    "invited_email": res.get("invited_email") or "",
                    "current_email": res.get("current_email") or "",
                    "error": "This invite was sent to a different address."}
        if code == "no_seats":
            return {"ok": False, "error": "That team has no seats left — ask an admin to add one.",
                    "purchased_seats": res.get("purchased_seats"),
                    "active_members": res.get("active_members")}
        _mark(False, code)
        return {"ok": False, "error": _CLAIM_ERRORS.get(code, "That invite couldn't be used")}
    except Exception as e:
        logger.debug("claim invite failed: %s", e)
        _mark(False, str(e))
        return {"ok": False, "error": "Couldn't reach the team service"}


def decline_invite(config, token) -> dict:
    """Turn the invite down (IDI-221). Marks it `rejected` so the admin can see it
    was seen and refused, rather than silently rotting to `expired`."""
    if not _gate(config):
        return {"ok": False, "error": "Sign in first"}
    try:
        res = _rpc(config, "org_decline_invite", {"p_token": _token_of(token)}) or {}
        if res.get("ok"):
            return {"ok": True}
        return {"ok": False, "error": _CLAIM_ERRORS.get(res.get("error"), "That invite isn't valid")}
    except Exception as e:
        logger.debug("decline invite failed: %s", e)
        return {"ok": False, "error": "Couldn't reach the team service"}


def pending_invites_for_me(config) -> list:
    """IDI-222's fallback. When a deep link is eaten by an in-app browser and the
    person installs manually, this is what still finds their invite after sign-in.
    Matches on the SESSION's own email server-side, so it can only ever return
    invites addressed to this user, and it carries no token."""
    if not _gate(config):
        return []
    try:
        res = _rpc(config, "org_pending_invites_for_me", {}) or {}
        return res.get("invites") or []
    except Exception as e:
        logger.debug("pending_invites_for_me failed: %s", e)
        return []


def accept_pending(config, org_id, save_config_fn) -> dict:
    """Accept an invite discovered by the lookup above. No token needed — the
    server re-derives it from the session's email, which already matched."""
    if not _gate(config):
        return {"ok": False, "error": "Sign in first"}
    try:
        res = _rpc(config, "org_accept_pending_invite", {"p_org": org_id}) or {}
        if res.get("ok"):
            _mark(True)
            return {"ok": True, "org": fetch(config, save_config_fn)}
        code = res.get("error") or ""
        if code == "no_seats":
            return {"ok": False, "error": "That team has no seats left — ask an admin to add one."}
        return {"ok": False, "error": _CLAIM_ERRORS.get(code, "That invite couldn't be used")}
    except Exception as e:
        logger.debug("accept_pending failed: %s", e)
        return {"ok": False, "error": "Couldn't reach the team service"}


def set_auto_join(config, enabled, save_config_fn) -> dict:
    """IDI-218 domain discovery. The DB refuses this outright on a generic domain,
    so a gmail-founded team can never become a discovery surface for strangers —
    this only translates that refusal into something a human can read."""
    org = get(config)
    if not org["org_id"]:
        return {"ok": False, "error": "No team"}
    try:
        res = _rpc(config, "org_set_auto_join",
                   {"p_org": org["org_id"], "p_enabled": bool(enabled)}) or {}
        if res.get("ok"):
            _mark(True)
            return {"ok": True, "org": fetch(config, save_config_fn)}
        code = res.get("error") or ""
        if code == "generic_domain":
            return {"ok": False, "error": (
                "Your team was created on a personal email domain, so anyone could "
                "claim it. Domain joining is only available on a company domain.")}
        return {"ok": False, "error": _ROLE_ERRORS.get(code, "Couldn't change that setting")}
    except Exception as e:
        logger.debug("set_auto_join failed: %s", e)
        return {"ok": False, "error": "Couldn't change that setting"}


_CLAIM_ERRORS = {
    "invalid_token": "That invite link isn't valid",
    "expired": "That invite has expired — ask for a new one",
    "already_used": "That invite has already been used",
    "already_in_org": "You're already in a team",
    "no_seats": "That team has no seats left",
    "not_authenticated": "Sign in first",
}


def set_role(config, user_id, role, save_config_fn) -> dict:
    try:
        org = get(config)
        res = _rpc(config, "org_set_role", {
            "p_org": org["org_id"], "p_user": user_id, "p_role": role}) or {}
        if not res.get("ok"):
            _mark(False, res.get("error") or "")
            return {"ok": False, "error": _ROLE_ERRORS.get(res.get("error"), "Couldn't change that role")}
        _mark(True)
        return {"ok": True, "org": fetch(config, save_config_fn)}
    except Exception as e:
        logger.debug("set_role failed: %s", e)
        _mark(False, str(e))
        return {"ok": False, "error": "Couldn't change that role"}


_ROLE_ERRORS = {
    "forbidden": "Only owners and admins can do that",
    "cannot_change_owner": "The owner's role can't be changed",
    "not_a_member": "They're not on the team any more",
}


def remove_member(config, user_id, save_config_fn) -> dict:
    """Remove someone (or, with your own id, leave the team)."""
    try:
        org = get(config)
        res = _rpc(config, "org_remove_member", {
            "p_org": org["org_id"], "p_user": user_id}) or {}
        if not res.get("ok"):
            _mark(False, res.get("error") or "")
            return {"ok": False, "error": _REMOVE_ERRORS.get(res.get("error"), "Couldn't remove them")}
        _mark(True)
        # Leaving is the one case where the cache must be dropped, not refreshed:
        # the shared vocabulary stops applying the moment membership ends.
        if user_id == (config or {}).get("sync_user_id"):
            clear(config, save_config_fn)
            return {"ok": True, "org": get(config)}
        return {"ok": True, "org": fetch(config, save_config_fn)}
    except Exception as e:
        logger.debug("remove_member failed: %s", e)
        _mark(False, str(e))
        return {"ok": False, "error": "Couldn't remove them"}


_REMOVE_ERRORS = {
    "forbidden": "Only owners and admins can do that",
    "cannot_remove_owner": "The owner can't be removed — transfer the team first",
    "not_a_member": "They're not on the team any more",
}


# ── settings & consent ────────────────────────────────────────────────────────

def set_consent(config, usage, leaderboard, save_config_fn) -> dict:
    """The member's OWN consent flags (Phase 5). Nobody can set these for someone
    else — the RPC keys on auth.uid(), not on a parameter."""
    try:
        org = get(config)
        if not org["org_id"]:
            return {"ok": False, "error": "No team"}
        _rpc(config, "org_set_consent", {
            "p_org": org["org_id"], "p_usage": bool(usage),
            "p_leaderboard": bool(leaderboard)})
        _mark(True)
        return {"ok": True, "org": fetch(config, save_config_fn)}
    except Exception as e:
        logger.debug("set_consent failed: %s", e)
        _mark(False, str(e))
        return {"ok": False, "error": "Couldn't save that preference"}


def set_org_settings(config, save_config_fn, **fields) -> dict:
    """Owner/admin edits to the org row (name, company_name, leaderboard_enabled).
    Allowlisted — a client must never be able to PATCH `plan`, `seats` or
    `owner_user_id` on its own authority."""
    allowed = {k: v for k, v in fields.items()
               if k in ("name", "company_name", "leaderboard_enabled",
                        "stats_visible_to_members") and v is not None}
    if not allowed:
        return {"ok": False, "error": "Nothing to save"}
    try:
        org = get(config)
        if org["role"] not in ("owner", "admin"):
            return {"ok": False, "error": "Only owners and admins can do that"}
        if ("leaderboard_enabled" in allowed or "stats_visible_to_members" in allowed) \
                and org["role"] != "owner":
            return {"ok": False, "error": "Only the owner can change that"}
        allowed["updated_at"] = "now()"
        _rest(config, "PATCH", "organizations",
              params={"id": f"eq.{org['org_id']}"}, body=allowed)
        _mark(True)
        return {"ok": True, "org": fetch(config, save_config_fn)}
    except Exception as e:
        logger.debug("set_org_settings failed: %s", e)
        _mark(False, str(e))
        return {"ok": False, "error": "Couldn't save the team settings"}


# ── shared dictionary (Phase 4) ───────────────────────────────────────────────

def save_team_dictionary(config, d, save_config_fn) -> dict:
    """Write the shared dictionary, compare-and-swap on `updated_at` (IDI-174's
    pattern): write filtered on the last-witnessed value; 0 rows means someone
    else won the race, so refetch, merge and retry ONCE. A double failure is
    REPORTED rather than silently dropped."""
    from app import dictionary
    org = get(config)
    if not org["org_id"]:
        return {"ok": False, "error": "No team"}
    if org["role"] not in ("owner", "admin"):
        return {"ok": False, "error": "Only owners and admins can edit the team dictionary"}
    body = dictionary.normalize(d)
    try:
        if _cas_write(config, org["org_id"], body, org.get("dictionary_updated_at") or ""):
            fetch(config, save_config_fn)
            _mark(True)
            return {"ok": True, "dictionary": get(config)["dictionary"]}
        remote, witness = _fetch_team_dictionary(config, org["org_id"])
        merged = dictionary.merge_dictionary(body, remote)
        if _cas_write(config, org["org_id"], merged, witness):
            fetch(config, save_config_fn)
            _mark(True)
            return {"ok": True, "dictionary": get(config)["dictionary"]}
        _mark(False, "conflict")
        return {"ok": False, "error": "Couldn't sync — another admin was editing. Try again."}
    except Exception as e:
        logger.debug("save_team_dictionary failed: %s", e)
        _mark(False, str(e))
        return {"ok": False, "error": "Couldn't save the team dictionary"}


def _cas_write(config, org_id, d, witness) -> bool:
    """One compare-and-swap PATCH (or the initial INSERT). True if it landed."""
    user_id = (config or {}).get("sync_user_id", "")
    payload = {
        "vocabulary": d["vocabulary"],
        "replacements": d["replacements"],
        "snippets": d["snippets"],
        "updated_by": user_id,
        "updated_at": "now()",
    }
    if not witness:
        # No row witnessed yet — org_create seeds one, but an org made before this
        # code shipped may not have it. Upsert rather than assume.
        _rest(config, "POST", "organization_dictionary",
              body=dict(payload, org_id=org_id),
              headers={"Prefer": "resolution=merge-duplicates,return=representation"})
        return True
    rows = _rest(config, "PATCH", "organization_dictionary",
                 params={"org_id": f"eq.{org_id}", "updated_at": f"eq.{witness}"},
                 body=payload,
                 headers={"Prefer": "return=representation"}) or []
    return len(rows) > 0


# ── usage insights (Phase 5) ──────────────────────────────────────────────────

def usage_summary(config, days=30) -> dict:
    """Per-member aggregates.

    Counts, durations and (via app_breakdown) app names ONLY — the RPC has no
    column that could carry transcript text, and members who haven't consented are
    absent from the result entirely rather than shown as zeroes (so their silence
    isn't itself a signal).

    NOT gated on role here. The RPC does the split — an owner/admin gets every
    consenting member, anyone else gets exactly their own row — the same as
    `org_usage_series` and `org_app_breakdown`. Gating it client-side as well is
    what made a plain member's whole Team screen read as zeroes: every total on
    that page is computed from these rows, so refusing to ask produced a team that
    looked like it had never dictated anything."""
    org = get(config)
    if not org["org_id"]:
        return {"ok": False, "rows": []}
    try:
        rows = _rpc(config, "org_usage_summary",
                    {"p_org": org["org_id"], "p_days": int(days)}) or []
        _mark(True)
        return {"ok": True, "rows": rows,
                "consented": sum(1 for m in org["members"] if m.get("usage_consent")),
                "members": len(org["members"])}
    except Exception as e:
        logger.debug("usage_summary failed: %s", e)
        _mark(False, str(e))
        return {"ok": False, "rows": []}


def usage_series(config, days=98) -> dict:
    """Daily word counts per member — the roster sparklines and the per-member
    activity heatmap.

    Returned as {user_id: {"YYYY-MM-DD": words}} so the UI can index straight into
    it. One call for the whole org; an admin gets every consenting member, anyone
    else gets only their own row (the RPC enforces that, not this)."""
    org = get(config)
    if not org["org_id"]:
        return {"ok": True, "series": {}}
    try:
        rows = _rpc(config, "org_usage_series",
                    {"p_org": org["org_id"], "p_days": int(days)}) or []
        out: dict = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            uid = str(r.get("user_id") or "")
            day = str(r.get("day") or "")[:10]
            if not uid or not day:
                continue
            out.setdefault(uid, {})[day] = int(r.get("words") or 0)
        _mark(True)
        return {"ok": True, "series": out}
    except Exception as e:
        logger.debug("usage_series failed: %s", e)
        _mark(False, str(e))
        return {"ok": False, "series": {}}


def seed_team_dictionary_from_personal(config, save_config_fn) -> dict:
    """Copy the owner's OWN dictionary into the team's (the post-create onboarding
    step). A team that starts empty has no reason to be used; one seeded with real
    vocabulary works from the first dictation.

    This is a MERGE, never a replace — it goes through the same CAS write as any
    other team-dictionary edit, and `merge_with_team` keeps whatever the team
    already had. The personal dictionary is left completely untouched: it is copied
    FROM, not moved."""
    from app import dictionary
    org = get(config)
    if not org["org_id"]:
        return {"ok": False, "error": "No team"}
    if org["role"] not in ("owner", "admin"):
        return {"ok": False, "error": "Only owners and admins can do that"}
    try:
        personal = dictionary.get(config)
        if not (personal["vocabulary"] or personal["replacements"] or personal["snippets"]):
            return {"ok": False, "error": "Your dictionary is empty — nothing to share yet"}
        # Team entries win here, unlike at dictation time: this is an explicit
        # "add mine to ours" action, so anything the team already agreed on stays.
        merged = dictionary.merge_with_team(dictionary.normalize(org.get("dictionary")), personal)
        res = save_team_dictionary(config, merged, save_config_fn)
        if not res.get("ok"):
            return res
        return {"ok": True, "dictionary": res.get("dictionary"),
                "added": {
                    "vocabulary": len(personal["vocabulary"]),
                    "replacements": len(personal["replacements"]),
                    "snippets": len(personal["snippets"]),
                }}
    except Exception as e:
        logger.debug("seed_team_dictionary failed: %s", e)
        _mark(False, str(e))
        return {"ok": False, "error": "Couldn't copy your dictionary to the team"}


def app_breakdown(config, days=30) -> dict:
    """Per-member per-app dictation counts — "where does each person actually use
    Flume?".

    Returned as {user_id: [{app, dictations, words}, …]}, biggest first, so the UI
    can index straight in. Only rows with an `app` value count, and that column is
    new (2026-08-21): every dictation before it shipped is NULL and unbackfillable,
    so this is sparse at first and fills in from here."""
    org = get(config)
    if not org["org_id"]:
        return {"ok": True, "apps": {}}
    try:
        rows = _rpc(config, "org_app_breakdown",
                    {"p_org": org["org_id"], "p_days": int(days)}) or []
        out: dict = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            uid = str(r.get("user_id") or "")
            name = str(r.get("app") or "").strip()
            if not uid or not name:
                continue
            out.setdefault(uid, []).append({
                "app": name,
                "dictations": int(r.get("dictations") or 0),
                "words": int(r.get("words") or 0),
            })
        _mark(True)
        return {"ok": True, "apps": out}
    except Exception as e:
        logger.debug("app_breakdown failed: %s", e)
        _mark(False, str(e))
        return {"ok": False, "apps": {}}


def leaderboard(config, days=7) -> dict:
    """The team-visible ranking (Phase 5b). Readable by every active member once
    the owner has enabled it org-wide; lists every active member who shares counts."""
    org = get(config)
    if not org["org_id"] or not org["leaderboard_enabled"]:
        return {"ok": True, "enabled": False, "rows": []}
    try:
        rows = _rpc(config, "org_leaderboard",
                    {"p_org": org["org_id"], "p_days": int(days)}) or []
        _mark(True)
        return {"ok": True, "enabled": True, "rows": rows}
    except Exception as e:
        logger.debug("leaderboard failed: %s", e)
        _mark(False, str(e))
        return {"ok": False, "enabled": True, "rows": []}
