"""!
@brief Conservative period-based forecast extraction from offline NOAA transcripts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from re import Match

from .extract import _SPOKEN_NUMBER, _number

_PERIOD = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"tonight|today|this afternoon|this evening|overnight|so night)"
    r"( night| morning| afternoon| evening)?\b"
)
_CONDITIONS = (
    "mostly sunny", "partly sunny", "mostly cloudy", "partly cloudy",
    "sunny", "cloudy", "mostly clear", "partly clear", "clear", "rain showers", "snow showers",
    "showers", "thunderstorms", "rain", "snow", "fog",
)
_TEMPERATURE = re.compile(
    r"\b(highs?|lows?|guys|ties|those|flows|close)\s+(?:(?:around|near|in the|of|from)\s+)?"
    r"(?:(upper|lower|mid|middle)\s+)?("
    + _SPOKEN_NUMBER
    + r"|twenties|thirties|forties|fifties|sixties|seventies|eighties|nineties)\b"
)
_PROBABILITY = re.compile(
    r"\b(" + _SPOKEN_NUMBER + r")\s*(?:percent|%)\s+chance\b"
)
_PROBABILITY_TRAILING = re.compile(
    r"\bchance\s+of\s+(?:rain|snow|precipitation|showers)\s+("
    + _SPOKEN_NUMBER + r")\s*(?:percent|%)\b"
)


@dataclass(frozen=True)
class ForecastPeriod:
    """!
    @brief Provide ForecastPeriod behavior.
    """
    period: str
    conditions: str | None = None
    high_f: int | None = None
    low_f: int | None = None
    precipitation_chance_percent: int | None = None
    high_description: str | None = None
    low_description: str | None = None


def period_matches(text: str, *, allow_sunday_alias: bool = False) -> list[Match[str]]:
    """!
    @brief Recognize 'so night' only immediately following a Sunday period.
    @param text The text value.
    @param allow_sunday_alias The allow sunday alias value.
    @return The operation result.
    """
    accepted = []
    previous = "sunday" if allow_sunday_alias else None
    for match in _PERIOD.finditer(text):
        name = match.group(0)
        if name == "so night" and previous != "sunday":
            continue
        accepted.append(match)
        previous = "sunday" if name == "sunday" else name
    return accepted


def extract_forecasts(transcript: str, *, allow_sunday_alias: bool = False) -> tuple[ForecastPeriod, ...]:
    """!
    @brief Extract explicitly named periods; never infer missing measurements.
    @param transcript The transcript value.
    @param allow_sunday_alias The allow sunday alias value.
    @return The operation result.
    """
    normalized = " ".join(transcript.lower().split())
    matches = period_matches(normalized, allow_sunday_alias=allow_sunday_alias)
    periods: list[ForecastPeriod] = []
    for i, match in enumerate(matches):
        phrase = normalized[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(normalized)]
        condition = next((c for c in _CONDITIONS if re.search(r"\b" + re.escape(c) + r"\b", phrase)), None)
        high = low = chance = None
        high_description = low_description = None
        for temp in _TEMPERATURE.finditer(phrase):
            qualifier, spoken = temp.group(2), temp.group(3)
            approximate = bool(qualifier) or spoken.endswith("ies")
            value = _number(spoken)
            if temp.group(1).startswith("high") or temp.group(1) in ("guys", "ties"):
                if approximate:
                    high_description = temp.group(0)
                elif value is not None and -100 <= value <= 150:
                    high = value
            else:
                if approximate:
                    low_description = temp.group(0)
                elif value is not None and -100 <= value <= 150:
                    low = value
        probability = _PROBABILITY.search(phrase) or _PROBABILITY_TRAILING.search(phrase)
        if probability:
            value = _number(probability.group(1))
            if value is not None and 0 <= value <= 100:
                chance = value
        if any(x is not None for x in (condition, high, low, chance, high_description, low_description)):
            periods.append(ForecastPeriod(
                period=("sunday night" if match.group(0) == "so night" else match.group(0)), conditions=condition,
                high_f=high, low_f=low,
                precipitation_chance_percent=chance,
                high_description=high_description,
                low_description=low_description,
            ))
    return tuple(periods)
