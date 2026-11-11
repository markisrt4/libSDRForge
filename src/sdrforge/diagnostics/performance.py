# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Low-overhead DSP timing and steady-state RF processing metrics."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class DspPerformanceSnapshot:
    blocks: int
    samples: int
    dsp_mean_ms: float
    dsp_max_ms: float
    dsp_recent_mean_ms: float
    rf_mean_ms: float
    dsp_utilization: float
    recent_dsp_utilization: float
    over_budget_blocks: int
    steady_processing_msps: float | None
    steady_rf_msps: float | None
    steady_elapsed_s: float
    steady_blocks: int


class DspPerformanceMonitor:
    """Measure DSP work against RF block duration, excluding startup for steady rate.

    The steady rate uses a wall-clock window starting after warmup_seconds;
    it is not a tuner sample-rate measurement. RF rate is measured from the
    sum of input block durations, while processing rate uses wall time.
    """

    def __init__(self, *, sample_rate_hz: int = 2_400_000,
                 warmup_seconds: float = 5.0, recent_blocks: int = 64,
                 clock: Callable[[], float] = time.perf_counter) -> None:
        if sample_rate_hz <= 0 or warmup_seconds < 0 or recent_blocks < 1:
            raise ValueError("invalid DSP monitor configuration")
        self.sample_rate_hz = sample_rate_hz
        self.warmup_seconds = warmup_seconds
        self._clock = clock
        self._start = clock()
        self._recent: deque[tuple[float, float]] = deque(maxlen=recent_blocks)
        self._blocks = 0
        self._samples = 0
        self._dsp_s = 0.0
        self._rf_s = 0.0
        self._max_s = 0.0
        self._over_budget = 0
        self._steady_start: float | None = None
        self._steady_samples = 0
        self._steady_rf_s = 0.0
        self._steady_blocks = 0

    def record(self, *, samples: int, dsp_seconds: float,
               completed_at: float | None = None) -> None:
        if samples <= 0 or dsp_seconds < 0:
            raise ValueError("samples must be positive and DSP time nonnegative")
        now = self._clock() if completed_at is None else completed_at
        rf_s = samples / self.sample_rate_hz
        self._blocks += 1
        self._samples += samples
        self._dsp_s += dsp_seconds
        self._rf_s += rf_s
        self._max_s = max(self._max_s, dsp_seconds)
        self._recent.append((dsp_seconds, rf_s))
        if dsp_seconds > rf_s:
            self._over_budget += 1
        if now - self._start >= self.warmup_seconds:
            if self._steady_start is None:
                self._steady_start = now - dsp_seconds
            self._steady_samples += samples
            self._steady_rf_s += rf_s
            self._steady_blocks += 1

    def snapshot(self) -> DspPerformanceSnapshot:
        now = self._clock()
        recent_dsp = sum(d for d, _ in self._recent)
        recent_rf = sum(r for _, r in self._recent)
        steady_elapsed = (max(0.0, now - self._steady_start)
                          if self._steady_start is not None else 0.0)
        return DspPerformanceSnapshot(
            blocks=self._blocks,
            samples=self._samples,
            dsp_mean_ms=round(self._dsp_s * 1000 / self._blocks, 3) if self._blocks else 0.0,
            dsp_max_ms=round(self._max_s * 1000, 3),
            dsp_recent_mean_ms=round(recent_dsp * 1000 / len(self._recent), 3)
            if self._recent else 0.0,
            rf_mean_ms=round(self._rf_s * 1000 / self._blocks, 3) if self._blocks else 0.0,
            dsp_utilization=round(self._dsp_s / self._rf_s, 4) if self._rf_s else 0.0,
            recent_dsp_utilization=round(recent_dsp / recent_rf, 4) if recent_rf else 0.0,
            over_budget_blocks=self._over_budget,
            steady_processing_msps=round(self._steady_samples / steady_elapsed / 1e6, 3)
            if steady_elapsed > 0 else None,
            steady_rf_msps=round(self._steady_rf_s / steady_elapsed * self.sample_rate_hz / 1e6, 3)
            if steady_elapsed > 0 else None,
            steady_elapsed_s=round(steady_elapsed, 3),
            steady_blocks=self._steady_blocks,
        )
