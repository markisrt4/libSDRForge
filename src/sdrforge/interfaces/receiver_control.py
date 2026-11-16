# SPDX-License-Identifier: MIT
"""Receiver control contract shared by services and transport adapters."""
from __future__ import annotations

from typing import Protocol


class ReceiverControlIf(Protocol):
    """Device-independent radio control surface."""

    def start(self) -> None:
        """Start receiver operation."""
        ...

    def stop(self) -> None:
        """Stop receiver operation."""
        ...

    def set_frequency(self, hz: int) -> None:
        """Tune the receiver to a frequency in hertz."""
        ...

    def get_frequency(self) -> int:
        """Return the tuned frequency in hertz."""
        ...

    def set_mode(self, mode: str, bandwidth: int) -> None:
        """Set the demodulation mode and bandwidth in hertz."""
        ...

    def get_mode(self) -> tuple[str, int]:
        """Return the demodulation mode and bandwidth in hertz."""
        ...

    def get_signal_strength(self) -> float | None:
        """Return the latest signal-strength estimate, when available."""
        ...

    def get_snr(self) -> float | None:
        """Return the latest signal-to-noise estimate, when available."""
        ...

    def get_rds(self) -> str | None:
        """Return the latest Radio Data System text, when available."""
        ...
