import logging
import math
import time
import numpy as np
import sounddevice as sd
import threading
from scipy import signal
from typing import Optional

logger = logging.getLogger("verbal.recorder")

CHANNELS = 1
DTYPE = "float32"
# Target peak level for Whisper — keeps audio in clean range
TARGET_PEAK = 0.5
# Ceiling on how long start() waits for the mic to deliver its first buffer before
# showing "Listening…".
#
# MEASURED on this machine (2018 Intel MacBook Pro, built-in mic, 5 cold starts):
# first buffer arrives after 193ms / median 267ms / 475ms worst. The old flat
# sleep(0.3) was therefore roughly RIGHT for this hardware, not wasteful — and
# cutting it to 50ms would invite the user to speak ~200ms before the mic is live.
# The ceiling sits above the observed worst case so a slow device is waited out
# rather than truncated; fast hardware still returns as soon as audio arrives.
_STREAM_READY_TIMEOUT = 0.6

# Noise reduction parameters
NOISE_REDUCTION_STRENGTH = 0.2
NOISE_SAMPLE_DURATION = 0.5  # seconds to sample noise floor

# Maximum recording length. Generous — a 16kHz mono clip this long is only a
# few MB, well within the transcription API's limits. When exceeded we keep the
# BEGINNING and ignore further audio (dictation should never lose its start).
MAX_RECORDING_SECONDS = 300

# ── Live level metering (drives the overlay waveform) ────────────────────────
# The block peak is mapped from dBFS onto 0..1: a quiet room sits around
# -55 dBFS and normal dictation peaks near -12, so speech fills most of the
# bar without the user having to raise their voice, and silence reads as flat.
LEVEL_FLOOR_DB = -55.0
LEVEL_CEIL_DB = -12.0
# Gamma applied after the dB map. A pure dB scale is generous to quiet sounds,
# so room tone still wobbled the bars; this pushes the bottom of the range down
# without touching speech. Shaping lives HERE, once, so the Mac (JS) and
# Windows (PIL) waveforms render the same number identically.
LEVEL_GAMMA = 1.5
# Asymmetric smoothing: rise almost instantly so a syllable shows up on the
# same frame, fall slowly so the bars don't strobe between words.
LEVEL_ATTACK = 0.55
LEVEL_RELEASE = 0.12


def _get_native_rate():
    try:
        d = sd.query_devices(kind='input')
        return int(d['default_samplerate'])
    except:
        return 48000


class Recorder:
    def __init__(self):
        self._buffer = []
        self._stream = None
        self._lock = threading.Lock()
        # Set by the audio callback on its first buffer, so start() can wait for
        # real audio instead of guessing with a sleep.
        self._first_block = threading.Event()
        self._recording = False
        self._sample_rate = _get_native_rate()
        self._noise_profile = None
        self._noise_floor = 0.0
        self._total_samples = 0
        self._max_samples = int(MAX_RECORDING_SECONDS * self._sample_rate)
        self._cap_warned = False
        self._paused = False
        self._level = 0.0
        # Optional streaming tap, set per take by set_tap(). None = the recorder
        # behaves exactly as it always has; the hybrid pipeline is the only caller.
        self._tap = None
        logger.info(f"Mic native rate: {self._sample_rate}Hz")

    def set_tap(self, fn):
        """Install (or clear with None) a per-block callback for streaming ASR.

        Contract for `fn(block, sample_rate)`: cheap, non-blocking, never raises.
        It is invoked on the PortAudio realtime thread, so anything slow here shows
        up as dropped audio. The callback is dropped permanently on its first
        exception — see _audio_callback."""
        self._tap = fn

    @property
    def sample_rate(self):
        return self._sample_rate

    @property
    def level(self):
        """Smoothed 0..1 mic level for the recording overlay's waveform.

        0.0 whenever we aren't capturing (idle or paused), so the bars settle
        flat instead of freezing at the last syllable.
        """
        if not self._recording or self._paused:
            return 0.0
        return self._level

    def _open_stream(self):
        stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=self._audio_callback,
            latency='low',  # Reduce latency for better responsiveness
        )
        stream.start()
        return stream

    def start(self):
        with self._lock:
            self._buffer = []
            self._total_samples = 0
            self._cap_warned = False
            self._paused = False
            self._level = 0.0
            self._recording = True
        self._first_block.clear()
        try:
            try:
                self._stream = self._open_stream()
            except Exception as e1:
                # A macOS audio-device change (e.g. AirPods connect/disconnect)
                # leaves PortAudio's cached device list stale — every open then
                # fails with AUHAL '!obj' / paInternalError -9986 until PortAudio
                # is re-initialized. Re-init, refresh the CURRENT default input
                # rate, and retry once so dictation survives device changes.
                logger.warning(f"Mic open failed ({e1}) — reinitializing PortAudio")
                sd._terminate()
                sd._initialize()
                try:
                    self._sample_rate = _get_native_rate()
                    self._max_samples = int(MAX_RECORDING_SECONDS * self._sample_rate)
                    logger.info(f"Mic native rate now: {self._sample_rate}Hz")
                except Exception:
                    pass
                self._stream = self._open_stream()

            # Wait until the mic is genuinely delivering audio, then return.
            #
            # This used to be a flat time.sleep(0.3). The stream is already started by
            # _open_stream() above, so that sleep never protected any audio — it delayed
            # the CALLER, which is what shows the "Listening…" cue. Its real (accidental)
            # job was to stop the user speaking before CoreAudio had woken up.
            #
            # A fixed 300ms is wrong in both directions: far too long for a built-in mic
            # (~20ms to first buffer) and potentially too short for Bluetooth, where the
            # device can take several hundred ms. So wait on the first buffer instead and
            # keep 300ms only as a ceiling — the cue now appears as soon as the mic is
            # actually live, typically well under 50ms, without regressing AirPods.
            if not self._first_block.wait(timeout=_STREAM_READY_TIMEOUT):
                logger.warning(
                    "No audio delivered within %.0fms of stream start — proceeding anyway",
                    _STREAM_READY_TIMEOUT * 1000)

            logger.info("Recording started")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self._recording = False
            raise

    def start_external(self, sample_rate: int = 16000):
        """Record from an EXTERNAL feed instead of opening our own InputStream.

        Used while a meeting is running: the meeting owns the one mic stream
        and forwards blocks here via feed_external() (a second InputStream on
        the same device makes CoreAudio drop one of them — 'my voice gets
        ignored' — and a failed open's PortAudio reinit killed the meeting's
        stream). stop() works unchanged (no stream to tear down).
        """
        with self._lock:
            self._buffer = []
            self._total_samples = 0
            self._cap_warned = False
            self._paused = False
            self._level = 0.0
            self._recording = True
        self._external = True
        self._sample_rate = int(sample_rate)
        self._max_samples = int(MAX_RECORDING_SECONDS * self._sample_rate)
        logger.info(f"Recording started (external mic tap @{self._sample_rate}Hz)")

    def feed_external(self, block):
        """Consume one mono float32 block from the external feed (any thread)."""
        try:
            if not getattr(self, "_external", False) or not self._recording:
                return
            self._audio_callback(block.reshape(-1, 1), len(block), None, None)
        except Exception:
            pass  # never throw into the meeting's audio callback

    def stop(self) -> Optional[np.ndarray]:
        self._external = False
        with self._lock:
            self._recording = False
            self._level = 0.0

        # Give callbacks time to finish processing last audio frames
        time.sleep(0.1)  # 100ms delay to ensure all audio is captured
        # Drop the streaming tap AFTER that settle, so the final blocks still reach
        # the stream, but no stale tap from this take can fire during the next one.
        self._tap = None
        
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.error(f"Error stopping stream: {e}")
            self._stream = None

        with self._lock:
            if not self._buffer:
                return None
            # Keep the ENTIRE recording (memory is bounded during capture by
            # MAX_RECORDING_SECONDS in the callback). Never trim the start.
            audio = np.concatenate(self._buffer, axis=0).flatten()
            self._buffer = []

        duration = len(audio) / self._sample_rate
        peak = np.max(np.abs(audio))
        logger.info(f"Captured {duration:.1f}s at {self._sample_rate}Hz, peak={peak:.4f}")

        # DISABLED: Audio enhancement was destroying speech content
        # Apply noise reduction and audio enhancement
        # if len(audio) > 0:
        #     audio = self._enhance_audio(audio)
        
        # Always normalize to TARGET_PEAK so Whisper gets clean, consistent audio
        if peak > 0.01:
            audio = audio / peak * TARGET_PEAK
            logger.info(f"Normalized audio: peak {peak:.4f} → {TARGET_PEAK}")
        else:
            logger.warning(f"Audio is silent (peak={peak:.4f})")

        return audio

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"Audio status: {status}")
        # First buffer of this take: unblock start(). Checked before setting so the
        # realtime thread does no work on any subsequent callback.
        if not self._first_block.is_set():
            self._first_block.set()
        with self._lock:
            capturing = self._recording and not self._paused
            if capturing:
                if self._total_samples < self._max_samples:
                    self._buffer.append(indata.copy())
                    self._total_samples += frames
                elif not self._cap_warned:
                    self._cap_warned = True
                    logger.warning(
                        f"Recording reached {MAX_RECORDING_SECONDS}s cap — "
                        "keeping the beginning, ignoring further audio")
        # Metering is done OUTSIDE the lock (it only touches a float) so the
        # audio callback keeps the lock for as short as possible.
        self._update_level(indata if capturing else None)
        # Streaming tap (hybrid pipeline). Also outside the lock, also last: this is
        # the PortAudio realtime thread, so the tap is contracted to do nothing but
        # copy bytes onto a queue — no network, no blocking, no allocation storms.
        # Wrapped because a broken tap must never be able to stop the recording;
        # losing the stream costs latency, losing the callback costs the dictation.
        if capturing and self._tap is not None:
            try:
                self._tap(indata, self._sample_rate)
            except Exception:
                self._tap = None      # one strike: never risk the mic thread twice

    def _update_level(self, block):
        """Fold one captured block into the smoothed level the overlay draws."""
        try:
            if block is None or len(block) == 0:
                target = 0.0
            else:
                peak = float(np.abs(block).max())
                db = 20.0 * math.log10(peak) if peak > 1e-6 else -120.0
                target = (db - LEVEL_FLOOR_DB) / (LEVEL_CEIL_DB - LEVEL_FLOOR_DB)
                target = min(1.0, max(0.0, target)) ** LEVEL_GAMMA
            k = LEVEL_ATTACK if target > self._level else LEVEL_RELEASE
            self._level += (target - self._level) * k
        except Exception:
            pass  # metering is cosmetic — it must never break capture

    def _enhance_audio(self, audio: np.ndarray) -> np.ndarray:
        """Apply noise reduction and audio enhancement for low-quality microphones."""
        if len(audio) == 0:
            return audio
            
        # Apply high-pass filter to remove low-frequency noise (rumble, hum)
        audio = self._apply_highpass_filter(audio)
        
        # Apply noise reduction
        audio = self._reduce_noise(audio)
        
        # Apply dynamic range compression for better clarity
        audio = self._apply_compression(audio)
        
        # Apply spectral enhancement for speech clarity
        audio = self._enhance_speech(audio)
        
        return audio

    def _apply_highpass_filter(self, audio: np.ndarray) -> np.ndarray:
        """Apply high-pass filter to remove low-frequency noise."""
        # Cutoff frequency for high-pass filter (80Hz to remove rumble)
        cutoff = 80.0
        nyquist = self._sample_rate / 2.0
        normalized_cutoff = cutoff / nyquist
        
        # Design Butterworth high-pass filter
        b, a = signal.butter(4, normalized_cutoff, btype='high', analog=False)
        
        # Apply filter
        filtered_audio = signal.filtfilt(b, a, audio)
        return filtered_audio

    def _reduce_noise(self, audio: np.ndarray) -> np.ndarray:
        """Apply spectral noise reduction."""
        if len(audio) < self._sample_rate * 0.1:  # Need at least 0.1 seconds
            return audio
            
        # Estimate noise floor from beginning of audio
        noise_samples = int(self._sample_rate * 0.1)  # First 100ms
        if len(audio) > noise_samples:
            noise_segment = audio[:noise_samples]
            noise_power = np.mean(noise_segment ** 2)
        else:
            noise_power = np.mean(audio ** 2) * 0.1  # Conservative estimate
            
        # Apply spectral subtraction
        # Convert to frequency domain
        fft_size = min(2048, len(audio))
        audio_fft = np.fft.rfft(audio, n=fft_size)
        
        # Estimate noise spectrum (assuming noise is relatively flat)
        noise_magnitude = np.sqrt(noise_power)
        
        # Apply noise reduction
        magnitude = np.abs(audio_fft)
        phase = np.angle(audio_fft)
        
        # Spectral subtraction with over-subtraction factor
        over_subtraction = 1.5
        reduced_magnitude = np.maximum(
            magnitude - over_subtraction * noise_magnitude,
            NOISE_REDUCTION_STRENGTH * magnitude
        )
        
        # Reconstruct signal
        reduced_fft = reduced_magnitude * np.exp(1j * phase)
        reduced_audio = np.fft.irfft(reduced_fft, n=len(audio))
        
        return reduced_audio.astype(np.float32)

    def _apply_compression(self, audio: np.ndarray) -> np.ndarray:
        """Apply dynamic range compression to enhance speech clarity."""
        # Simple automatic gain control
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 1e-6:
            return audio
            
        # Target RMS level
        target_rms = 0.1
        
        # Calculate gain
        gain = target_rms / rms
        gain = np.clip(gain, 0.5, 5.0)  # Limit gain to reasonable range
        
        # Apply compression with soft knee
        compressed = audio * gain
        
        # Apply soft limiting to prevent clipping
        limit_threshold = 0.9
        compressed = np.where(
            np.abs(compressed) > limit_threshold,
            np.sign(compressed) * (limit_threshold + (np.abs(compressed) - limit_threshold) * 0.3),
            compressed
        )
        
        return compressed

    def _enhance_speech(self, audio: np.ndarray) -> np.ndarray:
        """Apply speech enhancement techniques."""
        # Pre-emphasis filter to boost high frequencies (speech clarity)
        alpha = 0.95
        pre_emphasized = np.zeros_like(audio)
        pre_emphasized[0] = audio[0]
        pre_emphasized[1:] = audio[1:] - alpha * audio[:-1]
        
        # Apply simple formant enhancement (emphasize mid frequencies where speech is prominent)
        # Design band-pass filter for speech frequencies (300Hz - 3400Hz)
        low_freq = 300.0
        high_freq = 3400.0
        nyquist = self._sample_rate / 2.0
        
        if high_freq < nyquist:
            low_norm = low_freq / nyquist
            high_norm = high_freq / nyquist
            b, a = signal.butter(4, [low_norm, high_norm], btype='band', analog=False)
            enhanced = signal.filtfilt(b, a, pre_emphasized)
            
            # Blend original and enhanced for natural sound
            blend_factor = 0.3
            return (1 - blend_factor) * audio + blend_factor * enhanced
        else:
            return pre_emphasized

    def toggle_pause(self):
        """Pause/resume capture (used by the overlay pause button). While paused
        the mic keeps running but frames are dropped, so the start is preserved."""
        with self._lock:
            self._paused = not self._paused
        logger.info(f"Recording {'paused' if self._paused else 'resumed'}")
        return self._paused

    @property
    def is_recording(self):
        return self._recording

    def cleanup(self):
        """Explicitly clean up resources"""
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.error(f"Error cleaning up stream: {e}")
            self._stream = None
        with self._lock:
            self._buffer = []
            self._recording = False
            self._level = 0.0
            self._noise_profile = None
