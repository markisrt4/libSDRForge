"""!
@brief Chunked ADS-B IQ demodulation with bounded frame overlap.
"""

from __future__ import annotations

import numpy as np

from .iq_demodulator import demodulate_frames


class StreamingAdsbDemodulator:
    """!
    @brief Emit each complete DF17 frame once across arbitrary IQ chunk boundaries.
    Retain the last 120 microseconds of samples. Since the block demodulator
    only examines complete frames, any frame spanning a chunk boundary will
    first become eligible on a later feed.
    """

    def __init__(self, sample_rate: float, *, threshold: float = 4.0):
        """!
        @brief Handle   init  .
        @param self The current instance.
        @param sample_rate The sample rate value.
        @param threshold The threshold value.
        """
        if not np.isfinite(sample_rate) or sample_rate < 2e6:
            raise ValueError("sample_rate must be finite and >= 2 MS/s")
        if threshold <= 1:
            raise ValueError("threshold must be > 1")
        self.sample_rate = sample_rate
        self.threshold = threshold
        self._frame_samples = int(np.ceil(120 * sample_rate / 1e6))
        self._pending = np.empty(0, dtype=np.complex64)

    @property
    def buffered_samples(self) -> int:
        """!
        @brief Handle buffered samples.
        @param self The current instance.
        @return The operation result.
        """
        return len(self._pending)

    def reset(self) -> None:
        """!
        @brief Handle reset.
        @param self The current instance.
        """
        self._pending = np.empty(0, dtype=np.complex64)

    def feed(self, iq: np.ndarray) -> tuple[bytes, ...]:
        """!
        @brief Handle feed.
        @param self The current instance.
        @param iq The iq value.
        @return The operation result.
        """
        chunk = np.asarray(iq)
        if chunk.ndim != 1:
            raise ValueError("iq must be one-dimensional")
        if not np.issubdtype(chunk.dtype, np.number):
            raise ValueError("iq must be numeric")
        if len(chunk) == 0:
            return ()
        combined = np.concatenate((self._pending, chunk.astype(np.complex64)))
        # Leave one full frame minus one sample for next time. This ensures
        # every candidate start is examined once with a complete frame.
        keep = self._frame_samples - 1
        if len(combined) < self._frame_samples:
            self._pending = combined
            return ()
        frames = demodulate_frames(combined, self.sample_rate, threshold=self.threshold)
        self._pending = combined[-keep:].copy()
        return frames
