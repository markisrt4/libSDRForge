"""Hardware-free managed NOAA decoder lifecycle tests."""

import numpy as np
import pytest

from sdrforge.weather.forecast_service import NoaaForecastService
from sdrforge.weather.managed_noaa_decoder import ManagedNoaaDecoder


class Recognizer:
    def transcribe(self, pcm, sample_rate):
        return "Tonight cloudy. Tomorrow sunny."


def test_decoder_lifecycle():
    service = NoaaForecastService()
    decoder = ManagedNoaaDecoder(Recognizer(), service, frequency_hz=162_550_000)
    pcm = np.zeros(160, dtype=np.float32)
    with pytest.raises(RuntimeError, match="inactive"):
        decoder.feed(pcm)
    decoder.start()
    try:
        decoder.feed(pcm)
    finally:
        decoder.stop()
    with pytest.raises(RuntimeError, match="inactive"):
        decoder.feed(pcm)
    with pytest.raises(RuntimeError, match="cannot be reused"):
        decoder.start()


def test_decoder_stop_does_not_invalidate_newer_session():
    service = NoaaForecastService()
    decoder = ManagedNoaaDecoder(Recognizer(), service, frequency_hz=162_550_000)
    decoder.start()
    generation = service.begin_session()
    decoder.stop()
    event = {
        "event": "noaa_forecast_completed",
        "completed_forecast": {"forecast": {"period": "tonight"}},
    }
    assert service.publish_session(generation, event) is not None
