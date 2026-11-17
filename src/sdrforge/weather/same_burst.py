"""Energy-gated SAME burst segmentation for offline and chunked PCM.

This is an experimental capture segmenter, not a validated live RF detector.
Decoded messages are confirmed only from repeated matching SAME headers.
"""
from __future__ import annotations

import numpy as np

from .same_stream import StreamingSameCapture
from .same_messages import SameMessages, confirm_same_messages
from .same_tone_gate import is_same_tone_candidate


class SameBurstDetector:
    """Detect candidate AFSK bursts using frame RMS and silence duration.

    Processes complete analysis frames while retaining partial frames across
    feed calls. Captures consecutive bursts until finish(), then confirms
    matching headers. Silence and arbitrary chunk boundaries are tolerated.
    Optional tone_gate narrows acquisition to likely SAME frequencies.
    It is disabled by default to preserve the legacy energy-only behavior.
    This gate is not a substitute for repeated-header confirmation.
    """

    def __init__(self, sample_rate: int, *, frame_ms: int = 20,
                 threshold_rms: float = 0.08, silence_ms: int = 180,
                 max_burst_seconds: float = 8.0,
                 tone_gate: bool = False,
                 min_tone_fraction: float = 0.40) -> None:
        if sample_rate < 8000:
            raise ValueError("sample_rate must be at least 8000")
        if frame_ms <= 0 or silence_ms <= 0:
            raise ValueError("frame_ms and silence_ms must be positive")
        if not 0 < threshold_rms < 1:
            raise ValueError("threshold_rms must be in (0, 1)")
        if not 0 < min_tone_fraction <= 1:
            raise ValueError("min_tone_fraction must be in (0, 1]")
        self.tone_gate = tone_gate
        self.min_tone_fraction = min_tone_fraction
        self.sample_rate = sample_rate
        self.frame_samples = max(1, round(sample_rate * frame_ms / 1000))
        self.silent_frames = max(1, (silence_ms + frame_ms - 1) // frame_ms)
        self.threshold_rms = threshold_rms
        self.capture = StreamingSameCapture(sample_rate, max_seconds=max_burst_seconds)
        self.reset()

    def reset(self) -> None:
        self.capture.reset()
        self._pending = np.empty(0, dtype=np.float32)
        self._active = False
        self._quiet = 0
        self._decoded: list[bytes] = []
        self._truncated = False

    def _close_burst(self) -> None:
        result = self.capture.flush()
        if result.truncated:
            self._truncated = True
        elif result.decoded_bytes:
            self._decoded.append(result.decoded_bytes)
        self._active = False
        self._quiet = 0

    def _frame(self, frame: np.ndarray) -> None:
        rms = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))
        loud = rms >= self.threshold_rms
        # Apply spectral gating only to burst acquisition, not to every
        # subsequent frame. Individual SAME bits may lack both tones, and
        # a noisy frame must not prematurely end an active capture.
        candidate = loud and (not self.tone_gate or is_same_tone_candidate(
            frame, self.sample_rate, min_fraction=self.min_tone_fraction,
            min_rms=self.threshold_rms))
        if candidate and not self._active:
            self._active = True
            self._quiet = 0
        if not self._active:
            return
        self.capture.feed(frame)
        self._quiet = 0 if loud else self._quiet + 1
        if self._quiet >= self.silent_frames:
            self._close_burst()

    def feed(self, pcm: np.ndarray) -> None:
        audio = np.asarray(pcm)
        if audio.ndim != 1 or not np.issubdtype(audio.dtype, np.number):
            raise ValueError("pcm must be mono numeric samples")
        if not np.all(np.isfinite(audio)):
            raise ValueError("pcm must be finite")
        if not len(audio):
            return
        data = np.concatenate((self._pending, np.asarray(audio, dtype=np.float32)))
        frame_size = self.frame_samples
        complete = len(data) // frame_size
        for index in range(complete):
            self._frame(data[index * frame_size:(index + 1) * frame_size])
        self._pending = data[complete * frame_size:].copy()

    def finish(self) -> SameMessages:
        """Finish pending frames, decode bursts, and return confirmed messages."""
        if len(self._pending):
            # Do not pad with signal; frame RMS uses available samples.
            self._frame(self._pending)
            self._pending = np.empty(0, dtype=np.float32)
        if self._active:
            self._close_burst()
        decoded = b"\x00".join(self._decoded)
        messages = (SameMessages((), False) if self._truncated
                    else confirm_same_messages(decoded))
        self.reset()
        return messages
