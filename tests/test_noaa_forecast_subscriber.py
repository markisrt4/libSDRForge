"""Validate the NOAA telemetry envelope without opening network sockets."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from noaa_forecast_subscriber import decode_forecast_message

from sdrforge.protocols.zmq.publisher import ZmqTelemetryPublisher


class CaptureSocket:
    def __init__(self):
        self.messages = []

    def send(self, message, flags=0):
        self.messages.append(message)

    def close(self):
        pass


def test_forecast_pub_sub_round_trip():
    socket = CaptureSocket()
    publisher = ZmqTelemetryPublisher(socket=socket)
    event = {
        "event": "noaa_forecast_completed",
        "forecast_areas": ["monroe county"],
        "deduplication_status": "new",
        "completed_forecast": {"forecast": {"period": "tonight"}},
    }
    assert publisher.publish("noaa.forecast", event)
    assert decode_forecast_message(socket.messages[0]) == event


@pytest.mark.parametrize("message", [
    b"receiver {}",
    b"noaa.forecast",
    b"noaa.forecast {}",
    b'noaa.forecast {"schema_version":2,"payload":{}}',
    b'noaa.forecast {"schema_version":1,"payload":{"event":"wrong"}}',
])
def test_reject_invalid_forecast_envelopes(message):
    with pytest.raises(ValueError):
        decode_forecast_message(message)
