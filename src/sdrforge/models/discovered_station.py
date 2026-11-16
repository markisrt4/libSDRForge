"""A candidate station discovered by scanning, not a saved preset."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveredStation:
    """Provide discovered station behavior."""
    frequency_hz: int
    modulation: str
    signal_db: float
    noise_floor_db: float

    @property
    def margin_db(self) -> float:
        """Return the margin db."""
        return self.signal_db - self.noise_floor_db
