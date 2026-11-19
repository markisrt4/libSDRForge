"""Global airborne CPR position reconstruction from even/odd ADS-B frames."""
from __future__ import annotations

from math import acos, cos, floor, pi

CPR_SCALE = 131072


def _nl(latitude: float) -> int:
    """Number of longitude zones at latitude, per 1090ES CPR."""
    lat = abs(latitude)
    if lat >= 87:
        return 1 if lat > 87 else 2
    if lat < 1e-12:
        return 59
    nz = 15
    value = 1 - (1 - cos(pi / (2 * nz))) / cos(pi * lat / 180) ** 2
    value = max(-1.0, min(1.0, value))
    return max(1, floor(2 * pi / acos(value)))


def decode_global(
    even_lat: int, even_lon: int, odd_lat: int, odd_lon: int,
    *, most_recent_odd: bool,
) -> tuple[float, float] | None:
    """Decode paired airborne CPR, or None for inconsistent latitude zones.

    The caller must ensure frames are from the same ICAO aircraft, airborne,
    and close enough in time (normally <=10 seconds).
    """
    if any(not 0 <= x < CPR_SCALE for x in
           (even_lat, even_lon, odd_lat, odd_lon)):
        raise ValueError("CPR fractions must be 17-bit unsigned integers")
    yz0, yz1 = even_lat / CPR_SCALE, odd_lat / CPR_SCALE
    xz0, xz1 = even_lon / CPR_SCALE, odd_lon / CPR_SCALE
    j = floor(59 * yz0 - 60 * yz1 + 0.5)
    rlat0 = 6.0 * ((j % 60) + yz0)
    rlat1 = (360.0 / 59) * ((j % 59) + yz1)
    if rlat0 >= 270:
        rlat0 -= 360
    if rlat1 >= 270:
        rlat1 -= 360
    if not (-90 <= rlat0 <= 90 and -90 <= rlat1 <= 90):
        return None
    if _nl(rlat0) != _nl(rlat1):
        return None
    lat = rlat1 if most_recent_odd else rlat0
    ni = max(_nl(lat) - (1 if most_recent_odd else 0), 1)
    m = floor(xz0 * (_nl(lat) - 1) - xz1 * _nl(lat) + 0.5)
    lon_fraction = xz1 if most_recent_odd else xz0
    lon = (360.0 / ni) * ((m % ni) + lon_fraction)
    if lon >= 180:
        lon -= 360
    return lat, lon
