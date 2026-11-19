"""!
@brief Hardware-neutral interface for measuring a tuned frequency.
"""
from typing import Protocol


class SignalScannerIf(Protocol):
    """!
    @brief Provide signal scanner if behavior.
    """
    def measure(self, frequency_hz: int, modulation: str) -> tuple[float, float]:
        """!
        @brief Return signal level and noise floor in comparable dB units.

        @param self The current instance.
        @param frequency_hz The frequency in hertz.
        @param modulation The ``modulation`` value.
        @return The operation result.
        """
        ...
