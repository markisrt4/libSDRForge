"""Deterministic tone-gate tests; no SDR hardware required."""

import numpy as np
import pytest

from sdrforge.weather.same_afsk import synthesize_same_audio
from sdrforge.weather.same_tone_gate import (
    is_same_tone_candidate,
    same_tone_fraction,
)


def _tone(freq, *, rate=24000, seconds=0.2, amplitude=0.5):
    t = np.arange(int(rate * seconds)) / rate
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_same_afsk_detected():
    audio = synthesize_same_audio(b"ZCZC-WXR-RWT-026099+0030-3211200-KDTX/NWS-")
    assert is_same_tone_candidate(audio, 24000)


def test_space_tone_detected():
    assert is_same_tone_candidate(_tone(1562.5), 24000)


def test_mark_tone_detected():
    assert is_same_tone_candidate(_tone(2083.333333), 24000)


def test_unrelated_tone_rejected():
    assert not is_same_tone_candidate(_tone(1000), 24000)


def test_silence_rejected():
    assert not is_same_tone_candidate(np.zeros(4800), 24000)


def test_white_noise_rejected():
    noise = np.random.default_rng(123).normal(0, 0.3, 4800)
    assert not is_same_tone_candidate(noise, 24000)


def test_noise_mixed_with_afsk():
    audio = synthesize_same_audio(b"ZCZC")
    noise = np.random.default_rng(123).normal(0, 0.10, len(audio))
    assert is_same_tone_candidate(audio + noise, 24000)


def test_short_frame_safe():
    assert same_tone_fraction(np.ones(20), 24000) == 0.0


def test_nonfinite_rejected():
    with pytest.raises(ValueError):
        same_tone_fraction(np.array([np.nan]), 24000)


def test_invalid_gate_threshold():
    with pytest.raises(ValueError):
        is_same_tone_candidate(np.zeros(480), 24000, min_fraction=0)


def test_invalid_sample_rate():
    with pytest.raises(ValueError):
        same_tone_fraction(np.zeros(480), 4000)
