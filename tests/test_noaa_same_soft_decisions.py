"""Soft-decision SAME diagnostics; no inferred emergency alerts."""
import numpy as np

from sdrforge.weather.same_afsk import (
    _symbol_confidences, _uart_confidence, decode_same_audio_diagnostic,
    synthesize_same_audio,
)
from sdrforge.weather.same_benchmark import HEADER, add_awgn, benchmark


def test_soft_metrics_are_bounded():
    audio = synthesize_same_audio(HEADER)
    metrics = _symbol_confidences(audio, 24000, 0)
    assert len(metrics) > 0
    assert np.all(np.abs(metrics) <= 1.0000001)


def test_clean_mark_and_space_have_opposite_signs():
    audio = synthesize_same_audio(b"Z")
    metrics = _symbol_confidences(audio, 24000, 0)
    assert metrics[0] > 0
    assert np.any(metrics < 0)


def test_uart_confidence_empty():
    assert _uart_confidence(np.array([], dtype=float)) == 0.0


def test_uart_confidence_valid_frame():
    frame = np.array([-0.9] + [0.8] * 9)
    assert 0.79 < _uart_confidence(frame) < 0.91


def test_diagnostic_exposes_finite_confidence():
    audio = synthesize_same_audio(HEADER)
    result = decode_same_audio_diagnostic(audio, 24000)
    assert HEADER in result.data
    assert 0 <= result.decision_confidence <= 1


def test_noise_benchmark_reports_confidence():
    rows = benchmark(snrs=(20,), baud_errors=(0,), trials=1)
    assert 0 <= rows[0].mean_decision_confidence <= 1


def test_soft_confidence_does_not_mutate_audio():
    audio = synthesize_same_audio(b"ZCZC")
    before = audio.copy()
    _symbol_confidences(audio, 24000, 0)
    np.testing.assert_array_equal(audio, before)


def test_noise_decreases_average_soft_confidence():
    audio = synthesize_same_audio(HEADER)
    clean = _symbol_confidences(audio, 24000, 0)
    noisy = add_awgn(audio, -6, np.random.default_rng(19))
    degraded = _symbol_confidences(noisy, 24000, 0)
    assert np.mean(np.abs(clean)) > np.mean(np.abs(degraded))
