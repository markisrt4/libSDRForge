"""Bind auxiliary WEATHER lease and demodulated PCM to a transcription worker.

Hardware and DSP are injected. This bridge never opens or retunes the primary
receiver. The caller supplies an AuxiliaryReceiverRuntime already bound to an
independent auxiliary receiver, and feeds only its NFM mono 16 kHz output.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np

from .receiver_manager import AuxiliaryReceiverManager, ReceiverLease, ReceiverService
from .receiver_runtime import AuxiliaryReceiverRuntime
from .auxiliary_transcriber import AuxiliaryNoaaTranscriber


class AuxiliaryPcmSink(Protocol):
    def feed(self, pcm: np.ndarray) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...


class AuxiliaryNoaaSession:
    """Lease-scoped transcription for an explicitly injected auxiliary radio.

    No primary receiver argument or fallback is accepted. Caller must supply
    NFM-demodulated 16 kHz mono PCM via feed(). No hardware acquisition occurs
    here. Runtime is not closed because it belongs to the auxiliary service
    host and may be shared with TMC/ADSB.
    """

    def __init__(
        self,
        manager: AuxiliaryReceiverManager,
        runtime: AuxiliaryReceiverRuntime,
        transcriber: AuxiliaryPcmSink,
        *,
        owner: str = "noaa-transcription",
        priority: int = 100,
    ) -> None:
        if runtime.scheduler is not manager:
            raise ValueError("auxiliary runtime and lease manager must match")
        if not owner.strip():
            raise ValueError("owner must not be empty")
        self.manager = manager
        self.runtime = runtime
        self.transcriber = transcriber
        self.owner = owner
        self.priority = priority
        self._lease: ReceiverLease | None = None

    def start(self, now: float) -> None:
        if self._lease is not None:
            raise RuntimeError("NOAA session already started")
        lease = self.manager.acquire(
            self.owner, service=ReceiverService.WEATHER, priority=self.priority
        )
        try:
            self.runtime.step(now)
            if self.runtime.applied_target != (
                ReceiverService.WEATHER, self.manager.config.weather_frequency_hz
            ):
                raise RuntimeError("auxiliary WEATHER receiver was not activated")
            self.transcriber.start()
        except BaseException:
            self.manager.release(lease)
            raise
        self._lease = lease

    def require_weather(self) -> None:
        """Refuse IQ processing when the auxiliary WEATHER lease is inactive."""
        if self._lease is None:
            raise RuntimeError("NOAA session has no active auxiliary WEATHER lease")
        if self.runtime.applied_target != (
            ReceiverService.WEATHER, self.manager.config.weather_frequency_hz
        ):
            raise RuntimeError("auxiliary receiver is not tuned to NOAA")

    def feed(self, pcm: np.ndarray) -> None:
        self.require_weather()
        self.transcriber.feed(pcm)

    def stop(self) -> None:
        lease = self._lease
        if lease is None:
            return
        self._lease = None
        try:
            self.transcriber.stop()
        finally:
            self.manager.release(lease)

    def __enter__(self):
        if self._lease is None:
            raise RuntimeError("call start(now) before entering session")
        return self

    def __exit__(self, *_):
        self.stop()
