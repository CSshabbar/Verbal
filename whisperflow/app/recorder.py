import logging
import time
import numpy as np
import sounddevice as sd
import threading

logger = logging.getLogger("verbal.recorder")

CHANNELS = 1
DTYPE = "float32"
# Target peak level for Whisper — keeps audio in clean range
TARGET_PEAK = 0.5


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
            )
            self._stream.start()
            logger.info("Recording started")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self._recording = False
            raise

    def stop(self) -> np.ndarray | None:
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

    @property
    def is_recording(self):
        return self._recording
