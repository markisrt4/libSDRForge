"""Conservative extraction from NOAA speech transcripts and SAME headers.

Speech extraction is best-effort and must never be used to invent or confirm
severe weather warnings. SAME headers require a separate audio decoder.
"""
from __future__ import annotations
import re
from .models import SameAlert, WeatherObservation

_DIRECTIONS = r"(?:northeast|northwest|southeast|southwest|north|south|east|west|variable)"
_ONES = {word: value for value, word in enumerate(
    ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
)}
_TEENS = {word: value for value, word in enumerate(
    ("ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
     "sixteen", "seventeen", "eighteen", "nineteen"), start=10
)}
_TENS = {word: value for value, word in zip(
    ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"),
    range(20, 100, 10)
)}
_NUMBER_WORDS = _ONES | _TEENS | _TENS
_SPOKEN_NUMBER = r"(?:-?\\d{1,3}|(?:" + "|".join(_NUMBER_WORDS) + r")(?:[ -](?:" + "|".join(_ONES) + r"))?)"


def _number(value: str) -> int | None:
    if re.fullmatch(r"-?\\d{1,3}", value):
        return int(value)
    words = value.replace("-", " ").split()
    if len(words) == 1:
        return _NUMBER_WORDS.get(words[0])
    if len(words) == 2 and words[0] in _TENS and words[1] in _ONES:
        return _TENS[words[0]] + _ONES[words[1]]
    return None


def extract_observation(transcript: str, *, frequency_hz: int,
                        location: str | None = None) -> WeatherObservation:
    """Extract only explicitly spoken values; leave missing fields unset.

    Recognizes simple number words and limited Vosk substitutions observed
    in local NOAA test audio. Never infer a weather warning from transcript.
    """
    if frequency_hz <= 0:
        raise ValueError("frequency_hz must be positive")
    normalized = " ".join(transcript.lower().split())
    temperature = re.search(
        r"\\btemperature(?: is| in| of| was)?\\s+(" + _SPOKEN_NUMBER + r")\\s+degrees?\\b",
        normalized,
    )
    if temperature is None:
        temperature = re.search(
            r"\\btemperature(?: is| in| of| was)?\\s+(" + _SPOKEN_NUMBER + r")\\b",
            normalized,
        )
    humidity = re.search(
        r"\\b(?:relative )?humidity(?: is| and| of| was)?\\s+(" +
        _SPOKEN_NUMBER + r")\\s*(?:percent|%)\\b", normalized,
    )
    wind = re.search(
        r"\\b(?:winds?|when)\\s+(?:from the\\s+)?(" + _DIRECTIONS +
        r")\\s+(?:at|top)?\\s*(" + _SPOKEN_NUMBER +
        r")\\s*(?:miles per hour|mph)\\b", normalized,
    )
    temp = _number(temperature.group(1)) if temperature else None
    hum = _number(humidity.group(1)) if humidity else None
    speed = _number(wind.group(2)) if wind else None
    if hum is not None and not 0 <= hum <= 100:
        hum = None
    return WeatherObservation(
        source_frequency_hz=frequency_hz, transcript=transcript,
        temperature_f=temp, wind_direction=wind.group(1) if wind else None,
        wind_mph=speed, relative_humidity_percent=hum, location=location,
    )

# SAME format: ZCZC-ORG-EEE-PSSCCC[-PSSCCC...]+TTTT-JJJHHMM-LLLLLLLL-
_HEADER = re.compile(
    r"ZCZC-([A-Z]{3})-([A-Z]{3})-(\d{6}(?:-\d{6})*)\+(\d{4})-(\d{7})-([A-Z0-9/ ]{1,8})-"
)

def parse_same_header(header: str) -> SameAlert | None:
    """Parse a decoded SAME text header; does not demodulate SAME audio."""
    match = _HEADER.search(header)
    if match is None:
        return None
    originator, event, locations, duration, issued, sender = match.groups()
    return SameAlert(
        originator=originator, event=event,
        location_codes=tuple(locations.split("-")),
        duration=duration, issued_julian=issued, sender=sender.strip(),
        raw_header=match.group(0),
    )
