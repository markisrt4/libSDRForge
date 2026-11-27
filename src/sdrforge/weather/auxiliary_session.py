"""!
@brief Bind auxiliary WEATHER lease and demodulated PCM to a transcription worker.
"""

from __future__ import annotations

from typing import Protocol, Self

import numpy as np

from .receiver_manager import AuxiliaryReceiverManager, ReceiverLease, ReceiverService
from .receiver_runtime import AuxiliaryReceiverRuntime


class AuxiliaryPcmSink(Protocol):
    """!
    @brief Provide AuxiliaryPcmSink behavior.
    """

    def feed(self, pcm: np.ndarray) -> None:
        """!
        @brief Accept one block of normalized mono PCM.
        @param self The current instance.
        @param pcm The PCM block.
        """
        ...

    def start(self) -> None:
        """!
        @brief Start consuming PCM.
        @param self The current instance.
        """
        ...

    def stop(self) -> None:
        """!
        @brief Stop consuming PCM.
        @param self The current instance.
        """
        ...


class AuxiliaryNoaaSession:
    """!
    @brief Lease-scoped transcription for an explicitly injected auxiliary radio.
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
        """!
        @brief Provide   init   behavior.
        @param self The current instance.
        @param manager The manager value.
        @param runtime The runtime value.
        @param transcriber The transcriber value.
        @param owner The owner value.
        @param priority The priority value.
        """
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
        """!
        @brief Provide start behavior.
        @param self The current instance.
        @param now The now value.
        """
        if self._lease is not None:
            raise RuntimeError("NOAA session already started")
        lease = self.manager.acquire(
            self.owner, service=ReceiverService.WEATHER, priority=self.priority
        )
        try:
            self.runtime.step(now)
            if self.runtime.applied_target != (
                ReceiverService.WEATHER,
                self.manager.config.weather_frequency_hz,
            ):
                raise RuntimeError("auxiliary WEATHER receiver was not activated")
            self.transcriber.start()
        except BaseException:
            self.manager.release(lease)
            raise
        self._lease = lease

    def require_weather(self) -> None:
        """!
        @brief Refuse IQ processing when the auxiliary WEATHER lease is inactive.
        @param self The current instance.
        """
        if self._lease is None:
            raise RuntimeError("NOAA session has no active auxiliary WEATHER lease")
        if self.runtime.applied_target != (
            ReceiverService.WEATHER,
            self.manager.config.weather_frequency_hz,
        ):
            raise RuntimeError("auxiliary receiver is not tuned to NOAA")

    def feed(self, pcm: np.ndarray) -> None:
        """!
        @brief Provide feed behavior.
        @param self The current instance.
        @param pcm The pcm value.
        """
        self.require_weather()
        self.transcriber.feed(pcm)

    def stop(self) -> None:
        """!
        @brief Provide stop behavior.
        @param self The current instance.
        """
        lease = self._lease
        if lease is None:
            return
        self._lease = None
        try:
            self.transcriber.stop()
        finally:
            self.manager.release(lease)

    def __enter__(self) -> Self:
        """!
        @brief Provide   enter   behavior.
        @param self The current instance.
        @return The operation result.
        """
        if self._lease is None:
            raise RuntimeError("call start(now) before entering session")
        return self

    def __exit__(self, *_: object) -> None:
        """!
        @brief Provide   exit   behavior.
        @param self The current instance.
        @param _ The   value.
        """
        self.stop()
