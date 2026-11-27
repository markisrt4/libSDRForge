"""Generation-bound PCM sink for an already-owned auxiliary IQ source."""

from __future__ import annotations

import numpy as np

from .receiver_runtime import AuxiliaryReceiverRuntime


class ManagedNoaaPcmSession:
    """Bind one DSP bridge to one authorized weather acquisition generation."""

    def __init__(
        self, runtime: AuxiliaryReceiverRuntime, *, frequency_hz: int
    ) -> None:
        self._runtime = runtime
        self._frequency_hz = frequency_hz
        generation = runtime.weather_generation()
        if generation is None:
            raise RuntimeError("no active NOAA acquisition generation")
        self._generation = generation
        self.require_weather()

    def require_weather(self) -> None:
        """Reject a retired session before reading or demodulating IQ."""
        if (
            self._runtime.weather_generation() != self._generation
            or self._runtime.receiver.get_frequency() != self._frequency_hz
        ):
            raise RuntimeError("NOAA acquisition generation or frequency changed")

    def feed(self, pcm: np.ndarray) -> None:
        """Forward PCM using the original acquisition generation."""
        if not self._runtime.feed_weather_pcm(
            pcm, self._frequency_hz, generation=self._generation
        ):
            raise RuntimeError("NOAA PCM acquisition is no longer authorized")
