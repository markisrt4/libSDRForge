# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Per-virtual-channel RF diagnostics, independent of SDR hardware."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ChannelRfTelemetry:
    signal_power_dbfs: float
    noise_floor_dbfs: float
    estimated_snr_db: float
    peak_dbfs: float
    adc_clip_fraction: float
    iq_samples: int


def measure_channel_rf(iq: np.ndarray, *, adc_clip_fraction: float = 0.0) -> ChannelRfTelemetry:
    """Estimate in-channel spectral contrast, not calibrated RF SNR.

    Noise floor is the median spectral-bin power, and estimated SNR is
    peak-bin contrast above that median. FM modulation, adjacent signals,
    filtering and FFT size influence this value. Never use it as a
    calibrated RF signal-to-noise ratio.
    """
    samples = np.asarray(iq, dtype=np.complex64)
    if samples.ndim != 1 or not len(samples):
        raise ValueError("expected nonempty complex IQ vector")
    if not np.all(np.isfinite(samples)):
        raise ValueError("IQ contains nonfinite samples")
    power = float(np.mean(np.abs(samples) ** 2))
    peak = float(np.max(np.abs(samples) ** 2))
    # Use the last contiguous segment so this works on streaming blocks.
    segment = samples[-min(len(samples), 4096):]
    window = np.hanning(len(segment)).astype(np.float32)
    fft = np.fft.fft(segment * window)
    spectrum = (np.abs(fft) ** 2) / max(float(np.sum(window ** 2)), 1e-20)
    noise = float(np.median(spectrum))
    strongest = float(np.max(spectrum))
    eps = 1e-20
    return ChannelRfTelemetry(
        signal_power_dbfs=round(10 * np.log10(max(power, eps)), 2),
        noise_floor_dbfs=round(10 * np.log10(max(noise, eps)), 2),
        estimated_snr_db=round(10 * np.log10(max(strongest, eps) / max(noise, eps)), 2),
        peak_dbfs=round(10 * np.log10(max(peak, eps)), 2),
        adc_clip_fraction=round(adc_clip_fraction, 6),
        iq_samples=len(samples),
    )


def adc_clip_fraction(raw: bytes, *, threshold: int = 2) -> float:
    """Fraction of raw 8-bit I/Q components near either ADC rail."""
    if not 0 <= threshold < 128:
        raise ValueError("invalid ADC clipping threshold")
    values = np.frombuffer(raw, dtype=np.uint8)
    if not len(values):
        return 0.0
    return float(np.count_nonzero((values <= threshold) | (values >= 255 - threshold)) / len(values))
