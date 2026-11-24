# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""!
@brief Stateful AM envelope receiver: 2.4 MSPS IQ to 48 kHz mono PCM.
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np
from scipy import signal

from sdrforge.dsp.digital_downconverter import translate_iq
from sdrforge.models.iq import IqBlock, IqSampleFormat


class AmMonoDemodulator:
    """!
    @brief Envelope detection, DC rejection, audio low-pass and slow AGC.
    """

    def __init__(
        self, sample_rate_hz: int = 2_400_000,
        audio_rate_hz: int = 48_000,
        audio_bandwidth_hz: float = 4_000.0,
        channel_bandwidth_hz: int = 25_000,
        agc_target: float = 0.25,
        agc_time_constant_s: float = 0.25,
    ) -> None:
        """!
        @brief Provide   init   behavior.
        @param self The current instance.
        @param sample_rate_hz The sample rate hz value.
        @param audio_rate_hz The audio rate hz value.
        @param audio_bandwidth_hz The audio bandwidth hz value.
        @param channel_bandwidth_hz The channel bandwidth hz value.
        @param agc_target The agc target value.
        @param agc_time_constant_s The agc time constant s value.
        """
        if sample_rate_hz != 2_400_000 or audio_rate_hz != 48_000:
            raise ValueError("AM currently requires 2.4 MSPS IQ and 48 kHz PCM")
        if not 0 < audio_bandwidth_hz < 10_000:
            raise ValueError("audio_bandwidth_hz must be between 0 and 10000")
        if agc_target <= 0 or agc_time_constant_s <= 0:
            raise ValueError("AGC target and time constant must be positive")
        if channel_bandwidth_hz not in (6_000, 10_000, 12_500, 25_000):
            raise ValueError("AM channel bandwidth must be 6000, 10000, 12500, or 25000 Hz")
        self.channel_frequency_hz: int | None = None
        self._sample_index = 0
        self.channel_bandwidth_hz = channel_bandwidth_hz
        audio_bandwidth_hz = min(audio_bandwidth_hz, channel_bandwidth_hz * 0.40)
        self.sample_rate_hz = sample_rate_hz
        self.audio_rate_hz = audio_rate_hz
        self._rf_sos = signal.iirdesign(
            channel_bandwidth_hz * 0.45, channel_bandwidth_hz * 0.75,
            1, 65, fs=sample_rate_hz, output="sos"
        )
        self._rf_state = np.zeros((len(self._rf_sos), 2), dtype=np.complex128)
        self._rf_phase = 0
        self._audio_sos = signal.butter(
            5, audio_bandwidth_hz, fs=audio_rate_hz, output="sos"
        )
        self._audio_state = np.zeros((len(self._audio_sos), 2))
        # Remove carrier/DC after envelope detection.
        # A 5 ms carrier tracker rejects startup envelope transients while
        # preserving speech modulation (high-pass corner about 32 Hz).
        self._dc_alpha = 1 - np.exp(-1 / (audio_rate_hz * 0.005))
        self._dc_state = np.zeros(1)
        self._dc_initialized = False
        self._dc_b = [self._dc_alpha]
        self._dc_a = [1, -(1 - self._dc_alpha)]
        self._agc_target = agc_target
        self._agc_alpha = 1 - np.exp(-1 / (audio_rate_hz * agc_time_constant_s))
        self._agc_power = 0.0

    def process(self, block: IqBlock) -> np.ndarray:
        """!
        @brief Demodulate one block without resetting decimator or filter state.

        @param self The current instance.
        @param block The IQ sample block to process.
        @return The operation result.
        """
        if block.sample_format != IqSampleFormat.U8_INTERLEAVED:
            raise ValueError("AM requires unsigned interleaved IQ")
        if block.sample_rate_hz != self.sample_rate_hz or len(block.samples) % 2:
            raise ValueError("Unexpected IQ rate or incomplete IQ sample")
        raw = np.frombuffer(block.samples, dtype=np.uint8).astype(np.float32)
        iq = (((raw[::2] - 127.5) + 1j * (raw[1::2] - 127.5)) / 127.5).astype(np.complex64)
        frequency = self.channel_frequency_hz or block.center_frequency_hz
        offset = frequency - block.center_frequency_hz
        if abs(offset) + self.channel_bandwidth_hz / 2 >= self.sample_rate_hz / 2:
            raise ValueError("channel falls outside captured RF bandwidth")
        iq = translate_iq(iq, offset, self.sample_rate_hz, self._sample_index)
        self._sample_index = (self._sample_index + len(iq)) % self.sample_rate_hz
        filtered, self._rf_state = cast(Any, signal.sosfilt)(
            self._rf_sos, iq, zi=self._rf_state
        )
        length = len(filtered)
        decimated = filtered[self._rf_phase::50]
        self._rf_phase = (self._rf_phase - length) % 50
        if not len(decimated):
            return np.empty(0, dtype=np.float32)
        envelope = np.abs(decimated)
        if not self._dc_initialized:
            # Start the carrier estimate at the first envelope sample rather
            # than ramping up from zero and producing a large DC transient.
            self._dc_state[0] = (1 - self._dc_alpha) * float(envelope[0])
            self._dc_initialized = True
        dc, self._dc_state = signal.lfilter(
            self._dc_b, self._dc_a, envelope, zi=self._dc_state
        )
        audio = envelope - dc
        audio, self._audio_state = signal.sosfilt(
            self._audio_sos, audio, zi=self._audio_state
        )
        # AGC is block-independent: update the power estimate per sample.
        power = np.square(audio)
        smoothed, _state = signal.lfilter(
            [self._agc_alpha], self._dc_a[:1] + [-(1 - self._agc_alpha)],
            power, zi=[self._agc_power * (1 - self._agc_alpha)]
        )
        self._agc_power = float(smoothed[-1])
        gain = self._agc_target / np.sqrt(np.maximum(smoothed, 1e-5))
        result: np.ndarray = np.clip(audio * gain, -1, 1).astype(np.float32)
        return result
