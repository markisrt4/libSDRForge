"""Unit tests for the standalone transport clients."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_example(name: str):
    spec = importlib.util.spec_from_file_location(name, EXAMPLES / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_zmq_client_decodes_envelope() -> None:
    client = load_example("zmq_test_client")
    topic, payload = client.decode_message(
        b'spectrum ' + json.dumps({
            "schema_version": 1, "payload": {"bin_count": 2048},
        }).encode()
    )
    assert topic == "spectrum"
    assert payload == {"bin_count": 2048}
    with pytest.raises(ValueError):
        client.decode_message(b"no_separator")
    with pytest.raises(ValueError):
        client.decode_message(b'receiver {"schema_version":2,"payload":{}}')


def test_rest_client_request() -> None:
    client = load_example("rest_test_client")
    from threading import Thread

    from sdrforge.protocols.rest.server import RestControlServer

    class FakeReceiver:
        def get_frequency(self) -> int:
            return 104_300_000

        def get_mode(self) -> tuple[str, int]:
            return ("WFM", 200_000)

        def get_signal_strength(self) -> float | None:
            return None

        def get_snr(self) -> float | None:
            return None

        def get_rds(self) -> str | None:
            return None

    server = RestControlServer(FakeReceiver(), port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert client.request(
            f"http://127.0.0.1:{server.server_port}", "/v1/health"
        ) == {"status": "ok"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
