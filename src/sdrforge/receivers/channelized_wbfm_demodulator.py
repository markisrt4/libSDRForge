# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""WFM mono audio from already-channelized 240 kSPS complex IQ."""

from __future__ import annotations

from typing import cast

import numpy as np
from scipy import signal


class ChannelizedWbfmDemodulator:
    """Stateful 240 kSPS FM discriminator to 48 kHz PCM.

    Does not own RF hardware or repeat the 2.4 MSPS channel filter.
    """

    def __init__(self, *, input_rate_hz: int = 240_000,
                 audio_rate_hz: int = 48_000,
                 deemphasis_us: float = 75.0,
                 deviation_hz: float = 75_000.0) -> None:
        if input_rate_hz != 240_000 or audio_rate_hz != 48_000:
            raise ValueError("channelized WFM requires 240 kSPS IQ and 48 kHz PCM")
        if deemphasis_us <= 0 or deviation_hz <= 0:
            raise ValueError("deemphasis and deviation must be positive")
        self._audio_sos = signal.iirdesign(
            15_000, 24_000, 1, 70, fs=input_rate_hz, output="sos"
        )
        self._alpha = 1 - np.exp(-1 / (audio_rate_hz * deemphasis_us * 1e-6))
        self._scale = input_rate_hz / (2 * np.pi * deviation_hz)
        self.reset()

    def reset(self) -> None:
        self._previous_iq: complex | None = None
        self._audio_state = np.zeros((len(self._audio_sos), 2))
        self._audio_phase = 0
        self._deemphasis_state = np.zeros(1)
        self._dc_state = 0j

    def process(self, iq: np.ndarray) -> np.ndarray:
        """Process complex channel IQ, preserving continuity across calls."""
        samples = np.asarray(iq)
        if samples.ndim != 1 or not np.issubdtype(samples.dtype, np.complexfloating):
            raise ValueError("expected one-dimensional complex IQ")
        if not len(samples):
            return np.empty(0, dtype=np.float32)
        # Match the legacy WFM receiver's residual carrier/DC removal.
        alpha = 0.0001
        dc, _ = signal.lfilter(
            [alpha], [1, -(1 - alpha)], samples,
            zi=[self._dc_state * (1 - alpha)]
        )
        self._dc_state = complex(dc[-1])
        samples = samples - dc
        previous = (np.concatenate((samples[:1], samples[:-1]))
                    if self._previous_iq is None
                    else np.concatenate(([self._previous_iq], samples[:-1])))
        self._previous_iq = complex(samples[-1])
        discriminator = np.angle(samples * np.conj(previous))
        filtered, self._audio_state = signal.sosfilt(
            self._audio_sos, discriminator, zi=self._audio_state
        )
        audio = filtered[self._audio_phase::5]
        self._audio_phase = (self._audio_phase - len(filtered)) % 5
        audio *= self._scale
        output, self._deemphasis_state = signal.lfilter(
            [self._alpha], [1, -(1 - self._alpha)], audio,
            zi=self._deemphasis_state
        )
        return cast(np.ndarray, np.clip(output, -1, 1).astype(np.float32))
