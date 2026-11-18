"""!
@brief Deterministic RF measurements for hardware-free scan tests.
"""
from collections.abc import Mapping


class SimulatedSignalScanner:
    """!
    @brief Provide simulated signal scanner behavior.
    """
    def __init__(
        self, stations: Mapping[int, float], *,
        noise_floor_db: float = -90.0,
    ) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param stations The ``stations`` value.
        @param noise_floor_db The ``noise_floor_db`` value.
        """
        self.stations = dict(stations)
        self.noise_floor_db = noise_floor_db

    def measure(self, frequency_hz: int, modulation: str) -> tuple[float, float]:
        """!
        @brief Measure the component.

        @param self The current instance.
        @param frequency_hz The frequency in hertz.
        @param modulation The ``modulation`` value.
        @return The operation result.
        """
        return self.stations.get(frequency_hz, self.noise_floor_db), self.noise_floor_db
