"""Stateful, receiver-independent assembly of NOAA forecast transcript fragments.

Holds the most recent period open until the next period or explicit flush.
Never manufactures dates, temperatures, or severe weather alerts.
"""
from __future__ import annotations

from dataclasses import dataclass

from .forecast import ForecastPeriod, extract_forecasts, _PERIOD


@dataclass(frozen=True)
class AssembledForecast:
    forecast: ForecastPeriod
    transcript: str
    first_segment: int
    last_segment: int


class NoaaForecastAssembler:
    """Accumulate segments and emit completed periods without duplicating them."""

    def __init__(self) -> None:
        self._pending = ""
        self._first_segment: int | None = None
        self._last_segment: int | None = None
        self._next_index = 0

    def feed(self, transcript: str) -> tuple[AssembledForecast, ...]:
        if not isinstance(transcript, str):
            raise TypeError("transcript must be a string")
        index = self._next_index
        self._next_index += 1
        text = " ".join(transcript.split())
        if not text:
            return ()
        # Discard unrelated introductory speech until a forecast period starts.
        if not self._pending:
            match = _PERIOD.search(text.lower())
            if match is None:
                return ()
            text = text[match.start():]
            self._first_segment = index
        self._pending = (self._pending + " " + text).strip()
        self._last_segment = index
        matches = list(_PERIOD.finditer(self._pending.lower()))
        if len(matches) < 2:
            return ()
        # A newly named period closes the preceding one; retain the last period.
        boundary = matches[-1].start()
        completed = self._pending[:boundary].strip()
        self._pending = self._pending[boundary:].strip()
        forecasts = extract_forecasts(completed)
        first = self._first_segment if self._first_segment is not None else index
        self._first_segment = index
        return tuple(
            AssembledForecast(forecast=f, transcript=completed,
                              first_segment=first, last_segment=index)
            for f in forecasts
        )

    def flush(self) -> tuple[AssembledForecast, ...]:
        """Emit any last incomplete period at end-of-recording."""
        pending = self._pending
        first = self._first_segment
        last = self._last_segment
        self._pending = ""
        self._first_segment = None
        self._last_segment = None
        if not pending:
            return ()
        return tuple(
            AssembledForecast(forecast=f, transcript=pending,
                              first_segment=first or 0, last_segment=last or 0)
            for f in extract_forecasts(pending)
        )
