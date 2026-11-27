"""Regression for NOAA Vosk 'so night' Sunday-night transition."""

from sdrforge.weather.forecast import extract_forecasts
from sdrforge.weather.forecast_assembler import NoaaForecastAssembler


def test_sunday_night_alias_keeps_original_transcript():
    assembler = NoaaForecastAssembler()
    text = (
        "sunday mostly cloudy with a fifty percent chance of rain "
        "highs in the upper fifties so night mostly cloudy "
        "close in the mid thirties chance of rain thirty percent "
        "monday partly cloudy"
    )
    completed = assembler.feed(text)
    assert [item.forecast.period for item in completed] == ["sunday", "sunday night"]
    assert completed[0].forecast.precipitation_chance_percent == 50
    assert completed[1].forecast.precipitation_chance_percent == 30
    assert completed[1].transcript.startswith("so night")
    assert completed[1].forecast.low_description == "close in the mid thirties"


def test_unrelated_so_night_is_not_a_forecast_period():
    assert extract_forecasts("so night mostly cloudy") == ()
    assembler = NoaaForecastAssembler()
    assert assembler.feed("so night mostly cloudy") == ()
