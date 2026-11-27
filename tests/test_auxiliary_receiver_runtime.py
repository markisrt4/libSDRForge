"""Integration with simulated receiver, without SDR hardware."""

from threading import Event
from time import monotonic, sleep

import numpy as np
import pytest

from sdrforge.controllers.receiver_manager import ReceiverManager
from sdrforge.simulation.simulated_receiver import SimulatedReceiver
from sdrforge.weather.auxiliary_scheduler import AuxiliaryScheduleConfig
from sdrforge.weather.forecast_service import NoaaForecastService
from sdrforge.weather.managed_noaa_decoder import ManagedNoaaDecoder
from sdrforge.weather.receiver_manager import AuxiliaryReceiverManager, ReceiverService
from sdrforge.weather.receiver_runtime import AuxiliaryReceiverRuntime


def make_runtime(*, on_start=None, on_stop=None):
    primary = ReceiverManager(SimulatedReceiver(104_300_000))
    aux = ReceiverManager(SimulatedReceiver())
    schedule = AuxiliaryReceiverManager(
        AuxiliaryScheduleConfig(
            weather_dwell_seconds=10,
            tmc_dwell_seconds=5,
            tmc_frequencies_hz=(94_700_000,),
        )
    )
    runtime = AuxiliaryReceiverRuntime(
        schedule, aux, on_start=on_start, on_stop=on_stop
    )
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
        "state": "idle",
        "service": None,
        "frequency_hz": None,
        "error": None,
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


@pytest.mark.parametrize("token", [None, "wrong", "coordinator"])
def test_managed_auxiliary_runtime(token):
    receiver = ReceiverManager(SimulatedReceiver(), acquisition_token="coordinator")
    scheduler = AuxiliaryReceiverManager(AuxiliaryScheduleConfig())
    runtime = AuxiliaryReceiverRuntime(scheduler, receiver, acquisition_token=token)
    if token != "coordinator":
        with pytest.raises(PermissionError):
            runtime.step(0)
        assert runtime.applied_target is None
        assert not receiver.running
        return

    assert runtime.step(0).service is ReceiverService.WEATHER
    assert receiver.running
    assert receiver.get_frequency() == 162_550_000
    assert receiver.get_mode() == ("NFM", 12_500)
    runtime.close()
    assert not receiver.running


def test_failed_decoder_stop_blocks_retune():
    events = []
    blocked = [True]

    def stop(service):
        events.append(("stop", service))
        if blocked[0]:
            raise RuntimeError("decoder still running")

    _, aux, scheduler, runtime = make_runtime(
        on_start=lambda service: events.append(("start", service)),
        on_stop=stop,
    )
    runtime.step(0)
    lease = scheduler.acquire("map", service=ReceiverService.ADSB)
    with pytest.raises(RuntimeError, match="decoder still running"):
        runtime.step(1)
    assert runtime.applied_target is None
    assert aux.get_frequency() == 162_550_000
    assert runtime.status()["state"] == "error"
    assert all(service is ReceiverService.WEATHER for _, service in events)

    blocked[0] = False
    assert runtime.step(2).service is ReceiverService.ADSB
    assert aux.get_frequency() == 1_090_000_000
    assert events[-2:] == [
        ("stop", ReceiverService.WEATHER),
        ("start", ReceiverService.ADSB),
    ]
    scheduler.release(lease)
    runtime.close()


def test_weather_pcm_generation_across_preemption():
    class Recognizer:
        def transcribe(self, pcm, sample_rate):
            return "Tonight cloudy."

    forecasts = NoaaForecastService()
    scheduler = AuxiliaryReceiverManager(AuxiliaryScheduleConfig())
    receiver = ReceiverManager(SimulatedReceiver())
    decoders = []

    def factory(frequency):
        decoder = ManagedNoaaDecoder(Recognizer(), forecasts, frequency_hz=frequency)
        decoders.append(decoder)
        return decoder

    runtime = AuxiliaryReceiverRuntime(
        scheduler, receiver, noaa_decoder_factory=factory
    )
    pcm = np.zeros(160, dtype=np.float32)
    frequency = 162_550_000
    try:
        assert runtime.weather_generation() is None
        runtime.step(0)
        first = runtime.weather_generation()
        assert first is not None
        assert runtime.feed_weather_pcm(pcm, frequency, generation=first)
        assert not runtime.feed_weather_pcm(pcm, frequency + 1, generation=first)
        lease = scheduler.acquire("map", service=ReceiverService.ADSB)
        runtime.step(1)
        assert runtime.weather_generation() is None
        assert not runtime.feed_weather_pcm(pcm, frequency, generation=first)
        scheduler.release(lease)
        runtime.step(2)
        second = runtime.weather_generation()
        assert second is not None
        assert second != first
        assert len(decoders) == 2
        assert decoders[0] is not decoders[1]
        assert not runtime.feed_weather_pcm(pcm, frequency, generation=first)
        assert runtime.feed_weather_pcm(pcm, frequency, generation=second)
    finally:
        runtime.close()
    assert runtime.weather_generation() is None
    assert not runtime.feed_weather_pcm(pcm, frequency, generation=second)


def test_managed_pcm_publishes_forecast_and_preserves_history():
    published = []
    ready = Event()

    def submit(topic, record):
        published.append((topic, record))
        ready.set()
        return True

    class Recognizer:
        def __init__(self):
            self.transcripts = iter(
                ["thursday sunny forecast for monroe county", "tonight mostly cloudy"]
            )

        def transcribe(self, pcm, sample_rate):
            assert sample_rate == 16_000
            return next(self.transcripts)

    forecasts = NoaaForecastService(submit)
    scheduler = AuxiliaryReceiverManager(AuxiliaryScheduleConfig())
    receiver = ReceiverManager(SimulatedReceiver())

    def factory(frequency):
        return ManagedNoaaDecoder(
            Recognizer(), forecasts, frequency_hz=frequency, segment_seconds=0.01
        )

    runtime = AuxiliaryReceiverRuntime(
        scheduler, receiver, noaa_decoder_factory=factory
    )
    frequency = 162_550_000
    try:
        runtime.step(0)
        generation = runtime.weather_generation()
        assert generation is not None
        pcm = np.zeros(320, dtype=np.float32)
        assert runtime.feed_weather_pcm(pcm, frequency, generation=generation)
        assert ready.wait(timeout=3)
        deadline = monotonic() + 3
        while runtime.noaa_status()["decoder"]["processed_segments"] < 2:
            assert monotonic() < deadline
            sleep(0.01)
        status = runtime.noaa_status()["decoder"]
        assert status["active"]
        assert status["processed_segments"] == 2
        assert status["dropped_segments"] == 0
        assert status["last_error"] is None
        record = forecasts.history.latest()
        assert record is not None
        assert record["completed_forecast"]["forecast"]["period"] == "thursday"
        assert record["source_frequency_hz"] == frequency
        assert published == [("noaa.forecast", record)]
        lease = scheduler.acquire("map", service=ReceiverService.ADSB)
        runtime.step(1)
        assert runtime.noaa_status()["decoder"] is None
        assert forecasts.history.latest() == record
        scheduler.release(lease)
        runtime.step(2)
        assert runtime.noaa_status()["decoder"]["processed_segments"] == 0
        assert forecasts.history.latest() == record
    finally:
        runtime.close()
