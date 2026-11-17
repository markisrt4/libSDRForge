# SPDX-License-Identifier: MIT
"""!
@brief Serialize receiver commands across concurrent RigCTL clients.

The wrapped receiver implements the ReceiverControl protocol; this manager
does not own SDR hardware or depend on a particular device backend.
"""
from __future__ import annotations

from threading import RLock, Thread

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
        self._starting = False
        self._startup_error: str | None = None
        self._stop_after_start = False

    @property
    def running(self) -> bool:
        """!
        @brief Return the running.

        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            return self._running

    @property
    def starting(self) -> bool:
        with self._lock:
            return self._starting

    @property
    def startup_error(self) -> str | None:
        with self._lock:
            return self._startup_error

    def start_async(self) -> None:
        """Schedule hardware initialization without blocking REST/UI callers."""
        with self._lock:
            if self._running or self._starting:
                return
            self._starting = True
            self._stop_after_start = False
            self._startup_error = None
        Thread(target=self._startup_worker, name="sdrforge-start",
               daemon=True).start()

    def _startup_worker(self) -> None:
        try:
            self._receiver.start()
            with self._lock:
                self._running = True
                if self._stop_after_start:
                    self._receiver.stop()
                    self._running = False
        except Exception as exc:
            with self._lock:
                self._startup_error = str(exc)
        finally:
            with self._lock:
                self._starting = False

    def start(self) -> None:
        """Synchronous start retained for rigctl and existing API clients."""
        with self._lock:
            if not self._running:
                self._receiver.start()
                self._running = True
                self._startup_error = None

    def stop(self) -> None:
        with self._lock:
            if self._starting:
                self._stop_after_start = True
                return
            if self._running:
                self._receiver.stop()
                self._running = False

    def get_rf_configuration(self) -> dict[str, object]:
        with self._lock:
            return self._receiver.get_rf_configuration()

    def set_rf_configuration(self, changes: dict[str, object]) -> None:
        with self._lock:
            if self._running or self._starting:
                raise RuntimeError("stop receiver before changing RF settings")
            self._receiver.set_rf_configuration(changes)

    def set_frequency(self, hz: int) -> None:
        """!
        @brief Set the frequency.

        @param self The current instance.
        @param hz The ``hz`` value.
        """
        with self._lock:
            self._receiver.set_frequency(hz)

    def set_muted(self, muted: bool) -> None:
        """Mute local audio while leaving SDR acquisition running."""
        with self._lock:
            self._receiver.set_muted(muted)

    def get_muted(self) -> bool:
        """Report local audio mute state."""
        with self._lock:
            return self._receiver.get_muted()

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
