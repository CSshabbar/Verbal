import logging
import time
import threading
import tempfile
import os
import numpy as np
import soundfile as sf

logger = logging.getLogger("verbal.transcriber")


def transcribe(audio: np.ndarray, config: dict, sample_rate: int = 48000) -> str:
    """Transcribe audio. Priority: Groq -> Gemini -> Local Whisper.
    Backward-compatible: returns just the text ("" on silence or failure)."""
    return transcribe_with_status(audio, config, sample_rate)[0]


def transcribe_with_status(audio: np.ndarray, config: dict, sample_rate: int = 48000):
    """Like transcribe() but returns (text, status) where status is:
      'ok'      — got a transcription
      'silent'  — audio was empty/near-silent (no speech; not an error)
      'failed'  — every method failed (network/API down) — retryable
    """
    start = time.time()

    if audio is None or len(audio) == 0:
        logger.warning("Empty audio provided for transcription")
        return "", "silent"

    peak = np.max(np.abs(audio))
    if peak < 0.01:
        logger.warning(f"Audio is nearly silent (peak={peak:.4f})")
        return "", "silent"

    # Custom dictionary: bias Whisper with the user's vocabulary + fix up the
    # result with their replacement rules.
    try:
        from app import dictionary as _dict
        prompt = _dict.build_prompt(config)
        _apply_dict = lambda t: _dict.apply_replacements(t, config)
    except Exception:
        prompt, _apply_dict = None, (lambda t: t)

    # File tagging (desktop, flag-gated, best-effort). This whole block is wrapped
    # so ANY failure leaves transcription completely untouched (never raises). When
    # focused in a supported IDE with the toggle on:
    #   1. bias the Whisper prompt toward the currently open file names, and
    #   2. (Cursor/Windsurf only) rewrite spoken file references into @name.ext
    #      after the dictionary pass — but never when a dictionary replacement was
    #      applied to this transcript, and never when focus is the IDE terminal.
    _filetags = None
    try:
        from app import filetags as _filetags_mod
        from app.config import save_config as _save_config
        from app.injector import (get_focused_app_pid, get_focused_app_name,
                                   get_focused_app_bundle)
        # Classify the SAVED dictation-target app (captured at record start), not
        # the live frontmost app — by transcription time focus may be the overlay.
        _tgt_pid = get_focused_app_pid()
        _ide = _filetags_mod.supported_ide(get_focused_app_bundle(), get_focused_app_name())
        _is_terminal = _filetags_mod.focus_is_terminal() if _ide else False
        _known = []
        _enabled = config.get("filetag_enabled", False)
        if _enabled and _ide and not _is_terminal:
            # Fast synchronous read = the active file (fresh). The deep list comes
            # from the background harvest started at record-start; merge both via
            # the session/persisted cache so the whole open-file set is known.
            _live = _filetags_mod.read_open_files(_tgt_pid)
            _filetags_mod.remember_files(config, _live, _save_config)
            _known = _filetags_mod.get_seen_files(config)
            _frag = _filetags_mod.prompt_fragment(_known)
            if _frag:
                prompt = (prompt + " " + _frag) if prompt else _frag
        if _enabled:
            logger.debug("[filetag] enabled ide=%s terminal=%s target=%s pid=%s known=%d files=%s",
                         _ide, _is_terminal, get_focused_app_name(), _tgt_pid, len(_known), _known)
        # Tag rewriting for every recognized IDE (all are VS Code/Electron forks
        # with an @-file mention picker).
        if _enabled and _ide in _filetags_mod.TAGGING_IDES:
            _filetags = (_filetags_mod, _known, _is_terminal)
    except Exception as e:
        logger.debug("[filetag] setup skipped: %s", e)
        _filetags = None

    def finalize(t):
        # Dictionary replacements first; track whether they changed the text.
        before = t
        t = _apply_dict(t)
        dict_applied = (t != before)
        # File tagging is a no-op when a dict replacement applied or in a terminal
        # (both enforced inside tag()); guarded so it can never break the result.
        if _filetags is not None:
            try:
                _mod, _files, _is_term = _filetags
                _pre = t
                t = _mod.tag(t, _files, dict_applied, _is_term)
                if t != _pre:
                    logger.info("[filetag] tagged: %r -> %r", _pre, t)
                else:
                    logger.debug("[filetag] no tag (dict_applied=%s files=%s text=%r)",
                                 dict_applied, _files, _pre)
            except Exception as e:
                logger.debug("[filetag] tag() failed: %s", e)
        return t

    # Save at native sample rate — cloud APIs handle resampling
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    try:
        sf.write(tmp.name, audio, sample_rate)
        tmp.close()

        # 1. Groq (free Whisper Large V3 — best accuracy)
        for key in config.get("groq_api_keys", []):
            result = _transcribe_groq(tmp.name, key, prompt=prompt)
            if result is not None:
                result = finalize(result)
                logger.info(f"[Groq] {time.time()-start:.2f}s: '{result[:80]}'")
                return result, "ok"

        # 2. Gemini Flash (user has keys)
        for key in config.get("gemini_api_keys", []):
            result = _transcribe_gemini(tmp.name, key, prompt=prompt)
            if result is not None:
                result = finalize(result)
                logger.info(f"[Gemini] {time.time()-start:.2f}s: '{result[:80]}'")
                return result, "ok"

        # 3. Local whisper fallback — needs 16kHz (works offline)
        tmp16 = _resample_to_16k(audio, sample_rate)
        try:
            result = _transcribe_local(tmp16, config.get("whisper_model", "base"))
            if result:
                result = finalize(result)
                logger.info(f"[Local] {time.time()-start:.2f}s: '{result[:80]}'")
                return result, "ok"
            else:
                logger.warning("Local Whisper not available - all transcription methods failed")
        except Exception as e:
            logger.error(f"Local Whisper failed: {e}")
        finally:
            try:
                os.unlink(tmp16)
            except:
                pass

        # All methods failed (likely network/API down) — retryable
        logger.error("All transcription methods failed")
        return "", "failed"
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


def _transcribe_groq(wav_path: str, api_key: str, prompt: str | None = None) -> str | None:
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        with open(wav_path, "rb") as f:
            kwargs = dict(
                file=("audio.wav", f),
                model="whisper-large-v3-turbo",
                language="en",
                temperature=0.0,
            )
            if prompt:  # custom-dictionary vocabulary biasing
                kwargs["prompt"] = prompt
            result = client.audio.transcriptions.create(**kwargs)
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


def _transcribe_gemini(wav_path: str, api_key: str, prompt: str | None = None) -> str | None:
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        with open(wav_path, "rb") as f:
            audio_bytes = f.read()

        instruction = ("Transcribe this audio exactly word for word. Return ONLY the "
                       "transcription, nothing else. If you cannot understand the audio "
                       "clearly, return an empty response.")
        if prompt:  # custom-dictionary vocabulary hint
            instruction += (" Prefer these spellings for names/terms when they occur: "
                            + prompt)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(
            [
                {"mime_type": "audio/wav", "data": audio_bytes},
                instruction,
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
