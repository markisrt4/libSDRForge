"""!
@brief Hardware-independent auxiliary receiver arbitration.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .auxiliary_scheduler import (
    AuxiliaryMode,
    AuxiliaryReceiverScheduler,
    AuxiliaryScheduleConfig,
)


class ReceiverService(str, Enum):
    """!
    @brief Provide ReceiverService behavior.
    """
    WEATHER = "weather"
    TMC = "tmc"
    ADSB = "adsb"


@dataclass(frozen=True)
class ReceiverDecision:
    """!
    @brief Provide ReceiverDecision behavior.
    """
    service: ReceiverService
    frequency_hz: int
    changed: bool
    reason: str
    owner: str | None = None


@dataclass(frozen=True)
class ReceiverLease:
    """!
    @brief Provide ReceiverLease behavior.
    """
    token: int
    owner: str
    service: ReceiverService
    priority: int


class AuxiliaryReceiverManager:
    """!
    @brief Arbitrate on-demand services over the adaptive weather/TMC schedule.
    """

    def __init__(
        self,
        config: AuxiliaryScheduleConfig,
        *,
        adsb_frequency_hz: int = 1_090_000_000,
    ) -> None:
        """!
        @brief Provide   init   behavior.
        @param self The current instance.
        @param config The config value.
        @param adsb_frequency_hz The adsb frequency hz value.
        """
        if adsb_frequency_hz <= 0:
            raise ValueError("adsb_frequency_hz must be positive")
        self.config = config
        self.adsb_frequency_hz = adsb_frequency_hz
        self._scheduler = AuxiliaryReceiverScheduler(config)
        self._leases: dict[int, ReceiverLease] = {}
        self._next_token = 1
        self._last_time: float | None = None
        self._last_target: tuple[ReceiverService, int] | None = None
        self._was_leased = False

    def acquire(
        self, owner: str, *, service: ReceiverService, priority: int = 100
    ) -> ReceiverLease:
        """!
        @brief Provide acquire behavior.
        @param self The current instance.
        @param owner The owner value.
        @param service The service value.
        @param priority The priority value.
        @return The operation result.
        """
        if not owner.strip():
            raise ValueError("owner must be nonempty")
        if service is ReceiverService.TMC and not self.config.tmc_frequencies_hz:
            raise ValueError("no TMC frequency configured")
        lease = ReceiverLease(self._next_token, owner, service, priority)
        self._next_token += 1
        self._leases[lease.token] = lease
        return lease

    def release(self, lease: ReceiverLease) -> bool:
        """!
        @brief Return False for an already released or unknown lease.
        @param self The current instance.
        @param lease The lease value.
        @return The operation result.
        """
        if self._leases.get(lease.token) != lease:
            return False
        del self._leases[lease.token]
        return True

    def tick(self, now: float) -> ReceiverDecision:
        """!
        @brief Provide tick behavior.
        @param self The current instance.
        @param now The now value.
        @return The operation result.
        """
        if self._last_time is not None and now < self._last_time:
            raise ValueError("monotonic time cannot go backwards")
        self._last_time = now
        active = max(
            self._leases.values(),
            key=lambda lease: (lease.priority, lease.token),
            default=None,
        )
        if active is not None:
            frequencies = {
                ReceiverService.WEATHER: self.config.weather_frequency_hz,
                ReceiverService.ADSB: self.adsb_frequency_hz,
                ReceiverService.TMC: self.config.tmc_frequencies_hz[0]
                if self.config.tmc_frequencies_hz else 0,
            }
            service, frequency = active.service, frequencies[active.service]
            owner = active.owner
            reason = "lease"
        else:
            # Reset the adaptive dwell clock when returning from a lease.
            if self._was_leased:
                self._scheduler = AuxiliaryReceiverScheduler(self.config)
            decision = self._scheduler.tick(now)
            service = (ReceiverService.WEATHER if decision.mode is AuxiliaryMode.WEATHER
                       else ReceiverService.TMC)
            frequency, owner, reason = decision.frequency_hz, None, decision.reason
        target = (service, frequency)
        changed = target != self._last_target
        self._last_target = target
        self._was_leased = active is not None
        return ReceiverDecision(service, frequency, changed, reason, owner)


    def hold_for_alert(self, now: float, duration_seconds: float) -> None:
        """!
        @brief Pass validated NOAA alert hold to the adaptive scheduler.
        @param self The current instance.
        @param now The now value.
        @param duration_seconds The duration seconds value.
        """
        if not self._was_leased:
            self._scheduler.hold_for_alert(now, duration_seconds)

    def clear_alert_hold(self) -> None:
        """!
        @brief Provide clear alert hold behavior.
        @param self The current instance.
        """
        self._scheduler.clear_alert_hold()
