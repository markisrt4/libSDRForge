"""!
@brief Hardware-independent 1090 MHz Mode S preamble and PPM demodulation.
Input is complex baseband IQ. This first implementation targets complete buffers;
streaming overlap and RTL-SDR acquisition are separate milestones.
"""
from __future__ import annotations

import numpy as np

_PULSES = (0.0, 1.0, 3.5, 4.5)
_GAPS = (2.0, 2.5, 5.5, 6.5)


def _energy(power: np.ndarray, sample_rate: float, start_us: float, width_us: float) -> np.ndarray:
    """Window mean sampled at arbitrary fractional microsecond offsets."""
    n = max(1, round(width_us * sample_rate / 1e6))
    start = round(start_us * sample_rate / 1e6)
    if start + n > len(power):
        return np.empty(0)
    sums = np.concatenate(([0.0], np.cumsum(power, dtype=np.float64)))
    return np.asarray(
        (sums[start + n:] - sums[start:len(power) - n + 1]) / n,
        dtype=np.float64,
    )


def demodulate_frames(iq: np.ndarray, sample_rate: float, *, threshold: float = 4.0) -> tuple[bytes, ...]:
    """!
    @brief Extract 112-bit DF17 frames from a complete IQ buffer.
    Candidate preambles are gated by pulse/gap contrast. Final acceptance is
    delegated to CRC validation in the frame receiver session.
    @param iq The iq value.
    @param sample_rate The sample rate value.
    @param threshold The threshold value.
    @return The operation result.
    """
    if sample_rate < 2e6 or not np.isfinite(sample_rate):
        raise ValueError("sample_rate must be finite and >= 2 MS/s")
    if threshold <= 1:
        raise ValueError("threshold must be > 1")
    signal = np.asarray(iq)
    if signal.ndim != 1:
        raise ValueError("iq must be one-dimensional")
    power = np.abs(signal.astype(np.complex128)) ** 2
    samples_per_us = sample_rate / 1e6
    frame_samples = int(np.ceil(120 * samples_per_us))
    if len(power) < frame_samples:
        return ()
    # A pulse spans half a microsecond. Sample at its center using
    # interpolation so 2.4 MS/s does not require integral samples/bit.
    positions = np.arange(len(power), dtype=np.float64)
    centers = np.arange(0, len(power) - frame_samples + 1)
    def at(offset_us: float) -> np.ndarray:
        return np.asarray(
            np.interp(centers + offset_us * samples_per_us, positions, power),
            dtype=np.float64,
        )
    high = np.stack([at(t + .25) for t in _PULSES])
    low = np.stack([at(t + .25) for t in _GAPS])
    peak = np.min(high, axis=0)
    floor = np.max(low, axis=0)
    candidates = np.flatnonzero((peak > threshold * np.maximum(floor, 1e-12)) & (peak > 1e-8))
    frames: list[bytes] = []
    skip_until = 0
    for candidate in candidates:
        start = int(candidate)
        if start < skip_until:
            continue
        bit_centers = start + (8.0 + np.arange(112) + .25) * samples_per_us
        if sample_rate == 2e6:
            # Each half-bit is exactly one sample. Interpolating at its
            # midpoint blends adjacent PPM slots and produces ties for zero
            # bits (and sometimes one bits), losing the entire frame.
            early = power[np.floor(bit_centers).astype(np.int64)]
            late = power[np.floor(bit_centers + .5 * samples_per_us).astype(np.int64)]
        else:
            early = np.interp(bit_centers, positions, power)
            late = np.interp(bit_centers + .5 * samples_per_us, positions, power)
        bits = early > late
        # Avoid guessing bits with no meaningful energy.
        if np.any(np.maximum(early, late) < peak[np.searchsorted(centers, start)] * .15):
            continue
        raw = np.packbits(bits.astype(np.uint8)).tobytes()
        if raw[0] >> 3 == 17:
            frames.append(raw)
            skip_until = start + frame_samples
    return tuple(frames)
