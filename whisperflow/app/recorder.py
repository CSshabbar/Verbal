import logging
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

# Noise reduction parameters
NOISE_REDUCTION_STRENGTH = 0.2
NOISE_SAMPLE_DURATION = 0.5  # seconds to sample noise floor


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
        self._recording = False
        self._sample_rate = _get_native_rate()
        self._noise_profile = None
        self._noise_floor = 0.0
        logger.info(f"Mic native rate: {self._sample_rate}Hz")

    @property
    def sample_rate(self):
        return self._sample_rate

    def start(self):
        with self._lock:
            self._buffer = []
            self._recording = True
        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=CHANNELS,
                dtype=DTYPE,
                callback=self._audio_callback,
                latency='low',  # Reduce latency for better responsiveness
            )
            self._stream.start()
            logger.info("Recording started")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self._recording = False
            raise

    def stop(self) -> Optional[np.ndarray]:
        with self._lock:
            self._recording = False
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
            # Limit buffer size to prevent memory issues
            if len(self._buffer) > 1000:  # Roughly 30 seconds at 48kHz
                self._buffer = self._buffer[-1000:]
            audio = np.concatenate(self._buffer, axis=0).flatten()
            self._buffer = []

        duration = len(audio) / self._sample_rate
        peak = np.max(np.abs(audio))
        logger.info(f"Captured {duration:.1f}s at {self._sample_rate}Hz, peak={peak:.4f}")

        # Apply noise reduction and audio enhancement
        if len(audio) > 0:
            audio = self._enhance_audio(audio)
        
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
        with self._lock:
            if self._recording:
                self._buffer.append(indata.copy())

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
            self._noise_profile = None
