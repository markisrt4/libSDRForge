# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""!
@brief Hardware-independent FM acquisition session and stream continuity handling.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Literal, Self

import numpy as np

from sdrforge.adapters import RtlSdrSource
from sdrforge.diagnostics import DspPerformanceMonitor, DspPerformanceSnapshot
from sdrforge.interfaces.sdr_source_if import SdrSourceIf
from sdrforge.models.iq import IqBlock
from sdrforge.protocols.rds.receiver_controller import RdsReceiverStatus
from sdrforge.receivers import AmMonoDemodulator, NbfmMonoDemodulator, WbfmReceiver


@dataclass(frozen=True)
class RadioFrame:
    """!
    @brief One decoded PCM block and its current RDS metadata.
    """
    audio: np.ndarray
    rds: RdsReceiverStatus | None


@dataclass(frozen=True)
class RadioSessionStatus:
    """!
    @brief Acquisition and processing counters.
    """
    started: bool
    processed_blocks: int
    processed_iq_samples: int
    discontinuities: int
    last_error: str | None
    stereo_locked: bool
    stereo_blend: float
    performance: DspPerformanceSnapshot


class RadioSession:
    """!
    @brief Own RF warmup, discontinuity recovery, and one WFM receiver.

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
        iq_observer: Callable[[IqBlock], None] | None = None,
    ) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param frequency_hz The ``frequency_hz`` value.
        @param mode The ``mode`` value.
        @param rds_enabled The ``rds_enabled`` value.
        @param gain_db The ``gain_db`` value.
        @param rf_warmup_seconds The ``rf_warmup_seconds`` value.
        @param source The ``source`` value.
        @param iq_observer The ``iq_observer`` value.
        """
        if frequency_hz <= 0 or rf_warmup_seconds < 0:
            raise ValueError("frequency must be positive and warmup nonnegative")
        self.frequency_hz = frequency_hz
        self.acquisition_frequency_hz = frequency_hz
        self._receiver_mode = mode
        self._demodulation = "WFM"
        self._channel_bandwidth_hz = 200_000
        self._rds_enabled = rds_enabled
        self.gain_db = gain_db
        self.rf_warmup_seconds = rf_warmup_seconds
        self.source = source if source is not None else RtlSdrSource()
        self.iq_observer = iq_observer
        self.observer_errors = 0
        self.receiver: WbfmReceiver | AmMonoDemodulator | NbfmMonoDemodulator = WbfmReceiver(
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

    @classmethod
    def fm(
        cls, frequency_mhz: float, *,
        stereo: bool = True,
        rds: bool = False,
        gain_db: float | None = None,
        source: SdrSourceIf | None = None,
        rf_warmup_seconds: float = 2.0,
    ) -> RadioSession:
        """!
        @brief Create an FM session using MHz instead of integer Hz.

        Capture is asynchronous when supported by the default RTL-SDR adapter.
        Pass an injected source for hardware-free or alternate-hardware use.

        @param cls The current class.
        @param frequency_mhz The ``frequency_mhz`` value.
        @param stereo The ``stereo`` value.
        @param rds The ``rds`` value.
        @param gain_db The tuner gain in decibels, or ``None`` for automatic gain.
        @param source The ``source`` value.
        @param rf_warmup_seconds The ``rf_warmup_seconds`` value.
        @return The operation result.
        """
        if not np.isfinite(frequency_mhz) or not 87.5 <= frequency_mhz <= 108.0:
            raise ValueError("FM frequency must be between 87.5 and 108.0 MHz")
        if rds and not stereo:
            raise ValueError("RDS requires stereo reception")
        return cls(
            frequency_hz=round(frequency_mhz * 1_000_000),
            mode="stereo" if stereo else "mono",
            rds_enabled=rds,
            gain_db=gain_db,
            source=source,
            rf_warmup_seconds=rf_warmup_seconds,
        )

    @property
    def status(self) -> RadioSessionStatus:
        """!
        @brief Return the status.

        @param self The current instance.
        @return The operation result.
        """
        return RadioSessionStatus(
            self._started, self._blocks, self._samples,
            self._discontinuities, self._last_error,
            getattr(self.receiver, "stereo_locked", False), getattr(self.receiver, "stereo_blend", 0.0),
            self.performance.snapshot(),
        )

    @property
    def demodulation(self) -> str:
        """!
        @brief Return the active audio demodulation mode.
        @param self The current instance.
        @return The operation result.
        """
        return self._demodulation

    @property
    def channel_bandwidth_hz(self) -> int:
        """!
        @brief Return the configured channel bandwidth in hertz.
        @param self The current instance.
        @return The operation result.
        """
        return self._channel_bandwidth_hz

    def start(self) -> None:
        """!
        @brief Start the component.

        @param self The current instance.
        """
        if self._started:
            return
        self.source.open()
        try:
            self.source.set_sample_rate(2_400_000)
            self.source.set_gain(self.gain_db)
            self.source.set_center_frequency(self.frequency_hz)
            self.acquisition_frequency_hz = self.frequency_hz
            self._reset_receiver()
            self.source.start()
            target = round(self.rf_warmup_seconds * 2_400_000)
            consumed = 0
            while consumed < target:
                block = self.source.read_iq()
                self._validate_block(block)
                consumed += len(block.samples) // 2
            if target:
                self._reset_receiver()
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

    def _reset_receiver(self, *, preserve_metadata: bool = False) -> None:
        if isinstance(self.receiver, WbfmReceiver):
            self.receiver.channel_frequency_hz = self.frequency_hz
            self.receiver.reset(preserve_metadata=preserve_metadata)
        else:
            self.receiver = (AmMonoDemodulator(channel_bandwidth_hz=self._channel_bandwidth_hz)
                             if self._demodulation == "AM"
                             else NbfmMonoDemodulator(channel_bandwidth_hz=self._channel_bandwidth_hz))
            self.receiver.channel_frequency_hz = self.frequency_hz

    def set_demodulation(self, mode: str, bandwidth_hz: int = 0) -> None:
        """!
        @brief Select the live DSP without reopening the shared SDR source.
        @param self The current instance.
        @param mode The mode value.
        @param bandwidth_hz The bandwidth hz value.
        """
        canonical = "WFM" if mode.upper() == "FM" else mode.upper()
        defaults = {"WFM": 200_000, "NFM": 25_000, "AM": 25_000}
        if canonical not in defaults:
            raise ValueError(f"unsupported demodulation mode: {mode}")
        bandwidth = bandwidth_hz or defaults[canonical]
        if canonical == "WFM" and bandwidth not in (180_000, 200_000):
            raise ValueError("WFM bandwidth must be 180000 or 200000 Hz")
        supported = {"NFM": (7_500, 12_500, 25_000),
                     "AM": (6_000, 10_000, 12_500, 25_000)}
        if canonical in supported and bandwidth not in supported[canonical]:
            raise ValueError(f"unsupported {canonical} channel bandwidth: {bandwidth}")
        if (canonical, bandwidth) == (self._demodulation, self._channel_bandwidth_hz):
            return
        if canonical == "WFM":
            receiver: WbfmReceiver | AmMonoDemodulator | NbfmMonoDemodulator = WbfmReceiver(
                channel_frequency_hz=self.frequency_hz,
                mode=self._receiver_mode, rds_enabled=self._rds_enabled,
            )
        elif canonical == "AM":
            receiver = AmMonoDemodulator(channel_bandwidth_hz=bandwidth)
        else:
            receiver = NbfmMonoDemodulator(channel_bandwidth_hz=bandwidth)
        if self._started and not self._channel_fits(self.frequency_hz, bandwidth):
            self.source.set_center_frequency(self.frequency_hz)
            self.acquisition_frequency_hz = self.frequency_hz
        if isinstance(self.receiver, WbfmReceiver):
            self.receiver.close()
        receiver.channel_frequency_hz = self.frequency_hz
        self.receiver = receiver
        self._demodulation = canonical
        self._channel_bandwidth_hz = bandwidth
        self._last_timestamp_ns = None
        self._last_dropped_blocks = None

    def _channel_fits(self, frequency_hz: int, bandwidth_hz: int) -> bool:
        return abs(frequency_hz - self.acquisition_frequency_hz) + bandwidth_hz / 2 < 1_200_000

    def retune(self, frequency_hz: int) -> None:
        """!
        @brief Retune an open source without releasing its USB handle.
        @param self The current instance.
        @param frequency_hz The frequency hz value.
        """
        if frequency_hz <= 0:
            raise ValueError("frequency must be positive")
        if not self._started:
            self.frequency_hz = frequency_hz
            return
        if frequency_hz == self.frequency_hz:
            return
        if not self._channel_fits(frequency_hz, self._channel_bandwidth_hz):
            self.source.set_center_frequency(frequency_hz)
            self.acquisition_frequency_hz = frequency_hz
        self.frequency_hz = frequency_hz
        if isinstance(self.receiver, WbfmReceiver):
            self.receiver.close()
        if self._demodulation == "WFM":
            self.receiver = WbfmReceiver(
                channel_frequency_hz=frequency_hz,
                mode=self._receiver_mode, rds_enabled=self._rds_enabled,
            )
        else:
            self.receiver = (AmMonoDemodulator(channel_bandwidth_hz=self._channel_bandwidth_hz)
                             if self._demodulation == "AM"
                             else NbfmMonoDemodulator(channel_bandwidth_hz=self._channel_bandwidth_hz))
            self.receiver.channel_frequency_hz = self.frequency_hz
        self._last_timestamp_ns = None
        self._last_dropped_blocks = None

    def stop(self) -> None:
        """!
        @brief Stop the component.

        @param self The current instance.
        """
        if not self._started:
            return
        try:
            self.source.stop()
        finally:
            self._started = False
            self.source.close()
            self._reset_receiver()
            self._last_timestamp_ns = None
            self._last_dropped_blocks = None

    def __enter__(self) -> Self:
        """!
        @brief Enter the managed context.

        @param self The current instance.
        @return The operation result.
        """
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """!
        @brief Exit the managed context.

        @param self The current instance.
        @param exc_type The ``exc_type`` value.
        @param exc The ``exc`` value.
        @param tb The ``tb`` value.
        """
        self.stop()

    def _validate_block(self, block: object) -> None:
        from sdrforge.models.iq import IqBlock

        if not isinstance(block, IqBlock):
            raise TypeError("source must return IqBlock")
        if block.sample_rate_hz != 2_400_000:
            raise ValueError("unexpected source sample rate")
        if block.center_frequency_hz != self.acquisition_frequency_hz:
            raise ValueError("unexpected source center frequency")

    def _dropped_blocks(self) -> int | None:
        stats_fn = getattr(self.source, "get_acquisition_stats", None)
        if not callable(stats_fn):
            return None
        value = stats_fn().get("dropped_blocks")
        return int(value) if value is not None else None

    def read(self) -> RadioFrame:
        """!
        @brief Decode one block, resetting DSP after gaps while preserving RDS.

        @param self The current instance.
        @return The operation result.
        """
        if not self._started:
            raise RuntimeError("radio session is not started")
        try:
            block = self.source.read_iq()
            self._validate_block(block)
            if self.iq_observer is not None:
                try:
                    self.iq_observer(block)
                except Exception:  # noqa: BLE001 - optional telemetry must not break audio
                    self.observer_errors += 1
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
                self._reset_receiver(preserve_metadata=True)
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
            return RadioFrame(audio=audio, rds=getattr(self.receiver, "rds_status", None))
        except Exception as exc:
            self._last_error = str(exc)
            self._reset_receiver()
            self._last_timestamp_ns = None
            raise

    def stream(self) -> Iterator[RadioFrame]:
        """!
        @brief Yield decoded blocks until stopped or acquisition raises.

        @param self The current instance.
        @return The operation result.
        """
        while self._started:
            yield self.read()
