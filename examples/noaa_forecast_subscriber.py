"""Inspect NOAA forecast events from a dedicated SDRForge ZeroMQ publisher.

Install the optional transport dependency with: pip install 'libsdrforge[zmq]'
Start this subscriber before starting the live NOAA probe (PUB/SUB slow joiner).
"""
from __future__ import annotations

import argparse
import json


def decode_forecast_message(message: bytes) -> dict:
    """Validate a versioned SDRForge telemetry envelope for NOAA forecasts."""
    topic, separator, body = message.partition(b" ")
    if not separator or topic != b"noaa.forecast":
        raise ValueError("expected noaa.forecast topic and JSON envelope")
    envelope = json.loads(body)
    if not isinstance(envelope, dict) or envelope.get("schema_version") != 1:
        raise ValueError("unsupported telemetry envelope")
    payload = envelope.get("payload")
    if not isinstance(payload, dict) or payload.get("event") != "noaa_forecast_completed":
        raise ValueError("invalid NOAA forecast payload")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="tcp://127.0.0.1:5573")
    parser.add_argument("--count", type=int, default=0, help="Exit after N events; 0 means continuous")
    args = parser.parse_args()
    if args.count < 0:
        parser.error("--count must be nonnegative")
    try:
        import zmq
    except ImportError as exc:
        parser.error("pyzmq is required; install libsdrforge[zmq]")
        raise AssertionError("unreachable") from exc
    context = zmq.Context.instance()
    socket = context.socket(zmq.SUB)
    socket.setsockopt(zmq.SUBSCRIBE, b"noaa.forecast")
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect(args.endpoint)
    received = 0
    try:
        while args.count == 0 or received < args.count:
            try:
                message = socket.recv()
                payload = decode_forecast_message(message)
            except (ValueError, json.JSONDecodeError) as exc:
                print(json.dumps({"event": "noaa_forecast_decode_error", "error": str(exc)}), flush=True)
                continue
            print(json.dumps(payload), flush=True)
            received += 1
    except KeyboardInterrupt:
        pass
    finally:
        socket.close()


if __name__ == "__main__":
    main()
