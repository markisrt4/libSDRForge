"""Apply auxiliary scheduling decisions to a receiver control interface.

The runtime owns only the auxiliary receiver; primary FM is never referenced.
Decoders are injected as service-specific start/stop callbacks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sdrforge.controllers.receiver_manager import ReceiverManager
from .receiver_manager import AuxiliaryReceiverManager, ReceiverDecision, ReceiverService


@dataclass(frozen=True)
class ServiceProfile:
    mode: str
    bandwidth_hz: int


DEFAULT_PROFILES = {
    ReceiverService.WEATHER: ServiceProfile("NFM", 12_500),
    ReceiverService.TMC: ServiceProfile("WFM", 200_000),
    ReceiverService.ADSB: ServiceProfile("RAW", 2_000_000),
}


class AuxiliaryReceiverRuntime:
    """Hardware-independent execution layer with retry-on-failure semantics.

    Call step() with a monotonic timestamp. A failed tune leaves the applied
    target unchanged so the next step retries it. Decoder callbacks are
    optional and run only after tuning succeeds.
    """

    def __init__(
        self,
        scheduler: AuxiliaryReceiverManager,
        receiver: ReceiverManager,
        *,
        profiles: dict[ReceiverService, ServiceProfile] | None = None,
        on_start: Callable[[ReceiverService], None] | None = None,
        on_stop: Callable[[ReceiverService], None] | None = None,
    ) -> None:
        self.scheduler = scheduler
        self.receiver = receiver
        self.profiles = dict(DEFAULT_PROFILES if profiles is None else profiles)
        self.on_start = on_start
        self.on_stop = on_stop
        self._applied: tuple[ReceiverService, int] | None = None

    @property
    def applied_target(self) -> tuple[ReceiverService, int] | None:
        return self._applied

    def step(self, now: float) -> ReceiverDecision:
        decision = self.scheduler.tick(now)
        target = (decision.service, decision.frequency_hz)
        if target == self._applied:
            return ReceiverDecision(*target, changed=False, reason=decision.reason,
                                    owner=decision.owner)
        profile = self.profiles[decision.service]
        previous = self._applied
        if previous is not None and self.on_stop is not None:
            self.on_stop(previous[0])
        # The receiver manager serializes calls to the concrete adapter.
        # Never stop the primary receiver: this instance is auxiliary-only.
        self.receiver.start()
        try:
            self.receiver.set_mode(profile.mode, profile.bandwidth_hz)
            self.receiver.set_frequency(decision.frequency_hz)
            if self.on_start is not None:
                self.on_start(decision.service)
        except Exception:
            # The old decoder has stopped; do not claim that either pipeline
            # is active. A later step retries the requested target.
            self._applied = None
            raise
        self._applied = target
        return ReceiverDecision(decision.service, decision.frequency_hz,
                                changed=True, reason=decision.reason,
                                owner=decision.owner)

    def close(self) -> None:
        if self._applied is not None and self.on_stop is not None:
            self.on_stop(self._applied[0])
        self._applied = None
        self.receiver.stop()
