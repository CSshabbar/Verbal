import logging
import time
import threading
import tempfile
import os
import numpy as np
import soundfile as sf

logger = logging.getLogger("verbal.transcriber")


def transcribe(audio: np.ndarray, config: dict, sample_rate: int = 48000) -> str:
    """Transcribe audio. Priority: Groq -> Gemini -> Local Whisper."""
    start = time.time()

    # Save at native sample rate — cloud APIs handle resampling
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    try:
        sf.write(tmp.name, audio, sample_rate)
        tmp.close()

        # 1. Groq (free Whisper Large V3 — best accuracy)
        for key in config.get("groq_api_keys", []):
            result = _transcribe_groq(tmp.name, key)
            if result is not None:
                logger.info(f"[Groq] {time.time()-start:.2f}s: '{result[:80]}'")
                return result

        # 2. Gemini Flash (user has keys)
        for key in config.get("gemini_api_keys", []):
            result = _transcribe_gemini(tmp.name, key)
            if result is not None:
                logger.info(f"[Gemini] {time.time()-start:.2f}s: '{result[:80]}'")
                return result

        # 3. Local whisper fallback — needs 16kHz
        tmp16 = _resample_to_16k(audio, sample_rate)
        try:
            result = _transcribe_local(tmp16, config.get("whisper_model", "base"))
            logger.info(f"[Local] {time.time()-start:.2f}s: '{result[:80]}'")
            return result
        finally:
            try:
                os.unlink(tmp16)
            except:
                pass
    finally:
        try:
            os.unlink(tmp.name)
        except:
            pass


def _resample_to_16k(audio, orig_rate):
    """Resample audio to 16kHz for local Whisper."""
    if orig_rate == 16000:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        sf.write(tmp.name, audio, 16000)
        tmp.close()
        return tmp.name

    try:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(orig_rate, 16000)
        resampled = resample_poly(audio, 16000 // g, orig_rate // g).astype(np.float32)
    except ImportError:
        # Fallback: simple decimation
        ratio = orig_rate / 16000
        indices = np.arange(0, len(audio), ratio).astype(int)
        indices = indices[indices < len(audio)]
        resampled = audio[indices]

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(tmp.name, resampled, 16000)
    tmp.close()
    return tmp.name


def _transcribe_groq(wav_path: str, api_key: str) -> str | None:
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        with open(wav_path, "rb") as f:
            result = client.audio.transcriptions.create(
                file=("audio.wav", f),
                model="whisper-large-v3-turbo",
                language="en",
                temperature=0.0,
                prompt="Voice dictation of spoken English. Transcribe exactly what is said.",
            )
        text = result.text.strip()
        if text and text not in [".", "...", "you", "You", "Thank you.", "Thanks."]:
            return text
        return None
    except Exception as e:
        logger.warning(f"Groq failed: {e}")
        return None


def _transcribe_gemini(wav_path: str, api_key: str) -> str | None:
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        with open(wav_path, "rb") as f:
            audio_bytes = f.read()

        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(
            [
                {"mime_type": "audio/wav", "data": audio_bytes},
                "Transcribe this audio exactly word for word. Return ONLY the transcription, nothing else.",
            ],
            request_options={"timeout": 10},
        )

        text = response.text.strip()
        for prefix in ["Transcription:", "Here is the transcription:", "Audio transcription:"]:
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):].strip()
        text = text.strip('"').strip("'").strip()
        return text if text else None
    except Exception as e:
        logger.warning(f"Gemini failed: {e}")
        return None


_model = None
_model_lock = threading.Lock()
_model_name = None


def _transcribe_local(wav_path: str, model_name: str = "base") -> str:
    global _model, _model_name
    with _model_lock:
        if _model is None or _model_name != model_name:
            logger.info(f"Loading local Whisper '{model_name}'...")
            from faster_whisper import WhisperModel
            _model = WhisperModel(model_name, device="cpu", compute_type="int8")
            _model_name = model_name

    def _run(vad: bool) -> str:
        kwargs = dict(
            beam_size=1,
            best_of=1,
            temperature=0.0,
            condition_on_previous_text=False,
            language="en",
        )
        if vad:
            kwargs["vad_filter"] = True
            kwargs["vad_parameters"] = dict(
                min_silence_duration_ms=500,
                threshold=0.2,          # permissive — normalized audio sits around 0.5 peak
                min_speech_duration_ms=100,
            )
        else:
            kwargs["vad_filter"] = False

        segments, _ = _model.transcribe(wav_path, **kwargs)
        return " ".join(seg.text.strip() for seg in segments).strip()

    result = _run(vad=True)
    if not result:
        logger.warning("VAD filtered everything — retrying without VAD")
        result = _run(vad=False)
    return result
