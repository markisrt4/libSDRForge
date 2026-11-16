"""!
@brief Exclusive-session IQ scanner adapter for an SDR source.

The caller must own the source exclusively. This adapter never opens, closes,
starts, or stops playback on another owner's behalf.
"""
from __future__ import annotations

from collections.abc import Callable
from threading import Lock

from sdrforge.dsp.channel_power import measure_channel_power
from sdrforge.interfaces.sdr_source_if import SdrSourceIf


class IqSignalScannerAdapter:
    """!
    @brief Provide iq signal scanner adapter behavior.
    """
    def __init__(
        self,
        source: SdrSourceIf,
        *,
        channel_width_hz: int = 180_000,
        discard_blocks: int = 2,
        exclusive_access: Callable[[], bool] | None = None,
    ) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param source The ``source`` value.
        @param channel_width_hz The ``channel_width_hz`` value.
        @param discard_blocks The ``discard_blocks`` value.
        @param exclusive_access The ``exclusive_access`` value.
        """
        if discard_blocks < 0:
            raise ValueError("discard_blocks must be nonnegative")
        self.source = source
        self.channel_width_hz = channel_width_hz
        self.discard_blocks = discard_blocks
        self.exclusive_access = exclusive_access
        self._lock = Lock()

    def measure(self, frequency_hz: int, modulation: str) -> tuple[float, float]:
        """!
        @brief Measure one frequency, restoring tuning even on failure.

        Requires an already-open, started source with exclusive ownership.

        @param self The current instance.
        @param frequency_hz The frequency in hertz.
        @param modulation The ``modulation`` value.
        @return The operation result.
        """
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("scanner is already measuring")
        try:
            if self.exclusive_access is None or not self.exclusive_access():
                raise RuntimeError("exclusive receiver ownership required")
            if not self.source.is_connected():
                raise RuntimeError("SDR source is not connected")
            previous = self.source.get_center_frequency()
            if previous <= 0:
                raise RuntimeError("source must have an initial tuned frequency")
            try:
                self.source.set_center_frequency(frequency_hz)
                for _ in range(self.discard_blocks):
                    self.source.read_iq()
                block = self.source.read_iq()
                if block.center_frequency_hz != frequency_hz:
                    raise RuntimeError("stale IQ block after retuning")
                return measure_channel_power(
                    block, channel_width_hz=self.channel_width_hz,
                )
            finally:
                self.source.set_center_frequency(previous)
        finally:
            self._lock.release()
