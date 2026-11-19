"""Conservative NOAA forecast-area attribution from spoken headers.

Only explicit county names are attributed. A header found at the end of a
forecast applies to the *following* forecast, never retroactively.
"""
from __future__ import annotations

import re

_COUNTY = re.compile(r"\b([a-z]+(?:\s+[a-z]+)?)\s+county\b", re.IGNORECASE)
_BULLETIN = re.compile(r"\\b(?:here is|the following is)\\s+(?:the\\s+)?(?:extended\\s+)?forecast\\s+for\\b", re.IGNORECASE)
_HEADER = re.compile(r"\b(?:also\s+)?(?:the\s+)?forecast\s+for\b", re.IGNORECASE)


def _normalize_county(name: str) -> str:
    """Remove a known NOAA transcription artifact, not arbitrary place words."""
    normalized = name.lower().strip()
    return "monroe" if normalized == "leno monroe" else normalized


class ForecastAreaTracker:
    def __init__(self) -> None:
        self._area: str | None = None
        self._cycle = 0
        self._previous_period: str | None = None
        self._cycle_warning = False
        self._boundary_status = "none"

    @property
    def area(self) -> str | None:
        return self._area

    @property
    def cycle(self) -> int:
        return self._cycle

    @property
    def cycle_warning(self) -> bool:
        return self._cycle_warning

    @property
    def boundary_status(self) -> str:
        return self._boundary_status

    def observe_completed(self, transcript: str, period: str | None = None) -> str | None:
        """Return area for current forecast, then process next-area headers.

        Headers are deliberately not used to label the forecast preceding
        them. Ambiguous headers clear the area instead of guessing.
        """
        self._cycle_warning = False
        self._boundary_status = "none"
        # A return to a broad opening period after a named later period
        # suggests a restarted bulletin. Flag it and discard stale geography.
        # It is not proof of a cycle boundary; preserve that uncertainty.
        opening = {"today", "tonight"}
        if (
            period in opening
            and self._previous_period not in (None, "today", "tonight")
            and self._previous_period not in ("monday", "tuesday", "wednesday",
                                              "thursday", "friday", "saturday", "sunday")
        ):
            self._cycle += 1
            self._area = None
            self._cycle_warning = True
            self._boundary_status = "suspected"
        if period is not None:
            self._previous_period = period
        current = self._area
        # An explicit forecast introduction can start a new area, but when
        # heard after a period it describes the *next* forecast instead.
        headers = list(_HEADER.finditer(transcript))
        explicit = _BULLETIN.search(transcript)
        if explicit and not self._cycle_warning:
            self._boundary_status = "explicit_header"
            self._cycle += 1
        if headers:
            suffix = transcript[headers[-1].end():]
            counties = list(_COUNTY.finditer(suffix))
            # One explicit county is usable; multiple or none are ambiguous.
            self._area = (
                _normalize_county(counties[0].group(1)) + " county"
                if len(counties) == 1 else None
            )
        return current
