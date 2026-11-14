"""Hardware-free tests for the REST receiver control API."""
from __future__ import annotations

import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sdrforge.controllers.receiver_manager import ReceiverManager
from sdrforge.protocols.rest.server import RestControlServer


class FakeReceiver:
    def __init__(self) -> None:
        self.frequency = 104_300_000
        self.mode = ("WFM", 200_000)
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def set_frequency(self, hz: int) -> None:
        self.frequency = hz

    def get_frequency(self) -> int:
        return self.frequency

    def set_mode(self, mode: str, bandwidth: int) -> None:
        self.mode = (mode, bandwidth)

    def get_mode(self) -> tuple[str, int]:
        return self.mode

    def get_signal_strength(self) -> float | None:
        return -42.0

    def get_snr(self) -> float | None:
        return 23.0

    def get_rds(self) -> str | None:
        return "WOMC"


def test_rest_receiver_control() -> None:
    fake = FakeReceiver()
    manager = ReceiverManager(fake)
    server = RestControlServer(manager, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def request(path: str, body: dict[str, object] | None = None) -> tuple[int, dict]:
        data = None if body is None else json.dumps(body).encode()
        req = Request(base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=2) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    try:
        assert request("/v1/health") == (200, {"status": "ok"})
        assert request("/v1/receiver")[1]["frequency_hz"] == 104_300_000
        assert request("/v1/receiver/frequency", {"frequency_hz": 94_700_000}) == (200, {"ok": True})
        assert fake.frequency == 94_700_000
        assert request("/v1/receiver/mode", {"mode": "am", "bandwidth_hz": 9000}) == (200, {"ok": True})
        assert fake.mode == ("AM", 9000)
        assert request("/v1/receiver/start", {}) == (200, {"ok": True})
        assert fake.started
        assert request("/v1/receiver/stop", {}) == (200, {"ok": True})
        assert not fake.started
        assert request("/v1/receiver/frequency", {"frequency_hz": True})[0] == 400
        assert request("/v1/missing")[0] == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
