"""Regression coverage for multiple forecast periods in a single transcript."""
from sdrforge.weather.forecast_assembler import NoaaForecastAssembler


def test_multiple_periods_in_single_segment_keep_own_transcripts():
    assembler = NoaaForecastAssembler()
    completed = assembler.feed(
        "friday night clear saturday mostly sunny highs around sixty "
        "saturday night partly cloudy lows in the mid forties"
    )
    assert len(completed) == 2
    assert [item.forecast.period for item in completed] == [
        "friday night", "saturday"
    ]
    assert completed[0].transcript == "friday night clear"
    assert completed[1].transcript == "saturday mostly sunny highs around sixty"
    assert completed[1].forecast.high_f == 60
    tail = assembler.flush()
    assert len(tail) == 1
    assert tail[0].forecast.low_description == "lows in the mid forties"
