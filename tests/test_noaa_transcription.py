"""Offline weather transcription contracts, no RF hardware or model needed."""
import numpy as np
import pytest

from sdrforge.weather.transcription import NoaaTranscriptionPipeline
from sdrforge.weather.vosk_adapter import VoskOfflineRecognizer


class FakeRecognizer:
    def __init__(self, transcript):
        self.transcript = transcript
        self.calls = []

    def transcribe(self, pcm, sample_rate):
        self.calls.append((pcm.copy(), sample_rate))
        return self.transcript


def test_transcription_extracts_spoken_weather():
    fake = FakeRecognizer(
        "Temperature is 42. Relative humidity is 60 percent. "
        "Wind from the northwest at 12 miles per hour."
    )
    pipeline = NoaaTranscriptionPipeline(
        fake, frequency_hz=162_550_000, location="Detroit"
    )
    result = pipeline.process(np.zeros(16000), 16000)
    assert result.observation.temperature_f == 42
    assert result.observation.relative_humidity_percent == 60
    assert result.observation.wind_direction == "northwest"
    assert result.observation.wind_mph == 12
    assert result.observation.location == "Detroit"
    assert fake.calls[0][0].dtype == np.float32
    assert fake.calls[0][1] == 16000


def test_missing_values_are_not_invented():
    result = NoaaTranscriptionPipeline(
        FakeRecognizer("Weather conditions are changing")
    ).process(np.zeros(100), 16000)
    assert result.observation.temperature_f is None
    assert result.observation.wind_mph is None


@pytest.mark.parametrize("audio,rate", [
    (np.zeros((2, 2)), 16000),
    (np.array([np.nan]), 16000),
    (np.array([1.5]), 16000),
    (np.zeros(10), 0),
])
def test_rejects_invalid_audio(audio, rate):
    with pytest.raises(ValueError):
        NoaaTranscriptionPipeline(FakeRecognizer("")).process(audio, rate)


def test_vosk_requires_local_model(tmp_path):
    with pytest.raises(FileNotFoundError):
        VoskOfflineRecognizer(tmp_path / "missing")
