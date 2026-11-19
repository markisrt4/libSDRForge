"""!
@brief Offline NOAA audio transcription and structured observation orchestration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .extract import extract_observation
from .forecast import ForecastPeriod, extract_forecasts
from .models import WeatherObservation


class OfflineSpeechRecognizer(Protocol):
    """!
    @brief A local-only recognizer accepting mono floating-point PCM.
    """

    def transcribe(self, pcm: np.ndarray, sample_rate: int) -> str:
        """!
        @brief Provide transcribe behavior.
        @param self The current instance.
        @param pcm The pcm value.
        @param sample_rate The sample rate value.
        @return The operation result.
        """
        ...


@dataclass(frozen=True)
class TranscriptionResult:
    """!
    @brief Provide TranscriptionResult behavior.
    """
    transcript: str
    observation: WeatherObservation
    forecasts: tuple[ForecastPeriod, ...] = ()


class NoaaTranscriptionPipeline:
    """!
    @brief Convert demodulated NOAA audio to observations without network calls.
    """

    def __init__(self, recognizer: OfflineSpeechRecognizer, *,
                 frequency_hz: int = 162_550_000,
                 location: str | None = None) -> None:
        """!
        @brief Provide   init   behavior.
        @param self The current instance.
        @param recognizer The recognizer value.
        @param frequency_hz The frequency hz value.
        @param location The location value.
        """
        if frequency_hz <= 0:
            raise ValueError("frequency_hz must be positive")
        self.recognizer = recognizer
        self.frequency_hz = frequency_hz
        self.location = location

    def process(self, pcm: np.ndarray, sample_rate: int) -> TranscriptionResult:
        """!
        @brief Provide process behavior.
        @param self The current instance.
        @param pcm The pcm value.
        @param sample_rate The sample rate value.
        @return The operation result.
        """
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        audio = np.asarray(pcm)
        if audio.ndim != 1 or not np.issubdtype(audio.dtype, np.number):
            raise ValueError("pcm must be one-dimensional numeric audio")
        if not np.all(np.isfinite(audio)):
            raise ValueError("pcm must contain only finite samples")
        normalized = np.ascontiguousarray(audio, dtype=np.float32)
        if np.any(np.abs(normalized) > 1):
            raise ValueError("pcm must be normalized to [-1, 1]")
        transcript = self.recognizer.transcribe(normalized, sample_rate)
        if not isinstance(transcript, str):
            raise TypeError("recognizer must return a transcript string")
        return TranscriptionResult(
            transcript=transcript,
            forecasts=extract_forecasts(transcript),
            observation=extract_observation(
                transcript, frequency_hz=self.frequency_hz,
                location=self.location,
            ),
        )
