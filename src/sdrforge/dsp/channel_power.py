"""Estimate channel power relative to adjacent noise from raw IQ blocks."""
from __future__ import annotations

import numpy as np

from sdrforge.models.iq import IqBlock, IqSampleFormat


def measure_channel_power(
    block: IqBlock, *,
    channel_width_hz: int = 180_000,
    guard_width_hz: int = 40_000,
) -> tuple[float, float]:
    """Return channel and noise spectral-density levels in relative dB.

    Measurements are normalized per FFT bin; this is not calibrated dBm.
    Noise is estimated from the outer passband, excluding the channel and guard.
    """
    if block.sample_format != IqSampleFormat.U8_INTERLEAVED:
        raise ValueError("unsupported IQ sample format")
    if block.sample_rate_hz <= 0 or channel_width_hz <= 0 or guard_width_hz < 0:
        raise ValueError("invalid measurement settings")
    if channel_width_hz + 2 * guard_width_hz >= block.sample_rate_hz:
        raise ValueError("sample rate too low for channel and noise regions")
    if len(block.samples) < 128 or len(block.samples) % 2:
        raise ValueError("IQ block must contain at least 64 complete samples")
    raw = np.frombuffer(block.samples, dtype=np.uint8).astype(np.float64)
    iq = (raw[0::2] - 127.5) + 1j * (raw[1::2] - 127.5)
    iq -= np.mean(iq)
    window = np.hanning(iq.size)
    spectrum = np.fft.fftshift(np.fft.fft(iq * window))
    power = np.abs(spectrum) ** 2 / max(np.sum(window**2), 1.0)
    frequency = np.fft.fftshift(np.fft.fftfreq(iq.size, 1.0 / block.sample_rate_hz))
    channel = np.abs(frequency) <= channel_width_hz / 2
    noise = np.abs(frequency) >= channel_width_hz / 2 + guard_width_hz
    if not np.any(channel) or not np.any(noise):
        raise ValueError("insufficient FFT resolution")
    floor = np.finfo(np.float64).tiny
    signal_db = 10.0 * np.log10(max(float(np.mean(power[channel])), floor))
    noise_db = 10.0 * np.log10(max(float(np.median(power[noise])), floor))
    return signal_db, noise_db
