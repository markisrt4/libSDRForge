# SPDX-License-Identifier: MIT
"""Hardware-independent receiver manager tests."""
from concurrent.futures import ThreadPoolExecutor

from sdrforge.receiver_manager import ReceiverManager
from sdrforge.rigctl_simulator import SimulatedReceiver


class CountingReceiver(SimulatedReceiver):
    def __init__(self):
        super().__init__()
        self.starts = 0
        self.stops = 0

    def start(self):
        self.starts += 1
        super().start()

    def stop(self):
        self.stops += 1
        super().stop()


def test_start_stop_idempotent():
    receiver = CountingReceiver()
    manager = ReceiverManager(receiver)
    manager.start()
    manager.start()
    assert manager.running
    assert receiver.starts == 1
    manager.stop()
    manager.stop()
    assert not manager.running
    assert receiver.stops == 1


def test_tuning_and_mode_delegate():
    manager = ReceiverManager(SimulatedReceiver())
    manager.set_frequency(101_700_000)
    manager.set_mode("WFM", 200_000)
    assert manager.get_frequency() == 101_700_000
    assert manager.get_mode() == ("WFM", 200_000)


def test_concurrent_commands():
    manager = ReceiverManager(SimulatedReceiver())
    frequencies = [88_100_000 + i * 200_000 for i in range(32)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(manager.set_frequency, frequencies))
    assert manager.get_frequency() in frequencies


def test_failed_start_does_not_mark_running():
    class FailingReceiver(CountingReceiver):
        def start(self):
            raise RuntimeError("device unavailable")

    manager = ReceiverManager(FailingReceiver())
    try:
        manager.start()
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected receiver start failure")
    assert not manager.running
