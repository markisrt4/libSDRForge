# SPDX-License-Identifier: MIT
"""REST and RigCTL share a single simulated receiver instance."""
from __future__ import annotations

import json
from threading import Thread
from urllib.request import Request, urlopen

from sdrforge.controllers.receiver_service import ReceiverService
from sdrforge.protocols.receiver_http import ReceiverHttpServer
from sdrforge.protocols.rigctl.command_handler import RigctlCommandHandler


class FakeReceiver:
    def __init__(self) -> None:
        self.frequency = 104_300_000
        self.mode = ("WFM", 200_000)
        self.starts = 0
        self.stops = 0

    def start(self) -> None:
        self.starts += 1

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


def test_rest_and_rigctl_share_receiver() -> None:
    fake = FakeReceiver()
    receiver = ReceiverService(fake)
    rigctl = RigctlCommandHandler(receiver)
    server = ReceiverHttpServer(receiver)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert rigctl.dispatch("F 94700000") == "RPRT 0"
        with urlopen(base + "/v1/receiver", timeout=2) as response:
            status = json.load(response)
        assert status["frequency_hz"] == 94_700_000
        payload = json.dumps({"frequency_hz": 101_100_000, "mode": "FM",
                              "bandwidth_hz": 180_000}).encode()
        request = Request(base + "/v1/receiver/tuning", data=payload,
                          headers={"Content-Type": "application/json"}, method="PUT")
        with urlopen(request, timeout=2) as response:
            assert json.load(response)["mode"] == "FM"
        assert rigctl.dispatch("f") == "101100000"
        assert rigctl.dispatch("m") == "FM\n180000"
        with urlopen(Request(base + "/v1/receiver/start", data=b"", method="POST"),
                     timeout=2) as response:
            assert json.load(response)["state"] == "running"
        assert fake.starts == 1
        assert rigctl.dispatch(r"\stop") == "RPRT 0"
        with urlopen(base + "/v1/receiver", timeout=2) as response:
            assert json.load(response)["state"] == "stopped"
        assert fake.stops == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
