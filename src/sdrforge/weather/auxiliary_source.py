"""Explicit auxiliary IQ source pump for NOAA weather transcription.

The caller owns opening, tuning, starting, stopping and closing the SDR source.
No implicit device selection or primary receiver fallback is allowed.
"""
from __future__ import annotations

from sdrforge.models.iq import IqSampleFormat


class AuxiliaryNoaaSourcePump:
    """Read IQ from an injected auxiliary source into the NOAA DSP bridge.

    Caller must acquire and start an independent auxiliary SDR source before
    calling pump_once(). Fail closed if the source has been retuned, including
    after scheduler transitions to TMC or ADS-B.
    """

    def __init__(self, source, bridge, *, weather_frequency_hz: int) -> None:
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
        count = self.bridge.process(block)
        self.blocks += 1
        self.samples += count
        return count
