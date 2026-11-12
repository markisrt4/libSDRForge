#!/usr/bin/env python3
"""Run a simulated libSDRForge RigCTL receiver for ORC CLI integration tests.

Run: python -m sdrforge.rigctl_simulator --port 4532
No SDR dongle or audio hardware required.
"""
from __future__ import annotations

import argparse
from threading import RLock

from sdrforge.rigctl_server import RigctlServer


class SimulatedReceiver:
    def __init__(self, frequency_hz: int = 104_300_000) -> None:
        self._lock = RLock()
        self._frequency = frequency_hz
        self._mode = "WFM"
        self._bandwidth = 200_000
        self._running = False

    def start(self) -> None:
        with self._lock:
            self._running = True

    def stop(self) -> None:
        with self._lock:
            self._running = False

    def set_frequency(self, hz: int) -> None:
        with self._lock:
            self._frequency = hz

    def get_frequency(self) -> int:
        with self._lock:
            return self._frequency

    def set_mode(self, mode: str, bandwidth: int) -> None:
        with self._lock:
            self._mode, self._bandwidth = mode, bandwidth

    def get_mode(self) -> tuple[str, int]:
        with self._lock:
            return self._mode, self._bandwidth

    def get_signal_strength(self) -> float | None:
        return -35.0 if self._running else None

    def get_snr(self) -> float | None:
        return 22.0 if self._running else None

    def get_rds(self) -> str | None:
        return "SDRFORGE TEST" if self._running and self._mode == "WFM" else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulated libSDRForge RigCTL receiver")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4532)
    parser.add_argument("--frequency", type=int, default=104_300_000)
    args = parser.parse_args()
    if args.frequency <= 0:
        parser.error("frequency must be positive")
    with RigctlServer(SimulatedReceiver(args.frequency), args.host, args.port) as server:
        print(f"RigCTL simulator listening on {server.server_address}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
