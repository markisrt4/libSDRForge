# SPDX-License-Identifier: MIT
"""Optional, rate-limited IQ observer for SDR spectrum telemetry."""
from __future__ import annotations

import time
from typing import Protocol

from sdrforge.models.iq import IqBlock
from sdrforge.telemetry.iq_spectrum import iq_power_spectrum_db


class SpectrumSinkIf(Protocol):
    def submit_spectrum(
        self, power_db: object, *, center_frequency_hz: int,
        sample_rate_hz: int, timestamp_ns: int | None = None,
    ) -> bool: ...


class IqSpectrumObserver:
    """Compute at most one FFT per interval and submit it to a telemetry sink."""

    def __init__(
        self, sink: SpectrumSinkIf, *, rate_hz: float = 10.0,
        fft_size: int = 2048,
    ) -> None:
        if not 0 < rate_hz <= 100 or fft_size < 2:
            raise ValueError("invalid spectrum rate or FFT size")
        self.sink = sink
        self.rate_hz = rate_hz
        self.fft_size = fft_size
        self._last_ns: int | None = None
        self.dropped = 0

    def __call__(self, block: IqBlock) -> None:
        # IQ timestamps are monotonic, unlike wall-clock telemetry timestamps.
        now = block.timestamp_ns
        if self._last_ns is not None and now >= self._last_ns:
            if now - self._last_ns < int(1_000_000_000 / self.rate_hz):
                return
        self._last_ns = now
        bins = iq_power_spectrum_db(block, fft_size=self.fft_size)
        if not self.sink.submit_spectrum(
            bins, center_frequency_hz=block.center_frequency_hz,
            sample_rate_hz=block.sample_rate_hz,
            timestamp_ns=time.time_ns(),
        ):
            self.dropped += 1
