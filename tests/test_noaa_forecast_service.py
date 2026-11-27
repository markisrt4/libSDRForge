"""Hardware-free forecast publication tests."""

from sdrforge.weather.forecast_history import NoaaForecastHistory
from sdrforge.weather.forecast_service import NoaaForecastService


def event():
    return {
        "event": "noaa_forecast_completed",
        "completed_forecast": {"forecast": {"period": "tonight"}},
    }


def test_publication_matches_authoritative_history():
    messages = []

    def submit(topic, payload):
        messages.append((topic, payload))
        return True

    history = NoaaForecastHistory(clock=lambda: 42.0)
    service = NoaaForecastService(submit, history=history)
    record = service.publish(event())
    assert service.history is history
    assert messages == [("noaa.forecast", record)]
    assert history.latest() == record
    record.clear()
    assert messages[0][1]["received_at"] == 42.0
    assert history.latest() == messages[0][1]


def test_dropped_telemetry_does_not_lose_history():
    service = NoaaForecastService(lambda topic, payload: False)
    first = service.publish(event())
    second = service.publish(event())
    assert service.history.history() == [first, second]


def test_publication_without_telemetry():
    service = NoaaForecastService()
    assert service.publish(event()) == service.history.latest()


def test_session_publication_rejects_stale_callbacks():
    messages = []

    def submit(topic, payload):
        messages.append((topic, payload))
        return True

    service = NoaaForecastService(submit)
    first = service.begin_session()
    record = service.publish_session(first, event())
    assert record is not None
    service.end_session(first)
    assert service.publish_session(first, event()) is None

    second = service.begin_session()
    assert second != first
    service.end_session(first)
    assert service.publish_session(first, event()) is None
    next_record = service.publish_session(second, event())
    assert next_record is not None
    assert service.history.history() == [record, next_record]
    assert messages == [
        ("noaa.forecast", record),
        ("noaa.forecast", next_record),
    ]


def test_new_session_invalidates_previous_generation():
    service = NoaaForecastService()
    first = service.begin_session()
    second = service.begin_session()
    assert service.publish_session(first, event()) is None
    assert service.publish_session(second, event()) is not None
    assert len(service.history.history()) == 1
