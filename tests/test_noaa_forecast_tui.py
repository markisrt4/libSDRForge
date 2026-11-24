"""Hardware-free layout checks for the compact NOAA monitor."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from noaa_forecast_subscriber import forecast_body, render_dashboard


def event(period, area=None):
    return {
        "event": "noaa_forecast_completed",
        "forecast_area": area,
        "forecast_areas": [area] if area else [],
        "source_frequency_hz": 162_550_000,
        "completed_forecast": {
            "forecast": {
                "period": period,
                "conditions": "partly cloudy",
                "precipitation_chance_percent": 30,
            }
        },
    }


def test_compact_header_and_unknown_area():
    output = render_dashboard(
        [event("monday"), event("tuesday", "monroe county")],
        endpoint="tcp://127.0.0.1:5573",
        width=40,
        height=12,
    )
    assert "2 received | 1 scoped | 1 unknown" in output
    assert "162.550 MHz" in output
    assert "TUESDAY" in output
    assert all(len(line) <= 40 for line in output.splitlines())


def test_scrolling_exposes_older_forecasts():
    events = [event(str(day)) for day in range(15)]
    top = render_dashboard(events, endpoint="test", width=40, height=9)
    older = render_dashboard(events, endpoint="test", width=40, height=9, scroll=1000)
    assert "14 | Partly Cloudy" in top
    assert "0 | Partly Cloudy" in older
    assert len(top.splitlines()) == 9


def test_missing_forecast_fields_do_not_crash():
    assert forecast_body([{"completed_forecast": {"forecast": {}}}], 35)
