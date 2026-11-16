"""Conservative extraction from NOAA speech transcripts and SAME headers.

Speech extraction is best-effort and must never be used to invent or confirm
severe weather warnings. SAME headers require a separate audio decoder.
"""
from __future__ import annotations
import re
from .models import SameAlert, WeatherObservation

_DIRECTIONS = r"(?:north|south|east|west|northeast|northwest|southeast|southwest|variable)"
_NUMBER = r"(-?\d{1,3})"

def extract_observation(transcript: str, *, frequency_hz: int,
                        location: str | None = None) -> WeatherObservation:
    """Extract only explicitly spoken values; leave missing fields unset."""
    if frequency_hz <= 0:
        raise ValueError("frequency_hz must be positive")
    normalized = " ".join(transcript.lower().split())
    temperature = re.search(r"\btemperature(?: is| of| was)?\s+" + _NUMBER + r"\b", normalized)
    humidity = re.search(r"\b(?:relative )?humidity(?: is| of| was)?\s+(\d{1,3})\s*(?:percent|%)", normalized)
    wind = re.search(r"\bwinds?\s+(?:from the\s+)?(" + _DIRECTIONS + r")\s+(?:at\s+)?(\d{1,3})\s*(?:miles per hour|mph)\b", normalized)
    hum = int(humidity.group(1)) if humidity else None
    if hum is not None and not 0 <= hum <= 100:
        hum = None
    return WeatherObservation(
        source_frequency_hz=frequency_hz, transcript=transcript,
        temperature_f=int(temperature.group(1)) if temperature else None,
        wind_direction=wind.group(1) if wind else None,
        wind_mph=int(wind.group(2)) if wind else None,
        relative_humidity_percent=hum, location=location,
    )

# SAME format: ZCZC-ORG-EEE-PSSCCC[-PSSCCC...]+TTTT-JJJHHMM-LLLLLLLL-
_HEADER = re.compile(
    r"ZCZC-([A-Z]{3})-([A-Z]{3})-((?:\d{6}-)+)\+(\d{4})-(\d{7})-([A-Z0-9/ ]{1,8})-"
)

def parse_same_header(header: str) -> SameAlert | None:
    """Parse a decoded SAME text header; does not demodulate SAME audio."""
    match = _HEADER.search(header)
    if match is None:
        return None
    originator, event, locations, duration, issued, sender = match.groups()
    return SameAlert(
        originator=originator, event=event,
        location_codes=tuple(locations.rstrip("-").split("-")),
        duration=duration, issued_julian=issued, sender=sender.strip(),
        raw_header=match.group(0),
    )
