# SPDX-License-Identifier: MIT
"""Hardware-free FFT contract tests."""
import numpy as np
import pytest

from sdrforge.models.spectrum_frame import spectrum_from_iq


def test_spectrum_peak_tracks_known_complex_tone() -> None:
    size = 1024
    sample_rate = 1_024_000
    tone_bin = 96
    iq = np.exp(2j * np.pi * tone_bin * np.arange(size) / size)
    frame = spectrum_from_iq(
        iq, center_frequency_hz=104_300_000,
        sample_rate_hz=sample_rate, timestamp_ns=123,
    )
    assert frame.fft_size == size
    assert frame.bin_width_hz == 1000
    assert frame.timestamp_ns == 123
    assert np.argmax(frame.power_dbfs) == size // 2 + tone_bin
    assert frame.power_dbfs[size // 2 + tone_bin] == pytest.approx(0, abs=0.05)


def test_spectrum_rejects_invalid_input() -> None:
    with pytest.raises(ValueError, match="complex IQ"):
        spectrum_from_iq(
            np.ones(8), center_frequency_hz=100_000_000,
            sample_rate_hz=1_000_000, timestamp_ns=1,
        )
    with pytest.raises(ValueError, match="metadata"):
        spectrum_from_iq(
            np.ones(8, dtype=np.complex64), center_frequency_hz=100_000_000,
            sample_rate_hz=0, timestamp_ns=1,
        )
