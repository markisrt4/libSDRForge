# SPDX-License-Identifier: MIT
"""Hardware-independent lifecycle owner for a radio receiver."""
from __future__ import annotations

from enum import Enum
from threading import RLock

from sdrforge.interfaces.receiver_control import ReceiverControlIf


class ReceiverState(str, Enum):
    """Provide receiver state behavior."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class ReceiverService:
    """Serialize receiver lifecycle transitions across concurrent clients.

    The injected receiver is the sole hardware owner. This service never
    opens a second device and can be exercised with a fake receiver.
    """

    def __init__(self, receiver: ReceiverControlIf) -> None:
        self._receiver = receiver
        self._lock = RLock()
        self._state = ReceiverState.STOPPED
        self._last_error: str | None = None

    @property
    def state(self) -> ReceiverState:
        """Return the state."""
        with self._lock:
            return self._state

    @property
    def last_error(self) -> str | None:
        """Return the last error."""
        with self._lock:
            return self._last_error

    def start(self) -> None:
        """Start the component."""
        with self._lock:
            if self._state == ReceiverState.RUNNING:
                return
            if self._state != ReceiverState.STOPPED:
                raise RuntimeError(f"cannot start receiver in {self._state.value}")
            self._state = ReceiverState.STARTING
            self._last_error = None
            try:
                self._receiver.start()
            except Exception as exc:
                self._state = ReceiverState.ERROR
                self._last_error = str(exc)
                raise
            self._state = ReceiverState.RUNNING

    def stop(self) -> None:
        """Stop the component."""
        with self._lock:
            if self._state == ReceiverState.STOPPED:
                return
            self._state = ReceiverState.STOPPING
            try:
                self._receiver.stop()
            except Exception as exc:
                self._state = ReceiverState.ERROR
                self._last_error = str(exc)
                raise
            self._state = ReceiverState.STOPPED
            self._last_error = None

    def report_disconnect(self, reason: str = "receiver disconnected") -> None:
        """Mark a lost receiver and attempt to release its resources.

        Safe to call from a hardware monitoring thread. A subsequent stop()
        retries cleanup, and only a successful cleanup permits restart.
        """
        with self._lock:
            if self._state == ReceiverState.STOPPED:
                return
            self._state = ReceiverState.ERROR
            self._last_error = reason
            try:
                self._receiver.stop()
            except Exception as exc:
                self._last_error = f"{reason}; cleanup failed: {exc}"
                raise

    def restart(self) -> None:
        """Restart the component."""
        self.stop()
        self.start()

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
