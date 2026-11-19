"""Regression coverage for JSONL-only NOAA forecast replay."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from noaa_transcript_replay import replay_transcripts


def test_replay_assembles_across_segments(tmp_path):
    source = tmp_path / "transcripts.jsonl"
    events = [
        {"segment_index": 0, "transcript": "the forecast for monroe county thursday"},
        {"segment_index": 1, "transcript": "partly cloudy highs around sixty"},
        {"segment_index": 2, "transcript": "thursday night mostly cloudy lows in the upper thirties"},
    ]
    source.write_text("".join(json.dumps(event) + "\n" for event in events))
    output = []
    segments, forecasts = replay_transcripts(source, emit=output.append)
    assert (segments, forecasts) == (3, 2)
    completed = [json.loads(line)["completed_forecast"] for line in output]
    assert completed[0]["forecast"]["period"] == "thursday"
    assert completed[0]["forecast"]["high_f"] == 60
    assert completed[0]["first_segment"] == 0
    assert completed[1]["forecast"]["period"] == "thursday night"
    assert completed[1]["forecast"]["low_description"] == "lows in the upper thirties"


def test_replay_ignores_metadata_and_empty_transcript(tmp_path):
    source = tmp_path / "events.jsonl"
    source.write_text(
        json.dumps({"event": "noaa_probe_complete"}) + "\n"
        + json.dumps({"transcript": ""}) + "\n"
    )
    output = []
    assert replay_transcripts(source, emit=output.append) == (1, 0)
    assert output == []


def test_replay_rejects_invalid_transcript(tmp_path):
    source = tmp_path / "bad.jsonl"
    source.write_text(json.dumps({"transcript": None}) + "\n")
    try:
        replay_transcripts(source)
    except ValueError as exc:
        assert "Non-string transcript" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
