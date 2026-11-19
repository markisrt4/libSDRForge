"""!
@brief Immutable weather information extracted from received RF audio.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WeatherObservation:
    """!
    @brief Provide WeatherObservation behavior.
    """
    source_frequency_hz: int
    transcript: str
    temperature_f: int | None = None
    wind_direction: str | None = None
    wind_mph: int | None = None
    relative_humidity_percent: int | None = None
    observed_at: str | None = None
    location: str | None = None

@dataclass(frozen=True)
class SameAlert:
    """!
    @brief Provide SameAlert behavior.
    """
    originator: str
    event: str
    location_codes: tuple[str, ...]
    duration: str
    issued_julian: str
    sender: str
    raw_header: str
