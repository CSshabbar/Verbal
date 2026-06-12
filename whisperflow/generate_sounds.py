#!/usr/bin/env python3
"""Generate modern notification sounds for Verbal."""

import numpy as np
import wave
import struct
import os
import sys

SAMPLE_RATE = 44100

def save_wav(filename, samples):
    """Save float samples to 16-bit WAV file."""
    samples = np.clip(samples, -1.0, 1.0)
    samples_int = (samples * 32767).astype(np.int16)
    with wave.open(filename, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(samples_int.tobytes())


def envelope(duration, attack=0.01, decay=0.3, sustain_level=0.5, release=0.2):
    """Generate an ADSR-like envelope."""
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    env = np.zeros_like(t)
    attack_samples = int(attack * SAMPLE_RATE)
    decay_samples = int(decay * SAMPLE_RATE)
    release_samples = int(release * SAMPLE_RATE)
    sustain_samples = len(t) - attack_samples - decay_samples - release_samples

    if attack_samples > 0:
        env[:attack_samples] = np.linspace(0, 1, attack_samples)
    if decay_samples > 0:
        env[attack_samples:attack_samples + decay_samples] = np.linspace(1, sustain_level, decay_samples)
    if sustain_samples > 0:
        env[attack_samples + decay_samples:attack_samples + decay_samples + sustain_samples] = sustain_level
    if release_samples > 0:
        env[-release_samples:] = np.linspace(sustain_level, 0, release_samples)
    return env


def generate_start():
    """Gentle ascending chime - soft and welcoming."""
    duration = 0.35
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    
    # Two tones: base + harmonic, with slight pitch bend up
    freq = 523.25  # C5
    freq2 = 659.25  # E5
    
    # Gentle pitch rise
    pitch_bend = 1 + 0.03 * np.sin(np.pi * t / (2 * duration))
    
    wave1 = np.sin(2 * np.pi * freq * pitch_bend * t) * 0.5
    wave2 = np.sin(2 * np.pi * freq2 * pitch_bend * t) * 0.3
    
    # Add subtle warmth
    wave3 = np.sin(2 * np.pi * freq * 2 * t) * 0.1
    
    combined = wave1 + wave2 + wave3
    env = envelope(duration, attack=0.05, decay=0.1, sustain_level=0.7, release=0.15)
    return combined * env


def generate_stop():
    """Soft descending tone - gentle release."""
    duration = 0.25
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    
    freq = 440.0  # A4
    freq2 = 349.23  # F4
    
    # Pitch fall
    pitch_bend = 1 - 0.05 * (t / duration)
    
    wave1 = np.sin(2 * np.pi * freq * pitch_bend * t) * 0.5
    wave2 = np.sin(2 * np.pi * freq2 * pitch_bend * t) * 0.3
    
    combined = wave1 + wave2
    env = envelope(duration, attack=0.02, decay=0.1, sustain_level=0.6, release=0.12)
    return combined * env


def generate_done():
    """Satisfying success chime - clear and positive."""
    duration = 0.5
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    
    # Three-note ascending success chord
    freq1 = 523.25  # C5
    freq2 = 659.25  # E5
    freq3 = 783.99  # G5
    
    # Staggered entry for each note
    env1 = envelope(duration, attack=0.03, decay=0.15, sustain_level=0.8, release=0.2)
    env2 = np.zeros_like(t)
    env3 = np.zeros_like(t)
    
    delay2 = int(0.04 * SAMPLE_RATE)
    delay3 = int(0.08 * SAMPLE_RATE)
    
    env2[delay2:] = envelope(duration - 0.04, attack=0.03, decay=0.15, sustain_level=0.8, release=0.2)[:len(t)-delay2]
    env3[delay3:] = envelope(duration - 0.08, attack=0.03, decay=0.15, sustain_level=0.8, release=0.2)[:len(t)-delay3]
    
    wave1 = np.sin(2 * np.pi * freq1 * t) * 0.4
    wave2 = np.sin(2 * np.pi * freq2 * t) * 0.3
    wave3 = np.sin(2 * np.pi * freq3 * t) * 0.25
    
    # Add gentle shimmer
    shimmer = np.sin(2 * np.pi * 1046.5 * t) * 0.05 * np.exp(-t * 4)
    
    combined = wave1 * env1 + wave2 * env2 + wave3 * env3 + shimmer
    return combined


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "assets/sounds"
    os.makedirs(out_dir, exist_ok=True)
    
    sounds = {
        "start": generate_start(),
        "stop": generate_stop(),
        "done": generate_done(),
    }
    
    for name, samples in sounds.items():
        filepath = os.path.join(out_dir, f"{name}.wav")
        save_wav(filepath, samples)
        print(f"Generated: {filepath} ({len(samples)} samples)")
    
    print("Done! Modern notification sounds generated.")


if __name__ == "__main__":
    main()
