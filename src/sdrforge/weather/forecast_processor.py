"""!
@brief Convert receiver-independent NOAA transcripts into forecast events.
"""
from __future__ import annotations

from dataclasses import asdict

from .forecast_area import ForecastAreaTracker
from .forecast_assembler import AssembledForecast, NoaaForecastAssembler
from .forecast_deduplicator import NoaaForecastDeduplicator


class NoaaForecastProcessor:
    """!
    @brief Assemble, deduplicate, and publish NOAA forecast events.
    """

    def __init__(self, *, frequency_hz: int | None = None) -> None:
        """!
        @brief Initialize independent forecast state.
        @param self The processor instance.
        @param frequency_hz Optional source frequency in hertz.
        """
        self._assembler = NoaaForecastAssembler()
        self._areas = ForecastAreaTracker()
        self._dedup = NoaaForecastDeduplicator()
        self._frequency_hz = frequency_hz

    def feed(self, transcript: str, *, frequency_hz: int | None = None) -> tuple[dict[str, object], ...]:
        """!
        @brief Consume a transcript segment and emit completed forecasts.
        @param self The processor instance.
        @param transcript Transcript text to consume.
        @param frequency_hz Optional source frequency override.
        @return Completed forecast event dictionaries.
        """
        if frequency_hz is not None:
            self._frequency_hz = frequency_hz
        return self._events(self._assembler.feed(transcript))

    def flush(self) -> tuple[dict[str, object], ...]:
        """!
        @brief Flush any pending assembled forecast.
        @param self The processor instance.
        @return Completed forecast event dictionaries.
        """
        return self._events(self._assembler.flush())

    def _events(self, completed_forecasts: tuple[AssembledForecast, ...]) -> tuple[dict[str, object], ...]:
        events = []
        for completed in completed_forecasts:
            area = self._areas.observe_completed(
                completed.transcript, completed.forecast.period
            )
            dedup = self._dedup.observe(
                completed.forecast,
                cycle=self._areas.cycle,
                areas=self._areas.observed_areas,
            )
            if dedup.status == "duplicate":
                continue
            events.append({
                "event": "noaa_forecast_completed",
                "forecast_area": area,
                "forecast_areas": list(self._areas.observed_areas),
                "source_frequency_hz": self._frequency_hz,
                "forecast_cycle": self._areas.cycle,
                "cycle_boundary_suspected": self._areas.cycle_warning,
                "boundary_evidence": self._areas.boundary_status,
                "deduplication_status": dedup.status,
                "forecast_revision": dedup.revision,
                "completed_forecast": asdict(completed),
            })
        return tuple(events)
