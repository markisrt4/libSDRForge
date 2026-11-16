# SPDX-License-Identifier: MIT
"""!
@brief Immutable, transport-independent spectrum frame contract.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SpectrumFrame:
    """!
    @brief FFT power in relative dBFS, ordered from low to high RF frequency.

    Values are relative to full-scale complex samples, not calibrated dBm.
    Consumers can build a waterfall from successive frames.
    """

    center_frequency_hz: int
    sample_rate_hz: int
    timestamp_ns: int
    power_dbfs: tuple[float, ...]

    @property
    def fft_size(self) -> int:
        """!
        @brief Return the fft size.

        @param self The current instance.
        @return The operation result.
        """
        return len(self.power_dbfs)

    @property
    def bin_width_hz(self) -> float:
        """!
        @brief Return the bin width hz.

        @param self The current instance.
        @return The operation result.
        """
        return self.sample_rate_hz / self.fft_size


def spectrum_from_iq(
    iq: np.ndarray, *, center_frequency_hz: int, sample_rate_hz: int,
    timestamp_ns: int,
) -> SpectrumFrame:
    """!
    @brief Produce one centered, Hann-windowed FFT from complex IQ samples.

    @param iq The complex IQ samples to process.
    @param center_frequency_hz The ``center_frequency_hz`` value.
    @param sample_rate_hz The sample rate in hertz.
    @param timestamp_ns The ``timestamp_ns`` value.
    @return The operation result.
    """
    samples = np.asarray(iq)
    if samples.ndim != 1 or len(samples) < 2 or not np.iscomplexobj(samples):
        raise ValueError("expected at least two complex IQ samples")
    if sample_rate_hz <= 0 or center_frequency_hz < 0 or timestamp_ns < 0:
        raise ValueError("invalid spectrum metadata")
    window = np.hanning(len(samples))
    coherent_gain = float(np.sum(window))
    fft = np.fft.fftshift(np.fft.fft(samples * window)) / coherent_gain
    power = 20.0 * np.log10(np.maximum(np.abs(fft), 1e-12))
    return SpectrumFrame(
        center_frequency_hz=center_frequency_hz,
        sample_rate_hz=sample_rate_hz,
        timestamp_ns=timestamp_ns,
        power_dbfs=tuple(float(value) for value in power),
    )
