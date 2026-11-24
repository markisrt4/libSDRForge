#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""End-to-end simulated SDRForge REST, rigctl and ZMQ integration smoke test.

Runs on Linux without SDR hardware. Uses distinct ports to avoid a running service.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REST_PORT = 15570
RIGCTL_PORT = 14532
ZMQ_PORT = 15571
BASE = f"http://127.0.0.1:{REST_PORT}"


def request(path: str, *, post: bool = False) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=b"" if post else None,
        method="POST" if post else "GET",
    )
    with urllib.request.urlopen(req, timeout=3) as response:
        return json.load(response)


def await_condition(predicate, *, timeout: float = 20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = predicate()
            if result:
                return result
        except (OSError, ValueError, urllib.error.HTTPError):
            pass
        time.sleep(0.15)
    raise TimeoutError("integration condition was not satisfied")


def rigctl_frequency() -> int:
    with socket.create_connection(("127.0.0.1", RIGCTL_PORT), timeout=3) as sock:
        sock.settimeout(3)
        sock.sendall(bytes((102, 10)))
        data = sock.recv(256).decode("ascii").splitlines()
    return int(data[0])


def main() -> int:
    try:
        import zmq
    except ImportError as exc:
        raise SystemExit("Install pyzmq before running this test") from exc

    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        str(root / "examples/live_transport_server.py"),
        "--simulate",
        "--warmup",
        "0",
        "--no-rds",
        "--rest-port",
        str(REST_PORT),
        "--rigctl-port",
        str(RIGCTL_PORT),
        "--zmq-endpoint",
        f"tcp://127.0.0.1:{ZMQ_PORT}",
    ]
    process = subprocess.Popen(
        command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    context = zmq.Context()
    subscriber = context.socket(zmq.SUB)
    subscriber.setsockopt(zmq.LINGER, 0)
    subscriber.setsockopt(zmq.SUBSCRIBE, b"receiver ")
    subscriber.setsockopt(zmq.SUBSCRIBE, b"spectrum ")
    subscriber.connect(f"tcp://127.0.0.1:{ZMQ_PORT}")
    try:
        await_condition(lambda: request("/v1/health").get("status") == "ok")
        print("PASS REST health")
        initial = request("/v1/receiver")
        assert initial["running"] is False, initial
        assert rigctl_frequency() > 0
        print("PASS rigctl frequency")
        # Give the ZMQ subscription time to propagate before starting acquisition.
        time.sleep(0.4)
        request("/v1/receiver/start", post=True)
        await_condition(lambda: request("/v1/receiver").get("running") is True)
        print("PASS REST receiver start")
        topics = set()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and topics != {"receiver", "spectrum"}:
            if subscriber.poll(timeout=500):
                topic, encoded = subscriber.recv().split(b" ", 1)
                envelope = json.loads(encoded)
                assert envelope["schema_version"] == 1
                payload = envelope["payload"]
                if topic == b"receiver":
                    assert "channel_frequency_hz" in payload
                    assert "running" in payload
                    topics.add("receiver")
                elif topic == b"spectrum":
                    assert payload["bin_count"] == len(payload["power_db"])
                    topics.add("spectrum")
        assert topics == {"receiver", "spectrum"}, f"missing ZMQ topics: {topics}"
        print("PASS ZMQ receiver and spectrum")
        request("/v1/receiver/stop", post=True)
        await_condition(lambda: request("/v1/receiver").get("running") is False)
        print("PASS REST receiver stop")
        request("/v1/server/shutdown", post=True)
        process.wait(timeout=12)
        assert process.returncode == 0, f"server exited {process.returncode}"
        print("PASS clean server shutdown")
        return 0
    finally:
        subscriber.close()
        context.term()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if process.returncode:
            output = process.stdout.read() if process.stdout else ""
            if output:
                print(output[-4000:], file=sys.stderr)
        if process.stdout:
            process.stdout.close()


if __name__ == "__main__":
    raise SystemExit(main())
