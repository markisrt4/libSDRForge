# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""!
@brief Stateful narrowband FM demodulator for 2.4 MSPS IQ to 48 kHz mono PCM.
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np
from scipy import signal

from sdrforge.models.iq import IqBlock, IqSampleFormat


class NbfmMonoDemodulator:
    """!
    @brief Streaming NFM with RF channel filtering, discriminator and de-emphasis.
    """

    def __init__(
        self, sample_rate_hz: int = 2_400_000,
        audio_rate_hz: int = 48_000, deviation_hz: float = 5_000,
        deemphasis_us: float = 750.0,
        channel_bandwidth_hz: int = 25_000,
    ) -> None:
        """!
        @brief Provide   init   behavior.
        @param self The current instance.
        @param sample_rate_hz The sample rate hz value.
        @param audio_rate_hz The audio rate hz value.
        @param deviation_hz The deviation hz value.
        @param deemphasis_us The deemphasis us value.
        @param channel_bandwidth_hz The channel bandwidth hz value.
        """
        if sample_rate_hz != 2_400_000 or audio_rate_hz != 48_000:
            raise ValueError("NFM currently requires 2.4 MSPS IQ and 48 kHz PCM")
        if deviation_hz <= 0 or deemphasis_us <= 0:
            raise ValueError("deviation_hz and deemphasis_us must be positive")
        if channel_bandwidth_hz not in (7_500, 12_500, 25_000):
            raise ValueError("NFM channel bandwidth must be 7500, 12500, or 25000 Hz")
        self.channel_bandwidth_hz = channel_bandwidth_hz
        self.sample_rate_hz = sample_rate_hz
        self.audio_rate_hz = audio_rate_hz
        self.deviation_hz = deviation_hz
        # Filter before each decimation to reject adjacent channels and aliases.
        self._rf_stages = (
            (10, signal.iirdesign(95_000, 118_000, 1, 65, fs=2_400_000, output="sos")),
            (5, signal.iirdesign(
                channel_bandwidth_hz * 0.40, channel_bandwidth_hz * 0.70,
                1, 70, fs=240_000, output="sos"
            )),
        )
        self._rf_states = [
            np.zeros((len(sos), 2), dtype=np.complex128)
            for _, sos in self._rf_stages
        ]
        self._rf_phases = [0, 0]
        self._previous_iq: complex | None = None
        self._audio_sos = signal.iirdesign(
            3_000, 5_000, 1, 60, fs=48_000, output="sos"
        )
        self._audio_state = np.zeros((len(self._audio_sos), 2))
        alpha = 1 - np.exp(-1 / (audio_rate_hz * deemphasis_us * 1e-6))
        self._deemphasis_b = [alpha]
        self._deemphasis_a = [1, -(1 - alpha)]
        self._deemphasis_state = np.zeros(1)

    def process(self, block: IqBlock) -> np.ndarray:
        """!
        @brief Process an IQ block while preserving filter and decimator state.

        @param self The current instance.
        @param block The IQ sample block to process.
        @return The operation result.
        """
        if block.sample_format != IqSampleFormat.U8_INTERLEAVED:
            raise ValueError("NFM requires unsigned interleaved IQ")
        if block.sample_rate_hz != self.sample_rate_hz or len(block.samples) % 2:
            raise ValueError("Unexpected IQ rate or incomplete IQ sample")
        raw = np.frombuffer(block.samples, dtype=np.uint8).astype(np.float32)
        samples = (((raw[::2] - 127.5) + 1j * (raw[1::2] - 127.5)) / 127.5).astype(np.complex64)
        for stage, (factor, sos) in enumerate(self._rf_stages):
            samples, self._rf_states[stage] = cast(Any, signal.sosfilt)(
                sos, samples, zi=self._rf_states[stage]
            )
            length = len(samples)
            samples = samples[self._rf_phases[stage]::factor]
            self._rf_phases[stage] = (self._rf_phases[stage] - length) % factor
        if not len(samples):
            return np.empty(0, dtype=np.float32)
        previous = (
            np.concatenate((samples[:1], samples[:-1]))
            if self._previous_iq is None
            else np.concatenate(([self._previous_iq], samples[:-1]))
        )
        self._previous_iq = complex(samples[-1])
        phase = np.angle(samples * np.conj(previous))
        audio = phase * (self.audio_rate_hz / (2 * np.pi * self.deviation_hz))
        audio, self._audio_state = signal.sosfilt(
            self._audio_sos, audio, zi=self._audio_state
        )
        audio, self._deemphasis_state = signal.lfilter(
            self._deemphasis_b, self._deemphasis_a, audio,
            zi=self._deemphasis_state
        )
        result: np.ndarray = np.clip(audio, -1, 1).astype(np.float32)
        return result
