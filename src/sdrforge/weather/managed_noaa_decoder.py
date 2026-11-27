"""Session-scoped NOAA decoder using externally owned PCM acquisition."""

from __future__ import annotations

import numpy as np

from .auxiliary_transcriber import AuxiliaryNoaaTranscriber
from .forecast_processor import NoaaForecastProcessor
from .forecast_service import NoaaForecastService
from .transcription import NoaaTranscriptionPipeline, OfflineSpeechRecognizer


class ManagedNoaaDecoder:
    """Single-use decoder for one authorized NOAA reception session."""

    def __init__(
        self,
        recognizer: OfflineSpeechRecognizer,
        forecasts: NoaaForecastService,
        *,
        frequency_hz: int,
        segment_seconds: float = 10.0,
    ) -> None:
        self._forecasts = forecasts
        self._generation: int | None = None
        self._used = False
        self._frequency_hz = frequency_hz
        self._processor = NoaaForecastProcessor(frequency_hz=frequency_hz)
        pipeline = NoaaTranscriptionPipeline(recognizer, frequency_hz=frequency_hz)
        self._worker = AuxiliaryNoaaTranscriber(
            pipeline, self._on_transcript, segment_seconds=segment_seconds
        )

    def start(self) -> None:
        """Activate a fresh generation after acquisition has been authorized."""
        if self._used:
            raise RuntimeError("NOAA decoder sessions cannot be reused")
        self._used = True
        generation = self._forecasts.begin_session()
        self._generation = generation
        try:
            self._worker.start()
        except BaseException:
            self._forecasts.end_session(generation)
            self._generation = None
            raise

    def feed(self, pcm: np.ndarray) -> None:
        """Accept normalized 16 kHz mono PCM from the authorized receiver."""
        if self._generation is None:
            raise RuntimeError("NOAA decoder is inactive")
        self._worker.feed(pcm)

    def stop(self) -> None:
        """Invalidate publication before draining the transcription worker."""
        generation = self._generation
        self._generation = None
        if generation is not None:
            self._forecasts.end_session(generation)
        self._worker.stop(timeout=5.0)

    def status(self) -> dict[str, object]:
        """Return session-local transcription metrics without exposing PCM."""
        return {
            "active": self._generation is not None,
            "frequency_hz": self._frequency_hz,
            "processed_segments": self._worker.processed_segments,
            "dropped_segments": self._worker.dropped_segments,
            "last_error": self._worker.last_error,
        }

    def _on_transcript(self, event: dict[str, object]) -> None:
        generation = self._generation
        transcript = event.get("transcript")
        if generation is None or not isinstance(transcript, str):
            return
        for forecast in self._processor.feed(transcript):
            self._forecasts.publish_session(generation, forecast)
