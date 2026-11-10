# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Hardware-independent FM acquisition session and stream continuity handling."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Iterator, Literal

import numpy as np

from sdrforge.adapters import RtlSdrSource
from sdrforge.diagnostics import DspPerformanceMonitor, DspPerformanceSnapshot
from sdrforge.interfaces.sdr_source import SdrSourceIf
from sdrforge.protocols.rds.receiver_controller import RdsReceiverStatus
from sdrforge.receivers import WbfmReceiver


@dataclass(frozen=True)
class RadioFrame:
    """One decoded PCM block and its current RDS metadata."""
    audio: np.ndarray
    rds: RdsReceiverStatus | None


@dataclass(frozen=True)
class RadioSessionStatus:
    """Acquisition and processing counters."""
    started: bool
    processed_blocks: int
    processed_iq_samples: int
    discontinuities: int
    last_error: str | None
    stereo_locked: bool
    stereo_blend: float
    performance: DspPerformanceSnapshot


class RadioSession:
    """Own RF warmup, discontinuity recovery, and one WFM receiver.

    Source injection keeps tests independent of USB and allows future SDR
    adapters. The caller controls the iteration lifetime.
    """

    def __init__(
        self, *, frequency_hz: int,
        mode: Literal["mono", "stereo"] = "stereo",
        rds_enabled: bool = False,
        gain_db: float | None = 29.7,
        rf_warmup_seconds: float = 2.0,
        source: SdrSourceIf | None = None,
    ) -> None:
        if frequency_hz <= 0 or rf_warmup_seconds < 0:
            raise ValueError("frequency must be positive and warmup nonnegative")
        self.frequency_hz = frequency_hz
        self.gain_db = gain_db
        self.rf_warmup_seconds = rf_warmup_seconds
        self.source = source if source is not None else RtlSdrSource()
        self.receiver = WbfmReceiver(
            channel_frequency_hz=frequency_hz, mode=mode, rds_enabled=rds_enabled
        )
        self.performance = DspPerformanceMonitor()
        self._started = False
        self._blocks = 0
        self._samples = 0
        self._discontinuities = 0
        self._last_error: str | None = None
        self._last_timestamp_ns: int | None = None
        self._last_duration_ns = 0
        self._last_dropped_blocks: int | None = None

    @property
    def status(self) -> RadioSessionStatus:
        return RadioSessionStatus(
            self._started, self._blocks, self._samples,
            self._discontinuities, self._last_error,
            self.receiver.stereo_locked, self.receiver.stereo_blend,
            self.performance.snapshot(),
        )

    def start(self) -> None:
        if self._started:
            return
        self.source.open()
        try:
            self.source.set_sample_rate(2_400_000)
            self.source.set_gain(self.gain_db)
            self.source.set_center_frequency(self.frequency_hz)
            self.receiver.reset()
            self.source.start()
            target = round(self.rf_warmup_seconds * 2_400_000)
            consumed = 0
            while consumed < target:
                block = self.source.read_iq()
                self._validate_block(block)
                consumed += len(block.samples) // 2
            if target:
                self.receiver.reset()
        except Exception as exc:
            self._last_error = str(exc)
            self.source.close()
            raise
        self.performance = DspPerformanceMonitor()
        self._last_timestamp_ns = None
        self._last_duration_ns = 0
        self._last_dropped_blocks = None
        self._last_error = None
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        try:
            self.source.stop()
        finally:
            self._started = False
            self.source.close()
            self.receiver.reset()
            self._last_timestamp_ns = None
            self._last_dropped_blocks = None

    def __enter__(self) -> RadioSession:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.stop()

    def _validate_block(self, block: object) -> None:
        from sdrforge.models.iq import IqBlock

        if not isinstance(block, IqBlock):
            raise TypeError("source must return IqBlock")
        if block.sample_rate_hz != 2_400_000:
            raise ValueError("unexpected source sample rate")
        if block.center_frequency_hz != self.frequency_hz:
            raise ValueError("unexpected source center frequency")

    def _dropped_blocks(self) -> int | None:
        stats_fn = getattr(self.source, "get_acquisition_stats", None)
        if not callable(stats_fn):
            return None
        value = stats_fn().get("dropped_blocks")
        return int(value) if value is not None else None

    def read(self) -> RadioFrame:
        """Decode one block, resetting DSP after gaps while preserving RDS."""
        if not self._started:
            raise RuntimeError("radio session is not started")
        try:
            block = self.source.read_iq()
            self._validate_block(block)
            dropped = self._dropped_blocks()
            gap = (
                self._last_timestamp_ns is not None
                and block.timestamp_ns > self._last_timestamp_ns
                + max(self._last_duration_ns * 2, 20_000_000)
            )
            dropped_changed = (
                dropped is not None and self._last_dropped_blocks is not None
                and dropped > self._last_dropped_blocks
            )
            if gap or dropped_changed:
                self.receiver.reset(preserve_metadata=True)
                self._discontinuities += 1
            started = time.perf_counter()
            try:
                audio = self.receiver.process(block)
            finally:
                self.performance.record(
                    samples=len(block.samples) // 2,
                    dsp_seconds=time.perf_counter() - started,
                )
            self._last_timestamp_ns = block.timestamp_ns
            self._last_duration_ns = round(
                len(block.samples) * 1_000_000_000 / (2 * 2_400_000)
            )
            self._last_dropped_blocks = dropped
            self._blocks += 1
            self._samples += len(block.samples) // 2
            return RadioFrame(audio=audio, rds=self.receiver.rds_status)
        except Exception as exc:
            self._last_error = str(exc)
            self.receiver.reset()
            self._last_timestamp_ns = None
            raise

    def stream(self) -> Iterator[RadioFrame]:
        """Yield decoded blocks until stopped or acquisition raises."""
        while self._started:
            yield self.read()
