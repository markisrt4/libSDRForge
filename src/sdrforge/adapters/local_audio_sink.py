# SPDX-License-Identifier: MIT
"""!
@brief Local PCM playback with independently controllable mute and volume.
"""

from __future__ import annotations

from collections import deque
from threading import Lock, RLock
from time import monotonic
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
        """
        self._sample_rate = sample_rate
        self._volume = float(volume)
        self._muted = False
        self._stream: Any = None
        self._channels: int | None = None
        self._device_lock = Lock()
        self._stream_channels: int | None = None
        self._lock = RLock()
        self._prebuffer_frames = int(sample_rate * 0.6)
        self._pending: deque[np.ndarray] = deque()
        self._pending_frames = 0
        self._buffer_lock = Lock()
        self._primed = False
        self._underruns = 0
        self._dropped_frames = 0
        self._contention_count = 0
        self._rebuffer_count = 0
        self._startup_started: float | None = None
        self._startup_latency_ms: float | None = None

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
        """
        with self._lock:
            self._muted = bool(muted)
            if self._muted:
                self.reset_buffer()

    def set_volume(self, volume: float) -> None:
        """!
        @brief Handle set volume.
        @param self The current instance.
        @param volume The volume value.
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
        with self._buffer_lock:
            self._pending.clear()
            self._pending_frames = 0
            self._primed = False
            self._startup_started = None
            self._startup_latency_ms = None

    def write(self, audio: np.ndarray) -> None:
        """Submit PCM and service playback for synchronous callers."""
        self.submit_pcm(audio)
        self.service_device()

    def submit_pcm(self, audio: np.ndarray) -> None:
        """!
        @brief Handle write.
        @param self The current instance.
        @param audio The audio value.
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
            output = np.ascontiguousarray(np.clip(pcm * self._volume, -1.0, 1.0))
            with self._buffer_lock:
                if self._channels != pcm.shape[1]:
                    self._pending.clear()
                    self._pending_frames = 0
                    self._primed = False
                    self._startup_started = None
                    self._startup_latency_ms = None
                    self._channels = pcm.shape[1]
                if self._startup_started is None:
                    self._startup_started = monotonic()
                self._pending.append(output)
                self._pending_frames += len(output)
                while self._pending_frames > self._sample_rate:
                    chunk = self._pending.popleft()
                    dropped = min(len(chunk), self._pending_frames - self._sample_rate)
                    if dropped < len(chunk):
                        self._pending.appendleft(chunk[dropped:].copy())
                    self._pending_frames -= dropped
                    self._dropped_frames += dropped

    def service_device(self) -> None:
        """Start playback when sufficient PCM is available."""
        with self._device_lock:
            with self._lock, self._buffer_lock:
                ready = self._pending_frames >= self._prebuffer_frames
                channels = self._channels
                muted = self._muted
            if self._stream is not None and self._stream_channels != channels:
                self._close_stream()
            if self._stream is None and ready and channels is not None and not muted:
                try:
                    import sounddevice as sd
                except ImportError as exc:
                    raise RuntimeError(
                        "Linux audio requires libsdrforge[audio]"
                    ) from exc
                self._stream = sd.OutputStream(
                    samplerate=self._sample_rate,
                    channels=channels,
                    dtype="float32",
                    latency="high",
                    blocksize=0,
                    callback=self._render_audio,
                )
                self._stream_channels = channels
                try:
                    self._stream.start()
                except Exception:
                    self._stream.close()
                    self._stream = None
                    self._stream_channels = None
                    raise

    def _render_audio(self, outdata, frames, time_info, status) -> None:
        """Fill the device buffer without waiting for PCM or control operations."""
        outdata.fill(0)
        if not self._buffer_lock.acquire(blocking=False):
            self._contention_count += 1
            return
        try:
            if self._muted or outdata.shape[1] != self._channels:
                return
            if not self._primed:
                if self._pending_frames < max(self._prebuffer_frames, frames):
                    return
                self._primed = True
            if self._pending_frames < frames:
                self._underruns += 1
                self._rebuffer_count += 1
                self._primed = False
                return
            if self._startup_latency_ms is None and self._startup_started is not None:
                self._startup_latency_ms = (monotonic() - self._startup_started) * 1000
            offset = 0
            while offset < frames and self._pending:
                chunk = self._pending[0]
                count = min(frames - offset, len(chunk))
                outdata[offset : offset + count] = chunk[:count]
                offset += count
                self._pending_frames -= count
                if count == len(chunk):
                    self._pending.popleft()
                else:
                    self._pending[0] = chunk[count:]
        finally:
            self._buffer_lock.release()

    def diagnostics(self) -> dict[str, int | float | str | None]:
        """Return a snapshot of audio state and lifetime buffer counters."""
        with self._lock, self._buffer_lock:
            if self._muted:
                state = "MUTED"
            elif self._stream is None and not self._pending_frames:
                state = "STOPPED"
            elif self._primed:
                state = "PLAYING"
            else:
                state = "BUFFERING"
            return {
                "state": state,
                "startup_latency_ms": self._startup_latency_ms,
                "buffer_ms": self._pending_frames * 1000 / self._sample_rate,
                "prebuffer_ms": self._prebuffer_frames * 1000 / self._sample_rate,
                "underruns": self._underruns,
                "dropped_frames": self._dropped_frames,
                "callback_contention": self._contention_count,
                "rebuffer_count": self._rebuffer_count,
            }

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.abort()
            finally:
                self._stream.close()
                self._stream = None
                self._stream_channels = None

    def close(self) -> None:
        """!
        @brief Handle close.
        @param self The current instance.
        """
        with self._device_lock:
            try:
                self._close_stream()
            finally:
                with self._lock:
                    self.reset_buffer()
                    self._channels = None
