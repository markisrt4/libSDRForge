"""Auxiliary NOAA lease tests with no SDR hardware."""
import numpy as np
import pytest

from sdrforge.weather.auxiliary_scheduler import AuxiliaryScheduleConfig
from sdrforge.weather.receiver_manager import AuxiliaryReceiverManager, ReceiverService
from sdrforge.weather.auxiliary_session import AuxiliaryNoaaSession


class FakeRuntime:
    def __init__(self, manager, *, fail=False):
        self.scheduler = manager
        self.applied_target = None
        self.fail = fail

    def step(self, now):
        if self.fail:
            raise RuntimeError("auxiliary unavailable")
        decision = self.scheduler.tick(now)
        self.applied_target = (decision.service, decision.frequency_hz)


class FakeTranscriber:
    def __init__(self):
        self.calls = []

    def start(self):
        self.calls.append("start")

    def feed(self, pcm):
        self.calls.append(("feed", len(pcm)))

    def stop(self):
        self.calls.append("stop")


def test_auxiliary_noaa_session_uses_only_explicit_auxiliary():
    manager = AuxiliaryReceiverManager(AuxiliaryScheduleConfig())
    runtime = FakeRuntime(manager)
    sink = FakeTranscriber()
    session = AuxiliaryNoaaSession(manager, runtime, sink)
    with pytest.raises(RuntimeError, match="no active"):
        session.feed(np.zeros(16))
    session.start(0.0)
    assert runtime.applied_target == (ReceiverService.WEATHER, 162550000)
    session.feed(np.zeros(16))
    session.stop()
    assert sink.calls == ["start", ("feed", 16), "stop"]
    assert manager.tick(1.0).owner is None


def test_auxiliary_noaa_session_releases_lease_on_start_failure():
    manager = AuxiliaryReceiverManager(AuxiliaryScheduleConfig())
    runtime = FakeRuntime(manager, fail=True)
    sink = FakeTranscriber()
    session = AuxiliaryNoaaSession(manager, runtime, sink)
    with pytest.raises(RuntimeError, match="unavailable"):
        session.start(0.0)
    assert manager.tick(1.0).owner is None
    assert sink.calls == []


def test_auxiliary_noaa_session_rejects_mismatched_manager():
    first = AuxiliaryReceiverManager(AuxiliaryScheduleConfig())
    second = AuxiliaryReceiverManager(AuxiliaryScheduleConfig())
    with pytest.raises(ValueError, match="must match"):
        AuxiliaryNoaaSession(first, FakeRuntime(second), FakeTranscriber())


def test_auxiliary_noaa_session_detects_other_auxiliary_service():
    manager = AuxiliaryReceiverManager(AuxiliaryScheduleConfig())
    runtime = FakeRuntime(manager)
    session = AuxiliaryNoaaSession(manager, runtime, FakeTranscriber())
    session.start(0.0)
    runtime.applied_target = (ReceiverService.ADSB, 1090000000)
    try:
        with pytest.raises(RuntimeError, match="not tuned"):
            session.feed(np.zeros(16))
    finally:
        session.stop()
