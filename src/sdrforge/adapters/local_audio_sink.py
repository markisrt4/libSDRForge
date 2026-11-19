# SPDX-License-Identifier: MIT
"""!
@brief Local PCM playback with independently controllable mute and volume.
"""
from __future__ import annotations

from collections import deque
from threading import RLock
from typing import Any

import numpy as np


class LocalAudioSink:
    """!
    @brief Output decoded 48 kHz PCM without owning the SDR or DSP lifecycle.
    """

    def __init__(self, *, sample_rate: int = 48_000, volume: float = 1.0) -> None:
        """!
        @brief Handle   init  .
        @param self The current instance.
        @param sample_rate The sample rate value.
        @param volume The volume value.
        @return The operation result.
        """
        self._sample_rate = sample_rate
        self._volume = float(volume)
        self._muted = False
        self._stream: Any = None
        self._channels: int | None = None
        self._lock = RLock()
        self._prebuffer_frames = int(sample_rate * 0.4)
        self._pending: deque[np.ndarray] = deque()
        self._pending_frames = 0

    @property
    def muted(self) -> bool:
        """!
        @brief Handle muted.
        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            return self._muted

    def set_muted(self, muted: bool) -> None:
        """!
        @brief Handle set muted.
        @param self The current instance.
        @param muted The muted value.
        @return The operation result.
        """
        with self._lock:
            self._muted = bool(muted)

    def set_volume(self, volume: float) -> None:
        """!
        @brief Handle set volume.
        @param self The current instance.
        @param volume The volume value.
        @return The operation result.
        """
        if not 0.0 <= volume <= 1.0:
            raise ValueError("volume must be between 0 and 1")
        with self._lock:
            self._volume = float(volume)

    def reset_buffer(self) -> None:
        """!
        @brief Discard pending audio after a tune or acquisition restart.
        @param self The current instance.
        """
        with self._lock:
            self._pending.clear()
            self._pending_frames = 0

    def write(self, audio: np.ndarray) -> None:
        """!
        @brief Handle write.
        @param self The current instance.
        @param audio The audio value.
        @return The operation result.
        """
        pcm = np.asarray(audio, dtype=np.float32)
        if pcm.size == 0:
            return
        if pcm.ndim == 1:
            pcm = pcm.reshape(-1, 1)
        if pcm.ndim != 2 or pcm.shape[1] not in (1, 2):
            raise ValueError("expected mono or stereo PCM frames")
        with self._lock:
            if self._muted:
                self.reset_buffer()
                return
            if self._stream is None:
                self._pending.append(pcm.copy())
                self._pending_frames += len(pcm)
                if self._pending_frames < self._prebuffer_frames:
                    return
                pcm = np.concatenate(tuple(self._pending), axis=0)
                self._pending.clear()
                self._pending_frames = 0
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
                try:
                    self._stream.start()
                except Exception:
                    self._stream.close()
                    self._stream = None
                    raise
                self._channels = pcm.shape[1]
                # Prime PortAudio before the first decoded audio block.
                self._stream.write(np.zeros(
                    (self._sample_rate, pcm.shape[1]), dtype=np.float32))
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
        """!
        @brief Handle close.
        @param self The current instance.
        @return The operation result.
        """
        with self._lock:
            self._close_stream()
