"""Forecast geography must never be inferred from receiver frequency."""
import json
from pathlib import Path
import sys

from sdrforge.weather.forecast_area import ForecastAreaTracker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from noaa_transcript_replay import replay_transcripts


def test_header_applies_forward_only():
    tracker = ForecastAreaTracker()
    assert tracker.observe_completed(
        "thursday partly cloudy also the forecast for leno monroe county"
    ) is None
    assert tracker.observe_completed("tonight mostly cloudy") == "monroe county"


def test_ambiguous_header_clears_area():
    tracker = ForecastAreaTracker()
    tracker.observe_completed("forecast for monroe county")
    assert tracker.observe_completed("tonight clear") == "monroe county"
    assert tracker.observe_completed("forecast for other areas") == "monroe county"
    assert tracker.observe_completed("friday sunny") is None


def test_replay_emits_area_only_after_header(tmp_path):
    path = tmp_path / "sample.jsonl"
    transcripts = [
        "thursday sunny also the forecast for monroe county",
        "tonight mostly cloudy lows in the upper thirties",
        "friday sunny",
    ]
    path.write_text("".join(json.dumps({"transcript": t}) + "\n" for t in transcripts))
    lines = []
    replay_transcripts(path, emit=lines.append)
    events = [json.loads(line) for line in lines]
    assert events[0]["forecast_area"] is None
    assert events[1]["forecast_area"] == "monroe county"
