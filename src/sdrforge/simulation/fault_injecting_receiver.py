# SPDX-License-Identifier: MIT
"""Deterministic hardware fault injection for receiver integration tests.

This decorator deliberately does not require USB hardware. A simulated disconnect
persists until reconnect(); one-shot operation failures are consumed once.
"""
from __future__ import annotations

from threading import RLock

from sdrforge.interfaces.receiver_control import ReceiverControlIf


class FaultInjectingReceiver:
    def __init__(self, receiver: ReceiverControlIf) -> None:
        self._receiver = receiver
        self._lock = RLock()
        self._connected = True
        self._fail_next: set[str] = set()

    def disconnect(self) -> None:
        with self._lock:
            self._connected = False

    def reconnect(self) -> None:
        with self._lock:
            self._connected = True

    def fail_once(self, operation: str) -> None:
        if operation not in {
            "start", "stop", "set_frequency", "get_frequency",
            "set_mode", "get_mode", "get_signal_strength", "get_snr", "get_rds",
        }:
            raise ValueError(f"unknown operation: {operation}")
        with self._lock:
            self._fail_next.add(operation)

    def _check(self, operation: str) -> None:
        if not self._connected:
            raise RuntimeError("receiver disconnected")
        if operation in self._fail_next:
            self._fail_next.remove(operation)
            raise RuntimeError(f"injected {operation} failure")

    def start(self) -> None:
        with self._lock:
            self._check("start")
            self._receiver.start()

    def stop(self) -> None:
        with self._lock:
            self._check("stop")
            self._receiver.stop()

    def set_frequency(self, hz: int) -> None:
        with self._lock:
            self._check("set_frequency")
            self._receiver.set_frequency(hz)

    def get_frequency(self) -> int:
        with self._lock:
            self._check("get_frequency")
            return self._receiver.get_frequency()

    def set_mode(self, mode: str, bandwidth: int) -> None:
        with self._lock:
            self._check("set_mode")
            self._receiver.set_mode(mode, bandwidth)

    def get_mode(self) -> tuple[str, int]:
        with self._lock:
            self._check("get_mode")
            return self._receiver.get_mode()

    def get_signal_strength(self) -> float | None:
        with self._lock:
            self._check("get_signal_strength")
            return self._receiver.get_signal_strength()

    def get_snr(self) -> float | None:
        with self._lock:
            self._check("get_snr")
            return self._receiver.get_snr()

    def get_rds(self) -> str | None:
        with self._lock:
            self._check("get_rds")
            return self._receiver.get_rds()
