"""Opt-in SAME tone gating integration tests (no RF hardware)."""

import numpy as np
import pytest

from sdrforge.weather.same_afsk import synthesize_same_audio
from sdrforge.weather.same_burst import SameBurstDetector

HEADER = b"ZCZC-WXR-RWT-026099+0030-3211200-KDTX/NWS-"


def _tone(frequency, seconds=1.0):
    t = np.arange(int(24000 * seconds)) / 24000
    return (0.5 * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


def _repeated_headers():
    gap = np.zeros(12000, dtype=np.float32)
    return np.concatenate(
        [gap, synthesize_same_audio(HEADER), gap, synthesize_same_audio(HEADER), gap]
    )


def test_gate_rejects_loud_unrelated_tone():
    detector = SameBurstDetector(24000, tone_gate=True)
    detector.feed(_tone(1000))
    assert detector.capture.buffered_samples == 0


def test_gate_rejects_white_noise():
    detector = SameBurstDetector(24000, tone_gate=True)
    detector.feed(np.random.default_rng(123).normal(0, 0.3, 24000))
    assert detector.capture.buffered_samples == 0


def test_gate_accepts_same_header_burst():
    detector = SameBurstDetector(24000, tone_gate=True)
    detector.feed(synthesize_same_audio(HEADER))
    assert detector.capture.buffered_samples > 0


def test_gate_confirms_repeated_headers():
    detector = SameBurstDetector(24000, tone_gate=True)
    audio = _repeated_headers()
    for offset in range(0, len(audio), 911):
        detector.feed(audio[offset : offset + 911])
    result = detector.finish()
    assert len(result.alerts) == 1
    assert result.alerts[0].event == "RWT"


def test_gate_does_not_confirm_single_header():
    detector = SameBurstDetector(24000, tone_gate=True)
    detector.feed(synthesize_same_audio(HEADER))
    assert detector.finish().alerts == ()


def test_default_preserves_energy_only_mode():
    detector = SameBurstDetector(24000)
    detector.feed(_tone(1000))
    assert detector.capture.buffered_samples > 0


def test_reject_invalid_fraction():
    with pytest.raises(ValueError):
        SameBurstDetector(24000, tone_gate=True, min_tone_fraction=0)
