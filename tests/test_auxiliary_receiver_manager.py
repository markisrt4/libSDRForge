"""Pure on-demand auxiliary receiver arbitration tests."""
import pytest

from sdrforge.weather.auxiliary_scheduler import AuxiliaryScheduleConfig
from sdrforge.weather.receiver_manager import AuxiliaryReceiverManager, ReceiverService


def manager():
    return AuxiliaryReceiverManager(AuxiliaryScheduleConfig(
        weather_frequency_hz=162_550_000,
        tmc_frequencies_hz=(94_700_000,),
        weather_dwell_seconds=60,
        tmc_dwell_seconds=20,
    ))


def test_adaptive_by_default():
    mgr = manager()
    assert mgr.tick(0).service is ReceiverService.WEATHER
    assert not mgr.tick(1).changed
    assert mgr.tick(60).service is ReceiverService.TMC


def test_adsb_preempts_and_restores_weather():
    mgr = manager()
    mgr.tick(0)
    mgr.tick(60)
    lease = mgr.acquire("adsb_screen", service=ReceiverService.ADSB)
    active = mgr.tick(61)
    assert active.changed
    assert active.frequency_hz == 1_090_000_000
    assert active.owner == "adsb_screen"
    assert not mgr.tick(62).changed
    assert mgr.release(lease)
    restored = mgr.tick(63)
    assert restored.changed
    assert restored.service is ReceiverService.WEATHER
    assert not mgr.tick(122).changed
    assert mgr.tick(123).service is ReceiverService.TMC


def test_priority_and_release_order():
    mgr = manager()
    mgr.tick(0)
    low = mgr.acquire("weather_screen", service=ReceiverService.WEATHER, priority=10)
    high = mgr.acquire("adsb_screen", service=ReceiverService.ADSB, priority=100)
    assert mgr.tick(1).service is ReceiverService.ADSB
    assert mgr.release(high)
    assert mgr.tick(2).service is ReceiverService.WEATHER
    assert mgr.release(low)
    assert not mgr.release(low)


def test_no_tmc_configuration_rejects_tmc_lease():
    mgr = AuxiliaryReceiverManager(AuxiliaryScheduleConfig())
    with pytest.raises(ValueError):
        mgr.acquire("traffic", service=ReceiverService.TMC)


def test_monotonic_clock_required():
    mgr = manager()
    mgr.tick(10)
    with pytest.raises(ValueError):
        mgr.tick(9)


def test_invalid_adsb_frequency():
    with pytest.raises(ValueError):
        AuxiliaryReceiverManager(AuxiliaryScheduleConfig(), adsb_frequency_hz=0)
