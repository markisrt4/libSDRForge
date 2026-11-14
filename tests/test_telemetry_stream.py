"""Hardware-free asynchronous telemetry streaming tests."""
from __future__ import annotations

import numpy as np
import pytest

from sdrforge.telemetry.stream import TelemetryStream


class FakePublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []
        self.closed = False

    def publish(self, topic: str, payload: dict) -> bool:
        self.messages.append((topic, payload))
        return True

    def close(self) -> None:
        self.closed = True


def test_stream_sends_spectrum_and_receiver() -> None:
    publisher = FakePublisher()
    stream = TelemetryStream(publisher_factory=lambda: publisher)
    stream.start()
    assert stream.submit_spectrum(
        np.array([-10.0, -20.0]),
        center_frequency_hz=104_300_000,
        sample_rate_hz=200_000,
        timestamp_ns=42,
    )
    stream.stop()
    assert publisher.closed
    assert len(publisher.messages) == 1
    assert publisher.messages[0][0] == "spectrum"
    assert publisher.messages[0][1]["bin_count"] == 2


def test_stream_startup_failure() -> None:
    def fail() -> FakePublisher:
        raise RuntimeError("no socket")

    stream = TelemetryStream(publisher_factory=fail)
    with pytest.raises(RuntimeError, match="failed to start"):
        stream.start()


def test_invalid_capacity() -> None:
    with pytest.raises(ValueError):
        TelemetryStream(capacity=0)
