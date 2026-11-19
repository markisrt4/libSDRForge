"""Hardware-free tests for the synthetic IQ source."""
from __future__ import annotations

import numpy as np
import pytest

from sdrforge.adapters.simulated_iq import SimulatedIqSource
from sdrforge.telemetry.iq_spectrum import iq_power_spectrum_db


def test_simulated_source_produces_valid_continuous_iq() -> None:
    source = SimulatedIqSource(block_samples=4096)
    source.open()
    source.set_center_frequency(94_700_000)
    source.set_sample_rate(2_400_000)
    source.start()
    first = source.read_iq()
    second = source.read_iq()
    source.stop()
    source.close()
    assert first.center_frequency_hz == 94_700_000
    assert len(first.samples) == 8192
    assert second.timestamp_ns >= first.timestamp_ns
    assert first.samples != second.samples
    spectrum = iq_power_spectrum_db(first, fft_size=2048)
    assert spectrum.shape == (2048,)
    assert np.isfinite(spectrum).all()


def test_simulated_source_requires_start() -> None:
    source = SimulatedIqSource()
    with pytest.raises(RuntimeError, match="not started"):
        source.read_iq()
    with pytest.raises(RuntimeError, match="not opened"):
        source.start()


def test_simulated_source_rejects_bad_rate() -> None:
    source = SimulatedIqSource()
    with pytest.raises(ValueError, match="2.4 Msps"):
        source.set_sample_rate(1_000_000)
