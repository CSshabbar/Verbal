"""Streaming ASR for the `hybrid` pipeline.

Sends microphone audio to the `asr-stream` Edge Function WHILE you are still
speaking, so that by the time you stop, transcription is essentially already done.
Measured on the user's own clips: the tail after you stop is a flat ~0.3 s at any
length, where Groq's batch wait grows from 0.72 s (short) to 1.29 s (a minute).

The relay is what makes this possible without breaking Hard Rule #15: the vendor
key stays a Supabase function secret and this module only ever talks to our own
function, which normalizes both vendors down to one message shape.

DISCIPLINE, because this sits next to the recording path:
  * `feed()` is called from the PortAudio realtime callback. It does nothing but
    put bytes on a queue — never network I/O, never a lock held across a send.
  * Every public method swallows its own errors. A streaming failure must cost
    latency, never a dictation: `final_text()` returns None and the caller falls
    back to the ordinary upload path.
  * Nothing here runs unless the hybrid pipeline is selected AND the take is long
    enough to be worth it.
"""
import json
import logging
import queue
import threading
import time

import numpy as np

logger = logging.getLogger("verbal.asr_stream")

RATE = 16000
_SEND_CHUNK = int(RATE * 0.10) * 2      # 100 ms of PCM16 per frame
_QUEUE_MAX = 400                        # ~40 s of audio; drop rather than grow forever


def _endpoint(provider: str, config: dict) -> str:
    from app.sync import SUPABASE_URL, SUPABASE_KEY
    device = config.get("sync_user_id") or config.get("sync_device_name") or "desktop"
    base = SUPABASE_URL.replace("https://", "wss://").replace("http://", "ws://")
    # The relay runs with verify_jwt OFF (a websocket upgrade cannot carry the
    # normal Authorization header), so the key travels as a query param and the
    # function checks it itself. Same anon key every other client already uses.
    return (f"{base}/functions/v1/asr-stream"
            f"?provider={provider}&apikey={SUPABASE_KEY}&device={device}")


class AsrStream:
    """One streaming session. Create at record-start, feed blocks, then finish()."""

    def __init__(self, provider: str, config: dict, model: str | None = None):
        self.provider = provider
        self.model = model
        self._config = config
        self._q: "queue.Queue[bytes | None]" = queue.Queue(maxsize=_QUEUE_MAX)
        self._buf = bytearray()
        self._ws = None
        self._text = None
        self._err = None
        self._ready = threading.Event()
        self._done = threading.Event()
        self._stop = threading.Event()
        self._sent_bytes = 0
        self._dropped = 0
        self._t_stop = None
        self._t_final = None
        self._pump = None
        self._reader = None

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self) -> bool:
        """Open the socket and start the pump. False = not streaming this take."""
        try:
            import websocket
            url = _endpoint(self.provider, self._config)
            # enable_multithread is REQUIRED: the reader thread sits in recv()
            # while the pump thread sends. websocket-client uses NoLock() without
            # it, which corrupts the frame state and drops the connection.
            self._ws = websocket.create_connection(url, timeout=15, enable_multithread=True)
        except Exception as e:
            self._err = f"connect: {type(e).__name__}: {e}"[:180]
            logger.warning("[asr_stream] %s", self._err)
            self._ws = None
            return False
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._pump = threading.Thread(target=self._pump_loop, daemon=True)
        self._reader.start()
        self._pump.start()
        if self.model:
            self._send_json({"type": "config", "model": self.model})
        return True

    def feed(self, block: np.ndarray, in_rate: int):
        """Called from the audio callback. Must stay cheap and never raise."""
        if self._ws is None or self._stop.is_set():
            return
        try:
            mono = block.reshape(-1) if block.ndim > 1 else block
            if in_rate != RATE:
                # Cheap decimation, not resample_poly: this runs on the realtime
                # thread and a few dB of aliasing costs far less than a late frame.
                step = in_rate / float(RATE)
                idx = (np.arange(0, len(mono) / step) * step).astype(np.int32)
                idx = idx[idx < len(mono)]
                mono = mono[idx]
            pcm = (np.clip(mono, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
            self._q.put_nowait(pcm)
        except queue.Full:
            self._dropped += 1
        except Exception:
            pass                      # never let metering/format issues reach the mic

    def finish(self, timeout: float = 6.0) -> str | None:
        """Stop sending, flush, and wait for the final transcript."""
        self._t_stop = time.time()
        if self._ws is None:
            return None
        try:
            self._q.put_nowait(None)          # sentinel: pump flushes and sends done
        except Exception:
            self._stop.set()
        self._done.wait(timeout=timeout)
        self._stop.set()
        try:
            self._ws.close()
        except Exception:
            pass
        if self._dropped:
            logger.warning("[asr_stream] dropped %d blocks — transcript may be short",
                           self._dropped)
            return None                        # incomplete audio -> do not trust it
        if self._text:
            logger.info("[asr_stream] %s final in %.2fs after stop",
                        self.provider, self.wait_after_stop() or -1)
        elif self._err:
            logger.warning("[asr_stream] %s failed: %s", self.provider, self._err)
        return self._text or None

    def wait_after_stop(self):
        if self._t_final is None or self._t_stop is None:
            return None
        return max(0.0, self._t_final - self._t_stop)

    @property
    def error(self):
        return self._err

    # ── internals ────────────────────────────────────────────────────────────
    def _send_json(self, obj):
        try:
            self._ws.send(json.dumps(obj))
        except Exception as e:
            self._err = self._err or f"send: {type(e).__name__}"[:80]

    def _pump_loop(self):
        """Drains the queue onto the socket. The ONLY place that sends audio."""
        while not self._stop.is_set():
            try:
                item = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:                    # end of take
                try:
                    if self._buf and self._ws is not None:
                        self._ws.send_binary(bytes(self._buf))
                        self._buf.clear()
                    self._send_json({"type": "done"})
                except Exception as e:
                    self._err = self._err or f"flush: {type(e).__name__}"[:80]
                    self._done.set()
                return
            self._buf += item
            # Fixed-size frames with the remainder carried over. Sending whatever is
            # left produces short frames, and AssemblyAI closes the session on any
            # frame under 50 ms — the exact bug that broke the playground.
            while len(self._buf) >= _SEND_CHUNK and self._ws is not None:
                frame = bytes(self._buf[:_SEND_CHUNK])
                del self._buf[:_SEND_CHUNK]
                try:
                    self._ws.send_binary(frame)
                    self._sent_bytes += len(frame)
                except Exception as e:
                    self._err = f"send: {type(e).__name__}: {e}"[:140]
                    self._ws = None
                    self._done.set()
                    return

    def _read_loop(self):
        while not self._stop.is_set():
            try:
                msg = self._ws.recv()
            except Exception:
                self._done.set()
                return
            if not msg:
                self._done.set()
                return
            if isinstance(msg, bytes):
                continue
            try:
                j = json.loads(msg)
            except Exception:
                continue
            t = j.get("type")
            if t == "ready":
                self._ready.set()
            elif t == "final":
                self._text = (j.get("text") or "").strip() or None
                self._t_final = time.time()
                self._done.set()
                return
            elif t == "error":
                self._err = str(j.get("error"))[:180]
                self._done.set()
                return


# Below this many seconds of speech, streaming is not worth it: Groq's one-round-trip
# path is FASTER on short takes (0.87s vs ~1.07s measured), because streaming still
# has to pay its own formatting round trip. The two curves crossed at ~8s on the
# user's 20 clips, which is where this number comes from.
HYBRID_THRESHOLD_SEC = 8.0

# Only AssemblyAI is wired: Deno's WebSocket cannot set headers, so a vendor must
# accept a credential in the URL, and only AssemblyAI has a working token endpoint.
STREAM_PROVIDER = "assembly"


def should_stream(config: dict) -> str | None:
    """The provider to stream with, or None to not stream at all.

    Only the `hybrid` pipeline streams, and it always streams with AssemblyAI
    regardless of the batch Transcription-model choice — that choice governs the
    NON-streaming half, and the two are independent on purpose."""
    try:
        from app.config import feature_flag
        if not feature_flag(config, "hybrid_mode", False):
            return None
        return STREAM_PROVIDER
    except Exception as e:
        logger.debug("[asr_stream] disabled: %s", e)
        return None
