#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Probe SDRForge REST and rigctl contracts used by OpenRoadCode.

Start examples/live_transport_server.py --simulate in another terminal first.
No RF hardware is required. No receiver state is modified by this probe.
"""
from __future__ import annotations

import argparse
import json
import socket
import urllib.request


def probe(rest_port: int = 5570, rigctl_port: int = 4532) -> None:
    base = f"http://127.0.0.1:{rest_port}"
    for endpoint in ("/v1/health", "/v1/receiver", "/v1/audio"):
        with urllib.request.urlopen(base + endpoint, timeout=3) as response:
            data = json.load(response)
        if not isinstance(data, dict):
            raise ValueError(f"{endpoint} did not return a JSON object")
        if endpoint == "/v1/receiver":
            required = {"frequency_hz", "running", "mode", "bandwidth_hz"}
            if not required.issubset(data):
                raise ValueError(f"missing receiver keys: {required - data.keys()}")
        print(f"PASS REST {endpoint}: {data}")
    with socket.create_connection(("127.0.0.1", rigctl_port), timeout=3) as sock:
        sock.settimeout(3)
        sock.sendall(b"f\\n")
        reply = sock.recv(256).decode("ascii", errors="replace").strip()
        try:
            frequency = int(reply.splitlines()[0])
        except (ValueError, IndexError) as exc:
            raise RuntimeError(f"invalid rigctl frequency response: {reply!r}") from exc
        if frequency <= 0:
            raise ValueError(f"invalid rigctl frequency: {frequency}")
        print(f"PASS rigctl frequency: {frequency} Hz")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rest-port", type=int, default=5570)
    parser.add_argument("--rigctl-port", type=int, default=4532)
    args = parser.parse_args()
    probe(args.rest_port, args.rigctl_port)


if __name__ == "__main__":
    main()
