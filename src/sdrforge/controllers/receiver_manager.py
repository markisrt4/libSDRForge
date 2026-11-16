# SPDX-License-Identifier: MIT
"""Serialize receiver commands across concurrent RigCTL clients.

The wrapped receiver implements the ReceiverControl protocol; this manager
does not own SDR hardware or depend on a particular device backend.
"""
from __future__ import annotations

from threading import RLock

from sdrforge.interfaces.receiver_control import ReceiverControlIf


class ReceiverManager:
    """Thread-safe facade for one receiver and its lifecycle."""

    def __init__(self, receiver: ReceiverControlIf) -> None:
        self._receiver = receiver
        self._lock = RLock()
        self._running = False

    @property
    def running(self) -> bool:
        """Return the running."""
        with self._lock:
            return self._running

    def start(self) -> None:
        """Start the component."""
        with self._lock:
            if not self._running:
                self._receiver.start()
                self._running = True

    def stop(self) -> None:
        """Stop the component."""
        with self._lock:
            if self._running:
                self._receiver.stop()
                self._running = False

    def set_frequency(self, hz: int) -> None:
        """Set the frequency."""
        with self._lock:
            self._receiver.set_frequency(hz)

    def get_frequency(self) -> int:
        """Return the frequency."""
        with self._lock:
            return self._receiver.get_frequency()

    def set_mode(self, mode: str, bandwidth: int) -> None:
        """Set the mode."""
        with self._lock:
            self._receiver.set_mode(mode, bandwidth)

    def get_mode(self) -> tuple[str, int]:
        """Return the mode."""
        with self._lock:
            return self._receiver.get_mode()

    def get_signal_strength(self) -> float | None:
        """Return the signal strength."""
        with self._lock:
            return self._receiver.get_signal_strength()

    def get_snr(self) -> float | None:
        """Return the snr."""
        with self._lock:
            return self._receiver.get_snr()

    def get_rds(self) -> str | None:
        """Return the rds."""
        with self._lock:
            return self._receiver.get_rds()
