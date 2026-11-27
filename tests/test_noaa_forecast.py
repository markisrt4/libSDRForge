"""NOAA forecast parsing regression tests, offline and hardware-free."""

import numpy as np

from sdrforge.weather.forecast import extract_forecasts
from sdrforge.weather.transcription import NoaaTranscriptionPipeline


class FakeRecognizer:
    def __init__(self, text):
        self.text = text

    def transcribe(self, pcm, sample_rate):
        return self.text


def test_live_noaa_forecast_transcript():
    text = (
        "those in the lower forties saturday mostly sunny highs around sixty "
        "saturday night partly cloudy lows in the mid forties "
        "sunday mostly cloudy with a fifty percent chance of rain "
    )
    periods = extract_forecasts(text)
    assert len(periods) == 3
    assert periods[0].period == "saturday"
    assert periods[0].conditions == "mostly sunny"
    assert periods[0].high_f == 60
    assert periods[1].period == "saturday night"
    assert periods[1].conditions == "partly cloudy"
    assert periods[1].low_f is None  # "mid forties" is not an exact value
    assert periods[1].low_description == "lows in the mid forties"
    assert periods[2].precipitation_chance_percent == 50


def test_forecast_is_separate_from_current_observation():
    pipeline = NoaaTranscriptionPipeline(
        FakeRecognizer("saturday mostly sunny highs around sixty")
    )
    result = pipeline.process(np.zeros(16000, dtype=np.float32), 16000)
    assert result.observation.temperature_f is None
    assert result.forecasts[0].high_f == 60


def test_no_forecast_in_empty_or_current_observation():
    assert extract_forecasts("") == ()
    assert extract_forecasts("temperature is forty two degrees") == ()


def test_out_of_range_chance_ignored():
    periods = extract_forecasts("sunday sunny with a 120 percent chance of rain")
    assert len(periods) == 1
    assert periods[0].precipitation_chance_percent is None


def test_real_replay_approximate_low_and_vosk_high():
    periods = extract_forecasts(
        "tonight mostly cloudy lows in the upper thirties southwest wins "
        "five to ten mph thursday partly cloudy including guys around sixty"
    )
    assert len(periods) == 2
    assert periods[0].low_f is None
    assert periods[0].low_description == "lows in the upper thirties"
    assert periods[1].high_f == 60


def test_approximate_temperature_not_converted_to_exact_number():
    periods = extract_forecasts("saturday highs in the lower sixties")
    assert periods[0].high_f is None
    assert periods[0].high_description == "highs in the lower sixties"


def test_observed_vosk_temperature_keyword_substitutions():
    periods = extract_forecasts(
        "today sunny ties around sixty "
        "friday night mostly clear flows in the lower forties "
        "thursday night clear those in the lower forties"
    )
    assert len(periods) == 3
    assert periods[0].high_f == 60
    assert periods[1].low_description == "flows in the lower forties"
    assert periods[2].low_description == "those in the lower forties"
