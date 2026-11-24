"""Hardware-free IQ FFT and observer tests."""

from __future__ import annotations

import numpy as np
import pytest

from sdrforge.models.iq import IqBlock
from sdrforge.telemetry.iq_observer import IqSpectrumObserver
from sdrforge.telemetry.iq_spectrum import iq_power_spectrum_db


def block(timestamp_ns: int = 0) -> IqBlock:
    return IqBlock(
        samples=bytes([128, 128] * 4096),
        center_frequency_hz=104_300_000,
        sample_rate_hz=2_400_000,
        timestamp_ns=timestamp_ns,
    )


def test_spectrum_is_finite_and_shifted() -> None:
    bins = iq_power_spectrum_db(block(), fft_size=256)
    assert bins.shape == (256,)
    assert np.isfinite(bins).all()


def test_short_block_rejected() -> None:
    with pytest.raises(ValueError, match="shorter"):
        iq_power_spectrum_db(block(), fft_size=8192)


def test_observer_throttles_and_reports_drops() -> None:
    class Sink:
        def __init__(self) -> None:
            self.calls = 0

        def submit_spectrum(self, power_db: object, **kwargs: object) -> bool:
            self.calls += 1
            return False

    sink = Sink()
    observer = IqSpectrumObserver(sink, rate_hz=10)
    observer(block(0))
    observer(block(50_000_000))
    observer(block(100_000_000))
    assert sink.calls == 2
    assert observer.dropped == 2
