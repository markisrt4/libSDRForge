"""Hardware-independent frequency scan settings."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ScanConfig:
    start_hz: int = 87_500_000
    stop_hz: int = 108_000_000
    step_hz: int = 100_000
    threshold_db: float = 8.0
    modulation: str = "WFM"

    def __post_init__(self) -> None:
        if self.start_hz <= 0 or self.stop_hz < self.start_hz:
            raise ValueError("invalid frequency range")
        if self.step_hz <= 0:
            raise ValueError("step_hz must be positive")
        if self.modulation not in {"AM", "FM", "NFM", "WFM"}:
            raise ValueError("unsupported modulation")
