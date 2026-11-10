# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Full-band FM multiplex extraction from channelized IQ."""

from __future__ import annotations

import numpy as np
from scipy import signal


class FmMultiplexDiscriminator:
    """Preserve 19/38/57 kHz multiplex components at 240 kSPS."""

    def __init__(self, *, sample_rate_hz: int = 240_000,
                 deviation_hz: float = 75_000.0) -> None:
        if sample_rate_hz <= 0 or deviation_hz <= 0:
            raise ValueError("sample rate and deviation must be positive")
        self._scale = sample_rate_hz / (2 * np.pi * deviation_hz)
        self.reset()

    def reset(self) -> None:
        self._previous_iq: complex | None = None
        self._dc_state = 0j

    def process(self, iq: np.ndarray) -> np.ndarray:
        samples = np.asarray(iq)
        if samples.ndim != 1 or not np.issubdtype(samples.dtype, np.complexfloating):
            raise ValueError("expected one-dimensional complex IQ")
        if not len(samples):
            return np.empty(0, dtype=np.float32)
        alpha = 0.0001
        dc, _ = signal.lfilter(
            [alpha], [1, -(1 - alpha)], samples,
            zi=[self._dc_state * (1 - alpha)],
        )
        self._dc_state = complex(dc[-1])
        samples = samples - dc
        previous = (np.concatenate((samples[:1], samples[:-1]))
                    if self._previous_iq is None
                    else np.concatenate(([self._previous_iq], samples[:-1])))
        self._previous_iq = complex(samples[-1])
        return (np.angle(samples * np.conj(previous)) * self._scale).astype(np.float32)
