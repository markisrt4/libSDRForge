"""!
@brief Explicit auxiliary IQ source pump for NOAA weather transcription.
"""

from __future__ import annotations

from typing import Any

from sdrforge.models.iq import IqSampleFormat


class AuxiliaryNoaaSourcePump:
    """!
    @brief Read IQ from an injected auxiliary source into the NOAA DSP bridge.
    """

    def __init__(self, source: Any, bridge: Any, *, weather_frequency_hz: int) -> None:
        """!
        @brief Provide   init   behavior.
        @param self The current instance.
        @param source The source value.
        @param bridge The bridge value.
        @param weather_frequency_hz The weather frequency hz value.
        """
        if source is None or bridge is None:
            raise ValueError("explicit auxiliary source and bridge are required")
        if weather_frequency_hz <= 0:
            raise ValueError("weather_frequency_hz must be positive")
        self.source = source
        self.bridge = bridge
        self.weather_frequency_hz = weather_frequency_hz
        self.blocks = 0
        self.samples = 0

    def pump_once(self) -> int:
        # Validate lease before read, then validate the block after read to
        # reject buffered IQ from a prior service or stale tuner setting.
        """!
        @brief Provide pump once behavior.
        @param self The current instance.
        @return The operation result.
        """
        self.bridge.session.require_weather()
        block = self.source.read_iq()
        if block.center_frequency_hz != self.weather_frequency_hz:
            raise RuntimeError(
                f"auxiliary IQ frequency mismatch: {block.center_frequency_hz} "
                f"!= {self.weather_frequency_hz}"
            )
        if block.sample_rate_hz != 2_400_000:
            raise ValueError("NOAA IQ source requires 2.4 MSPS")
        if block.sample_format != IqSampleFormat.U8_INTERLEAVED:
            raise ValueError("NOAA IQ source requires interleaved unsigned 8-bit IQ")
        count = int(self.bridge.process(block))
        self.blocks += 1
        self.samples += count
        return count
