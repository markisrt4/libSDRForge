# SPDX-License-Identifier: MIT
"""!
@brief Hardware-independent lifecycle owner for a radio receiver.
"""
from __future__ import annotations

from enum import Enum
from threading import RLock

from sdrforge.interfaces.receiver_control_if import ReceiverControlIf


class ReceiverState(str, Enum):
    """!
    @brief Provide receiver state behavior.
    """
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class ReceiverService:
    """!
    @brief Serialize receiver lifecycle transitions across concurrent clients.

    The injected receiver is the sole hardware owner. This service never
    opens a second device and can be exercised with a fake receiver.
    """

    def __init__(self, receiver: ReceiverControlIf) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param receiver The ``receiver`` value.
        """
        self._receiver = receiver
        self._lock = RLock()
        self._state = ReceiverState.STOPPED
        self._last_error: str | None = None

    @property
    def state(self) -> ReceiverState:
        """!
        @brief Return the state.

        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            return self._state

    @property
    def last_error(self) -> str | None:
        """!
        @brief Return the last error.

        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            return self._last_error

    def start(self) -> None:
        """!
        @brief Start the component.

        @param self The current instance.
        """
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
        """!
        @brief Stop the component.

        @param self The current instance.
        """
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
        """!
        @brief Mark a lost receiver and attempt to release its resources.

        Safe to call from a hardware monitoring thread. A subsequent stop()
        retries cleanup, and only a successful cleanup permits restart.

        @param self The current instance.
        @param reason The ``reason`` value.
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
        """!
        @brief Restart the component.

        @param self The current instance.
        """
        self.stop()
        self.start()

    def set_frequency(self, hz: int) -> None:
        """!
        @brief Set the frequency.

        @param self The current instance.
        @param hz The ``hz`` value.
        """
        with self._lock:
            self._receiver.set_frequency(hz)

    def get_frequency(self) -> int:
        """!
        @brief Return the frequency.

        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            return self._receiver.get_frequency()

    def set_mode(self, mode: str, bandwidth: int) -> None:
        """!
        @brief Set the mode.

        @param self The current instance.
        @param mode The demodulation mode.
        @param bandwidth The channel bandwidth in hertz.
        """
        with self._lock:
            self._receiver.set_mode(mode, bandwidth)

    def get_mode(self) -> tuple[str, int]:
        """!
        @brief Return the mode.

        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            return self._receiver.get_mode()

    def get_signal_strength(self) -> float | None:
        """!
        @brief Return the signal strength.

        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            return self._receiver.get_signal_strength()

    def get_snr(self) -> float | None:
        """!
        @brief Return the snr.

        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            return self._receiver.get_snr()

    def get_rds(self) -> str | None:
        """!
        @brief Return the rds.

        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            return self._receiver.get_rds()
