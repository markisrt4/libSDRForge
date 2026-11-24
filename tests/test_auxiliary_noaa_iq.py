"""Hardware-free tests for auxiliary NOAA IQ/audio bridge."""

import numpy as np
import pytest

from sdrforge.weather.auxiliary_iq import AuxiliaryNoaaIqBridge


class Session:
    def __init__(self):
        self.allowed = True
        self.blocks = []

    def require_weather(self):
        if not self.allowed:
            raise RuntimeError("auxiliary WEATHER lease unavailable")

    def feed(self, pcm):
        self.require_weather()
        self.blocks.append(pcm.copy())


class FakeDemodulator:
    def __init__(self):
        self.calls = 0

    def process(self, block):
        self.calls += 1
        return np.asarray(block, dtype=np.float32)


def test_48k_to_16k_streaming_chunk_continuity():
    samples = np.sin(2 * np.pi * 1000 * np.arange(4800) / 48000).astype(np.float32)
    first = Session()
    second = Session()
    continuous = AuxiliaryNoaaIqBridge(first, demodulator=FakeDemodulator())
    chunked = AuxiliaryNoaaIqBridge(second, demodulator=FakeDemodulator())
    continuous.process(samples)
    for part in np.array_split(samples, 13):
        chunked.process(part)
    a = np.concatenate(first.blocks)
    b = np.concatenate(second.blocks)
    assert len(a) == len(b) == 1600
    np.testing.assert_allclose(a, b, atol=1e-6)
    assert np.max(np.abs(a)) <= 1.01


def test_no_iq_demodulation_without_weather_lease():
    session = Session()
    demod = FakeDemodulator()
    bridge = AuxiliaryNoaaIqBridge(session, demodulator=demod)
    session.allowed = False
    with pytest.raises(RuntimeError, match="lease unavailable"):
        bridge.process(np.ones(480, dtype=np.float32))
    assert demod.calls == 0
    assert session.blocks == []


def test_empty_audio_does_not_feed_worker():
    session = Session()
    bridge = AuxiliaryNoaaIqBridge(session, demodulator=FakeDemodulator())
    assert bridge.process(np.array([], dtype=np.float32)) == 0
    assert session.blocks == []


def test_overrange_demodulated_pcm_is_bounded_before_feed():
    session = Session()
    bridge = AuxiliaryNoaaIqBridge(session, demodulator=FakeDemodulator())
    loud = (4.0 * np.sin(2 * np.pi * 1000 * np.arange(4800) / 48000)).astype(np.float32)
    assert bridge.process(loud) == 1600
    output = np.concatenate(session.blocks)
    assert np.all(np.isfinite(output))
    assert np.max(np.abs(output)) <= 1.0
    assert np.any(np.abs(output) == 1.0)
