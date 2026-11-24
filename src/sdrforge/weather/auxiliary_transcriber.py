"""!
@brief Bounded, auxiliary-only NOAA PCM transcription worker.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime

import numpy as np

from .transcription import NoaaTranscriptionPipeline


class AuxiliaryNoaaTranscriber:
    """!
    @brief Nonblocking PCM ingestion and bounded background transcription.
    """

    def __init__(
        self,
        pipeline: NoaaTranscriptionPipeline,
        emit: Callable[[dict[str, object]], None],
        *,
        sample_rate: int = 16_000,
        segment_seconds: float = 10.0,
        queue_capacity: int = 2,
    ) -> None:
        """!
        @brief Provide   init   behavior.
        @param self The current instance.
        @param pipeline The pipeline value.
        @param emit The emit value.
        @param sample_rate The sample rate value.
        @param segment_seconds The segment seconds value.
        @param queue_capacity The queue capacity value.
        """
        if sample_rate <= 0 or segment_seconds <= 0 or queue_capacity <= 0:
            raise ValueError(
                "sample rate, segment duration and queue capacity must be positive"
            )
        self.pipeline = pipeline
        self.emit = emit
        self.sample_rate = sample_rate
        self.segment_samples = round(sample_rate * segment_seconds)
        if self.segment_samples <= 0:
            raise ValueError("segment duration is too short")
        self._pending: queue.Queue[np.ndarray] = queue.Queue(maxsize=queue_capacity)
        self._buffer = np.empty(0, dtype=np.float32)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self.dropped_segments = 0
        self.processed_segments = 0
        self.last_error: str | None = None

    def start(self) -> None:
        """!
        @brief Provide start behavior.
        @param self The current instance.
        """
        if self._worker is not None:
            raise RuntimeError("worker already started")
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._run, name="noaa-aux-vosk", daemon=True
        )
        self._worker.start()

    def feed(self, pcm: np.ndarray) -> None:
        """!
        @brief Called only with auxiliary NFM demodulated PCM, never primary audio.
        @param self The current instance.
        @param pcm The pcm value.
        """
        if self._worker is None or self._stop.is_set():
            raise RuntimeError("auxiliary transcriber is not running")
        audio = np.asarray(pcm, dtype=np.float32)
        if audio.ndim != 1 or not np.all(np.isfinite(audio)):
            raise ValueError("expected finite mono PCM")
        if np.any(np.abs(audio) > 1):
            raise ValueError("expected normalized PCM")
        with self._lock:
            self._buffer = np.concatenate((self._buffer, audio))
            while len(self._buffer) >= self.segment_samples:
                segment = self._buffer[: self.segment_samples].copy()
                self._buffer = self._buffer[self.segment_samples :]
                try:
                    self._pending.put_nowait(segment)
                except queue.Full:
                    self.dropped_segments += 1

    def _run(self) -> None:
        while not self._stop.is_set() or not self._pending.empty():
            try:
                segment = self._pending.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                result = self.pipeline.process(segment, self.sample_rate)
                self.emit(
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "receiver": "auxiliary",
                        "frequency_hz": self.pipeline.frequency_hz,
                        "transcript": result.transcript,
                        "observation": asdict(result.observation),
                        "forecasts": [asdict(period) for period in result.forecasts],
                        "dropped_segments": self.dropped_segments,
                    }
                )
                self.processed_segments += 1
            except Exception as exc:  # noqa: BLE001 - keep transcription worker alive
                self.last_error = f"{type(exc).__name__}: {exc}"
            finally:
                self._pending.task_done()

    def stop(self, *, timeout: float | None = None) -> None:
        """!
        @brief Provide stop behavior.
        @param self The current instance.
        @param timeout The timeout value.
        """
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout)
            if self._worker.is_alive():
                raise TimeoutError("NOAA transcription worker has not stopped")
            self._worker = None
