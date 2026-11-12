# SPDX-License-Identifier: MIT
"""Hardware-free receiver simulation for development and testing."""
from __future__ import annotations

from threading import RLock


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


