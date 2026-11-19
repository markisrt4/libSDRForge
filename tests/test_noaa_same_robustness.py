"""Reproducible SAME tone-gate robustness tests.

These characterize candidate detection only, not reliable header decoding.
"""
import numpy as np
import pytest

from sdrforge.weather.same_afsk import synthesize_same_audio
from sdrforge.weather.same_burst import SameBurstDetector
from sdrforge.weather.same_tone_gate import is_same_tone_candidate, same_tone_fraction

RATE = 24000
HEADER = b"ZCZC-WXR-RWT-026099+0030-3211200-KDTX/NWS-"


def _tone(frequency, amplitude=0.4, seconds=0.2):
    t = np.arange(round(RATE * seconds)) / RATE
    return (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


@pytest.mark.parametrize("offset_hz", [-60, -30, 0, 30, 60])
def test_mark_frequency_offset_candidate(offset_hz):
    assert is_same_tone_candidate(_tone(2083.333333 + offset_hz), RATE)


@pytest.mark.parametrize("offset_hz", [-60, 0, 60])
def test_space_frequency_offset_candidate(offset_hz):
    assert is_same_tone_candidate(_tone(1562.5 + offset_hz), RATE)


@pytest.mark.parametrize("noise_std", [0.03, 0.08, 0.12])
def test_same_audio_with_additive_noise(noise_std):
    signal = synthesize_same_audio(HEADER)
    rng = np.random.default_rng(100)
    noisy = signal + rng.normal(0, noise_std, len(signal))
    assert is_same_tone_candidate(noisy, RATE)


@pytest.mark.parametrize("amplitude", [0.08, 0.15, 0.3])
def test_weak_but_clean_tone(amplitude):
    assert is_same_tone_candidate(_tone(1562.5, amplitude=amplitude), RATE)


def test_noise_does_not_trigger_burst_acquisition():
    rng = np.random.default_rng(8)
    detector = SameBurstDetector(RATE, tone_gate=True)
    samples = rng.normal(0, 0.4, RATE).astype(np.float32)
    for offset in range(0, len(samples), 271):
        detector.feed(samples[offset:offset + 271])
    assert detector.capture.buffered_samples == 0
    assert detector.finish().alerts == ()


def test_low_amplitude_unrelated_tone_is_rejected():
    assert not is_same_tone_candidate(_tone(1000, amplitude=0.5), RATE)


def test_zero_energy_fraction():
    assert same_tone_fraction(np.zeros(4800), RATE) == 0.0
