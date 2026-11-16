# SPDX-License-Identifier: MIT
"""!
@brief Serialize receiver commands across concurrent RigCTL clients.

The wrapped receiver implements the ReceiverControl protocol; this manager
does not own SDR hardware or depend on a particular device backend.
"""
from __future__ import annotations

from threading import RLock

from sdrforge.interfaces.receiver_control_if import ReceiverControlIf


class ReceiverManager:
    """!
    @brief Thread-safe facade for one receiver and its lifecycle.
    """

    def __init__(self, receiver: ReceiverControlIf) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param receiver The ``receiver`` value.
        """
        self._receiver = receiver
        self._lock = RLock()
        self._running = False

    @property
    def running(self) -> bool:
        """!
        @brief Return the running.

        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            return self._running

    def start(self) -> None:
        """!
        @brief Start the component.

        @param self The current instance.
        """
        with self._lock:
            if not self._running:
                self._receiver.start()
                self._running = True

    def stop(self) -> None:
        """!
        @brief Stop the component.

        @param self The current instance.
        """
        with self._lock:
            if self._running:
                self._receiver.stop()
                self._running = False

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
