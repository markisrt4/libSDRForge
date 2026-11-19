"""Pure scheduler tests: no RTL-SDR, clocks, threads, or networking."""
import pytest

from sdrforge.weather.auxiliary_scheduler import (
    AuxiliaryMode,
    AuxiliaryReceiverScheduler,
    AuxiliaryScheduleConfig,
)


def make_scheduler(**overrides):
    settings = dict(
        weather_frequency_hz=162_550_000,
        tmc_frequencies_hz=(94_700_000, 101_100_000),
        weather_dwell_seconds=60,
        tmc_dwell_seconds=20,
        max_alert_hold_seconds=120,
    )
    settings.update(overrides)
    return AuxiliaryReceiverScheduler(AuxiliaryScheduleConfig(**settings))


def test_initial_weather_then_tmc_then_weather():
    scheduler = make_scheduler()
    assert scheduler.tick(0).frequency_hz == 162_550_000
    assert not scheduler.tick(59).changed
    tmc = scheduler.tick(60)
    assert (tmc.mode, tmc.frequency_hz, tmc.changed) == (
        AuxiliaryMode.TMC, 94_700_000, True,
    )
    assert not scheduler.tick(79).changed
    assert scheduler.tick(80).mode is AuxiliaryMode.WEATHER
    assert scheduler.tick(140).frequency_hz == 101_100_000


def test_weather_only_if_no_tmc_frequencies():
    scheduler = make_scheduler(tmc_frequencies_hz=())
    scheduler.tick(0)
    assert scheduler.tick(10000).reason == "no_tmc_stations"
    assert scheduler.tick(10001).mode is AuxiliaryMode.WEATHER


def test_alert_holds_weather_then_releases():
    scheduler = make_scheduler()
    scheduler.tick(0)
    scheduler.hold_for_alert(55, 80)
    assert scheduler.tick(60).reason == "alert_hold"
    assert scheduler.tick(134).mode is AuxiliaryMode.WEATHER
    assert scheduler.tick(135).mode is AuxiliaryMode.TMC


def test_alert_hold_is_bounded():
    scheduler = make_scheduler()
    scheduler.tick(0)
    scheduler.hold_for_alert(55, 9999)
    assert scheduler.tick(174).mode is AuxiliaryMode.WEATHER
    assert scheduler.tick(175).mode is AuxiliaryMode.TMC


def test_alert_does_not_retune_away_from_tmc():
    scheduler = make_scheduler()
    scheduler.tick(0)
    scheduler.tick(60)
    scheduler.hold_for_alert(65, 100)
    assert scheduler.tick(80).mode is AuxiliaryMode.WEATHER
    assert scheduler.tick(140).mode is AuxiliaryMode.TMC


def test_alert_hold_can_be_cleared():
    scheduler = make_scheduler()
    scheduler.tick(0)
    scheduler.hold_for_alert(59, 100)
    scheduler.clear_alert_hold()
    assert scheduler.tick(60).mode is AuxiliaryMode.TMC


def test_time_reversal_rejected():
    scheduler = make_scheduler()
    scheduler.tick(10)
    with pytest.raises(ValueError):
        scheduler.tick(9)


@pytest.mark.parametrize("changes", [
    {"weather_frequency_hz": 0},
    {"tmc_frequencies_hz": (0,)},
    {"weather_dwell_seconds": 0},
    {"tmc_dwell_seconds": -1},
    {"max_alert_hold_seconds": 0},
])
def test_invalid_config(changes):
    with pytest.raises(ValueError):
        make_scheduler(**changes)
