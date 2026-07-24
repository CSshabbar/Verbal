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


class SyncClient:
    def __init__(self, user_id: str, device_name: str, on_receive):
        self.user_id     = user_id
        self.device_id   = platform.node()
        self.device_name = device_name or platform.node()
        self.on_receive  = on_receive
        self._ws         = None
        self._connected  = False
        self._ref        = 0
        self._thread     = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        # Register this device and start heartbeat
        threading.Thread(target=self._register_device, daemon=True).start()
        logger.info(f"SyncClient started — user={user_id[:12]} device={self.device_id}")

    def _register_device(self):
        """Register this device in Supabase and update last_seen every 60s."""
        from app.auth import auth_header
        while True:
            try:
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
                        "last_seen":   __import__('datetime').datetime.now(
                            __import__('datetime').timezone.utc).isoformat(),
                    },
                    timeout=5,
                )
            except Exception as e:
                logger.debug(f"Device register error: {e}")
            time.sleep(60)

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
        while True:
            try:
                self._listen()
            except Exception as e:
                logger.warning(f"Sync listener crashed: {e} — retry in 5s")
            time.sleep(5)

    def _listen(self):
        import websocket
        import time
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

                # Postgres INSERT event
                if event == "postgres_changes":
                    data   = payload.get("data", {})
                    record = data.get("record", {})
                    # Skip own inserts
                    if record.get("device_id") == self.device_id:
                        return
                    # Respect target_device_id — only receive if targeted at us or broadcast
                    target = record.get("target_device_id")
                    if target and target != self.device_id:
                        return
                    text        = record.get("text", "")
                    device_name = record.get("device_name", "Unknown")
                    if text:
                        logger.info(f"Sync received from '{device_name}': '{text[:60]}'")
                        if self.on_receive:
                            self.on_receive(text, device_name)

            except Exception as e:
                logger.error(f"Sync message error: {e} — raw: {raw[:200]}")

        def on_close(ws, code, msg):
            self._connected = False
            logger.info(f"Sync WebSocket closed (code={code})")
            # Attempt to reconnect after a delay
            if not hasattr(self, '_reconnecting') or not self._reconnecting:
                self._reconnecting = True
                time.sleep(5)  # Wait before reconnecting
                self._reconnecting = False
                # Restart the connection
                try:
                    self._listen()
                except Exception as e:
                    logger.error(f"Failed to restart sync listener: {e}")

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
            while self._ws is ws:
                time.sleep(1200)
                if self._ws is not ws or not self._connected:
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
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass


def fetch_devices(user_id: str, exclude_device_id: str) -> list:
    """Fetch all devices for this user except the current one (seen in last 5 min)."""
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
