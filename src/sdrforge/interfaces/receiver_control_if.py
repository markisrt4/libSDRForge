# SPDX-License-Identifier: MIT
"""!
@brief Receiver control contract shared by services and transport adapters.
"""

from __future__ import annotations

from typing import Protocol


class ReceiverControlIf(Protocol):
    """!
    @brief Device-independent radio control surface.
    """

    def start(self) -> None:
        """!
        @brief Start receiver operation.

        @param self The current instance.
        """
        ...

    def stop(self) -> None:
        """!
        @brief Stop receiver operation.

        @param self The current instance.
        """
        ...

    def set_frequency(self, hz: int) -> None:
        """!
        @brief Tune the receiver to a frequency in hertz.

        @param self The current instance.
        @param hz The ``hz`` value.
        """
        ...

    def get_frequency(self) -> int:
        """!
        @brief Return the tuned frequency in hertz.

        @param self The current instance.
        @return The operation result.
        """
        ...

    def set_mode(self, mode: str, bandwidth: int) -> None:
        """!
        @brief Set the demodulation mode and bandwidth in hertz.

        @param self The current instance.
        @param mode The demodulation mode.
        @param bandwidth The channel bandwidth in hertz.
        """
        ...

    def get_mode(self) -> tuple[str, int]:
        """!
        @brief Return the demodulation mode and bandwidth in hertz.

        @param self The current instance.
        @return The operation result.
        """
        ...

    def get_signal_strength(self) -> float | None:
        """!
        @brief Return the latest signal-strength estimate, when available.

        @param self The current instance.
        @return The operation result.
        """
        ...

    def get_snr(self) -> float | None:
        """!
        @brief Return the latest signal-to-noise estimate, when available.

        @param self The current instance.
        @return The operation result.
        """
        ...

    def get_rds(self) -> str | None:
        """!
        @brief Return the latest Radio Data System text, when available.

        @param self The current instance.
        @return The operation result.
        """
        ...

    def get_rf_configuration(self) -> dict[str, object]:
        """!
        @brief Return the receiver's current RF hardware configuration.

        @param self The current instance.
        @return A dictionary of RF configuration values.
        """
        ...

    def set_rf_configuration(self, changes: dict[str, object]) -> None:
        """!
        @brief Apply RF hardware configuration changes.

        @param self The current instance.
        @param changes Requested RF configuration values.
        """
        ...

    def set_muted(self, muted: bool) -> None:
        """!
        @brief Set local audio mute without stopping RF acquisition.

        @param self The current instance.
        @param muted Whether local audio should be muted.
        """
        ...

    def get_muted(self) -> bool:
        """!
        @brief Return whether local audio is muted.

        @param self The current instance.
        @return True when local audio is muted.
        """
        ...
