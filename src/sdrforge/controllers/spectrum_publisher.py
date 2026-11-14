# SPDX-License-Identifier: MIT
"""Hardware-independent, rate-limited spectrum publication."""
from __future__ import annotations

from collections import deque
from threading import RLock

import numpy as np

from sdrforge.models.spectrum_frame import SpectrumFrame, spectrum_from_iq


class SpectrumSubscription:
    """Bounded queue of immutable frames; oldest frames drop on overflow."""

    def __init__(self, max_frames: int) -> None:
        if max_frames < 1:
            raise ValueError("max_frames must be positive")
        self._frames: deque[SpectrumFrame] = deque(maxlen=max_frames)
        self._lock = RLock()
        self._closed = False

    def _offer(self, frame: SpectrumFrame) -> None:
        with self._lock:
            if not self._closed:
                self._frames.append(frame)

    def poll(self) -> SpectrumFrame | None:
        """Return the oldest pending frame without blocking."""
        with self._lock:
            return self._frames.popleft() if self._frames else None

    def poll_latest(self) -> SpectrumFrame | None:
        """Return the newest frame, discarding obsolete queued frames."""
        with self._lock:
            if not self._frames:
                return None
            frame = self._frames[-1]
            self._frames.clear()
            return frame

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._frames.clear()


class SpectrumPublisher:
    """Convert incoming IQ blocks to FFT frames at a bounded output rate.

    Timestamps are monotonic nanoseconds supplied by the caller. The IQ
    producer owns sampling and hardware; this publisher owns no device.
    """

    def __init__(self, *, fft_size: int = 2048, max_fps: float = 15.0) -> None:
        if fft_size < 2 or max_fps <= 0:
            raise ValueError("invalid spectrum configuration")
        self.fft_size = fft_size
        self._period_ns = max(1, int(1_000_000_000 / max_fps))
        self._lock = RLock()
        self._last_timestamp_ns: int | None = None
        self._subscribers: set[SpectrumSubscription] = set()

    def subscribe(self, *, max_frames: int = 3) -> SpectrumSubscription:
        subscription = SpectrumSubscription(max_frames)
        with self._lock:
            self._subscribers.add(subscription)
        return subscription

    def unsubscribe(self, subscription: SpectrumSubscription) -> None:
        with self._lock:
            self._subscribers.discard(subscription)
        subscription.close()

    def reset(self) -> None:
        """Allow immediate publication after retuning or stream restart."""
        with self._lock:
            self._last_timestamp_ns = None

    def publish_iq(
        self, iq: np.ndarray, *, center_frequency_hz: int,
        sample_rate_hz: int, timestamp_ns: int,
    ) -> SpectrumFrame | None:
        """Publish a frame if its timestamp passes the frame-rate gate.

        Returns None when throttled. No callback executes on the IQ thread.
        """
        with self._lock:
            last = self._last_timestamp_ns
            if last is not None and 0 <= timestamp_ns - last < self._period_ns:
                return None
            samples = np.asarray(iq)
            if samples.ndim != 1 or len(samples) < self.fft_size:
                raise ValueError("IQ block shorter than configured FFT")
            frame = spectrum_from_iq(
                samples[-self.fft_size:],
                center_frequency_hz=center_frequency_hz,
                sample_rate_hz=sample_rate_hz,
                timestamp_ns=timestamp_ns,
            )
            self._last_timestamp_ns = timestamp_ns
            for subscriber in self._subscribers:
                subscriber._offer(frame)
            return frame
