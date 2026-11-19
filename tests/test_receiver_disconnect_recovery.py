# SPDX-License-Identifier: MIT
"""Hardware-free fault injection for acquisition-worker disconnect recovery."""
from __future__ import annotations

import json
import threading
import time
import urllib.request

from sdrforge.controllers.receiver_manager import ReceiverManager
from sdrforge.protocols.rest.server import RestControlServer
from sdrforge.rigctl_simulator import SimulatedReceiver


class DisconnectingReceiver(SimulatedReceiver):
    """Receiver whose acquisition worker can fail independently of control."""

    def __init__(self) -> None:
        super().__init__()
        self.alive = False
        self.error = None
        self.starts = 0
        self.stops = 0

    @property
    def worker_alive(self) -> bool:
        return self.alive

    @property
    def worker_error(self) -> str | None:
        return self.error

    def start(self) -> None:
        self.starts += 1
        self.error = None
        self.alive = True
        super().start()

    def stop(self) -> None:
        self.stops += 1
        self.alive = False
        super().stop()

    def disconnect(self) -> None:
        self.error = "RTL-SDR USB disconnected"
        self.alive = False


def test_disconnect_reports_stopped_and_allows_restart() -> None:
    receiver = DisconnectingReceiver()
    manager = ReceiverManager(receiver)
    manager.start()
    assert manager.running
    receiver.disconnect()
    assert manager.running is False
    assert manager.startup_error == "RTL-SDR USB disconnected"
    manager.start()
    assert manager.running
    assert manager.startup_error is None
    assert receiver.starts == 2
    manager.stop()
    assert not manager.running


def test_async_restart_after_disconnect() -> None:
    receiver = DisconnectingReceiver()
    manager = ReceiverManager(receiver)
    manager.start()
    receiver.disconnect()
    manager.start_async()
    deadline = time.monotonic() + 3
    while manager.starting and time.monotonic() < deadline:
        time.sleep(0.01)
    assert manager.running
    assert receiver.starts == 2
    manager.stop()


def test_rest_reports_disconnect_and_recovery() -> None:
    receiver = DisconnectingReceiver()
    manager = ReceiverManager(receiver)
    server = RestControlServer(manager, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def status() -> dict:
        with urllib.request.urlopen(base + "/v1/receiver", timeout=2) as response:
            return json.load(response)

    try:
        manager.start()
        assert status()["running"] is True
        receiver.disconnect()
        failed = status()
        assert failed["running"] is False
        assert failed["startup_error"] == "RTL-SDR USB disconnected"
        manager.start()
        recovered = status()
        assert recovered["running"] is True
        assert recovered["startup_error"] is None
    finally:
        manager.stop()
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
