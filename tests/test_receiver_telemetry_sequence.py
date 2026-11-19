"""Verify receiver snapshots carry restart-safe ordering metadata."""

from types import SimpleNamespace

from sdrforge.telemetry.stream import TelemetryStream


def test_receiver_sequence_increases_and_new_stream_resets() -> None:
    receiver = SimpleNamespace()
    first = TelemetryStream()
    second = TelemetryStream()
    # Inspect snapshots without needing a ZeroMQ socket or SDR hardware.
    snapshots = []
    first.submit = lambda topic, payload: snapshots.append((topic, payload)) or True
    assert first.submit_receiver(receiver, frequency_hz=104_300_000)
    assert first.submit_receiver(receiver, frequency_hz=104_300_000)
    assert [payload["sequence"] for _, payload in snapshots] == [1, 2]
    assert snapshots[0][1]["stream_id"] == snapshots[1][1]["stream_id"]
    second_snapshots = []
    second.submit = lambda topic, payload: second_snapshots.append(payload) or True
    assert second.submit_receiver(receiver, frequency_hz=104_300_000)
    assert second_snapshots[0]["sequence"] == 1
    assert second_snapshots[0]["stream_id"] != snapshots[0][1]["stream_id"]
