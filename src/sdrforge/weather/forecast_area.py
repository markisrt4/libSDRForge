"""Conservative NOAA forecast-area attribution from spoken headers.

Only explicit county names are attributed. A header found at the end of a
forecast applies to the *following* forecast, never retroactively.
"""
from __future__ import annotations

import re

_COUNTY = re.compile(r"\b([a-z]+(?:\s+[a-z]+)?)\s+county\b", re.IGNORECASE)
_HEADER = re.compile(r"\b(?:also\s+)?(?:the\s+)?forecast\s+for\b", re.IGNORECASE)


def _normalize_county(name: str) -> str:
    """Remove a known NOAA transcription artifact, not arbitrary place words."""
    normalized = name.lower().strip()
    return "monroe" if normalized == "leno monroe" else normalized


class ForecastAreaTracker:
    def __init__(self) -> None:
        self._area: str | None = None

    @property
    def area(self) -> str | None:
        return self._area

    def observe_completed(self, transcript: str) -> str | None:
        """Return area for current forecast, then process next-area headers.

        Headers are deliberately not used to label the forecast preceding
        them. Ambiguous headers clear the area instead of guessing.
        """
        current = self._area
        headers = list(_HEADER.finditer(transcript))
        if headers:
            suffix = transcript[headers[-1].end():]
            counties = list(_COUNTY.finditer(suffix))
            # One explicit county is usable; multiple or none are ambiguous.
            self._area = (
                _normalize_county(counties[0].group(1)) + " county"
                if len(counties) == 1 else None
            )
        return current
