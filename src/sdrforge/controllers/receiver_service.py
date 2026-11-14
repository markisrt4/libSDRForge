# SPDX-License-Identifier: MIT
"""Hardware-independent lifecycle owner for a radio receiver."""
from __future__ import annotations

from enum import Enum
from threading import RLock

from sdrforge.interfaces.receiver_control import ReceiverControlIf


class ReceiverState(str, Enum):
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
        with self._lock:
            return self._state

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def start(self) -> None:
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
        self.stop()
        self.start()

    def set_frequency(self, hz: int) -> None:
        with self._lock:
            self._receiver.set_frequency(hz)

    def get_frequency(self) -> int:
        with self._lock:
            return self._receiver.get_frequency()

    def set_mode(self, mode: str, bandwidth: int) -> None:
        with self._lock:
            self._receiver.set_mode(mode, bandwidth)

    def get_mode(self) -> tuple[str, int]:
        with self._lock:
            return self._receiver.get_mode()

    def get_signal_strength(self) -> float | None:
        with self._lock:
            return self._receiver.get_signal_strength()

    def get_snr(self) -> float | None:
        with self._lock:
            return self._receiver.get_snr()

    def get_rds(self) -> str | None:
        with self._lock:
            return self._receiver.get_rds()
