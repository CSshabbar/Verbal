import logging
import time
import threading
import tempfile
import os
import numpy as np
import soundfile as sf

logger = logging.getLogger("verbal.transcriber")

# Groq's Whisper API rejects a bias prompt longer than 896 chars. The dictionary
# glossary + open-file list can exceed that in a large project, which 400s every
# Groq call and fails transcription. Keep the combined prompt safely under it.
_GROQ_PROMPT_CHAR_CAP = 850

# Settings → Transcription model. One table so the UI, the validator and the request
# builder cannot drift. `provider` is what groq-proxy dispatches on; `model` is the id
# that provider wants. Measured on the user's own 20 clips (see context/03-features.md):
# Groq ~1.0s, ElevenLabs ~1.75s, AssemblyAI ~5s (upload-then-poll) — the alternatives
# buy accuracy, not speed, and `bias` records whether a Whisper-style prompt applies
# (only Whisper takes one; sending the glossary elsewhere is meaningless or harmful).
ASR_CHOICES = {
    "auto":                    {"provider": "groq",     "model": None,               "bias": True},
    "whisper-large-v3-turbo":  {"provider": "groq",     "model": "whisper-large-v3-turbo", "bias": True},
    "whisper-large-v3":        {"provider": "groq",     "model": "whisper-large-v3", "bias": True},
    "eleven-scribe-v1":        {"provider": "eleven",   "model": "scribe_v1",        "bias": False},
    "aai-universal-2":         {"provider": "assembly", "model": "universal-2",      "bias": False},
    "aai-universal-3-5-pro":   {"provider": "assembly", "model": "universal-3-5-pro", "bias": False},
    # Google Gemini 3.5 Transcribe (2026-08-27 trial). `model` here is the transcription
    # MODE, not a model id — the proxy always calls `gemini-3.5-transcribe`:
    #   verbatim → raw words, then Flume's normal formatting hop (apples-to-apples
    #              against every other ASR row)
    #   smart    → Gemini removes fillers / applies self-corrections / punctuates itself
    #              (the mode that could one day replace the formatting hop entirely)
    "gemini-3-5-transcribe":       {"provider": "gemini", "model": "verbatim", "bias": False},
    "gemini-3-5-transcribe-smart": {"provider": "gemini", "model": "smart",    "bias": False},
}


def asr_choice(config: dict) -> dict:
    """Resolve `asr_model` to a provider/model pair, falling back to auto on anything
    unrecognised rather than forwarding a bad id that would fail every dictation."""
    return ASR_CHOICES.get(str(config.get("asr_model") or "auto").strip(),
                           ASR_CHOICES["auto"])


def transcribe(audio: np.ndarray, config: dict, sample_rate: int = 48000) -> str:
    """Transcribe audio. Priority: Groq -> Gemini -> Local Whisper.
    Backward-compatible: returns just the text ("" on silence or failure)."""
    return transcribe_with_status(audio, config, sample_rate)[0]


def resolve_language(config: dict, override: str | None = None) -> str | None:
    """Resolve the spoken language: explicit override > config['spoken_language'].
    Returns an ISO-639-1 code, or None for auto-detect."""
    lang = (override or config.get("spoken_language") or "en").strip().lower()
    return None if lang in ("auto", "") else lang


def transcribe_with_status(audio: np.ndarray, config: dict, sample_rate: int = 48000,
                           language: str | None = None,
                           chain: dict | None = None, sidecar: dict | None = None,
                           words: bool = False):
    """Like transcribe() but returns (text, status) where status is:
      'ok'      — got a transcription
      'silent'  — audio was empty/near-silent (no speech; not an error)
      'failed'  — every method failed (network/API down) — retryable

    `language`: ISO code or 'auto' — overrides config['spoken_language'] (used by
    the per-meeting language picker). Whisper is natively multilingual; English
    was previously hard-pinned here, which silently broke every other language.

    `chain` / `sidecar` (`chained_mode`, opt-in): ask the proxy to also run the
    formatting completion inside this same round trip. Build `chain` with
    ai_cleanup.build_chain_spec() at the call site, which is where the active app
    is known. The formatted text comes back in `sidecar["formatted"]`, already put
    through finalize() so it gets the same prompt-echo scrub, dictionary
    replacements and file tagging as the unchained path.

    Only the Groq-proxy branch chains. Every fallback (local Groq key, Gemini,
    local Whisper) leaves the sidecar empty, so the caller formats locally exactly
    as it does today — the fast path being unavailable never costs a dictation.
    """
    start = time.time()

    if audio is None or len(audio) == 0:
        logger.warning("Empty audio provided for transcription")
        return "", "silent"

    peak = np.max(np.abs(audio))
    if peak < 0.01:
        logger.warning(f"Audio is nearly silent (peak={peak:.4f})")
        return "", "silent"

    lang = resolve_language(config, language)

    # Custom dictionary: bias Whisper with the user's vocabulary + fix up the
    # result with their replacement rules. The glossary is English text and the
    # Whisper prompt also HINTS the language — so it is only attached for
    # English; for auto/other languages it would drag detection toward English.
    _dict_mod = None
    try:
        from app import dictionary as _dict
        _dict_mod = _dict
        if lang == "en":
            prompt = _dict.build_prompt(config)
        else:
            prompt = None
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
        # W5/W8: injector is platform-native. `app.injector` imports Quartz/
        # AppKit at module load, so on Windows we must import the win_injector
        # variant. Same public names on both sides — see win_injector docstring.
        import sys as _sys
        if _sys.platform == "win32":
            from app.win_injector import (get_focused_app_pid, get_focused_app_name,
                                          get_focused_app_bundle)
        else:
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

    # Cap the combined bias prompt under Groq's 896-char limit. Glossary comes
    # first (user vocab preserved); excess file names are trimmed at a comma
    # boundary. Harmless for Gemini/local, which have no such limit.
    if prompt and len(prompt) > _GROQ_PROMPT_CHAR_CAP:
        clipped = prompt[:_GROQ_PROMPT_CHAR_CAP]
        cut = clipped.rfind(",")
        if cut > 40:
            clipped = clipped[:cut]
        prompt = clipped.rstrip(" ,") + "."
        logger.debug("[filetag] bias prompt capped to %d chars", len(prompt))

    def finalize(t, biased=True):
        # Bias-prompt echo FIRST. Whisper continues the glossary we sent when it
        # hears no real speech, so "Glossary, M.T.:" arrives as the transcript
        # and would be injected verbatim into the user's editor. Strip it before
        # anything else looks at the text; "" means it was nothing but echo.
        # `biased=False` for the local-Whisper path, which is sent no prompt and
        # therefore can't echo one.
        if biased and prompt and _dict_mod is not None:
            try:
                t = _dict_mod.strip_prompt_echo(t, prompt)
            except Exception as e:
                logger.debug("prompt-echo scrub failed: %s", e)
        if not t or not t.strip():
            return ""
        # Dictionary replacements next; track whether they changed the text.
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

    # Downsample ONCE, up front, and upload 16 kHz mono FLAC.
    #
    # Every Whisper implementation resamples its input to 16 kHz mono before the
    # mel frontend ever sees it, so shipping the mic's native 48 kHz was paying 3×
    # the bytes to send information the model then throws away — and on the
    # dictation critical path those bytes are pure latency. FLAC is lossless and
    # roughly halves it again. The full-rate audio is still what gets archived by
    # `recordings.save_wav`; only the wire format changes here.
    #
    # `wav16` is the same audio as a WAV, materialized lazily: Gemini is sent raw
    # bytes under an `audio/wav` mime type and local faster-whisper wants a plain
    # WAV path, but neither runs unless Groq already failed — so on the hot path
    # we never write it at all.
    try:
        audio16 = _to_16k_array(audio, sample_rate)
        tmp = _write_temp(audio16, ".flac", "FLAC")
    except Exception as e:
        # Rule #1: never raise out of the dictation path. 'failed' is retryable
        # and keeps the recording, so the user loses nothing.
        logger.error("upload encode failed: %s", e)
        return "", "failed"
    wav16 = None

    def _wav16():
        nonlocal wav16
        if wav16 is None:
            wav16 = _write_temp(audio16, ".wav", "WAV")
        return wav16

    try:
        # 1. Groq via the Supabase proxy (key held server-side — no local key needed).
        # Non-English pinned languages route to full large-v3 — the turbo distil
        # is noticeably weaker on lower-resource languages.
        from app.groq_proxy import transcribe_via_proxy
        # "auto" (the default) keeps the original routing; an explicit choice from
        # Settings wins for every language.
        _ch = asr_choice(config)
        _alt = _ch["provider"] != "groq"
        _model_id = _ch["model"] or (
            "whisper-large-v3" if lang not in (None, "en") else "whisper-large-v3-turbo")
        # A Whisper bias prompt means nothing to ElevenLabs/AssemblyAI, and Whisper's
        # prompt-echo failure mode is Whisper-specific — so the glossary is only sent
        # to Groq, and finalize() is told not to look for an echo that cannot happen.
        _prompt_for_call = prompt if _ch["bias"] else None
        proxy_text = transcribe_via_proxy(
            tmp, config, prompt=_prompt_for_call, language=lang,
            model=(None if _alt else _model_id),
            provider=(_ch["provider"] if _alt else None),
            alt_model=(_ch["model"] if _alt else None),
            chain=chain, sidecar=sidecar, words=words)
        # FAIL CLOSED: an alternate provider that is unconfigured, down or out of
        # credit must never cost a dictation, so fall straight back to Groq — the
        # provider is a preference, not a dependency.
        if _alt and not proxy_text:
            logger.warning("[%s] unavailable — falling back to Groq for this dictation",
                           _ch["provider"])
            if sidecar is not None:
                sidecar.clear()
            _model_id = ("whisper-large-v3" if lang not in (None, "en")
                         else "whisper-large-v3-turbo")
            _alt, _prompt_for_call = False, prompt
            proxy_text = transcribe_via_proxy(tmp, config, prompt=prompt, language=lang,
                                              model=_model_id, chain=chain, sidecar=sidecar,
                                              words=words)
        if proxy_text and proxy_text not in (".", "...", "uh", "um", "ah", "hm"):
            # The chain formatted the RAW ASR output, so its result has not been
            # through finalize() yet. Run it through the same scrub the unchained
            # text gets — the one ordering difference being that dictionary
            # replacements now land AFTER formatting instead of before. The
            # grounding block already lists those terms to the formatter, so the
            # model still prefers the user's spelling; this is the safety net.
            # biased=False when no glossary was actually sent (alternate providers get
            # none): strip_prompt_echo would then be hunting an echo that cannot exist,
            # and its heuristics could clip legitimate words instead.
            _biased = _prompt_for_call is not None
            if sidecar is not None and sidecar.get("formatted"):
                try:
                    sidecar["formatted"] = finalize(sidecar["formatted"], biased=_biased) or None
                except Exception as e:
                    logger.debug("chained finalize failed — formatting locally: %s", e)
                    sidecar["formatted"], sidecar["chain_ok"] = None, False
            proxy_text = finalize(proxy_text, biased=_biased)
            if not proxy_text:
                # The model heard no speech and parroted our glossary back. That
                # is silence, not a failure — do NOT fall through to the other
                # providers, they would parrot the same prompt on the same audio.
                logger.warning("[Groq proxy] bias-prompt echo only — treating as silence")
                return "", "silent"
            logger.info(f"[Groq proxy] {time.time()-start:.2f}s: '{proxy_text[:80]}'")
            return proxy_text, "ok"

        # 1b. Legacy fallback: any local Groq keys still configured
        for key in config.get("groq_api_keys", []):
            result = _transcribe_groq(tmp, key, prompt=prompt, language=lang)
            if result is not None:
                result = finalize(result)
                if not result:
                    logger.warning("[Groq] bias-prompt echo only — treating as silence")
                    return "", "silent"
                logger.info(f"[Groq] {time.time()-start:.2f}s: '{result[:80]}'")
                return result, "ok"

        # 2. Gemini Flash (user has keys)
        for key in config.get("gemini_api_keys", []):
            result = _transcribe_gemini(_wav16(), key, prompt=prompt, language=lang)
            if result is not None:
                result = finalize(result)
                if not result:
                    logger.warning("[Gemini] bias-prompt echo only — treating as silence")
                    return "", "silent"
                logger.info(f"[Gemini] {time.time()-start:.2f}s: '{result[:80]}'")
                return result, "ok"

        # 3. Local whisper fallback — needs 16kHz (works offline)
        try:
            result = _transcribe_local(_wav16(), config.get("whisper_model", "base"), language=lang)
            if result:
                result = finalize(result, biased=False)   # local gets no prompt
                logger.info(f"[Local] {time.time()-start:.2f}s: '{result[:80]}'")
                return result, "ok"
            else:
                logger.warning("Local Whisper not available - all transcription methods failed")
        except Exception as e:
            logger.error(f"Local Whisper failed: {e}")

        # All methods failed (likely network/API down) — retryable
        logger.error("All transcription methods failed")
        return "", "failed"
    finally:
        for _p in (tmp, wav16):
            if _p:
                try:
                    os.unlink(_p)
                except Exception:
                    pass


def _to_16k_array(audio, orig_rate):
    """Resample to 16 kHz mono — the rate every Whisper backend works in."""
    if int(orig_rate) == 16000:
        return audio.astype(np.float32)
    try:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(int(orig_rate), 16000)
        return resample_poly(audio, 16000 // g, int(orig_rate) // g).astype(np.float32)
    except ImportError:
        # Fallback: simple decimation
        ratio = orig_rate / 16000
        indices = np.arange(0, len(audio), ratio).astype(int)
        indices = indices[indices < len(audio)]
        return audio[indices].astype(np.float32)


def _write_temp(audio16, suffix, fmt):
    """Write already-16 kHz audio to a temp file. FLAC falls back to WAV if this
    libsndfile build can't encode it (never let a container choice break a
    transcription — Hard Rule #1)."""
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.close()
        sf.write(tmp.name, audio16, 16000, format=fmt, subtype="PCM_16")
        return tmp.name
    except Exception as e:
        if fmt == "FLAC":
            logger.warning("FLAC encode unavailable (%s) — falling back to WAV", e)
            return _write_temp(audio16, ".wav", "WAV")
        raise


def _transcribe_groq(wav_path: str, api_key: str, prompt: str | None = None,
                     language: str | None = "en") -> str | None:
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        with open(wav_path, "rb") as f:
            kwargs = dict(
                # Groq reads the container from this filename — keep the real
                # extension (the upload is FLAC on the normal path).
                file=("audio" + (os.path.splitext(wav_path)[1].lower() or ".wav"), f),
                model="whisper-large-v3" if language not in (None, "en") else "whisper-large-v3-turbo",
                temperature=0.0,
            )
            if language:                     # omit → Whisper auto-detects
                kwargs["language"] = language
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


def _transcribe_gemini(wav_path: str, api_key: str, prompt: str | None = None,
                       language: str | None = "en") -> str | None:
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        with open(wav_path, "rb") as f:
            audio_bytes = f.read()

        instruction = ("Transcribe this audio exactly word for word, in the language "
                       "actually spoken — never translate. Return ONLY the transcription, "
                       "nothing else. If you cannot understand the audio clearly, return "
                       "an empty response.")
        if language and language != "en":
            instruction += f" The audio is expected to be in ISO language '{language}'."
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


def _transcribe_local(wav_path: str, model_name: str = "base",
                      language: str | None = "en") -> str | None:
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
            segments, info = _model.transcribe(wav_path, beam_size=1, language=language)
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
            language=language,
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
