"""Offline source-pump safety tests: no USB hardware required."""
import pytest

from sdrforge.models.iq import IqBlock
from sdrforge.weather.auxiliary_source import AuxiliaryNoaaSourcePump


class Session:
    def __init__(self):
        self.active = True
        self.checked = 0

    def require_weather(self):
        self.checked += 1
        if not self.active:
            raise RuntimeError("WEATHER lease inactive")


class Bridge:
    def __init__(self):
        self.session = Session()
        self.received = []

    def process(self, block):
        self.received.append(block)
        return 42


class Source:
    def __init__(self, frequency=162_550_000, rate=2_400_000):
        self.block = IqBlock(
            samples=b"\x80\x80" * 512,
            center_frequency_hz=frequency,
            sample_rate_hz=rate,
            timestamp_ns=1,
        )
        self.reads = 0

    def read_iq(self):
        self.reads += 1
        return self.block


def test_pump_forwards_only_matching_weather_iq():
    source, bridge = Source(), Bridge()
    pump = AuxiliaryNoaaSourcePump(
        source, bridge, weather_frequency_hz=162_550_000
    )
    assert pump.pump_once() == 42
    assert pump.blocks == 1
    assert pump.samples == 42
    assert bridge.received == [source.block]


def test_no_read_without_weather_lease():
    source, bridge = Source(), Bridge()
    bridge.session.active = False
    pump = AuxiliaryNoaaSourcePump(
        source, bridge, weather_frequency_hz=162_550_000
    )
    with pytest.raises(RuntimeError, match="lease inactive"):
        pump.pump_once()
    assert source.reads == 0


@pytest.mark.parametrize("frequency,rate,error", [
    (94_700_000, 2_400_000, "frequency mismatch"),
    (162_550_000, 1_024_000, "2.4 MSPS"),
])
def test_rejects_stale_or_incompatible_iq(frequency, rate, error):
    source, bridge = Source(frequency, rate), Bridge()
    pump = AuxiliaryNoaaSourcePump(
        source, bridge, weather_frequency_hz=162_550_000
    )
    with pytest.raises((RuntimeError, ValueError), match=error):
        pump.pump_once()
    assert bridge.received == []
