"""Forecast deduplication must preserve updates and unknown-area broadcasts."""

import json
import sys
from pathlib import Path

from sdrforge.weather.forecast import ForecastPeriod
from sdrforge.weather.forecast_deduplicator import NoaaForecastDeduplicator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from noaa_transcript_replay import replay_transcripts


def test_duplicate_and_revision():
    dedup = NoaaForecastDeduplicator()
    first = ForecastPeriod("tonight", conditions="clear")
    updated = ForecastPeriod("tonight", conditions="cloudy")
    kw = {"cycle": 0, "areas": ("monroe county",)}
    assert dedup.observe(first, **kw).status == "new"
    assert dedup.observe(first, **kw).status == "duplicate"
    revision = dedup.observe(updated, **kw)
    assert (revision.status, revision.revision) == ("revised", 2)
    assert dedup.observe(updated, **kw).status == "duplicate"
    assert dedup.observe(first, **kw).revision == 3


def test_cycle_and_group_isolation():
    dedup = NoaaForecastDeduplicator()
    forecast = ForecastPeriod("friday", conditions="sunny")
    assert dedup.observe(forecast, cycle=0, areas=("monroe county",)).status == "new"
    assert dedup.observe(forecast, cycle=1, areas=("monroe county",)).status == "new"
    assert dedup.observe(forecast, cycle=0, areas=("macomb county",)).status == "new"
    assert (
        dedup.observe(
            forecast, cycle=0, areas=("macomb county", "monroe county")
        ).status
        == "new"
    )
    assert (
        dedup.observe(
            forecast, cycle=0, areas=("monroe county", "macomb county")
        ).status
        == "duplicate"
    )


def test_unknown_geography_never_suppressed():
    dedup = NoaaForecastDeduplicator()
    forecast = ForecastPeriod("today", conditions="sunny")
    assert dedup.observe(forecast, cycle=0, areas=()).status == "unscoped"
    assert dedup.observe(forecast, cycle=0, areas=()).status == "unscoped"


def test_replay_marks_first_scoped_forecast(tmp_path):
    source = tmp_path / "recording.jsonl"
    source.write_text(
        json.dumps({"transcript": "thursday sunny forecast for monroe county"})
        + "\n"
        + json.dumps({"transcript": "tonight cloudy"})
        + "\n"
    )
    output = []
    replay_transcripts(source, emit=output.append)
    events = [json.loads(line) for line in output]
    assert events[0]["deduplication_status"] == "unscoped"
    assert events[1]["deduplication_status"] == "new"
    assert events[1]["forecast_revision"] == 1
