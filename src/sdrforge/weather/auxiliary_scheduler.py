"""Deterministic, hardware-independent scheduling for an auxiliary SDR.

The caller owns tuning and passes a monotonic timestamp to tick(). No sleep,
USB, network, or SDR dependencies are required.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AuxiliaryMode(str, Enum):
    WEATHER = "weather"
    TMC = "tmc"


@dataclass(frozen=True)
class AuxiliaryScheduleConfig:
    weather_frequency_hz: int = 162_550_000
    tmc_frequencies_hz: tuple[int, ...] = ()
    weather_dwell_seconds: float = 180.0
    tmc_dwell_seconds: float = 90.0
    max_alert_hold_seconds: float = 600.0

    def __post_init__(self) -> None:
        if self.weather_frequency_hz <= 0:
            raise ValueError("weather_frequency_hz must be positive")
        if any(f <= 0 for f in self.tmc_frequencies_hz):
            raise ValueError("TMC frequencies must be positive")
        if any(v <= 0 for v in (
            self.weather_dwell_seconds, self.tmc_dwell_seconds,
            self.max_alert_hold_seconds,
        )):
            raise ValueError("dwell and alert hold durations must be positive")


@dataclass(frozen=True)
class TuneDecision:
    mode: AuxiliaryMode
    frequency_hz: int
    changed: bool
    reason: str


class AuxiliaryReceiverScheduler:
    """Schedule NOAA and TMC listening windows without controlling hardware.

    A caller must apply each changed tuning decision and call tick() again
    with a monotonic clock. SAME alerts can hold the NOAA receiver in place;
    the hold has a maximum duration to avoid indefinite lockup.
    """

    def __init__(self, config: AuxiliaryScheduleConfig) -> None:
        self.config = config
        self._mode = AuxiliaryMode.WEATHER
        self._frequency = config.weather_frequency_hz
        self._entered_at: float | None = None
        self._last_now: float | None = None
        self._tmc_index = 0
        self._alert_until: float | None = None

    def tick(self, now: float) -> TuneDecision:
        if self._last_now is not None and now < self._last_now:
            raise ValueError("monotonic time cannot go backwards")
        self._last_now = now
        if self._entered_at is None:
            self._entered_at = now
            return self._decision(True, "initial")
        if not self.config.tmc_frequencies_hz:
            return self._decision(False, "no_tmc_stations")
        if self._mode is AuxiliaryMode.WEATHER and self._alert_until is not None:
            if now < self._alert_until:
                return self._decision(False, "alert_hold")
            self._alert_until = None
        dwell = (self.config.weather_dwell_seconds if self._mode is AuxiliaryMode.WEATHER
                 else self.config.tmc_dwell_seconds)
        if now - self._entered_at < dwell:
            return self._decision(False, "dwell")
        if self._mode is AuxiliaryMode.WEATHER:
            self._mode = AuxiliaryMode.TMC
            self._frequency = self.config.tmc_frequencies_hz[self._tmc_index]
            self._tmc_index = (self._tmc_index + 1) % len(self.config.tmc_frequencies_hz)
        else:
            self._mode = AuxiliaryMode.WEATHER
            self._frequency = self.config.weather_frequency_hz
        self._entered_at = now
        return self._decision(True, "dwell_elapsed")

    def hold_for_alert(self, now: float, duration_seconds: float) -> None:
        """Hold NOAA tuning while an alert is being received.

        Only applies when currently on NOAA. A caller should call this on a
        validated SAME alert start and clear_alert_hold() at end-of-message.
        """
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if self._last_now is not None and now < self._last_now:
            raise ValueError("monotonic time cannot go backwards")
        if self._mode is not AuxiliaryMode.WEATHER:
            return
        until = now + min(duration_seconds, self.config.max_alert_hold_seconds)
        self._alert_until = max(self._alert_until or until, until)

    def clear_alert_hold(self) -> None:
        self._alert_until = None

    def _decision(self, changed: bool, reason: str) -> TuneDecision:
        return TuneDecision(self._mode, self._frequency, changed, reason)
