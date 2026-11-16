"""Apply auxiliary scheduling decisions to a receiver control interface.

The runtime owns only the auxiliary receiver; primary FM is never referenced.
Decoders are injected as service-specific start/stop callbacks.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
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
        self._lock = RLock()
        self._error: str | None = None

    @property
    def applied_target(self) -> tuple[ReceiverService, int] | None:
        return self._applied

    def status(self) -> dict[str, object]:
        """JSON-serializable status for REST or ZMQ telemetry adapters."""
        with self._lock:
            if self._applied is None:
                return {"state": "error" if self._error else "idle",
                        "service": None, "frequency_hz": None,
                        "error": self._error}
            return {"state": "running", "service": self._applied[0].value,
                    "frequency_hz": self._applied[1], "error": self._error}

    def step(self, now: float) -> ReceiverDecision:
        with self._lock:
            decision = self.scheduler.tick(now)
            target = (decision.service, decision.frequency_hz)
            if target == self._applied:
                return ReceiverDecision(decision.service, decision.frequency_hz,
                                        False, decision.reason, decision.owner)
            profile = self.profiles[decision.service]
            previous = self._applied
            # Clear the old target before stopping its decoder: if stop fails,
            # we must not claim the old service is still healthy.
            self._applied = None
            try:
                if previous is not None and self.on_stop is not None:
                    self.on_stop(previous[0])
                self.receiver.start()
                self.receiver.set_mode(profile.mode, profile.bandwidth_hz)
                self.receiver.set_frequency(decision.frequency_hz)
                if self.on_start is not None:
                    self.on_start(decision.service)
            except Exception as exc:
                self._error = f"{type(exc).__name__}: {exc}"
                # A failed decoder start may have partially allocated resources.
                # Best-effort cleanup must not mask the original error.
                if self.on_stop is not None:
                    try:
                        self.on_stop(decision.service)
                    except Exception:
                        pass
                raise
            self._applied = target
            self._error = None
            return ReceiverDecision(decision.service, decision.frequency_hz,
                                    True, decision.reason, decision.owner)

    def close(self) -> None:
        with self._lock:
            previous = self._applied
            self._applied = None
            try:
                if previous is not None and self.on_stop is not None:
                    self.on_stop(previous[0])
            finally:
                self.receiver.stop()
