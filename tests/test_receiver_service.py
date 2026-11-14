# SPDX-License-Identifier: MIT
"""Hardware-free receiver lifecycle contract tests."""
import pytest

from sdrforge.controllers.receiver_service import ReceiverService, ReceiverState


class FakeReceiver:
    def __init__(self) -> None:
        self.starts = 0
        self.stops = 0
        self.fail_start = False
        self.frequency = 104_300_000
        self.mode = ("WFM", 200_000)

    def start(self) -> None:
        self.starts += 1
        if self.fail_start:
            raise RuntimeError("device disconnected")

    def stop(self) -> None:
        self.stops += 1

    def set_frequency(self, hz: int) -> None:
        self.frequency = hz

    def get_frequency(self) -> int:
        return self.frequency

    def set_mode(self, mode: str, bandwidth: int) -> None:
        self.mode = (mode, bandwidth)

    def get_mode(self) -> tuple[str, int]:
        return self.mode

    def get_signal_strength(self) -> float | None:
        return None

    def get_snr(self) -> float | None:
        return None

    def get_rds(self) -> str | None:
        return None


def test_start_stop_are_idempotent() -> None:
    receiver = FakeReceiver()
    service = ReceiverService(receiver)
    service.start()
    service.start()
    assert receiver.starts == 1
    assert service.state == ReceiverState.RUNNING
    service.stop()
    service.stop()
    assert receiver.stops == 1
    assert service.state == ReceiverState.STOPPED


def test_restart_and_controls() -> None:
    receiver = FakeReceiver()
    service = ReceiverService(receiver)
    service.start()
    service.restart()
    assert (receiver.starts, receiver.stops) == (2, 1)
    service.set_frequency(94_700_000)
    service.set_mode("FM", 180_000)
    assert service.get_frequency() == 94_700_000
    assert service.get_mode() == ("FM", 180_000)


def test_start_failure_records_error_and_stop_recovers() -> None:
    receiver = FakeReceiver()
    receiver.fail_start = True
    service = ReceiverService(receiver)
    with pytest.raises(RuntimeError, match="disconnected"):
        service.start()
    assert service.state == ReceiverState.ERROR
    assert service.last_error == "device disconnected"
    service.stop()
    receiver.fail_start = False
    service.start()
    assert service.state == ReceiverState.RUNNING
    assert service.last_error is None


def test_disconnect_releases_receiver_and_allows_recovery() -> None:
    receiver = FakeReceiver()
    service = ReceiverService(receiver)
    service.start()
    service.report_disconnect("USB removed")
    assert service.state == ReceiverState.ERROR
    assert service.last_error == "USB removed"
    assert receiver.stops == 1
    with pytest.raises(RuntimeError, match="cannot start"):
        service.start()
    service.stop()
    service.start()
    assert service.state == ReceiverState.RUNNING
    assert receiver.starts == 2
