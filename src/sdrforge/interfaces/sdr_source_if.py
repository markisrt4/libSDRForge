# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""!
@brief Interface for hardware-independent software-defined radio IQ sources.
"""

from abc import ABC, abstractmethod

from sdrforge.models.iq import IqBlock, SdrCapabilities


class SdrSourceIf(ABC):
    """!
    @brief Define tuner control and raw IQ acquisition independent of transport.
    """

    @abstractmethod
    def open(self) -> None:
        """!
        @brief Open and initialize the SDR source.

        @param self The current instance.
        """

    @abstractmethod
    def close(self) -> None:
        """!
        @brief Stop acquisition and release resources owned by the SDR source.

        @param self The current instance.
        """

    @abstractmethod
    def is_connected(self) -> bool:
        """!
        @brief Return whether the SDR source is initialized and available.

        @param self The current instance.
        @return The operation result.
        """

    @abstractmethod
    def get_capabilities(self) -> SdrCapabilities:
        """!
        @brief Return tuning and sampling capabilities for the source.

        @param self The current instance.
        @return The operation result.
        """

    @abstractmethod
    def set_center_frequency(self, frequency_hz: int) -> None:
        """!
        @brief Set the RF center frequency in hertz.

        @param self The current instance.
        @param frequency_hz The frequency in hertz.
        """

    @abstractmethod
    def get_center_frequency(self) -> int:
        """!
        @brief Return the configured RF center frequency in hertz.

        @param self The current instance.
        @return The operation result.
        """

    @abstractmethod
    def set_sample_rate(self, sample_rate_hz: int) -> None:
        """!
        @brief Set the IQ sample rate in samples per second.

        @param self The current instance.
        @param sample_rate_hz The sample rate in hertz.
        """

    @abstractmethod
    def get_sample_rate(self) -> int:
        """!
        @brief Return the configured IQ sample rate in samples per second.

        @param self The current instance.
        @return The operation result.
        """

    @abstractmethod
    def set_gain(self, gain_db: float | None) -> None:
        """!
        @brief Set tuner gain in decibels, or use automatic gain when None.

        @param self The current instance.
        @param gain_db The tuner gain in decibels, or ``None`` for automatic gain.
        """

    @abstractmethod
    def start(self) -> None:
        """!
        @brief Start IQ acquisition.

        @param self The current instance.
        """

    @abstractmethod
    def stop(self) -> None:
        """!
        @brief Stop IQ acquisition without closing the source.

        @param self The current instance.
        """

    @abstractmethod
    def read_iq(self) -> IqBlock:
        """!
        @brief Block until the next IQ block is available or acquisition stops.

        @param self The current instance.
        @return The operation result.
        """
