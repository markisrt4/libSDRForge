# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""!
@brief Full-band FM multiplex extraction from channelized IQ.
"""

from __future__ import annotations

from typing import cast

import numpy as np
from scipy import signal


class FmMultiplexDiscriminator:
    """!
    @brief Preserve 19/38/57 kHz multiplex components at 240 kSPS.
    """

    def __init__(
        self, *, sample_rate_hz: int = 240_000, deviation_hz: float = 75_000.0
    ) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param sample_rate_hz The ``sample_rate_hz`` value.
        @param deviation_hz The ``deviation_hz`` value.
        """
        if sample_rate_hz <= 0 or deviation_hz <= 0:
            raise ValueError("sample rate and deviation must be positive")
        self._scale = sample_rate_hz / (2 * np.pi * deviation_hz)
        self.reset()

    def reset(self) -> None:
        """!
        @brief Reset the component.

        @param self The current instance.
        """
        self._previous_iq: complex | None = None
        self._dc_state = 0j

    def process(self, iq: np.ndarray) -> np.ndarray:
        """!
        @brief Process the component.

        @param self The current instance.
        @param iq The complex IQ samples to process.
        @return The operation result.
        """
        samples = np.asarray(iq)
        if samples.ndim != 1 or not np.issubdtype(samples.dtype, np.complexfloating):
            raise ValueError("expected one-dimensional complex IQ")
        if not len(samples):
            return np.empty(0, dtype=np.float32)
        alpha = 0.0001
        dc, _ = signal.lfilter(
            [alpha],
            [1, -(1 - alpha)],
            samples,
            zi=[self._dc_state * (1 - alpha)],
        )
        self._dc_state = complex(dc[-1])
        samples = samples - dc
        previous = (
            np.concatenate((samples[:1], samples[:-1]))
            if self._previous_iq is None
            else np.concatenate(([self._previous_iq], samples[:-1]))
        )
        self._previous_iq = complex(samples[-1])
        return cast(
            np.ndarray,
            (np.angle(samples * np.conj(previous)) * self._scale).astype(np.float32),
        )
