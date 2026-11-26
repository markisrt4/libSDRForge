"""Hardware-free NOAA forecast history tests."""

import pytest

from sdrforge.weather.forecast_history import NoaaForecastHistory


def event():
    return {
        "event": "noaa_forecast_completed",
        "completed_forecast": {"forecast": {"period": "tonight"}},
    }


def test_history_retains_bounded_ordered_records():
    history = NoaaForecastHistory(capacity=2, clock=lambda: 100.0)
    assert history.latest() is None
    for _ in range(3):
        history.record(event())
    records = history.history()
    assert [record["publisher_sequence"] for record in records] == [2, 3]
    assert records[0]["publisher_id"] == records[1]["publisher_id"]
    assert history.latest() == records[-1]
    assert records[-1]["received_at"] == 100.0


def test_history_isolated_from_mutable_events_and_results():
    history = NoaaForecastHistory()
    original = event()
    result = history.record(original)
    original.clear()
    result.clear()
    records = history.history()
    records[0].clear()
    assert history.latest()["event"] == "noaa_forecast_completed"


def test_publisher_restart_has_distinct_identity():
    first = NoaaForecastHistory().record(event())
    second = NoaaForecastHistory().record(event())
    assert first["publisher_id"] != second["publisher_id"]
    assert first["publisher_sequence"] == second["publisher_sequence"] == 1


def test_invalid_event_does_not_enter_history():
    history = NoaaForecastHistory()
    with pytest.raises(ValueError):
        history.record({"event": "unknown"})
    assert history.latest() is None


def test_invalid_capacity():
    with pytest.raises(ValueError):
        NoaaForecastHistory(capacity=0)
