# SPDX-License-Identifier: MIT
"""!
@brief Compute a bounded RF spectrum preview from an interleaved U8 IQ block.
"""

from __future__ import annotations

import numpy as np

from sdrforge.models.iq import IqBlock, IqSampleFormat


def iq_power_spectrum_db(block: IqBlock, *, fft_size: int = 2048) -> np.ndarray:
    """!
    @brief Return fftshift-ordered relative power in dB, without changing IQ data.

    @param block The IQ sample block to process.
    @param fft_size The ``fft_size`` value.
    @return The operation result.
    """
    if fft_size < 2:
        raise ValueError("fft_size must be at least 2")
    if block.sample_format != IqSampleFormat.U8_INTERLEAVED:
        raise ValueError("unsupported IQ format")
    samples = np.frombuffer(block.samples, dtype=np.uint8)
    if samples.size < 2 * fft_size:
        raise ValueError("IQ block shorter than requested FFT")
    # Work on only one window to keep the observer's CPU cost bounded.
    iq = samples[: 2 * fft_size].astype(np.float32)
    complex_iq = (iq[0::2] - 127.5) + 1j * (iq[1::2] - 127.5)
    windowed = complex_iq * np.hanning(fft_size)
    spectrum = np.fft.fftshift(np.fft.fft(windowed))
    return (20.0 * np.log10(np.maximum(np.abs(spectrum), 1e-12))).astype(np.float32)
