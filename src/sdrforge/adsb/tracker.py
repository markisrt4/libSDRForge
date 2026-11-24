"""!
@brief Aggregate ADS-B aircraft state and expire stale CPR position pairs.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .cpr import decode_global
from .protocol import AdsbMessage


@dataclass(frozen=True)
class Aircraft:
    """!
    @brief Current decoded aircraft state and last observation time.
    """

    icao: str
    last_seen: float
    callsign: str | None = None
    altitude_ft: int | None = None
    speed_kt: float | None = None
    heading_deg: float | None = None
    vertical_rate_fpm: int | None = None
    latitude: float | None = None
    longitude: float | None = None


class AircraftTracker:
    """!
    @brief Merge validated aircraft messages using a monotonic clock.
    """

    def __init__(self, *, ttl_seconds: float = 120, cpr_pair_seconds: float = 10):
        """!
        @brief Initialize aircraft and CPR expiration windows.
        @param self The aircraft tracker.
        @param ttl_seconds Aircraft expiration age in seconds.
        @param cpr_pair_seconds Maximum age difference for CPR pairing.
        """
        if ttl_seconds <= 0 or cpr_pair_seconds <= 0:
            raise ValueError("timeouts must be positive")
        self.ttl_seconds = ttl_seconds
        self.cpr_pair_seconds = cpr_pair_seconds
        self._aircraft: dict[str, Aircraft] = {}
        self._cpr: dict[str, dict[bool, tuple[float, int, int]]] = {}
        self._last_now: float | None = None

    def update(self, message: AdsbMessage, now: float) -> Aircraft:
        """!
        @brief Merge one decoded ADS-B message into an aircraft track.
        @param self The aircraft tracker.
        @param message Decoded ADS-B message.
        @param now Monotonic observation time.
        @return Updated aircraft state.
        """
        self._check_time(now)
        self.expire(now)
        current = self._aircraft.get(message.icao, Aircraft(message.icao, now))
        updated = replace(
            current,
            last_seen=now,
            callsign=message.callsign
            if message.callsign is not None
            else current.callsign,
            altitude_ft=message.altitude_ft
            if message.altitude_ft is not None
            else current.altitude_ft,
            speed_kt=message.speed_kt
            if message.speed_kt is not None
            else current.speed_kt,
            heading_deg=message.heading_deg
            if message.heading_deg is not None
            else current.heading_deg,
            vertical_rate_fpm=(
                message.vertical_rate_fpm
                if message.vertical_rate_fpm is not None
                else current.vertical_rate_fpm
            ),
        )
        if (
            message.cpr_odd is not None
            and message.cpr_lat is not None
            and message.cpr_lon is not None
        ):
            pair = self._cpr.setdefault(message.icao, {})
            pair[message.cpr_odd] = (now, message.cpr_lat, message.cpr_lon)
            if False in pair and True in pair:
                even, odd = pair[False], pair[True]
                if abs(even[0] - odd[0]) <= self.cpr_pair_seconds:
                    position = decode_global(
                        even[1],
                        even[2],
                        odd[1],
                        odd[2],
                        most_recent_odd=odd[0] > even[0],
                    )
                    if position is not None:
                        updated = replace(
                            updated, latitude=position[0], longitude=position[1]
                        )
        self._aircraft[message.icao] = updated
        return updated

    def expire(self, now: float) -> None:
        """!
        @brief Remove stale aircraft and CPR observations.
        @param self The aircraft tracker.
        @param now Current monotonic time.
        """
        self._check_time(now)
        for icao, aircraft in list(self._aircraft.items()):
            if now - aircraft.last_seen > self.ttl_seconds:
                del self._aircraft[icao]
                self._cpr.pop(icao, None)
        for icao, pair in list(self._cpr.items()):
            for parity, (timestamp, _, _) in list(pair.items()):
                if now - timestamp > self.cpr_pair_seconds:
                    del pair[parity]
            if not pair:
                del self._cpr[icao]

    def snapshot(self, now: float) -> tuple[Aircraft, ...]:
        """!
        @brief Return sorted, non-expired aircraft states.
        @param self The aircraft tracker.
        @param now Current monotonic time.
        @return Snapshot of tracked aircraft.
        """
        self.expire(now)
        return tuple(sorted(self._aircraft.values(), key=lambda a: a.icao))

    def _check_time(self, now: float) -> None:
        if self._last_now is not None and now < self._last_now:
            raise ValueError("monotonic time cannot go backwards")
        self._last_now = now
