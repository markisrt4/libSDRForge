# SPDX-License-Identifier: MIT
"""!
@brief Serialize receiver commands across concurrent RigCTL clients.

The wrapped receiver implements the ReceiverControl protocol; this manager
does not own SDR hardware or depend on a particular device backend.
"""

from __future__ import annotations

import time
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
        self._startup_started_at: float | None = None
        self._startup_duration_ms: float | None = None

    @property
    def running(self) -> bool:
        """!
        @brief Return the running.

        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            if self._running:
                worker_alive = getattr(self._receiver, "worker_alive", None)
                if worker_alive is False:
                    self._running = False
                    self._startup_error = getattr(self._receiver, "worker_error", None)
            return self._running

    @property
    def starting(self) -> bool:
        """!
        @brief Whether receiver startup is in progress.
        @param self The receiver manager.
        @return Startup state.
        """
        with self._lock:
            return self._starting

    @property
    def startup_duration_ms(self) -> float | None:
        """!
        @brief Last startup duration in milliseconds.
        @param self The receiver manager.
        @return Elapsed startup duration or None.
        """
        with self._lock:
            return self._startup_duration_ms

    @property
    def startup_elapsed_ms(self) -> float | None:
        """!
        @brief Elapsed time for the current startup.
        @param self The receiver manager.
        @return Elapsed startup time or None.
        """
        with self._lock:
            if not self._starting or self._startup_started_at is None:
                return None
            return round((time.monotonic() - self._startup_started_at) * 1000, 1)

    @property
    def startup_error(self) -> str | None:
        """!
        @brief Most recent startup error.
        @param self The receiver manager.
        @return Error text or None.
        """
        with self._lock:
            return self._startup_error

    def start_async(self) -> None:
        """!
        @brief Start the receiver in a background thread.
        @param self The receiver manager.
        """
        _ = self.running  # Reconcile an unexpectedly exited acquisition worker.
        with self._lock:
            if self._running or self._starting:
                return
            self._starting = True
            self._startup_started_at = time.monotonic()
            self._startup_duration_ms = None
            self._stop_after_start = False
            self._startup_error = None
        Thread(target=self._startup_worker, name="sdrforge-start", daemon=True).start()

    def _startup_worker(self) -> None:
        try:
            self._receiver.start()
            with self._lock:
                self._running = True
                if self._stop_after_start:
                    self._receiver.stop()
                    self._running = False
        except Exception as exc:  # noqa: BLE001 - isolate asynchronous receiver startup failures
            with self._lock:
                self._startup_error = str(exc)
        finally:
            with self._lock:
                if self._startup_started_at is not None:
                    self._startup_duration_ms = round(
                        (time.monotonic() - self._startup_started_at) * 1000, 1
                    )
                self._starting = False

    def start(self) -> None:
        """!
        @brief Start the receiver synchronously.
        @param self The receiver manager.
        """
        _ = self.running  # Reconcile an unexpectedly exited acquisition worker.
        with self._lock:
            if not self._running:
                self._receiver.start()
                self._running = True
                self._startup_error = None

    def stop(self) -> None:
        """!
        @brief Stop the receiver or defer stopping until startup finishes.
        @param self The receiver manager.
        """
        with self._lock:
            if self._starting:
                self._stop_after_start = True
                return
            if self._running:
                self._receiver.stop()
                self._running = False

    def get_rf_configuration(self) -> dict[str, object]:
        """!
        @brief Read current RF configuration.
        @param self The receiver manager.
        @return RF configuration values.
        """
        with self._lock:
            return self._receiver.get_rf_configuration()

    def set_rf_configuration(self, changes: dict[str, object]) -> None:
        """!
        @brief Apply RF configuration while stopped.
        @param self The receiver manager.
        @param changes Requested RF settings.
        """
        with self._lock:
            if self._running or self._starting:
                raise RuntimeError("stop receiver before changing RF settings")
            self._receiver.set_rf_configuration(changes)

    def pan_acquisition(self, center_hz: int) -> None:
        """!
        @brief Request an acquisition center change.
        @param self The current instance.
        @param center_hz Requested RF center in hertz.
        """
        with self._lock:
            callback = getattr(self._receiver, "pan_acquisition", None)
            if not callable(callback):
                raise RuntimeError("acquisition pan is not supported")  # noqa: TRY004
            callback(center_hz)

    def recenter(self) -> None:
        """!
        @brief Request acquisition recenter when supported by the backend.
        @param self The current instance.
        """
        with self._lock:
            callback = getattr(self._receiver, "recenter", None)
            if not callable(callback):
                raise RuntimeError("acquisition recenter is not supported")  # noqa: TRY004
            callback()

    def set_frequency(self, hz: int) -> None:
        """!
        @brief Set the frequency.

        @param self The current instance.
        @param hz The ``hz`` value.
        """
        with self._lock:
            self._receiver.set_frequency(hz)

    def set_muted(self, muted: bool) -> None:
        """!
        @brief Set local audio mute.
        @param self The receiver manager.
        @param muted Mute state.
        """
        with self._lock:
            self._receiver.set_muted(muted)

    def get_audio_diagnostics(self) -> dict[str, object]:
        """!
        @brief Return optional playback diagnostics from the receiver adapter.
        @param self The current instance.
        @return Available playback diagnostics.
        """
        with self._lock:
            getter = getattr(self._receiver, "get_audio_diagnostics", None)
            return getter() if callable(getter) else {}

    def get_muted(self) -> bool:
        """!
        @brief Read local audio mute state.
        @param self The receiver manager.
        @return True if muted.
        """
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

    def get_rds_status(self) -> dict[str, object] | None:
        """!
        @brief Return optional structured RDS telemetry without changing rigctl.
        @param self The receiver manager.
        @return Structured RDS status when the receiver provides it.
        """
        with self._lock:
            getter = getattr(self._receiver, "get_rds_status", None)
            return getter() if callable(getter) else None

    def get_rds(self) -> str | None:
        """!
        @brief Return the rds.

        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            return self._receiver.get_rds()
