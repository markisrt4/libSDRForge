"""!
@brief Apply auxiliary scheduling decisions to a receiver control interface.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock

import numpy as np

from sdrforge.controllers.receiver_manager import ReceiverManager

from .managed_noaa_decoder import ManagedNoaaDecoder
from .receiver_manager import (
    AuxiliaryReceiverManager,
    ReceiverDecision,
    ReceiverService,
)


@dataclass(frozen=True)
class ServiceProfile:
    """!
    @brief Provide ServiceProfile behavior.
    """

    mode: str
    bandwidth_hz: int


DEFAULT_PROFILES = {
    ReceiverService.WEATHER: ServiceProfile("NFM", 12_500),
    ReceiverService.TMC: ServiceProfile("WFM", 200_000),
    ReceiverService.ADSB: ServiceProfile("RAW", 2_000_000),
}


class AuxiliaryReceiverRuntime:
    """!
    @brief Hardware-independent execution layer with retry-on-failure semantics.
    """

    def __init__(
        self,
        scheduler: AuxiliaryReceiverManager,
        receiver: ReceiverManager,
        *,
        profiles: dict[ReceiverService, ServiceProfile] | None = None,
        on_start: Callable[[ReceiverService], None] | None = None,
        on_stop: Callable[[ReceiverService], None] | None = None,
        acquisition_token: str | None = None,
        noaa_decoder_factory: Callable[[int], ManagedNoaaDecoder] | None = None,
    ) -> None:
        """!
        @brief Provide   init   behavior.
        @param self The current instance.
        @param scheduler The scheduler value.
        @param receiver The receiver value.
        @param profiles The profiles value.
        @param on_start The on start value.
        @param on_stop The on stop value.
        @param acquisition_token Credential supplied by the acquisition coordinator.
        @param noaa_decoder_factory Optional factory for a fresh WEATHER decoder.
        """
        self.scheduler = scheduler
        self.receiver = receiver
        self.profiles = dict(DEFAULT_PROFILES if profiles is None else profiles)
        self.on_start = on_start
        self.on_stop = on_stop
        self._acquisition_token = acquisition_token
        self._noaa_decoder_factory = noaa_decoder_factory
        self._noaa_decoder: ManagedNoaaDecoder | None = None
        self._weather_generation = 0
        self._applied: tuple[ReceiverService, int] | None = None
        self._lock = RLock()
        self._error: str | None = None
        self._decoder_service: ReceiverService | None = None

    @property
    def applied_target(self) -> tuple[ReceiverService, int] | None:
        """!
        @brief Provide applied target behavior.
        @param self The current instance.
        @return The operation result.
        """
        return self._applied

    def status(self) -> dict[str, object]:
        """!
        @brief JSON-serializable status for REST or ZMQ telemetry adapters.
        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            if self._applied is None:
                return {
                    "state": "error" if self._error else "idle",
                    "service": None,
                    "frequency_hz": None,
                    "error": self._error,
                }
            return {
                "state": "running",
                "service": self._applied[0].value,
                "frequency_hz": self._applied[1],
                "error": self._error,
            }

    def step(self, now: float) -> ReceiverDecision:
        """!
        @brief Provide step behavior.
        @param self The current instance.
        @param now The now value.
        @return The operation result.
        """
        with self._lock:
            decision = self.scheduler.tick(now)
            target = (decision.service, decision.frequency_hz)
            if target == self._applied and self.receiver.running:
                return ReceiverDecision(
                    decision.service,
                    decision.frequency_hz,
                    False,
                    decision.reason,
                    decision.owner,
                )
            profile = self.profiles[decision.service]
            # Clear the old target before stopping its decoder: if stop fails,
            # we must not claim the old service is still healthy.
            self._applied = None
            try:
                self._stop_decoder()
                self.receiver.start(token=self._acquisition_token)
                self.receiver.set_mode(
                    profile.mode, profile.bandwidth_hz, token=self._acquisition_token
                )
                self.receiver.set_frequency(
                    decision.frequency_hz, token=self._acquisition_token
                )
                self._decoder_service = decision.service
                if self.on_start is not None:
                    self.on_start(decision.service)
                if (
                    decision.service is ReceiverService.WEATHER
                    and self._noaa_decoder_factory is not None
                ):
                    self._noaa_decoder = self._noaa_decoder_factory(
                        decision.frequency_hz
                    )
                    self._noaa_decoder.start()
                    self._weather_generation += 1
            except Exception as exc:
                self._error = f"{type(exc).__name__}: {exc}"
                # A failed decoder start may have partially allocated resources.
                # Best-effort cleanup must not mask the original error.
                if self._decoder_service is not None:
                    try:
                        self._stop_decoder()
                    except Exception as cleanup_exc:  # noqa: BLE001 - preserve original startup error
                        self._error += f"; cleanup failed: {type(cleanup_exc).__name__}: {cleanup_exc}"
                raise
            self._applied = target
            self._error = None
            return ReceiverDecision(
                decision.service,
                decision.frequency_hz,
                True,
                decision.reason,
                decision.owner,
            )

    def weather_generation(self) -> int | None:
        """!
        @brief Return the generation to capture when starting a PCM producer.
        @param self The current instance.
        @return Active generation or None when WEATHER is inactive.
        """
        with self._lock:
            if self._applied is None or self._noaa_decoder is None:
                return None
            if not self.receiver.running:
                return None
            return self._weather_generation

    def feed_weather_pcm(
        self, pcm: np.ndarray, frequency_hz: int, *, generation: int
    ) -> bool:
        """!
        @brief Route PCM from the active auxiliary WEATHER acquisition.
        @param self The current instance.
        @param pcm Normalized mono PCM at 16 kHz.
        @param frequency_hz Frequency associated with the PCM block.
        @param generation Generation captured by the producer before acquisition.
        @return Whether the block was accepted.
        """
        with self._lock:
            if (
                generation != self._weather_generation
                or self._applied != (ReceiverService.WEATHER, frequency_hz)
                or not self.receiver.running
                or self.receiver.get_frequency() != frequency_hz
                or self._noaa_decoder is None
            ):
                return False
            self._noaa_decoder.feed(pcm)
            return True

    def _stop_decoder(self) -> None:
        if self._noaa_decoder is not None:
            self._noaa_decoder.stop()
            self._noaa_decoder = None
        if self._decoder_service is not None:
            if self.on_stop is not None:
                self.on_stop(self._decoder_service)
            self._decoder_service = None

    def close(self) -> None:
        """!
        @brief Provide close behavior.
        @param self The current instance.
        """
        with self._lock:
            self._applied = None
            try:
                self._stop_decoder()
            finally:
                self.receiver.stop(token=self._acquisition_token)
