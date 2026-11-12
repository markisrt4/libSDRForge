# SPDX-License-Identifier: MIT
"""Hardware-free tests for simulated device failures and recovery."""
import socket
import threading

import pytest

from sdrforge.fault_injecting_receiver import FaultInjectingReceiver
from sdrforge.receiver_manager import ReceiverManager
from sdrforge.rigctl_server import RigctlServer
from sdrforge.rigctl_simulator import SimulatedReceiver


def test_disconnection_blocks_operations_and_reconnect_restores_tuning():
    receiver = FaultInjectingReceiver(SimulatedReceiver())
    manager = ReceiverManager(receiver)
    receiver.disconnect()
    with pytest.raises(RuntimeError, match="disconnected"):
        manager.start()
    assert not manager.running
    receiver.reconnect()
    manager.start()
    manager.set_frequency(101_700_000)
    assert manager.running
    assert manager.get_frequency() == 101_700_000


def test_failed_tuning_preserves_previous_frequency():
    receiver = FaultInjectingReceiver(SimulatedReceiver())
    manager = ReceiverManager(receiver)
    receiver.fail_once("set_frequency")
    with pytest.raises(RuntimeError, match="injected"):
        manager.set_frequency(99_500_000)
    assert manager.get_frequency() == 104_300_000
    manager.set_frequency(99_500_000)
    assert manager.get_frequency() == 99_500_000


def test_failed_stop_can_be_retried():
    receiver = FaultInjectingReceiver(SimulatedReceiver())
    manager = ReceiverManager(receiver)
    manager.start()
    receiver.fail_once("stop")
    with pytest.raises(RuntimeError, match="injected"):
        manager.stop()
    assert manager.running
    manager.stop()
    assert not manager.running


def test_rigctl_reports_failure_and_recovers_over_tcp():
    receiver = FaultInjectingReceiver(SimulatedReceiver())
    manager = ReceiverManager(receiver)
    with RigctlServer(manager, port=0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def send(command: str) -> str:
                with socket.create_connection(server.server_address, timeout=2) as sock:
                    sock.sendall((command + "\n").encode())
                    sock.shutdown(socket.SHUT_WR)
                    return sock.makefile("r").read().strip()

            receiver.disconnect()
            assert send(r"\start") == "RPRT -1"
            assert not manager.running
            receiver.reconnect()
            assert send(r"\start") == "RPRT 0"
            receiver.fail_once("set_frequency")
            assert send("F 101700000") == "RPRT -1"
            assert send("f") == "104300000"
            assert send("F 101700000") == "RPRT 0"
            assert send("f") == "101700000"
        finally:
            server.shutdown()
            thread.join(timeout=2)
