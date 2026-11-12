"""Synthetic IQ channel power tests, no tuner required."""
import numpy as np
import pytest

from sdrforge.dsp.channel_power import measure_channel_power
from sdrforge.models.iq import IqBlock


def _block(tone: bool) -> IqBlock:
    rng = np.random.default_rng(42)
    count = 4096
    noise = rng.normal(0, 7, count) + 1j * rng.normal(0, 7, count)
    if tone:
        noise += 45 * np.exp(2j * np.pi * 100_000 * np.arange(count) / 2_400_000)
    iq = np.column_stack((np.real(noise), np.imag(noise)))
    encoded = np.clip(np.rint(iq + 127.5), 0, 255).astype(np.uint8).tobytes()
    return IqBlock(encoded, 104_300_000, 2_400_000, 0)


def test_in_band_signal_exceeds_noise() -> None:
    signal, noise = measure_channel_power(_block(True), channel_width_hz=220_000)
    assert signal - noise > 8.0


def test_noise_only_has_no_strong_channel() -> None:
    signal, noise = measure_channel_power(_block(False), channel_width_hz=220_000)
    assert signal - noise < 8.0


def test_invalid_bandwidth_rejected() -> None:
    with pytest.raises(ValueError):
        measure_channel_power(_block(True), channel_width_hz=2_400_000)
