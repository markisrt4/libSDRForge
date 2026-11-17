"""Bounded chunked SAME AFSK capture and confirmation.

Reference implementation: accumulates audio across arbitrary feed boundaries,
then decodes on flush(). No alert is emitted from a partial capture.
Live low-latency symbol tracking and noise resilience remain future work.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .same_afsk import decode_same_audio
from .same_messages import SameMessages, confirm_same_messages


@dataclass(frozen=True)
class SameCaptureResult:
    decoded_bytes: bytes
    messages: SameMessages
    truncated: bool


class StreamingSameCapture:
    """Bounded recorder with deterministic chunk handling.

    The name denotes streaming *input*, not incremental symbol decoding.
    Call flush at the end of a SAME burst. Truncated captures are untrusted:
    no alert confirmation is returned if earlier audio was discarded.
    """

    def __init__(self, sample_rate: int, *, max_seconds: float = 15.0) -> None:
        if sample_rate < 8000:
            raise ValueError("sample_rate must be at least 8000")
        if not 0 < max_seconds <= 120:
            raise ValueError("max_seconds must be in (0, 120]")
        self.sample_rate = sample_rate
        self.max_samples = max(1, int(sample_rate * max_seconds))
        self.reset()

    def reset(self) -> None:
        self._chunks: list[np.ndarray] = []
        self._length = 0
        self._truncated = False

    @property
    def buffered_samples(self) -> int:
        return self._length

    @property
    def truncated(self) -> bool:
        return self._truncated

    def feed(self, pcm: np.ndarray) -> None:
        audio = np.asarray(pcm)
        if audio.ndim != 1 or not np.issubdtype(audio.dtype, np.number):
            raise ValueError("pcm must be one-dimensional numeric audio")
        if not np.all(np.isfinite(audio)):
            raise ValueError("pcm must contain only finite samples")
        if not len(audio):
            return
        # Retain independent storage; callers may reuse their input buffers.
        chunk = np.array(audio, dtype=np.float32, copy=True)
        if len(chunk) >= self.max_samples:
            self._truncated |= self._length > 0 or len(chunk) > self.max_samples
            self._chunks = [chunk[-self.max_samples:].copy()]
            self._length = self.max_samples
            return
        self._chunks.append(chunk)
        self._length += len(chunk)
        while self._length > self.max_samples:
            overflow = self._length - self.max_samples
            oldest = self._chunks[0]
            if len(oldest) <= overflow:
                self._chunks.pop(0)
                self._length -= len(oldest)
            else:
                self._chunks[0] = oldest[overflow:].copy()
                self._length -= overflow
            self._truncated = True

    def flush(self) -> SameCaptureResult:
        audio = (np.concatenate(self._chunks) if self._chunks
                 else np.empty(0, dtype=np.float32))
        truncated = self._truncated
        self.reset()
        decoded = decode_same_audio(audio, self.sample_rate)
        # A partial rolling window cannot establish repeated transmissions.
        messages = (SameMessages((), False) if truncated
                    else confirm_same_messages(decoded))
        return SameCaptureResult(decoded, messages, truncated)
