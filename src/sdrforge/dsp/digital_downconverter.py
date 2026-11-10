# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Stateful digital downconverter for virtual SDR channels.

One instance per virtual receiver; it does not own or retune the RF device.
"""

from __future__ import annotations

import numpy as np
from scipy import signal

from sdrforge.models.iq import IqBlock, IqSampleFormat


class DigitalDownconverter:
    """Shift one RF channel to baseband and anti-alias decimate its IQ."""

    def __init__(self, *, input_rate_hz: int = 2_400_000,
                 output_rate_hz: int = 240_000,
                 channel_bandwidth_hz: int = 180_000) -> None:
        if input_rate_hz <= 0 or output_rate_hz <= 0:
            raise ValueError("sample rates must be positive")
        if input_rate_hz % output_rate_hz:
            raise ValueError("input rate must be an integer multiple of output rate")
        if not 0 < channel_bandwidth_hz < output_rate_hz:
            raise ValueError("channel bandwidth must fit inside output sample rate")
        self.input_rate_hz = input_rate_hz
        self.output_rate_hz = output_rate_hz
        self.channel_bandwidth_hz = channel_bandwidth_hz
        self._factor = input_rate_hz // output_rate_hz
        passband = channel_bandwidth_hz / 2
        stopband = (passband + output_rate_hz / 2) / 2
        self._sos = signal.iirdesign(
            passband, stopband, 1, 65, fs=input_rate_hz, output="sos"
        )
        self.reset()

    def reset(self) -> None:
        """Reset filter and oscillator history after an RF discontinuity."""
        self._state = np.zeros((len(self._sos), 2), dtype=np.complex128)
        self._phase = 0
        self._sample_index = 0
        self._last_center_hz: int | None = None
        self._last_channel_hz: int | None = None

    def process(self, block: IqBlock, channel_frequency_hz: int) -> np.ndarray:
        """Return complex baseband IQ at output_rate_hz.

        The requested channel must fit inside the captured Nyquist window,
        including half its occupied bandwidth.
        """
        if block.sample_format != IqSampleFormat.U8_INTERLEAVED:
            raise ValueError("unsupported IQ sample format")
        if block.sample_rate_hz != self.input_rate_hz or len(block.samples) % 2:
            raise ValueError("unexpected IQ rate or incomplete IQ pair")
        offset = channel_frequency_hz - block.center_frequency_hz
        if abs(offset) + self.channel_bandwidth_hz / 2 >= self.input_rate_hz / 2:
            raise ValueError("virtual channel falls outside captured RF bandwidth")
        if (self._last_center_hz is not None and
            (self._last_center_hz != block.center_frequency_hz or
             self._last_channel_hz != channel_frequency_hz)):
            self.reset()
        self._last_center_hz = block.center_frequency_hz
        self._last_channel_hz = channel_frequency_hz
        raw = np.frombuffer(block.samples, dtype=np.uint8).astype(np.float32)
        iq = ((raw[::2] - 127.5) + 1j * (raw[1::2] - 127.5)) / 127.5
        count = len(iq)
        # The common single-station case is tuned to the hardware center.
        # Avoid constructing a full-rate oscillator and multiplying every
        # sample by unity; retain the same filter and decimation state.
        if offset == 0:
            shifted = iq
        else:
            indices = np.arange(count, dtype=np.float64) + self._sample_index
            shifted = iq * np.exp(-2j * np.pi * offset * indices / self.input_rate_hz)
        filtered, self._state = signal.sosfilt(  # type: ignore[assignment,arg-type]
            self._sos, shifted, zi=self._state
        )
        result = filtered[self._phase::self._factor]
        self._phase = (self._phase - count) % self._factor
        self._sample_index = (self._sample_index + count) % self.input_rate_hz
        return result.astype(np.complex64)
