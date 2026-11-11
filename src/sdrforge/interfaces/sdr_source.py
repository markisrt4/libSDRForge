# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Interface for hardware-independent software-defined radio IQ sources."""

from abc import ABC, abstractmethod

from sdrforge.models.iq import IqBlock, SdrCapabilities


class SdrSourceIf(ABC):
    """Define tuner control and raw IQ acquisition independent of transport."""

    @abstractmethod
    def open(self) -> None:
        """Open and initialize the SDR source."""

    @abstractmethod
    def close(self) -> None:
        """Stop acquisition and release resources owned by the SDR source."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return whether the SDR source is initialized and available."""

    @abstractmethod
    def get_capabilities(self) -> SdrCapabilities:
        """Return tuning and sampling capabilities for the source."""

    @abstractmethod
    def set_center_frequency(self, frequency_hz: int) -> None:
        """Set the RF center frequency in hertz."""

    @abstractmethod
    def get_center_frequency(self) -> int:
        """Return the configured RF center frequency in hertz."""

    @abstractmethod
    def set_sample_rate(self, sample_rate_hz: int) -> None:
        """Set the IQ sample rate in samples per second."""

    @abstractmethod
    def get_sample_rate(self) -> int:
        """Return the configured IQ sample rate in samples per second."""

    @abstractmethod
    def set_gain(self, gain_db: float | None) -> None:
        """Set tuner gain in decibels, or use automatic gain when None."""

    @abstractmethod
    def start(self) -> None:
        """Start IQ acquisition."""

    @abstractmethod
    def stop(self) -> None:
        """Stop IQ acquisition without closing the source."""

    @abstractmethod
    def read_iq(self) -> IqBlock:
        """Block until the next IQ block is available or acquisition stops."""
