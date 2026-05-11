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

logger = logging.getLogger("verbal.sync")

SUPABASE_URL = "https://ovpcthjingugwvpxlsna.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92cGN0aGppbmd1Z3d2cHhsc25hIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNjQzMDYsImV4cCI6MjA5Mzg0MDMwNn0"
    ".XwTBo8L-aEUmmSl6dJXNqA2QXzGFOpIVB5W9eDI8j28"
)
REST_URL = f"{SUPABASE_URL}/rest/v1"
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
        while True:
            try:
                httpx.post(
                    f"{REST_URL}/devices?on_conflict=user_id,device_id",
                    headers={
                        "apikey":        SUPABASE_KEY,
                        "Authorization": f"Bearer {SUPABASE_KEY}",
                        "Content-Type":  "application/json",
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
        threading.Thread(target=self._push_rest, args=(text, target_device_id), daemon=True).start()

    def _push_rest(self, text: str, target_device_id: str | None = None):
        try:
            payload = {
                "user_id":     self.user_id,
                "device_id":   self.device_id,
                "device_name": self.device_name,
                "text":        text,
            }
            if target_device_id:
                payload["target_device_id"] = target_device_id

            resp = httpx.post(
                f"{REST_URL}/transcriptions",
                headers={
                    "apikey":        SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type":  "application/json",
                    "Prefer":        "return=minimal",
                },
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
                    }
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

        def on_error(ws, error):
            logger.error(f"Sync WebSocket error: {error}")

        ws = websocket.WebSocketApp(
            WS_URL,
            header={"Authorization": f"Bearer {SUPABASE_KEY}"},
            on_open=on_open,
            on_message=on_message,
            on_close=on_close,
            on_error=on_error,
        )
        self._ws = ws
        ws.run_forever(ping_interval=25, ping_timeout=10)

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
    try:
        import datetime
        cutoff = (datetime.datetime.now(datetime.timezone.utc) -
                  datetime.timedelta(minutes=5)).isoformat()
        resp = httpx.get(
            f"{REST_URL}/devices",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
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
