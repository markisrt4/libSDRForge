"""Experimental SAME tone-selective frame gate.

This gate detects energy concentrated near the two SAME AFSK frequencies.
It is not an alert validator and cannot replace repeated-header checks.
"""
from __future__ import annotations

import numpy as np

from .same_afsk import MARK_HZ, SPACE_HZ


def same_tone_fraction(pcm: np.ndarray, sample_rate: int) -> float:
    """Fraction of windowed spectral energy near SAME mark/space tones.

    Uses FFT bins with a +/- 100 Hz tolerance to accommodate short frames
    and clock offsets. Returns zero for silence. A high fraction is only a
    candidate-burst indicator, not evidence of a valid SAME header.
    """
    if sample_rate < 8000:
        raise ValueError("sample_rate must be at least 8000")
    samples = np.asarray(pcm)
    if samples.ndim != 1 or not np.issubdtype(samples.dtype, np.number):
        raise ValueError("pcm must be mono numeric samples")
    if not np.all(np.isfinite(samples)):
        raise ValueError("pcm must be finite")
    if len(samples) < max(16, int(sample_rate * 0.01)):
        return 0.0
    audio = samples.astype(np.float64, copy=False)
    audio = audio - audio.mean()
    if not np.any(audio):
        return 0.0
    spectrum = np.abs(np.fft.rfft(audio * np.hanning(len(audio)))) ** 2
    freqs = np.fft.rfftfreq(len(audio), 1 / sample_rate)
    # Remove DC and low-frequency drift from the denominator.
    valid = freqs >= 200
    total = float(np.sum(spectrum[valid]))
    if total <= 1e-20:
        return 0.0
    tone_bins = ((np.abs(freqs - SPACE_HZ) <= 100)
                 | (np.abs(freqs - MARK_HZ) <= 100))
    return float(np.sum(spectrum[tone_bins]) / total)


def is_same_tone_candidate(pcm: np.ndarray, sample_rate: int, *,
                           min_fraction: float = 0.40,
                           min_rms: float = 0.02) -> bool:
    """Check both signal level and concentration near SAME tones."""
    if not 0 < min_fraction <= 1:
        raise ValueError("min_fraction must be in (0, 1]")
    if not 0 <= min_rms < 1:
        raise ValueError("min_rms must be in [0, 1)")
    samples = np.asarray(pcm)
    fraction = same_tone_fraction(samples, sample_rate)
    if not len(samples):
        return False
    rms = float(np.sqrt(np.mean(np.asarray(samples, dtype=np.float64) ** 2)))
    return rms >= min_rms and fraction >= min_fraction
