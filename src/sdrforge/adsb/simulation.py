"""Deterministic synthetic aircraft snapshots in SDRForge's aviation units."""
from math import cos, degrees, pi, radians, sin

EARTH_RADIUS_M = 6371000.0


def simulated_aircraft(elapsed_s: float, count: int = 10, *,
                       center_lat: float = 42.5, center_lon: float = -83.0) -> tuple[dict[str, object], ...]:
    """Return transport-neutral aircraft records with tracker-compatible keys."""
    if count < 0 or count > 0x1000000:
        raise ValueError("aircraft count out of range")
    if not -90 < center_lat < 90 or not -180 <= center_lon <= 180:
        raise ValueError("invalid center")
    results = []
    for index in range(count):
        angle = (2 * pi * index / max(count, 1)) + elapsed_s * (0.004 + index * 0.0002)
        radius = 12000 + index * 2500
        latitude = center_lat + degrees(radius * cos(angle) / EARTH_RADIUS_M)
        longitude = center_lon + degrees(radius * sin(angle) / (EARTH_RADIUS_M * cos(radians(center_lat))))
        results.append({
            "icao": f"{0xA00000 + index:06X}",
            "latitude": latitude, "longitude": ((longitude + 180) % 360) - 180,
            "altitude_ft": (1500 + index * 300) / 0.3048,
            "speed_kt": (80 + index * 5) / (1852 / 3600),
            "heading_deg": degrees(angle + pi / 2) % 360,
            "callsign": f"TEST{index + 1:03d}",
            "last_seen": elapsed_s,
        })
    return tuple(results)
