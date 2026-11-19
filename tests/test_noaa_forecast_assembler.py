"""Hardware-free tests for multi-segment NOAA forecast assembly."""
from sdrforge.weather.forecast_assembler import NoaaForecastAssembler


def test_forecast_continues_across_segments():
    assembler = NoaaForecastAssembler()
    assert assembler.feed("the forecast for monroe county thursday") == ()
    assert assembler.feed("partly cloudy highs around sixty southwest winds") == ()
    done = assembler.feed("five to fifteen miles per hour thursday night")
    assert len(done) == 1
    assert done[0].forecast.period == "thursday"
    assert done[0].forecast.conditions == "partly cloudy"
    assert done[0].forecast.high_f == 60
    assert done[0].first_segment == 0
    assert done[0].last_segment == 2


def test_flush_last_period_and_no_duplicate():
    assembler = NoaaForecastAssembler()
    assert assembler.feed("saturday mostly sunny highs around sixty") == ()
    completed = assembler.feed("saturday night partly cloudy")
    assert len(completed) == 1
    assert completed[0].forecast.period == "saturday"
    tail = assembler.flush()
    assert len(tail) == 1
    assert tail[0].forecast.period == "saturday night"
    assert assembler.flush() == ()


def test_unrelated_or_empty_segments_not_forecasts():
    assembler = NoaaForecastAssembler()
    assert assembler.feed("monroe county") == ()
    assert assembler.feed("") == ()
    assert assembler.flush() == ()
