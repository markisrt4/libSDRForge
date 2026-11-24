"""SAME clock selection and byte-error diagnostics regression tests."""

import numpy as np

from sdrforge.weather.same_afsk import (
    BAUD,
    decode_same_audio,
    decode_same_audio_diagnostic,
    synthesize_same_audio,
)
from sdrforge.weather.same_benchmark import HEADER, _byte_errors, benchmark


def test_diagnostic_preserves_public_decoder_bytes():
    audio = synthesize_same_audio(HEADER)
    result = decode_same_audio_diagnostic(audio, 24000)
    assert result.data == decode_same_audio(audio, 24000)
    assert HEADER in result.data
    assert result.complete_headers >= 1


def test_selected_clock_reported_for_single_hypothesis():
    audio = synthesize_same_audio(HEADER, baud=BAUD + 1)
    result = decode_same_audio_diagnostic(audio, 24000, baud_offsets=(1.0,))
    assert result.baud_offset == 1.0
    assert HEADER in result.data


def test_empty_audio_returns_empty_diagnostic():
    result = decode_same_audio_diagnostic(np.array([]), 24000)
    assert result.data == b""
    assert result.complete_headers == 0


def test_exact_alignment_zero_errors():
    assert _byte_errors(HEADER, b"junk" + HEADER + b"tail") == (0, len(HEADER))


def test_single_corrupt_byte_counted():
    corrupted = HEADER[:15] + b"?" + HEADER[16:]
    errors, prefix = _byte_errors(HEADER, corrupted)
    assert errors == 1
    assert prefix == 15


def test_missing_bytes_counted():
    assert _byte_errors(b"ABCDE", b"ABC") == (2, 3)


def test_benchmark_reports_diagnostics():
    row = benchmark(snrs=(80,), baud_errors=(0,), trials=1)[0]
    assert row.exact_headers == 1
    assert row.mean_byte_errors == 0
    assert row.mean_prefix_bytes == len(HEADER)
    assert row.selected_baud_offsets == (0.0,)
