"""Test telemetry framing and backpressure without pyzmq or SDR hardware."""
import json

import pytest

from sdrforge.protocols.zmq.publisher import ZmqTelemetryPublisher


class FakeSocket:
    def __init__(self) -> None:
        self.messages: list[bytes] = []
        self.block = False
        self.closed = False

    def send(self, message: bytes, flags: int) -> None:
        assert flags == 1
        if self.block:
            raise BlockingIOError
        self.messages.append(message)

    def close(self) -> None:
        self.closed = True


def test_publish_and_drop() -> None:
    socket = FakeSocket()
    publisher = ZmqTelemetryPublisher(socket=socket)
    assert publisher.publish("spectrum", {"bins_db": [-50.0, -40.0]})
    topic, raw = socket.messages[0].split(b" ", 1)
    assert topic == b"spectrum"
    assert json.loads(raw) == {
        "schema_version": 1,
        "payload": {"bins_db": [-50.0, -40.0]},
    }
    socket.block = True
    assert not publisher.publish("spectrum", {"bins_db": []})
    assert publisher.dropped_messages == 1
    with pytest.raises(ValueError):
        publisher.publish("bad topic", {})
    publisher.close()
    assert socket.closed
