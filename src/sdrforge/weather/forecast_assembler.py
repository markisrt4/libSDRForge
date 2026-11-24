"""!
@brief Stateful, receiver-independent assembly of NOAA forecast transcript fragments.
"""

from __future__ import annotations

from dataclasses import dataclass

from .forecast import ForecastPeriod, extract_forecasts, period_matches


@dataclass(frozen=True)
class AssembledForecast:
    """!
    @brief Provide AssembledForecast behavior.
    """

    forecast: ForecastPeriod
    transcript: str
    first_segment: int
    last_segment: int


class NoaaForecastAssembler:
    """!
    @brief Accumulate segments and emit completed periods without duplicating them.
    """

    def __init__(self) -> None:
        """!
        @brief Provide   init   behavior.
        @param self The current instance.
        """
        self._pending = ""
        self._first_segment: int | None = None
        self._last_segment: int | None = None
        self._next_index = 0

    def feed(self, transcript: str) -> tuple[AssembledForecast, ...]:
        """!
        @brief Provide feed behavior.
        @param self The current instance.
        @param transcript The transcript value.
        @return The operation result.
        """
        if not isinstance(transcript, str):
            raise TypeError("transcript must be a string")
        index = self._next_index
        self._next_index += 1
        text = " ".join(transcript.split())
        if not text:
            return ()
        # Discard unrelated introductory speech until a forecast period starts.
        if not self._pending:
            match = next(iter(period_matches(text.lower())), None)
            if match is None:
                return ()
            text = text[match.start() :]
            self._first_segment = index
        self._pending = (self._pending + " " + text).strip()
        self._last_segment = index
        matches = period_matches(self._pending.lower())
        if len(matches) < 2:
            return ()
        # Emit every completed period, even when several occur in one segment.
        completed: list[AssembledForecast] = []
        first = self._first_segment if self._first_segment is not None else index
        for i, match in enumerate(matches[:-1]):
            fragment = self._pending[match.start() : matches[i + 1].start()].strip()
            for forecast in extract_forecasts(
                fragment, allow_sunday_alias=fragment.startswith("so night")
            ):
                completed.append(
                    AssembledForecast(
                        forecast=forecast,
                        transcript=fragment,
                        first_segment=first if i == 0 else index,
                        last_segment=index,
                    )
                )
        self._pending = self._pending[matches[-1].start() :].strip()
        self._first_segment = index
        return tuple(completed)

    def flush(self) -> tuple[AssembledForecast, ...]:
        """!
        @brief Emit any last incomplete period at end-of-recording.
        @param self The current instance.
        @return The operation result.
        """
        pending = self._pending
        first = self._first_segment
        last = self._last_segment
        self._pending = ""
        self._first_segment = None
        self._last_segment = None
        if not pending:
            return ()
        return tuple(
            AssembledForecast(
                forecast=f,
                transcript=pending,
                first_segment=first or 0,
                last_segment=last or 0,
            )
            for f in extract_forecasts(
                pending, allow_sunday_alias=pending.startswith("so night")
            )
        )
