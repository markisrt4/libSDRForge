# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""AM mono audio from channelized 240 kSPS complex IQ."""

from __future__ import annotations

import numpy as np
from scipy import signal


class ChannelizedAmDemodulator:
    """Stateful AM envelope detection, carrier rejection, filtering and AGC."""

    def __init__(self, *, input_rate_hz: int = 240_000,
                 audio_rate_hz: int = 48_000,
                 audio_bandwidth_hz: float = 4_000.0,
                 agc_target: float = 0.25,
                 agc_time_constant_s: float = 0.25) -> None:
        if input_rate_hz != 240_000 or audio_rate_hz != 48_000:
            raise ValueError("channelized AM requires 240 kSPS IQ and 48 kHz PCM")
        if not 0 < audio_bandwidth_hz < 10_000:
            raise ValueError("audio bandwidth must be between 0 and 10000 Hz")
        if agc_target <= 0 or agc_time_constant_s <= 0:
            raise ValueError("AGC target and time constant must be positive")
        self._rf_sos = signal.iirdesign(
            12_000, 23_000, 1, 65, fs=input_rate_hz, output="sos"
        )
        self._audio_sos = signal.butter(
            5, audio_bandwidth_hz, fs=audio_rate_hz, output="sos"
        )
        self._dc_alpha = 1 - np.exp(-1 / (audio_rate_hz * 0.005))
        self._agc_alpha = 1 - np.exp(-1 / (audio_rate_hz * agc_time_constant_s))
        self._agc_target = agc_target
        self.reset()

    def reset(self) -> None:
        """Clear all streaming filter, decimator and gain state."""
        self._rf_state = np.zeros((len(self._rf_sos), 2), dtype=np.complex128)
        self._rf_phase = 0
        self._audio_state = np.zeros((len(self._audio_sos), 2))
        self._dc_state = np.zeros(1)
        self._dc_initialized = False
        self._agc_power = 0.0

    def process(self, iq: np.ndarray) -> np.ndarray:
        """Return 48 kHz float32 mono PCM from complex 240 kSPS IQ."""
        samples = np.asarray(iq)
        if samples.ndim != 1 or not np.issubdtype(samples.dtype, np.complexfloating):
            raise ValueError("expected one-dimensional complex IQ")
        if not len(samples):
            return np.empty(0, dtype=np.float32)
        filtered, self._rf_state = signal.sosfilt(
            self._rf_sos, samples, zi=self._rf_state
        )
        envelope = np.abs(filtered[self._rf_phase::5])
        self._rf_phase = (self._rf_phase - len(filtered)) % 5
        if not len(envelope):
            return np.empty(0, dtype=np.float32)
        if not self._dc_initialized:
            self._dc_state[0] = (1 - self._dc_alpha) * float(envelope[0])
            self._dc_initialized = True
        dc, self._dc_state = signal.lfilter(
            [self._dc_alpha], [1, -(1 - self._dc_alpha)],
            envelope, zi=self._dc_state
        )
        audio, self._audio_state = signal.sosfilt(
            self._audio_sos, envelope - dc, zi=self._audio_state
        )
        power, state = signal.lfilter(
            [self._agc_alpha], [1, -(1 - self._agc_alpha)],
            np.square(audio), zi=[self._agc_power * (1 - self._agc_alpha)]
        )
        self._agc_power = float(power[-1])
        gain = self._agc_target / np.sqrt(np.maximum(power, 1e-5))
        return np.clip(audio * gain, -1, 1).astype(np.float32)
