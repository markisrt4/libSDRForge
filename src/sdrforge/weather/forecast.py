"""Conservative period-based forecast extraction from offline NOAA transcripts.

Only explicitly spoken values are returned. Forecasts are not observations or
authoritative alerts. No date is inferred from weekday names.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .extract import _SPOKEN_NUMBER, _number

_PERIOD = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"tonight|today|this afternoon|this evening|overnight)"
    r"( night| morning| afternoon| evening)?\b"
)
_CONDITIONS = (
    "mostly sunny", "partly sunny", "mostly cloudy", "partly cloudy",
    "sunny", "cloudy", "clear", "rain showers", "snow showers",
    "showers", "thunderstorms", "rain", "snow", "fog",
)
_TEMPERATURE = re.compile(
    r"\b(highs?|lows?)\s+(?:around|near|in the|of|from)?\s*"
    r"(?:upper|lower|mid|middle)?\s*(" + _SPOKEN_NUMBER + r")\b"
)
_PROBABILITY = re.compile(
    r"\b(" + _SPOKEN_NUMBER + r")\s*(?:percent|%)\s+chance\b"
)


@dataclass(frozen=True)
class ForecastPeriod:
    period: str
    conditions: str | None = None
    high_f: int | None = None
    low_f: int | None = None
    precipitation_chance_percent: int | None = None


def extract_forecasts(transcript: str) -> tuple[ForecastPeriod, ...]:
    """Extract explicitly named periods; never infer missing measurements.

    Approximate phrases such as 'mid forties' are deliberately not converted
    into exact temperatures. A preceding fragment without a period is ignored.
    """
    normalized = " ".join(transcript.lower().split())
    matches = list(_PERIOD.finditer(normalized))
    periods: list[ForecastPeriod] = []
    for i, match in enumerate(matches):
        phrase = normalized[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(normalized)]
        condition = next((c for c in _CONDITIONS if re.search(r"\b" + re.escape(c) + r"\b", phrase)), None)
        high = low = chance = None
        for temp in _TEMPERATURE.finditer(phrase):
            value = _number(temp.group(2))
            if value is None or not -100 <= value <= 150:
                continue
            if temp.group(1).startswith("high"):
                high = value
            else:
                low = value
        probability = _PROBABILITY.search(phrase)
        if probability:
            value = _number(probability.group(1))
            if value is not None and 0 <= value <= 100:
                chance = value
        if condition is not None or high is not None or low is not None or chance is not None:
            periods.append(ForecastPeriod(
                period=match.group(0), conditions=condition,
                high_f=high, low_f=low,
                precipitation_chance_percent=chance,
            ))
    return tuple(periods)
