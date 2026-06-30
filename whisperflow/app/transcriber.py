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
    
    # Handle empty or silent audio
    if audio is None or len(audio) == 0:
        logger.warning("Empty audio provided for transcription")
        return ""
        
    peak = np.max(np.abs(audio))
    if peak < 0.01:
        logger.warning(f"Audio is nearly silent (peak={peak:.4f})")
        return ""

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
            if result:
                logger.info(f"[Local] {time.time()-start:.2f}s: '{result[:80]}'")
                return result
            else:
                logger.warning("Local Whisper not available - all transcription methods failed")
        except Exception as e:
            logger.error(f"Local Whisper failed: {e}")
        finally:
            try:
                os.unlink(tmp16)
            except:
                pass
        
        # All methods failed
        logger.error("All transcription methods failed")
        return ""
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
        logger.debug(f"Calling Groq API with file: {wav_path}")
        with open(wav_path, "rb") as f:
            # Use whisper-large-v3 (not turbo) - turbo has issues with some API keys
            result = client.audio.transcriptions.create(
                file=("audio.wav", f),
                model="whisper-large-v3",  # Changed from whisper-large-v3-turbo
                response_format="verbose_json",  # Get more detailed response
            )
        text = result.text.strip()
        logger.debug(f"Groq returned: '{text[:100] if text else 'EMPTY'}'")
        # Filter out common hallucinations for low-quality audio
        # But keep them if user actually spoke (we'll show warning)
        hallucinations = [".", "...", "uh", "um", "ah", "hm"]
        if text and text in hallucinations:
            logger.warning(f"Groq returned likely hallucination: '{text}'")
            return None
        # Special handling for "Thank you." / "Thanks." - common Groq hallucination on silence
        if text in ["Thank you.", "Thanks."]:
            logger.warning(f"Groq hallucinated '{text}' - likely no speech detected. Speak louder!")
            # Return it anyway so user knows something went wrong
            return text
        if text:
            logger.info(f"Groq transcription successful: {len(text)} chars")
            return text
        logger.warning(f"Groq returned empty result")
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
                "Transcribe this audio exactly word for word. Return ONLY the transcription, nothing else. If you cannot understand the audio clearly, return an empty response.",
            ],
            request_options={"timeout": 10},
        )

        text = response.text.strip()
        for prefix in ["Transcription:", "Here is the transcription:", "Audio transcription:"]:
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):].strip()
        text = text.strip('"').strip("'").strip()
        
        # Filter out common hallucinations for low-quality audio
        if text and len(text) > 1 and text not in [".", "...", "you", "You", "Thank you.", "Thanks.", "uh", "um", "ah", "hm"]:
            return text
        return None
    except Exception as e:
        logger.warning(f"Gemini failed: {e}")
        return None


# Global model cache
_model = None
_model_name = None
_model_lock = threading.Lock()


def _transcribe_local(wav_path: str, model_name: str = "base") -> str | None:
    global _model, _model_name
    with _model_lock:
        if _model is None or _model_name != model_name:
            logger.info(f"Loading local Whisper '{model_name}'...")
            try:
                from faster_whisper import WhisperModel
                _model = WhisperModel(model_name, device="cpu", compute_type="int8")
                _model_name = model_name
            except ImportError as e:
                logger.error(f"Failed to import faster_whisper: {e}")
                logger.warning("Local Whisper not available - install with: pip install faster-whisper")
                return None
            except Exception as e:
                logger.error(f"Failed to load Whisper model: {e}")
                return None
        
        # Model loaded, proceed with transcription
        try:
            segments, info = _model.transcribe(wav_path, beam_size=1, language="en")
            result = " ".join([segment.text for segment in segments]).strip()
            return result if result else None
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            return None

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

        try:
            segments, _ = _model.transcribe(wav_path, **kwargs)
            result = " ".join(seg.text.strip() for seg in segments).strip()
            
            # Filter out common hallucinations for low-quality audio
            if result and len(result) > 1 and result not in [".", "...", "you", "You", "Thank you.", "Thanks.", "uh", "um", "ah", "hm"]:
                return result
            return ""
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise Exception(f"Transcription failed: {e}")

    result = _run(vad=True)
    if not result and _model_name in ["base", "small"]:
        logger.warning("VAD filtered everything — retrying without VAD")
        result = _run(vad=False)
    return result
