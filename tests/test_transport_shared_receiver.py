"""Verify REST and rigctl share tuning state through one receiver manager."""

import json
import socket
from contextlib import ExitStack
from threading import Thread
from urllib.request import Request, urlopen

from sdrforge.controllers.receiver_manager import ReceiverManager
from sdrforge.protocols.rest.server import RestControlServer
from sdrforge.protocols.rigctl.server import RigctlServer
from sdrforge.simulation.simulated_receiver import SimulatedReceiver


def test_rest_tuning_is_visible_to_rigctl_and_back() -> None:
    manager = ReceiverManager(SimulatedReceiver())
    with ExitStack() as stack:
        rest = stack.enter_context(RestControlServer(manager, port=0))
        rigctl = stack.enter_context(RigctlServer(manager, port=0))
        for server in (rest, rigctl):
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            stack.callback(worker.join, timeout=2)
            stack.callback(server.shutdown)

        def rigctl_command(command: str) -> str:
            with socket.create_connection(rigctl.server_address, timeout=2) as connection:
                connection.sendall((command + "\n").encode("ascii"))
                connection.shutdown(socket.SHUT_WR)
                with connection.makefile("r", encoding="ascii") as reply:
                    return reply.read().strip()

        base = f"http://127.0.0.1:{rest.server_port}/v1/receiver"
        tune = Request(
            f"{base}/frequency",
            data=b'{"frequency_hz":101100000}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(tune, timeout=2) as response:
            assert json.load(response) == {"ok": True}
        assert rigctl_command("f") == "101100000"

        assert rigctl_command("F 102300000") == "RPRT 0"
        with urlopen(base, timeout=2) as response:
            assert json.load(response)["frequency_hz"] == 102300000
