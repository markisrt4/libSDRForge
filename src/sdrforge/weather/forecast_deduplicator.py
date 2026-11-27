"""!
@brief Deduplicate structured NOAA forecasts without guessing geography.

Unknown geography is never deduplicated: two unidentified broadcasts may
describe different places. Changed forecasts are emitted as revisions.
"""

from __future__ import annotations

from dataclasses import dataclass

from .forecast import ForecastPeriod


@dataclass(frozen=True)
class DeduplicationResult:
    """!
    @brief Report whether a forecast is new, duplicate, or revised.
    """

    status: str
    revision: int


class NoaaForecastDeduplicator:
    """!
    @brief Track the latest forecast for each cycle, county group and period.
    """

    def __init__(self) -> None:
        """!
        @brief Initialize forecast revision history.
        @param self The deduplicator instance.
        """
        self._seen: dict[
            tuple[int, tuple[str, ...], str], tuple[ForecastPeriod, int]
        ] = {}

    def observe(
        self,
        forecast: ForecastPeriod,
        *,
        cycle: int,
        areas: tuple[str, ...],
    ) -> DeduplicationResult:
        """!
        @brief Classify a forecast and update its revision history.
        @param self The deduplicator instance.
        @param forecast Structured forecast to classify.
        @param cycle Current forecast bulletin cycle.
        @param areas Explicitly identified county areas.
        @return Classification and revision number.


        A duplicate has the same structured forecast as the last version for
        that key. Raw transcripts can differ without changing forecast data.
        """
        if not areas:
            return DeduplicationResult("unscoped", 1)
        key = (cycle, tuple(sorted(set(areas))), forecast.period)
        previous = self._seen.get(key)
        if previous is None:
            self._seen[key] = (forecast, 1)
            return DeduplicationResult("new", 1)
        old_forecast, revision = previous
        if old_forecast == forecast:
            return DeduplicationResult("duplicate", revision)
        revision += 1
        self._seen[key] = (forecast, revision)
        return DeduplicationResult("revised", revision)
