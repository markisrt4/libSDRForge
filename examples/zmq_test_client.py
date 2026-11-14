# SPDX-License-Identifier: MIT
"""Inspect live libSDRForge ZMQ telemetry, including topic rates and payloads."""
from __future__ import annotations

import argparse
import json
import time


def decode_message(message: bytes) -> tuple[str, dict]:
    topic_bytes, separator, body = message.partition(b" ")
    if not separator:
        raise ValueError("missing ZMQ topic separator")
    topic = topic_bytes.decode("ascii")
    envelope = json.loads(body)
    if not isinstance(envelope, dict) or envelope.get("schema_version") != 1:
        raise ValueError("unsupported telemetry envelope")
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise TypeError("telemetry payload must be an object")
    return topic, payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="tcp://127.0.0.1:5571")
    parser.add_argument("--topic", action="append", choices=("spectrum", "receiver"))
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    try:
        import zmq
    except ImportError:
        print("pyzmq missing: pip install -e '.[zmq]'")
        return 2
    context = zmq.Context.instance()
    socket = context.socket(zmq.SUB)
    socket.setsockopt(zmq.LINGER, 0)
    socket.setsockopt(zmq.RCVHWM, 32)
    for topic in args.topic or ["spectrum", "receiver"]:
        socket.setsockopt(zmq.SUBSCRIBE, topic.encode("ascii"))
    socket.connect(args.endpoint)
    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)
    counts: dict[str, int] = {}
    deadline = time.monotonic() + args.seconds
    print(f"Listening on {args.endpoint} for {args.seconds:g}s")
    try:
        while time.monotonic() < deadline:
            timeout_ms = min(250, max(0, int((deadline - time.monotonic()) * 1000)))
            if not dict(poller.poll(timeout_ms)).get(socket):
                continue
            topic, payload = decode_message(socket.recv())
            counts[topic] = counts.get(topic, 0) + 1
            if args.verbose:
                print(topic, json.dumps(payload, separators=(",", ":")))
            elif counts[topic] == 1:
                print(f"{topic}: first payload fields: {', '.join(payload)}")
    except (ValueError, TypeError, UnicodeError) as exc:
        print(f"Invalid telemetry: {exc}")
        return 1
    finally:
        socket.close()
    for topic, count in sorted(counts.items()):
        print(f"{topic}: {count} messages, {count / args.seconds:.2f} msg/s")
    if not counts:
        print("No telemetry received. Check that a publisher is running.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
