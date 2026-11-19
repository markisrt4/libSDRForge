"""!\n@brief Conservatively attribute NOAA forecasts to spoken county headers.

Only explicit county names are attributed. A header found at the end of a
forecast applies to the *following* forecast, never retroactively.
"""
from __future__ import annotations

import re
from itertools import pairwise

_COUNTY = re.compile(r"\b([a-z]+(?:\s+[a-z]+)?)\s+county\b", re.IGNORECASE)
_BULLETIN = re.compile(r"\b(?:here is|the following is)\s+(?:the\s+)?(?:extended\s+)?forecast\s+for\b", re.IGNORECASE)
_HEADER = re.compile(r"\b(?:also\s+)?(?:the\s+)?forecast\s+for\b", re.IGNORECASE)


def _normalize_county(name: str) -> str:
    """Remove a known NOAA transcription artifact, not arbitrary place words."""
    normalized = name.lower().strip()
    normalized = re.sub(r"^(?:and|or)\s+", "", normalized)
    return "monroe" if normalized == "leno monroe" else normalized


class ForecastAreaTracker:
    """!\n    @brief Track explicit forecast areas and suspected bulletin cycles.\n    """\n    def __init__(self) -> None:
        """!\n        @brief Initialize forecast attribution state.\n        @param self The tracker instance.\n        """\n        self._area: str | None = None
        self._areas: tuple[str, ...] = ()
        self._cycle = 0
        self._previous_period: str | None = None
        self._cycle_warning = False
        self._boundary_status = "none"

    @property
    def area(self) -> str | None:
        """!\n        @brief Return the current area state.\n        @param self The tracker instance.\n        @return The requested attribution state.\n        """\n        return self._area

    @property
    def observed_areas(self) -> tuple[str, ...]:
        """!\n        @brief Return the current observed areas state.\n        @param self The tracker instance.\n        @return The requested attribution state.\n        """\n        return getattr(self, "_observed_areas", ())

    @property
    def areas(self) -> tuple[str, ...]:
        """!\n        @brief Return the current areas state.\n        @param self The tracker instance.\n        @return The requested attribution state.\n        """\n        return self._areas

    @property
    def cycle(self) -> int:
        """!\n        @brief Return the current cycle state.\n        @param self The tracker instance.\n        @return The requested attribution state.\n        """\n        return self._cycle

    @property
    def cycle_warning(self) -> bool:
        """!\n        @brief Return the current cycle warning state.\n        @param self The tracker instance.\n        @return The requested attribution state.\n        """\n        return self._cycle_warning

    @property
    def boundary_status(self) -> str:
        """!\n        @brief Return the current boundary status state.\n        @param self The tracker instance.\n        @return The requested attribution state.\n        """\n        return self._boundary_status

    def observe_completed(self, transcript: str, period: str | None = None) -> str | None:
        """!\n        @brief Return current area and process headers for subsequent forecasts.\n        @param self The tracker instance.\n        @param transcript Completed forecast transcript.\n        @param period Optional named forecast period.\n        @return The current area when unambiguously identified.\n

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
            self._areas = ()
            self._cycle_warning = True
            self._boundary_status = "suspected"
        if period is not None:
            self._previous_period = period
        current = self._area
        current_areas = self._areas
        self._observed_areas = current_areas
        # An explicit forecast introduction can start a new area, but when
        # heard after a period it describes the *next* forecast instead.
        headers = list(_HEADER.finditer(transcript))
        explicit = _BULLETIN.search(transcript)
        if explicit and not self._cycle_warning:
            self._boundary_status = "explicit_header"
        if headers:
            suffix = transcript[headers[-1].end():]
            counties = list(_COUNTY.finditer(suffix))
            # Only accept a list with an explicit conjunction between counties.
            # Avoid treating arbitrary speech as a multi-county announcement.
            names = tuple(dict.fromkeys(
                _normalize_county(match.group(1)) + " county" for match in counties
            ))
            separators = [
                suffix[left.end():right.start()].strip().lower()
                for left, right in pairwise(counties)
            ]
            valid_group = all(sep in ("and", "or", ",", ", and", "") for sep in separators)
            self._areas = names if names and valid_group else ()
            self._area = self._areas[0] if len(self._areas) == 1 else None
        return current
