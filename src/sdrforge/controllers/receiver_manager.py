# SPDX-License-Identifier: MIT
"""!
@brief Serialize receiver commands across concurrent RigCTL clients.

The wrapped receiver implements the ReceiverControl protocol; this manager
does not own SDR hardware or depend on a particular device backend.
"""

from __future__ import annotations

import hmac
import time
from threading import RLock, Thread

from sdrforge.interfaces.receiver_control_if import ReceiverControlIf


class ReceiverManager:
    """!
    @brief Thread-safe facade for one receiver and its lifecycle.
    """

    def __init__(
        self, receiver: ReceiverControlIf, *, acquisition_token: str | None = None
    ) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param receiver The ``receiver`` value.
        @param acquisition_token Optional managed acquisition credential.
        """
        if acquisition_token == "":
            raise ValueError("acquisition token must not be empty")
        self._acquisition_token = acquisition_token
        self._receiver = receiver
        self._lock = RLock()
        self._running = False
        self._closed = False
        self._starting = False
        self._startup_thread: Thread | None = None
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

    def authorize_acquisition(self, token: str | None) -> None:
        """!
        @brief Verify permission to change managed receiver state.
        @param self The receiver manager.
        @param token Managed acquisition credential.
        @exception PermissionError The credential is missing or invalid.
        """
        expected = self._acquisition_token
        if expected is not None and (
            token is None or not hmac.compare_digest(token.encode(), expected.encode())
        ):
            raise PermissionError("Managed acquisition requires authorization")

    def start_async(self, *, token: str | None = None) -> None:
        """!
        @brief Start the receiver in a background thread.
        @param self The receiver manager.
        @param token Managed acquisition credential.
        """
        self.authorize_acquisition(token)
        with self._lock:
            if self._closed:
                raise RuntimeError("receiver manager is closed")
            _ = self.running  # Reconcile an unexpectedly exited acquisition worker.
            if self._running or self._starting:
                return
            self._starting = True
            self._startup_started_at = time.monotonic()
            self._startup_duration_ms = None
            self._stop_after_start = False
            self._startup_error = None
            worker = Thread(
                target=self._startup_worker, name="sdrforge-start", daemon=True
            )
            try:
                worker.start()
            except RuntimeError:
                self._starting = False
                raise
            self._startup_thread = worker

    def _startup_worker(self) -> None:
        error = None
        try:
            self._start_backend()
        except Exception as exc:  # noqa: BLE001 - isolate asynchronous startup failures
            error = str(exc)
        with self._lock:
            self._running = error is None
            try:
                if self._running and self._stop_after_start:
                    self._receiver.stop()
                    self._running = False
            except Exception as exc:  # noqa: BLE001 - preserve deferred stop failure
                error = str(exc)
            finally:
                self._startup_error = error
                if self._startup_started_at is not None:
                    self._startup_duration_ms = round(
                        (time.monotonic() - self._startup_started_at) * 1000, 1
                    )
                self._starting = False

    def _start_backend(self) -> None:
        try:
            self._receiver.start()
        except Exception:
            try:
                self._receiver.stop()
            except Exception as exc:
                raise RuntimeError(f"Receiver startup cleanup failed: {exc}") from exc
            raise

    def start(self, *, token: str | None = None) -> None:
        """!
        @brief Start the receiver synchronously.
        @param self The receiver manager.
        @param token Managed acquisition credential.
        """
        self.authorize_acquisition(token)
        with self._lock:
            if self._closed:
                raise RuntimeError("receiver manager is closed")
            _ = self.running  # Reconcile an unexpectedly exited acquisition worker.
            if not self._running and not self._starting:
                self._start_backend()
                self._running = True
                self._startup_error = None

    def stop(self, *, token: str | None = None) -> None:
        """!
        @brief Stop the receiver or defer stopping until startup finishes.
        @param self The receiver manager.
        @param token Managed acquisition credential.
        """
        self.authorize_acquisition(token)
        self._stop()

    def close(self) -> None:
        """!
        @brief Clean up acquisition during trusted process teardown.
        @param self The receiver manager.
        """
        with self._lock:
            self._closed = True
            self._stop_after_start = True
            worker = self._startup_thread
        if worker is not None:
            worker.join()
        self._stop()

    def _stop(self) -> None:
        with self._lock:
            if self._starting:
                self._stop_after_start = True
                return
            if self._running or self.get_release_status()["hardware_released"] is False:
                self._receiver.stop()
                self._running = False

    def get_release_status(self) -> dict[str, object]:
        """! @brief Report backend hardware release evidence when supported.
        @param self The receiver manager.
        @return Release confirmation and error details.
        """
        with self._lock:
            if self._starting:
                return {"hardware_released": False, "release_error": None}
            getter = getattr(self._receiver, "get_release_status", None)
            if callable(getter):
                return getter()
            return {"hardware_released": None, "release_error": None}

    def get_rf_configuration(self) -> dict[str, object]:
        """!
        @brief Read current RF configuration.
        @param self The receiver manager.
        @return RF configuration values.
        """
        with self._lock:
            return self._receiver.get_rf_configuration()

    def set_rf_configuration(
        self, changes: dict[str, object], *, token: str | None = None
    ) -> None:
        """!
        @brief Apply RF configuration while stopped.
        @param self The receiver manager.
        @param changes Requested RF settings.
        @param token Managed acquisition credential.
        """
        self.authorize_acquisition(token)
        with self._lock:
            if self._running or self._starting:
                raise RuntimeError("stop receiver before changing RF settings")
            self._receiver.set_rf_configuration(changes)

    def pan_acquisition(self, center_hz: int, *, token: str | None = None) -> None:
        """!
        @brief Request an acquisition center change.
        @param self The current instance.
        @param center_hz Requested RF center in hertz.
        @param token Managed acquisition credential.
        """
        self.authorize_acquisition(token)
        with self._lock:
            if self._starting:
                raise RuntimeError("receiver startup is in progress")
            callback = getattr(self._receiver, "pan_acquisition", None)
            if not callable(callback):
                raise RuntimeError("acquisition pan is not supported")  # noqa: TRY004
            callback(center_hz)

    def recenter(self, *, token: str | None = None) -> None:
        """!
        @brief Request acquisition recenter when supported by the backend.
        @param self The current instance.
        @param token Managed acquisition credential.
        """
        self.authorize_acquisition(token)
        with self._lock:
            if self._starting:
                raise RuntimeError("receiver startup is in progress")
            callback = getattr(self._receiver, "recenter", None)
            if not callable(callback):
                raise RuntimeError("acquisition recenter is not supported")  # noqa: TRY004
            callback()

    def set_frequency(self, hz: int, *, token: str | None = None) -> None:
        """!
        @brief Set the frequency.

        @param self The current instance.
        @param hz The ``hz`` value.
        @param token Managed acquisition credential.
        """
        self.authorize_acquisition(token)
        with self._lock:
            if self._starting:
                raise RuntimeError("receiver startup is in progress")
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

    def set_mode(self, mode: str, bandwidth: int, *, token: str | None = None) -> None:
        """!
        @brief Set the mode.

        @param self The current instance.
        @param mode The demodulation mode.
        @param bandwidth The channel bandwidth in hertz.
        @param token Managed acquisition credential.
        """
        self.authorize_acquisition(token)
        with self._lock:
            if self._starting:
                raise RuntimeError("receiver startup is in progress")
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
