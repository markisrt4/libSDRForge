"""Hardware-neutral interface for measuring a tuned frequency."""
from typing import Protocol


class SignalScannerIf(Protocol):
    """Provide signal scanner if behavior."""
    def measure(self, frequency_hz: int, modulation: str) -> tuple[float, float]:
        """Return signal level and noise floor in comparable dB units."""
        ...
