"""Synthesize a calm, rights-free ambient bed (no licensing, no attribution).

A sustained minor chord with soft detuned layers + slow tremolo + gentle
fade in/out. Deliberately quiet so it sits under text. Reproducible for automation.
"""
import wave

import numpy as np

SR = 44100


def generate(duration, path):
    n = int(SR * duration)
    t = np.linspace(0, duration, n, endpoint=False)

    # A-minor bed: A2, A3, C4, E4  (calm, reflective)
    freqs = [110.0, 220.0, 261.63, 329.63]
    sig = np.zeros(n)
    for f in freqs:
        sig += np.sin(2 * np.pi * f * t) * 0.5
        sig += np.sin(2 * np.pi * f * 1.004 * t) * 0.22   # detune warmth
        sig += np.sin(2 * np.pi * f * 2 * t) * 0.06        # soft harmonic
    sig += np.sin(2 * np.pi * 659.25 * t) * 0.04           # faint E5 shimmer

    # slow breathing tremolo
    sig *= 0.85 + 0.15 * np.sin(2 * np.pi * 0.07 * t)

    # overall fade in / out
    env = np.ones(n)
    fi, fo = int(1.4 * SR), int(2.6 * SR)
    env[:fi] = np.linspace(0, 1, fi)
    env[-fo:] = np.linspace(1, 0, fo)
    sig *= env

    sig = sig / np.max(np.abs(sig)) * 0.20   # keep it quiet (background)
    pcm = (np.column_stack([sig, sig]) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


if __name__ == "__main__":
    import sys
    generate(float(sys.argv[1]) if len(sys.argv) > 1 else 30.0,
             sys.argv[2] if len(sys.argv) > 2 else "ambient.wav")
    print("wrote ambient")
