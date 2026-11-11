# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Fractional-rate streaming RDS symbol timing recovery."""

from __future__ import annotations

import numpy as np


class RdsSymbolTimingRecovery:
    """Gardner timing loop with linear interpolation and 1 symbol/output.

    Operates on carrier-corrected, pulse-shaped complex BPSK at 12 kSPS.
    The Gardner detector is insensitive to BPSK polarity. Output symbols
    retain the 180-degree ambiguity for downstream differential decoding.
    This is an experimental timing loop, not an RDS bit decoder.
    """

    INPUT_RATE_HZ = 12_000
    SYMBOL_RATE_HZ = 1_187.5
    RDS_HALF_BIT_RATE_HZ = 2_375.0

    def __init__(self, *, timing_gain: float = 0.035,
                 rate_gain: float = 0.0002,
                 symbol_rate_hz: float = SYMBOL_RATE_HZ) -> None:
        if not 0 < timing_gain <= 0.5 or not 0 <= rate_gain <= 0.01:
            raise ValueError("invalid timing loop gains")
        if not 0 < symbol_rate_hz < self.INPUT_RATE_HZ / 2:
            raise ValueError("invalid symbol rate")
        self._symbol_rate_hz = float(symbol_rate_hz)
        self._timing_gain = timing_gain
        self._rate_gain = rate_gain
        self._nominal_period = self.INPUT_RATE_HZ / self._symbol_rate_hz
        self.reset()

    def reset(self) -> None:
        self._buffer = np.empty(0, dtype=np.complex64)
        self._buffer_start = 0
        self._next_time = self._nominal_period * 1.5
        self._period = self._nominal_period
        self._previous_symbol: complex | None = None

    @property
    def symbol_rate_hz(self) -> float:
        return self._symbol_rate_hz

    @property
    def samples_per_symbol(self) -> float:
        return self._period

    def _interpolate(self, time: float) -> complex:
        position = time - self._buffer_start
        index = int(np.floor(position))
        fraction = position - index
        return complex((1 - fraction) * self._buffer[index]
                       + fraction * self._buffer[index + 1])

    def process(self, baseband: np.ndarray) -> np.ndarray:
        samples = np.asarray(baseband)
        if samples.ndim != 1 or not np.issubdtype(samples.dtype, np.complexfloating):
            raise ValueError("expected one-dimensional complex baseband")
        if not np.all(np.isfinite(samples)):
            raise ValueError("baseband must contain finite samples")
        if len(samples):
            self._buffer = np.concatenate((self._buffer, samples.astype(np.complex64)))
        recovered = []
        while self._next_time + 1 < self._buffer_start + len(self._buffer):
            current = self._interpolate(self._next_time)
            if self._previous_symbol is not None:
                midpoint = self._interpolate(self._next_time - self._period / 2)
                # Gardner error: the mid-symbol sample should be at the
                # transition midpoint between consecutive symbol decisions.
                error = np.real((self._previous_symbol - current)
                                * np.conj(midpoint))
                magnitude = max(abs(self._previous_symbol) ** 2,
                                abs(current) ** 2, 1e-8)
                error = float(np.clip(error / magnitude, -1.0, 1.0))
                self._period = float(np.clip(
                    self._period + self._rate_gain * error,
                    self._nominal_period * 0.98,
                    self._nominal_period * 1.02))
                adjustment = self._timing_gain * error
            else:
                adjustment = 0.0
            recovered.append(current)
            self._previous_symbol = current
            self._next_time += self._period + adjustment
        # Retain only samples required for the next midpoint interpolation.
        retain_from = max(self._buffer_start,
                          int(np.floor(self._next_time - self._period)) - 2)
        discard = retain_from - self._buffer_start
        if discard:
            self._buffer = self._buffer[discard:]
            self._buffer_start = retain_from
        return np.asarray(recovered, dtype=np.complex64)
