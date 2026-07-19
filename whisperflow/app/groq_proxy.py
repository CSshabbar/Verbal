"""Client for the Supabase `groq-proxy` Edge Function.

All desktop Groq access goes through this so the Groq key lives ONLY on the server
(a Supabase function secret). The desktop authenticates with the Supabase anon key
and sends its account/device id as the fallback rate-limit identity. Fails soft
(returns None) so callers can fall back to a local key or Gemini.
"""
import logging

logger = logging.getLogger(__name__)


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


def transcribe_via_proxy(wav_path: str, config: dict, prompt: str | None = None,
                         timeout: float = 30.0, language: str | None = "en",
                         model: str | None = None) -> str | None:
    """Transcribe a WAV via the proxy (multipart → Groq /audio/transcriptions).
    language=None → Whisper auto-detects; the proxy forwards the form as-is."""
    try:
        import httpx
        data = {"model": model or "whisper-large-v3-turbo", "temperature": "0"}
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt
        with open(wav_path, "rb") as f:
            files = {"file": ("audio.wav", f, "audio/wav")}
            resp = httpx.post(_endpoint(), headers=_headers(config), data=data,
                              files=files, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("groq-proxy transcription %s: %s", resp.status_code, resp.text[:200])
            return None
        return (resp.json().get("text") or "").strip() or None
    except Exception as e:
        logger.warning("groq-proxy transcription failed: %s", e)
        return None


def chat_via_proxy(messages: list, config: dict, model: str = "llama-3.3-70b-versatile",
                   max_tokens: int = 2048, timeout: float = 10.0,
                   response_format: dict | None = None) -> str | None:
    """Chat completion via the proxy (JSON → Groq /chat/completions).
    Pass response_format={"type": "json_object"} for Groq's strict JSON mode."""
    try:
        import httpx
        payload = {"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
        if response_format:
            payload["response_format"] = response_format
        resp = httpx.post(_endpoint(), headers=_headers(config, json=True), json=payload, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("groq-proxy chat %s: %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip() or None
    except Exception as e:
        logger.warning("groq-proxy chat failed: %s", e)
        return None
