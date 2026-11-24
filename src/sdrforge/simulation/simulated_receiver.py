# SPDX-License-Identifier: MIT
"""!
@brief Hardware-free receiver simulation for development and testing.
"""

from __future__ import annotations

from threading import RLock


class SimulatedReceiver:
    """!
    @brief Provide simulated receiver behavior.
    """

    def __init__(self, frequency_hz: int = 104_300_000) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param frequency_hz The ``frequency_hz`` value.
        """
        self._lock = RLock()
        self._frequency = frequency_hz
        self._mode = "WFM"
        self._bandwidth = 200_000
        self._running = False
        self._muted = False

    def start(self) -> None:
        """!
        @brief Start the component.

        @param self The current instance.
        """
        with self._lock:
            self._running = True

    def stop(self) -> None:
        """!
        @brief Stop the component.

        @param self The current instance.
        """
        with self._lock:
            self._running = False

    def set_frequency(self, hz: int) -> None:
        """!
        @brief Set the frequency.

        @param self The current instance.
        @param hz The ``hz`` value.
        """
        with self._lock:
            self._frequency = hz

    def get_frequency(self) -> int:
        """!
        @brief Return the frequency.

        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            return self._frequency

    def set_mode(self, mode: str, bandwidth: int) -> None:
        """!
        @brief Set the mode.

        @param self The current instance.
        @param mode The demodulation mode.
        @param bandwidth The channel bandwidth in hertz.
        """
        with self._lock:
            self._mode, self._bandwidth = mode, bandwidth

    def get_mode(self) -> tuple[str, int]:
        """!
        @brief Return the mode.

        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            return self._mode, self._bandwidth

    def get_signal_strength(self) -> float | None:
        """!
        @brief Return the signal strength.

        @param self The current instance.
        @return The operation result.
        """
        return -35.0 if self._running else None

    def get_snr(self) -> float | None:
        """!
        @brief Return the snr.

        @param self The current instance.
        @return The operation result.
        """
        return 22.0 if self._running else None

    def get_rds(self) -> str | None:
        """!
        @brief Return the rds.

        @param self The current instance.
        @return The operation result.
        """
        return "SDRFORGE TEST" if self._running and self._mode == "WFM" else None

    def get_rf_configuration(self) -> dict[str, object]:
        """! @brief Return simulated RF configuration. @param self The current instance. @return RF settings."""
        return {}

    def set_rf_configuration(self, changes: dict[str, object]) -> None:
        """! @brief Reject unsupported simulated RF settings. @param self The current instance. @param changes Requested settings."""
        if changes:
            raise ValueError("simulated receiver has no RF configuration")

    def set_muted(self, muted: bool) -> None:
        """! @brief Set simulated audio mute. @param self The current instance. @param muted Mute state."""
        self._muted = muted

    def get_muted(self) -> bool:
        """! @brief Return simulated audio mute. @param self The current instance. @return Mute state."""
        return self._muted
