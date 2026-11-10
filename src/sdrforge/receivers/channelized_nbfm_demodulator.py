# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Narrowband FM mono audio from channelized 240 kSPS complex IQ."""

from __future__ import annotations

import numpy as np
from scipy import signal


class ChannelizedNbfmDemodulator:
    """Stateful NFM discriminator, RF filtering and 48 kHz PCM output."""

    def __init__(self, *, input_rate_hz: int = 240_000,
                 audio_rate_hz: int = 48_000, deviation_hz: float = 5_000,
                 deemphasis_us: float = 750.0) -> None:
        if input_rate_hz != 240_000 or audio_rate_hz != 48_000:
            raise ValueError("channelized NFM requires 240 kSPS IQ and 48 kHz PCM")
        if deviation_hz <= 0 or deemphasis_us <= 0:
            raise ValueError("deviation and deemphasis must be positive")
        self._rf_sos = signal.iirdesign(
            12_000, 23_000, 1, 70, fs=input_rate_hz, output="sos"
        )
        self._audio_sos = signal.iirdesign(
            3_000, 5_000, 1, 60, fs=audio_rate_hz, output="sos"
        )
        self._scale = audio_rate_hz / (2 * np.pi * deviation_hz)
        self._alpha = 1 - np.exp(-1 / (audio_rate_hz * deemphasis_us * 1e-6))
        self.reset()

    def reset(self) -> None:
        self._rf_state = np.zeros((len(self._rf_sos), 2), dtype=np.complex128)
        self._decimation_phase = 0
        self._previous_iq: complex | None = None
        self._audio_state = np.zeros((len(self._audio_sos), 2))
        self._deemphasis_state = np.zeros(1)

    def process(self, iq: np.ndarray) -> np.ndarray:
        """Demodulate complex channel IQ without losing chunk continuity."""
        samples = np.asarray(iq)
        if samples.ndim != 1 or not np.issubdtype(samples.dtype, np.complexfloating):
            raise ValueError("expected one-dimensional complex IQ")
        if not len(samples):
            return np.empty(0, dtype=np.float32)
        filtered, self._rf_state = signal.sosfilt(
            self._rf_sos, samples, zi=self._rf_state
        )
        decimated = filtered[self._decimation_phase::5]
        self._decimation_phase = (self._decimation_phase - len(filtered)) % 5
        if not len(decimated):
            return np.empty(0, dtype=np.float32)
        previous = (np.concatenate((decimated[:1], decimated[:-1]))
                    if self._previous_iq is None
                    else np.concatenate(([self._previous_iq], decimated[:-1])))
        self._previous_iq = complex(decimated[-1])
        discriminator = np.angle(decimated * np.conj(previous)) * self._scale
        audio, self._audio_state = signal.sosfilt(
            self._audio_sos, discriminator, zi=self._audio_state
        )
        output, self._deemphasis_state = signal.lfilter(
            [self._alpha], [1, -(1 - self._alpha)], audio,
            zi=self._deemphasis_state
        )
        return np.clip(output, -1, 1).astype(np.float32)
