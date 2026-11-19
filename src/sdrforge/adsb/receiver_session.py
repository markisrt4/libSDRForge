"""!
@brief Reusable frame-level ADS-B session independent of SDR hardware and CLI.
"""
from __future__ import annotations

from dataclasses import dataclass

from .protocol import decode_message, modes_crc
from .tracker import Aircraft, AircraftTracker


@dataclass(frozen=True)
class ReceiverStatistics:
    """!
    @brief Represent ReceiverStatistics.
    """
    frames_seen: int
    frames_valid: int
    crc_failures: int
    unsupported_frames: int
    aircraft_tracked: int
    position_fixes: int


class AdsbReceiverSession:
    """!
    @brief Accept complete Mode S frames and maintain aircraft tracks.
    """

    def __init__(self, *, ttl_seconds: float = 120):
        """!
        @brief Handle   init  .
        @param self The current instance.
        @param ttl_seconds The ttl seconds value.
        """
        self.tracker = AircraftTracker(ttl_seconds=ttl_seconds)
        self.frames_seen = 0
        self.frames_valid = 0
        self.crc_failures = 0
        self.unsupported_frames = 0

    def accept(self, frame: bytes | str, now: float) -> Aircraft | None:
        """!
        @brief Handle accept.
        @param self The current instance.
        @param frame The frame value.
        @param now The now value.
        @return The operation result.
        """
        self.frames_seen += 1
        if isinstance(frame, str):
            try:
                raw = bytes.fromhex(frame.strip().removeprefix("*").removesuffix(";"))
            except ValueError:
                self.unsupported_frames += 1
                return None
        else:
            raw = frame
        if len(raw) != 14 or raw[0] >> 3 != 17:
            self.unsupported_frames += 1
            return None
        if modes_crc(raw) != 0:
            self.crc_failures += 1
            return None
        message = decode_message(raw)
        if message is None:
            self.unsupported_frames += 1
            return None
        self.frames_valid += 1
        return self.tracker.update(message, now)

    def statistics(self, now: float) -> ReceiverStatistics:
        """!
        @brief Handle statistics.
        @param self The current instance.
        @param now The now value.
        @return The operation result.
        """
        aircraft = self.tracker.snapshot(now)
        return ReceiverStatistics(
            frames_seen=self.frames_seen,
            frames_valid=self.frames_valid,
            crc_failures=self.crc_failures,
            unsupported_frames=self.unsupported_frames,
            aircraft_tracked=len(aircraft),
            position_fixes=sum(a.latitude is not None and a.longitude is not None for a in aircraft),
        )
