"""Deterministic RF measurements for hardware-free scan tests."""
from collections.abc import Mapping


class SimulatedSignalScanner:
    """Provide simulated signal scanner behavior."""
    def __init__(
        self, stations: Mapping[int, float], *,
        noise_floor_db: float = -90.0,
    ) -> None:
        self.stations = dict(stations)
        self.noise_floor_db = noise_floor_db

    def measure(self, frequency_hz: int, modulation: str) -> tuple[float, float]:
        """Measure the component."""
        return self.stations.get(frequency_hz, self.noise_floor_db), self.noise_floor_db
