"""Client for the Supabase `groq-proxy` Edge Function.

All desktop Groq access goes through this so the Groq key lives ONLY on the server
(a Supabase function secret). The desktop authenticates with the Supabase anon key
and sends its account/device id as the fallback rate-limit identity. Fails soft
(returns None) so callers can fall back to a local key or Gemini.
"""
import logging

logger = logging.getLogger(__name__)


class ProxyPayloadTooLarge(Exception):
    """Groq rejected the request (413) — the shared key's tokens-per-minute
    budget can't fit this request. Callers that can shrink their payload
    should catch this and retry smaller; others fail closed like any error."""


def _endpoint() -> str:
    from app.sync import SUPABASE_URL
    return f"{SUPABASE_URL}/functions/v1/groq-proxy"


def _headers(config: dict, json: bool = False) -> dict:
    from app.sync import SUPABASE_KEY
    device = config.get("sync_user_id") or config.get("sync_device_name") or "desktop"
    h = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "apikey": SUPABASE_KEY,
        "x-flume-device": str(device),
    }
    if json:
        h["Content-Type"] = "application/json"
    return h


_MIME = {".flac": "audio/flac", ".wav": "audio/wav", ".ogg": "audio/ogg",
         ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".webm": "audio/webm"}


def transcribe_via_proxy(wav_path: str, config: dict, prompt: str | None = None,
                         timeout: float = 30.0, language: str | None = "en",
                         model: str | None = None,
                         chain: dict | None = None,
                         sidecar: dict | None = None,
                         provider: str | None = None,
                         alt_model: str | None = None,
                         words: bool = False) -> str | None:
    """Transcribe an audio file via the proxy (multipart → Groq /audio/transcriptions).
    language=None → Whisper auto-detects; the proxy forwards the form as-is.

    The upload filename/mime are derived from `wav_path` rather than hardcoded:
    Groq identifies the container from the multipart filename, so sending FLAC
    bytes labelled `audio.wav` is rejected.

    `chain` (opt-in, `chained_mode`) asks the Edge Function to ALSO run the
    formatting completion server-side and return it in the same response, so the
    Mac pays one round trip instead of two. Shape:
        {"system": <system prompt>, "user": <user message with {{TEXT}}>,
         "model": <chat model id>, "reasoning_effort": <"low"|"medium"|"high", optional>}
    `{{TEXT}}` in `user` is substituted server-side with the ASR output. The
    prompt and model still come from the client, so chaining changes only WHERE
    the second call is made — not what it asks for.

    `sidecar` (opt-in out-param) receives the chain outcome without changing this
    function's return type, which several callers depend on:
        {"formatted": str|None, "chain_ok": bool, "asr_ms": int, "fmt_ms": int}
    A chain that errors server-side leaves formatted=None and chain_ok=False; the
    transcription itself is unaffected, so the caller just formats locally.
    """
    try:
        import os
        import httpx
        data = {"model": model or "whisper-large-v3-turbo", "temperature": "0"}
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt
        # Alternate ASR provider (Settings → Transcription model). The proxy holds the
        # provider key and normalizes the reply to Groq's `{text}` shape, so nothing
        # below this line changes per provider. `model` is still sent and simply
        # ignored server-side on these branches.
        if provider and provider != "groq":
            data["asr_provider"] = provider
            if alt_model:
                data["asr_alt_model"] = alt_model
        # Per-word timestamps (meetings → speaker-turn splitting). Groq's
        # verbose_json keeps the same `text` field, so nothing else changes;
        # alternate providers are normalized to `{text}` and never carry words.
        if words and not (provider and provider != "groq"):
            data["response_format"] = "verbose_json"
            data["timestamp_granularities[]"] = "word"
        # The server only chains when it is sent a system prompt (see index.ts
        # `wantChain && chainSystem`), so an empty/malformed chain dict degrades
        # to a plain transcription rather than to an error.
        if chain and chain.get("system"):
            data["chain"] = "1"
            data["chain_system"] = chain["system"]
            data["chain_user"] = chain.get("user") or "{{TEXT}}"
            if chain.get("model"):
                data["chain_model"] = chain["model"]
            if chain.get("reasoning_effort"):
                data["chain_reasoning_effort"] = chain["reasoning_effort"]
            # Dictionary find->replace rules, applied server-side BEFORE formatting so
            # the formatter reads the same corrected text it would read unchained.
            if chain.get("replace"):
                import json as _json
                data["chain_replace"] = _json.dumps(chain["replace"])
        ext = os.path.splitext(wav_path)[1].lower()
        name, mime = "audio" + (ext or ".wav"), _MIME.get(ext, "audio/wav")
        with open(wav_path, "rb") as f:
            files = {"file": (name, f, mime)}
            resp = httpx.post(_endpoint(), headers=_headers(config), data=data,
                              files=files, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("groq-proxy transcription %s: %s", resp.status_code, resp.text[:200])
            return None
        body = resp.json()
        if sidecar is not None and words and isinstance(body.get("words"), list):
            sidecar["words"] = body["words"]      # [{word, start, end}] relative seconds
        if sidecar is not None:
            _c = body.get("chain") or {}
            _fmt = (_c.get("formatted") or "").strip()
            sidecar["chain_ok"] = bool(_c.get("ok")) and bool(_fmt)
            sidecar["formatted"] = _fmt or None
            sidecar["asr_ms"] = _c.get("asr_ms")
            sidecar["fmt_ms"] = _c.get("fmt_ms")
            if chain and not sidecar["chain_ok"]:
                logger.warning("chained_mode: server-side format unavailable "
                               "(%s) — formatting locally", _c.get("error") or "no chain in response")
        return (body.get("text") or "").strip() or None
    except Exception as e:
        logger.warning("groq-proxy transcription failed: %s", e)
        return None


def chat_via_proxy(messages: list, config: dict, model: str = "openai/gpt-oss-120b",
                   max_tokens: int = 2048, timeout: float = 10.0,
                   response_format: dict | None = None,
                   provider: str | None = None,
                   reasoning_effort: str | None = None) -> str | None:
    """Chat completion via the proxy (JSON → Groq /chat/completions).
    Pass response_format={"type": "json_object"} for Groq's strict JSON mode.
    Pass provider="ollama" to route to Ollama Cloud instead (model = an Ollama tag,
    e.g. "gpt-oss:120b") — same OpenAI-compatible request/response shape.
    Pass reasoning_effort="low"/"medium"/"high" for the gpt-oss family — they default
    to "medium" and silently spend hundreds of hidden thinking tokens on even a purely
    mechanical formatting request (see ai_cleanup.py's SPEED_CLEANUP_MODEL comment for
    the measured cost). This function forwards it as-is; the Edge Function's JSON
    /chat/completions branch passes the whole payload through unmodified, so no
    server-side change is needed for THIS path."""
    try:
        import httpx
        payload = {"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
        if response_format:
            payload["response_format"] = response_format
        if provider:
            payload["provider"] = provider
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        resp = httpx.post(_endpoint(), headers=_headers(config, json=True), json=payload, timeout=timeout)
        if resp.status_code == 413:
            raise ProxyPayloadTooLarge(resp.text[:200])
        if resp.status_code != 200:
            logger.warning("groq-proxy chat %s: %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip() or None
    except ProxyPayloadTooLarge:
        raise
    except Exception as e:
        logger.warning("groq-proxy chat failed: %s", e)
        return None


def diarize_submit(object_path: str, config: dict, timeout: float = 20.0,
                   language: str | None = None) -> str | None:
    """Ask the proxy to start speaker diarization for an uploaded meeting WAV.

    `object_path` is the bare `meeting-audio` bucket path (`<user>/<meeting>.wav`).
    The audio never leaves the bucket through us — the proxy signs a short-lived URL
    and AssemblyAI fetches the file itself, so this call is tiny regardless of how
    long the meeting was. Returns a transcript id to poll, or None (fail-soft)."""
    try:
        import httpx
        resp = httpx.post(_endpoint(), headers=_headers(config, json=True),
                          json={"diarize": {"object": object_path,
                                            "language": (language or "").strip().lower() or None}},
                          timeout=timeout)
        if resp.status_code != 200:
            logger.warning("diarize submit %s: %s", resp.status_code, resp.text[:160])
            return None
        return (resp.json().get("id") or "").strip() or None
    except Exception as e:
        logger.warning("diarize submit failed: %s", e)
        return None


def diarize_poll(transcript_id: str, config: dict, timeout: float = 20.0):
    """One poll. Returns:
      list of {"speaker","start","end"} (seconds)  — done
      None                                          — still processing, poll again
      False                                         — failed, stop polling"""
    try:
        import httpx
        resp = httpx.post(_endpoint(), headers=_headers(config, json=True),
                          json={"diarize": {"poll": transcript_id}}, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("diarize poll %s: %s", resp.status_code, resp.text[:160])
            return False
        j = resp.json()
        if j.get("status") == "completed":
            return j.get("utterances") or []
        if j.get("status") == "error":
            logger.warning("diarize failed upstream: %s", j.get("error"))
            return False
        return None
    except Exception as e:
        logger.warning("diarize poll failed: %s", e)
        return False
