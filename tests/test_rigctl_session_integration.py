# SPDX-License-Identifier: MIT
"""Exercise rigctl TCP mode changes against the real DSP session, without USB."""

from __future__ import annotations

import socket
import threading

from sdrforge.protocols.rigctl.server import RigctlServer
from sdrforge.session import RadioSession


class SessionReceiver:
    """Minimal receiver adapter for exercising rigctl and DSP together."""

    def __init__(self) -> None:
        self.session = RadioSession(frequency_hz=104_300_000, rf_warmup_seconds=0)

    def set_mode(self, mode: str, bandwidth: int) -> None:
        self.session.set_demodulation(mode, bandwidth)

    def get_mode(self) -> tuple[str, int]:
        return self.session.demodulation, self.session.channel_bandwidth_hz

    def set_frequency(self, hz: int) -> None:
        self.session.retune(hz)

    def get_frequency(self) -> int:
        return self.session.frequency_hz


def test_rigctl_changes_real_session_dsp_configuration() -> None:
    receiver = SessionReceiver()
    server = RigctlServer(receiver, port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        def send(command: str) -> str:
            with socket.create_connection(server.server_address, timeout=2) as conn:
                conn.sendall((command + "\n").encode())
                conn.shutdown(socket.SHUT_WR)
                with conn.makefile("r", encoding="utf-8") as stream:
                    return stream.read().strip()

        for mode, bandwidth in (
            ("NFM", 7_500), ("NFM", 12_500), ("AM", 6_000),
            ("AM", 10_000), ("WFM", 200_000),
        ):
            assert send(f"M {mode} {bandwidth}") == "RPRT 0"
            assert send("m") == f"{mode}\n{bandwidth}"
            assert receiver.session.demodulation == mode
            assert receiver.session.channel_bandwidth_hz == bandwidth
            assert receiver.session.receiver is not None

        assert send("M AM 11000") == "RPRT -1"
        assert send("m") == "WFM\n200000"
        assert send("F 162550000") == "RPRT 0"
        assert send("f") == "162550000"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
