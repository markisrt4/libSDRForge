# SPDX-License-Identifier: MIT
"""Local PCM playback with independently controllable mute and volume."""
from __future__ import annotations

from threading import RLock
from typing import Any

import numpy as np


class LocalAudioSink:
    """Output decoded 48 kHz PCM without owning the SDR or DSP lifecycle."""

    def __init__(self, *, sample_rate: int = 48_000, volume: float = 1.0) -> None:
        self._sample_rate = sample_rate
        self._volume = float(volume)
        self._muted = False
        self._stream: Any = None
        self._channels: int | None = None
        self._lock = RLock()

    @property
    def muted(self) -> bool:
        with self._lock:
            return self._muted

    def set_muted(self, muted: bool) -> None:
        with self._lock:
            self._muted = bool(muted)

    def set_volume(self, volume: float) -> None:
        if not 0.0 <= volume <= 1.0:
            raise ValueError("volume must be between 0 and 1")
        with self._lock:
            self._volume = float(volume)

    def write(self, audio: np.ndarray) -> None:
        pcm = np.asarray(audio, dtype=np.float32)
        if pcm.size == 0:
            return
        if pcm.ndim == 1:
            pcm = pcm.reshape(-1, 1)
        if pcm.ndim != 2 or pcm.shape[1] not in (1, 2):
            raise ValueError("expected mono or stereo PCM frames")
        with self._lock:
            if self._muted:
                return
            if self._stream is None or self._channels != pcm.shape[1]:
                self._close_stream()
                try:
                    import sounddevice as sd
                except ImportError as exc:
                    raise RuntimeError("Linux audio requires libsdrforge[audio]") from exc
                self._stream = sd.OutputStream(
                    samplerate=self._sample_rate, channels=pcm.shape[1],
                    dtype="float32", latency="high",
                )
                self._stream.start()
                self._channels = pcm.shape[1]
            self._stream.write(np.ascontiguousarray(
                np.clip(pcm * self._volume, -1.0, 1.0)
            ))

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
            finally:
                self._stream.close()
                self._stream = None
                self._channels = None

    def close(self) -> None:
        with self._lock:
            self._close_stream()
