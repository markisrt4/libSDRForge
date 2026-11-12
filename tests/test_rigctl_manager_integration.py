# SPDX-License-Identifier: MIT
"""End-to-end TCP tests through the receiver manager, without hardware."""
import socket
import threading

from sdrforge.receiver_manager import ReceiverManager
from sdrforge.rigctl_server import RigctlServer
from sdrforge.rigctl_simulator import SimulatedReceiver


def test_rigctl_manager_round_trip():
    manager = ReceiverManager(SimulatedReceiver())
    with RigctlServer(manager, port=0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            def send(command: str) -> str:
                with socket.create_connection(server.server_address, timeout=2) as conn:
                    conn.sendall((command + "\n").encode())
                    conn.shutdown(socket.SHUT_WR)
                    return conn.makefile("r").read().strip()

            assert send("f") == "104300000"
            assert send("F 101700000") == "RPRT 0"
            assert send("f") == "101700000"
            assert send("M WFM 200000") == "RPRT 0"
            assert send("m") == "WFM\n200000"
            assert send(r"\start") == "RPRT 0"
            assert manager.running
            assert send("l STRENGTH") == "-35.0"
            assert send("l SNR") == "22.0"
            assert send("l RDS") == "SDRFORGE TEST"
            assert send(r"\stop") == "RPRT 0"
            assert not manager.running
            assert send("l RDS") == ""
        finally:
            server.shutdown()
            worker.join(timeout=2)
