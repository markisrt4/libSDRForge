# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Streaming BPSK Costas carrier recovery for 12 kSPS RDS baseband."""

from __future__ import annotations

import numpy as np


class RdsCarrierRecovery:
    """Second-order decision-directed Costas loop.

    Removes residual carrier frequency/phase from complex RDS baseband.
    BPSK has an unavoidable 180-degree phase ambiguity; differential
    decoding in a later stage resolves that ambiguity.
    """

    SAMPLE_RATE_HZ = 12_000

    def __init__(self, *, loop_bandwidth: float = 0.015,
                 max_offset_hz: float = 150.0) -> None:
        if not 0 < loop_bandwidth < 0.2:
            raise ValueError("loop_bandwidth must be between 0 and 0.2")
        if not 0 < max_offset_hz < self.SAMPLE_RATE_HZ / 2:
            raise ValueError("invalid maximum carrier offset")
        damping = 0.707
        denominator = 1 + 2 * damping * loop_bandwidth + loop_bandwidth ** 2
        self._alpha = 4 * damping * loop_bandwidth / denominator
        self._beta = 4 * loop_bandwidth ** 2 / denominator
        self._max_frequency = 2 * np.pi * max_offset_hz / self.SAMPLE_RATE_HZ
        self.reset()

    def reset(self) -> None:
        self._phase = 0.0
        self._frequency = 0.0

    @property
    def frequency_offset_hz(self) -> float:
        return self._frequency * self.SAMPLE_RATE_HZ / (2 * np.pi)

    def process(self, baseband: np.ndarray) -> np.ndarray:
        samples = np.asarray(baseband)
        if samples.ndim != 1 or not np.issubdtype(samples.dtype, np.complexfloating):
            raise ValueError("expected one-dimensional complex RDS baseband")
        if not np.all(np.isfinite(samples)):
            raise ValueError("RDS baseband must be finite")
        result = np.empty(len(samples), dtype=np.complex64)
        phase = self._phase
        frequency = self._frequency
        for index, sample in enumerate(samples):
            rotated = sample * np.exp(-1j * phase)
            result[index] = rotated
            # Normalized BPSK detector limits sensitivity to RF amplitude.
            error = (1.0 if rotated.real >= 0 else -1.0) * rotated.imag
            error /= max(abs(rotated), 1e-8)
            error = float(np.clip(error, -1.0, 1.0))
            frequency = float(np.clip(
                frequency + self._beta * error,
                -self._max_frequency, self._max_frequency))
            phase = (phase + frequency + self._alpha * error + np.pi) % (2 * np.pi) - np.pi
        self._phase = phase
        self._frequency = frequency
        return result
