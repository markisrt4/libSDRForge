# SPDX-License-Identifier: MIT
"""Hardware-free spectrum telemetry regression across radio mode changes."""

from __future__ import annotations

import numpy as np

from sdrforge.models.iq import IqBlock
from sdrforge.session import RadioSession
from sdrforge.telemetry.iq_observer import IqSpectrumObserver


class SpectrumSink:
    def __init__(self) -> None:
        self.frames: list[dict[str, object]] = []

    def submit_spectrum(
        self,
        power_db: object,
        *,
        center_frequency_hz: int,
        sample_rate_hz: int,
        timestamp_ns: int | None = None,
    ) -> bool:
        self.frames.append(
            {
                "power_db": power_db,
                "center_frequency_hz": center_frequency_hz,
                "sample_rate_hz": sample_rate_hz,
                "timestamp_ns": timestamp_ns,
            }
        )
        return True


def test_spectrum_observer_survives_demodulation_changes() -> None:
    sink = SpectrumSink()
    observer = IqSpectrumObserver(sink, rate_hz=10)
    session = RadioSession(frequency_hz=104_300_000, rf_warmup_seconds=0)
    samples = np.tile(np.array([192, 128, 128, 192], dtype=np.uint8), 2048).tobytes()

    for index, (mode, bandwidth) in enumerate(
        (
            ("WFM", 200_000),
            ("NFM", 12_500),
            ("AM", 6_000),
            ("NFM", 7_500),
            ("WFM", 180_000),
        )
    ):
        session.set_demodulation(mode, bandwidth)
        observer(
            IqBlock(
                samples,
                104_300_000,
                2_400_000,
                (index + 1) * 200_000_000,
            )
        )
        assert session.demodulation == mode
        assert session.channel_bandwidth_hz == bandwidth

    assert len(sink.frames) == 5
    for frame in sink.frames:
        assert frame["center_frequency_hz"] == 104_300_000
        assert frame["sample_rate_hz"] == 2_400_000
        bins = np.asarray(frame["power_db"])
        assert bins.shape == (2048,)
        assert np.all(np.isfinite(bins))
