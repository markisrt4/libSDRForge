"""Model-free integration tests for offline NOAA WAV processing."""

import json
import wave

import numpy as np
import pytest

from sdrforge.weather.offline_wav import read_mono_wav, transcribe_wav


class FakeRecognizer:
    def __init__(self):
        self.samples = None
        self.rate = None

    def transcribe(self, pcm, sample_rate):
        self.samples = pcm
        self.rate = sample_rate
        return "Temperature is 41. Relative humidity is 68 percent."


def write_wav(path, *, channels=1, width=2, rate=16000):
    with wave.open(str(path), "wb") as recording:
        recording.setnchannels(channels)
        recording.setsampwidth(width)
        recording.setframerate(rate)
        recording.writeframes(b"\x00" * (rate * channels * width // 10))


def test_offline_wav_to_structured_weather(tmp_path):
    path = tmp_path / "weather.wav"
    write_wav(path)
    recognizer = FakeRecognizer()
    result = transcribe_wav(path, recognizer, location="Detroit")
    assert result["observation"]["temperature_f"] == 41
    assert result["observation"]["relative_humidity_percent"] == 68
    assert result["observation"]["location"] == "Detroit"
    assert result["observation"]["wind_mph"] is None
    assert recognizer.rate == 16000
    assert recognizer.samples.dtype == np.float32
    assert json.loads(json.dumps(result)) == result


def test_wav_samples_normalized(tmp_path):
    path = tmp_path / "samples.wav"
    with wave.open(str(path), "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(8000)
        recording.writeframes(np.array([-32768, 0, 32767], dtype="<i2").tobytes())
    pcm, rate = read_mono_wav(path)
    assert rate == 8000
    np.testing.assert_allclose(pcm, [-1, 0, 32767 / 32768])


@pytest.mark.parametrize("channels,width", [(2, 2), (1, 1)])
def test_rejects_incompatible_wav(tmp_path, channels, width):
    path = tmp_path / "bad.wav"
    write_wav(path, channels=channels, width=width)
    with pytest.raises(ValueError):
        read_mono_wav(path)
