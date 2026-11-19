"""Integration with simulated receiver, without SDR hardware."""
import pytest

from sdrforge.controllers.receiver_manager import ReceiverManager
from sdrforge.simulation.simulated_receiver import SimulatedReceiver
from sdrforge.weather.auxiliary_scheduler import AuxiliaryScheduleConfig
from sdrforge.weather.receiver_manager import AuxiliaryReceiverManager, ReceiverService
from sdrforge.weather.receiver_runtime import AuxiliaryReceiverRuntime


def make_runtime(*, on_start=None, on_stop=None):
    primary = ReceiverManager(SimulatedReceiver(104_300_000))
    aux = ReceiverManager(SimulatedReceiver())
    schedule = AuxiliaryReceiverManager(AuxiliaryScheduleConfig(
        weather_dwell_seconds=10, tmc_dwell_seconds=5,
        tmc_frequencies_hz=(94_700_000,),
    ))
    runtime = AuxiliaryReceiverRuntime(schedule, aux, on_start=on_start, on_stop=on_stop)
    return primary, aux, schedule, runtime


def test_transitions_and_primary_isolation():
    primary, aux, scheduler, runtime = make_runtime()
    primary.start()
    assert runtime.step(0).service is ReceiverService.WEATHER
    assert aux.get_frequency() == 162_550_000
    assert aux.get_mode() == ("NFM", 12_500)
    assert not runtime.step(1).changed
    assert runtime.step(10).service is ReceiverService.TMC
    assert aux.get_mode() == ("WFM", 200_000)
    lease = scheduler.acquire("map", service=ReceiverService.ADSB)
    assert runtime.step(11).frequency_hz == 1_090_000_000
    assert aux.get_mode() == ("RAW", 2_000_000)
    scheduler.release(lease)
    assert runtime.step(12).service is ReceiverService.WEATHER
    assert primary.get_frequency() == 104_300_000
    runtime.close()
    assert not aux.running
    assert primary.running


def test_decoder_lifecycle_callbacks():
    events = []
    _, _, _, runtime = make_runtime(
        on_start=lambda service: events.append(("start", service)),
        on_stop=lambda service: events.append(("stop", service)),
    )
    runtime.step(0)
    runtime.step(10)
    runtime.close()
    assert events == [
        ("start", ReceiverService.WEATHER),
        ("stop", ReceiverService.WEATHER),
        ("start", ReceiverService.TMC),
        ("stop", ReceiverService.TMC),
    ]


def test_failed_tune_retries():
    class FailingReceiver(SimulatedReceiver):
        def __init__(self):
            super().__init__()
            self.fail_once = True

        def set_frequency(self, hz):
            if self.fail_once:
                self.fail_once = False
                raise OSError("simulated USB failure")
            super().set_frequency(hz)

    scheduler = AuxiliaryReceiverManager(AuxiliaryScheduleConfig())
    receiver = ReceiverManager(FailingReceiver())
    runtime = AuxiliaryReceiverRuntime(scheduler, receiver)
    with pytest.raises(OSError):
        runtime.step(0)
    assert runtime.applied_target is None
    assert runtime.step(1).changed
    assert receiver.get_frequency() == 162_550_000


def test_status_tracks_running_and_closed():
    _, _, _, runtime = make_runtime()
    assert runtime.status() == {
        "state": "idle", "service": None, "frequency_hz": None, "error": None,
    }
    runtime.step(0)
    assert runtime.status()["service"] == "weather"
    assert runtime.status()["state"] == "running"
    runtime.close()
    assert runtime.status()["state"] == "idle"


def test_decoder_start_failure_cleans_up_and_recovers():
    events = []
    fail = [True]

    def start(service):
        events.append(("start", service))
        if fail[0]:
            fail[0] = False
            raise RuntimeError("decoder unavailable")

    _, _, _, runtime = make_runtime(
        on_start=start,
        on_stop=lambda service: events.append(("stop", service)),
    )
    with pytest.raises(RuntimeError, match="decoder unavailable"):
        runtime.step(0)
    assert runtime.status()["state"] == "error"
    assert "decoder unavailable" in runtime.status()["error"]
    assert events == [
        ("start", ReceiverService.WEATHER),
        ("stop", ReceiverService.WEATHER),
    ]
    assert runtime.step(1).changed
    assert runtime.status()["error"] is None
    assert runtime.status()["state"] == "running"
