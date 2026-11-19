"""Replay and live transcription share the same forecast processing rules."""
from sdrforge.weather.forecast_processor import NoaaForecastProcessor


def test_processor_emits_scoped_forecast_and_flushes_last_period():
    processor = NoaaForecastProcessor(frequency_hz=162550000)
    assert processor.feed("thursday sunny forecast for monroe county") == ()
    first = processor.feed("tonight mostly cloudy")
    assert len(first) == 1
    assert first[0]["completed_forecast"]["forecast"]["period"] == "thursday"
    assert first[0]["forecast_areas"] == []
    final = processor.flush()
    assert len(final) == 1
    assert final[0]["forecast_areas"] == ["monroe county"]
    assert final[0]["source_frequency_hz"] == 162550000
    assert final[0]["deduplication_status"] == "new"
    assert processor.flush() == ()


def test_processor_tracks_latest_known_frequency():
    processor = NoaaForecastProcessor()
    processor.feed("monday mostly clear", frequency_hz=162550000)
    final = processor.flush()
    assert final[0]["source_frequency_hz"] == 162550000
    assert final[0]["completed_forecast"]["forecast"]["conditions"] == "mostly clear"
