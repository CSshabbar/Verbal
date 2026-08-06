"""
Verbal cross-device sync via Supabase Realtime.

Flow:
  Mac transcribes → push to Supabase → iPhone receives → clipboard
  iPhone transcribes → push to Supabase → Mac receives → clipboard + paste
"""

import json
import logging
import platform
import threading
import time
import httpx

from app.config import PLATFORM
from app.supabase_config import SUPABASE_URL, SUPABASE_KEY, REST_URL

logger = logging.getLogger("verbal.sync")

# Supabase Realtime WebSocket endpoint
WS_URL = (
    f"wss://ovpcthjingugwvpxlsna.supabase.co/realtime/v1/websocket"
    f"?apikey={SUPABASE_KEY}&vsn=1.0.0"
)


def _utc_now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class SyncClient:
    # Backfill is bounded: a reconnect must never dump an unbounded backlog of
    # old dictations into whatever app happens to be focused.
    BACKFILL_LIMIT = 50

    def __init__(self, user_id: str, device_name: str, on_receive):
        self.user_id     = user_id
        self.device_id   = platform.node()
        self.device_name = device_name or platform.node()
        self.on_receive  = on_receive
        self._ws         = None
        self._connected  = False
        self._ref        = 0
        # IDI-171: one shutdown signal for BOTH background loops. Without it
        # `stop()` only closed the socket — `_run()` reconnected 5s later and
        # `_register_device` kept heart-beating a signed-out device forever
        # (which also resurrected the `devices` row sign-out had just deleted).
        self._stop       = threading.Event()
        # Newest transcription `created_at` we have already handled. Seeded to
        # NOW so the first connect can't replay history; every later
        # (re)connect backfills only the gap it actually missed.
        self._last_seen_at = _utc_now_iso()
        self._seen_ids   = set()
        self._seen_order = []
        self._thread     = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        # Register this device and start heartbeat
        threading.Thread(target=self._register_device, daemon=True).start()
        logger.info(f"SyncClient started — user={user_id[:12]} device={self.device_id}")

    def _register_device(self):
        """Register this device in Supabase and update last_seen every 60s."""
        from app.auth import auth_header, cloud_allowed
        while not self._stop.is_set():
            try:
                if not cloud_allowed():
                    return   # signed out — never heartbeat into an ex-account
                httpx.post(
                    f"{REST_URL}/devices?on_conflict=user_id,device_id",
                    headers={
                        **auth_header(json=True),
                        "Prefer":        "return=minimal,resolution=merge-duplicates",
                    },
                    json={
                        "user_id":     self.user_id,
                        "device_id":   self.device_id,
                        "device_name": self.device_name,
                        "device_type": PLATFORM,
                        "last_seen":   _utc_now_iso(),
                    },
                    timeout=5,
                )
            except Exception as e:
                logger.debug(f"Device register error: {e}")
            self._stop.wait(60)

    def _next_ref(self) -> str:
        self._ref += 1
        return str(self._ref)

    def push(self, text: str, target_device_id: str | None = None):
        """Insert transcription via REST. If target_device_id set, only that device receives it."""
        logger.info(f"Sync push request: target={target_device_id}")
        threading.Thread(target=self._push_rest, args=(text, target_device_id), daemon=True).start()

    def _push_rest(self, text: str, target_device_id: str | None = None):
        from app.auth import auth_header
        try:
            payload = {
                "user_id":     self.user_id,
                "device_id":   self.device_id,
                "device_name": self.device_name,
                "text":        text,
            }
            # Only include target_device_id if it's not None (None means broadcast)
            if target_device_id:
                payload["target_device_id"] = target_device_id
                logger.debug(f"Targeting specific device: {target_device_id}")
            else:
                logger.debug("Broadcasting to all devices")

            resp = httpx.post(
                f"{REST_URL}/transcriptions",
                headers={**auth_header(json=True), "Prefer": "return=minimal"},
                json=payload,
                timeout=5,
            )
            if resp.status_code in (200, 201):
                logger.info(f"Sync pushed: '{text[:50]}'" + (f" → {target_device_id[:12]}" if target_device_id else ""))
            else:
                logger.warning(f"Sync push failed {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Sync push error: {e}")

    def _run(self):
        """THE reconnect loop — the only one (IDI-171).

        `on_close` used to call `_listen()` again from inside the close
        handler, *on top of* this loop, so a flapping connection could stack
        two (or more) live sockets, each with its own token-refresh thread and
        each delivering every INSERT again. Now `on_close` only signals and
        returns: `run_forever` unwinds, `_listen` returns, and this loop owns
        the backoff."""
        delay = 5
        while not self._stop.is_set():
            try:
                self._listen()
                delay = 5           # a real connection happened → reset backoff
            except Exception as e:
                logger.warning(f"Sync listener crashed: {e} — retry in {delay}s")
                delay = min(delay * 2, 60)
            if self._stop.is_set():
                break
            self._stop.wait(delay)

    # ── missed-while-disconnected backfill (IDI-171) ──────────────────────────
    def _remember(self, record) -> bool:
        """Track the newest created_at + a bounded recent-id set. Returns False
        when this row has already been handled (realtime/backfill overlap)."""
        rid = record.get("id")
        if rid:
            if rid in self._seen_ids:
                return False
            self._seen_ids.add(rid)
            self._seen_order.append(rid)
            if len(self._seen_order) > 200:
                self._seen_ids.discard(self._seen_order.pop(0))
        created = record.get("created_at") or ""
        if created and created > self._last_seen_at:
            self._last_seen_at = created
        return True

    def _deliver(self, record):
        """The single receive path — shared by realtime INSERTs and backfill,
        so the own-device / targeted-device filters can't drift apart."""
        if not self._remember(record):
            return
        if record.get("device_id") == self.device_id:
            return                       # skip our own inserts
        target = record.get("target_device_id")
        if target and target != self.device_id:
            return                       # targeted at another device
        text = record.get("text", "")
        if text and self.on_receive:
            logger.info(f"Sync received from '{record.get('device_name','Unknown')}': '{text[:60]}'")
            self.on_receive(text, record.get("device_name", "Unknown"))

    def _backfill(self):
        """After a (re)connect, replay any transcriptions inserted while we
        were asleep/disconnected. Bounded (BACKFILL_LIMIT), user-scoped, and
        routed through `_deliver` so the targeted-filter still applies."""
        from app.auth import auth_header, cloud_allowed
        try:
            if self._stop.is_set() or not cloud_allowed():
                return
            resp = httpx.get(
                f"{REST_URL}/transcriptions",
                headers=auth_header(),
                params={
                    "user_id":    f"eq.{self.user_id}",
                    "created_at": f"gt.{self._last_seen_at}",
                    "select":     "id,text,device_id,device_name,target_device_id,created_at",
                    "order":      "created_at.asc",
                    "limit":      str(self.BACKFILL_LIMIT),
                },
                timeout=8,
            )
            if resp.status_code != 200:
                logger.debug(f"Sync backfill skipped ({resp.status_code})")
                return
            rows = resp.json() or []
            if rows:
                logger.info(f"Sync backfill: {len(rows)} missed row(s)")
            for r in rows:
                if self._stop.is_set():
                    return
                if isinstance(r, dict):
                    self._deliver(r)
        except Exception as e:
            logger.debug(f"Sync backfill error: {e}")

    def _listen(self):
        import websocket
        from app.auth import get_access_token

        # Realtime evaluates postgres_changes RLS off the JWT in the join
        # payload's `access_token` (falls back to the apikey/anon role if
        # omitted) — MER-29: forward the signed-in user's token here too, so
        # a future auth.uid()-scoped policy on `transcriptions` doesn't also
        # require a Realtime protocol change at cutover time.
        ws_token = get_access_token() or SUPABASE_KEY

        def on_open(ws):
            self._connected = True
            logger.info("Sync WebSocket connected — subscribing to postgres_changes")

            # Single join message with postgres_changes config
            # Topic must be "realtime:*" for postgres_changes
            ws.send(json.dumps({
                "topic": "realtime:*",
                "event": "phx_join",
                "payload": {
                    "config": {
                        "postgres_changes": [
                            {
                                "event":  "INSERT",
                                "schema": "public",
                                "table":  "transcriptions",
                                "filter": f"user_id=eq.{self.user_id}",
                            }
                        ]
                    },
                    "access_token": ws_token,
                },
                "ref": self._next_ref(),
            }))
            # Catch up on anything inserted while we were away. Off the socket
            # thread — the REST round-trip must not stall the reader.
            threading.Thread(target=self._backfill, daemon=True).start()

        def on_message(ws, raw):
            try:
                msg     = json.loads(raw)
                topic   = msg.get("topic", "")
                event   = msg.get("event", "")
                payload = msg.get("payload", {})

                logger.debug(f"WS msg: topic={topic} event={event}")

                # Phoenix heartbeat — must reply or connection drops
                if topic == "phoenix" and event == "heartbeat":
                    ws.send(json.dumps({
                        "topic":   "phoenix",
                        "event":   "heartbeat",
                        "payload": {},
                        "ref":     msg.get("ref"),
                    }))
                    return

                # Subscription confirmed
                if event == "phx_reply" and payload.get("status") == "ok":
                    logger.info("Sync subscription confirmed ✓")
                    return

                # Postgres INSERT event — one shared receive path (own-device
                # skip, target filter, dedup) with the reconnect backfill.
                if event == "postgres_changes":
                    data   = payload.get("data", {})
                    self._deliver(data.get("record", {}) or {})

            except Exception as e:
                logger.error(f"Sync message error: {e} — raw: {raw[:200]}")

        def on_close(ws, code, msg):
            # SIGNAL ONLY (IDI-171). Reconnecting from inside the close handler
            # ran a second `_listen()` underneath the outer `_run()` retry loop,
            # so connections could stack. `run_forever` returns right after
            # this, `_listen` unwinds, and `_run` owns the retry/backoff.
            self._connected = False
            if self._ws is ws:
                self._ws = None
            logger.info(f"Sync WebSocket closed (code={code})")

        def on_error(ws, error):
            logger.error(f"Sync WebSocket error: {error}")
            # Don't let errors crash the entire application
            pass

        def _refresh_ws_token_loop(ws):
            # Access tokens are short-lived (~1h) but this WS connection can
            # stay open far longer — push a refreshed token onto the already
            # joined channel every 20 min so a long session doesn't silently
            # start running on a stale/expired JWT. Exits once this specific
            # connection is replaced (reconnect) or closed.
            while self._ws is ws and not self._stop.is_set():
                self._stop.wait(1200)
                if self._ws is not ws or not self._connected or self._stop.is_set():
                    return
                try:
                    fresh = get_access_token()
                    if fresh:
                        ws.send(json.dumps({
                            "topic": "realtime:*",
                            "event": "access_token",
                            "payload": {"access_token": fresh},
                            "ref": self._next_ref(),
                        }))
                except Exception as e:
                    logger.debug(f"WS token refresh push failed: {e}")

        try:
            ws = websocket.WebSocketApp(
                WS_URL,
                header={"Authorization": f"Bearer {ws_token}"},
                on_open=on_open,
                on_message=on_message,
                on_close=on_close,
                on_error=on_error,
            )
            self._ws = ws
            threading.Thread(target=_refresh_ws_token_loop, args=(ws,), daemon=True).start()
            ws.run_forever(ping_interval=25, ping_timeout=10)
        except Exception as e:
            logger.error(f"Sync WebSocket failed to start: {e}")
            # Continue running even if sync fails

    @property
    def connected(self) -> bool:
        return self._connected

    def stop(self):
        """Permanent shutdown: no reconnect, no further device heartbeat."""
        self._stop.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        self._ws = None
        self._connected = False


def register_device_presence(user_id: str, device_id: str, device_name: str) -> None:
    """Lightweight presence upsert — refresh THIS device's last_seen so other
    devices see it online, INDEPENDENT of whether the content-sync SyncClient is
    running (being signed in is enough).

    Driven by an APP-LEVEL heartbeat (`main._presence_loop` / `win_main`), NOT
    by a dashboard-window loop: it used to ride `flume_web_dashboard`'s
    `while self._window is not None` refresh loop, so closing the dashboard
    made the Mac go Offline to every other device within ~5 min (IDI-177).

    Gated on being SIGNED IN (`cloud_allowed`), never on `sync_user_id` alone —
    that id used to survive sign-out and kept an ex-account's device online.
    Best-effort / fail-closed."""
    if not user_id or not device_id:
        return
    from app.auth import auth_header, cloud_allowed
    import datetime
    if not cloud_allowed():
        return
    try:
        httpx.post(
            f"{REST_URL}/devices?on_conflict=user_id,device_id",
            headers={**auth_header(json=True),
                     "Prefer": "return=minimal,resolution=merge-duplicates"},
            json={"user_id": user_id, "device_id": device_id,
                  "device_name": device_name or device_id, "device_type": PLATFORM,
                  "last_seen": datetime.datetime.now(datetime.timezone.utc).isoformat()},
            timeout=5,
        )
    except Exception as e:
        logger.debug(f"register_device_presence error: {e}")


def delete_device_presence(user_id: str, device_id: str = "", headers: dict | None = None) -> None:
    """Remove THIS device's `devices` row on sign-out (IDI-170) — scoped by
    user_id AND device_id so it can never touch another device (or another
    account). `device_id` defaults to the same identity the presence upsert
    uses (`platform.node()`, which is also `SyncClient.device_id`).

    `headers` lets the caller pass REST headers captured BEFORE the local
    session was torn down; without a session we'd fall back to the anon key,
    which works today under the permissive RLS but won't after the
    `auth.uid()` cutover. Best-effort / fail-closed."""
    device_id = device_id or platform.node()
    if not user_id or not device_id:
        return
    try:
        if headers is None:
            from app.auth import auth_header
            headers = auth_header()
        httpx.delete(
            f"{REST_URL}/devices",
            headers={**headers, "Prefer": "return=minimal"},
            params={"user_id": f"eq.{user_id}", "device_id": f"eq.{device_id}"},
            timeout=5,
        )
        logger.info("Removed device row for %s… on sign-out", device_id[:24])
    except Exception as e:
        logger.debug(f"delete_device_presence error: {e}")


def fetch_account_devices(user_id: str, exclude_device_id: str = "") -> list:
    """ALL devices on the account, each tagged with an ``online`` flag (last_seen
    within 5 min) — NOT just the last-5-min set that ``fetch_devices`` returns.

    This backs the "your devices" list: a device must stay VISIBLE even when its
    heartbeat is stale (app closed / sync off), or two apps can't see each other
    unless both are actively syncing right now. Optionally excludes the current
    device. Fail-closed to []."""
    from app.auth import auth_header
    import datetime
    try:
        params = {
            "user_id": f"eq.{user_id}",
            "select":  "device_id,device_name,device_type,last_seen",
            "order":   "last_seen.desc",
        }
        if exclude_device_id:
            params["device_id"] = f"neq.{exclude_device_id}"
        resp = httpx.get(f"{REST_URL}/devices", headers=auth_header(), params=params, timeout=5)
        if resp.status_code != 200:
            return []
        now = datetime.datetime.now(datetime.timezone.utc)
        rows = resp.json() or []
        for d in rows:
            ls = d.get("last_seen")
            online = False
            if ls:
                try:
                    t = datetime.datetime.fromisoformat(str(ls).replace("Z", "+00:00"))
                    if t.tzinfo is None:
                        t = t.replace(tzinfo=datetime.timezone.utc)
                    online = (now - t).total_seconds() < 300
                except Exception:
                    online = False
            d["online"] = online
        return rows
    except Exception as e:
        logger.error(f"fetch_account_devices error: {e}")
        return []


def fetch_devices(user_id: str, exclude_device_id: str) -> list:
    """Fetch all devices for this user except the current one (seen in last 5 min).

    Kept for the sign-in "is another device online right now?" detection; the
    dashboard device LIST uses fetch_account_devices (which also shows offline)."""
    from app.auth import auth_header
    try:
        import datetime
        cutoff = (datetime.datetime.now(datetime.timezone.utc) -
                  datetime.timedelta(minutes=5)).isoformat()
        resp = httpx.get(
            f"{REST_URL}/devices",
            headers=auth_header(),
            params={
                "user_id":   f"eq.{user_id}",
                "device_id": f"neq.{exclude_device_id}",
                "last_seen": f"gte.{cutoff}",
                "select":    "device_id,device_name,device_type",
            },
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.error(f"fetch_devices error: {e}")
    return []
