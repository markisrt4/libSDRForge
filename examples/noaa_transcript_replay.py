"""Replay saved NOAA transcript JSONL without Vosk, audio, or SDR hardware."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from sdrforge.weather.forecast_area import ForecastAreaTracker
from sdrforge.weather.forecast_assembler import NoaaForecastAssembler


def replay_transcripts(source: Path, emit=print) -> tuple[int, int]:
    """Emit completed forecast JSONL; return (segments, forecasts)."""
    assembler = NoaaForecastAssembler()
    areas = ForecastAreaTracker()
    segments = forecasts = 0
    with source.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_number}: {exc}") from exc
            if not isinstance(event, dict):
                raise TypeError(f"Expected JSON object at line {line_number}")
            if "transcript" not in event:
                # Ignore metadata and completion events from earlier replay runs.
                continue
            transcript = event["transcript"]
            if not isinstance(transcript, str):
                raise TypeError(f"Non-string transcript at line {line_number}")
            segments += 1
            for completed in assembler.feed(transcript):
                area = areas.observe_completed(completed.transcript)
                emit(json.dumps({"event": "noaa_forecast_completed",
                                 "forecast_area": area,
                                 "source_frequency_hz": event.get("frequency_hz"),
                                 "completed_forecast": asdict(completed)}))
                forecasts += 1
    for completed in assembler.flush():
        area = areas.observe_completed(completed.transcript)
        emit(json.dumps({"event": "noaa_forecast_completed",
                         "forecast_area": area,
                         "completed_forecast": asdict(completed)}))
        forecasts += 1
    return segments, forecasts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Existing NOAA transcript JSONL")
    parser.add_argument("--output", type=Path, help="Completed forecasts JSONL")
    args = parser.parse_args()
    if args.output and args.output.resolve() == args.input.resolve():
        parser.error("output must differ from input")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as output:
            segments, forecasts = replay_transcripts(
                args.input, emit=lambda line: output.write(line + "\n")
            )
    else:
        segments, forecasts = replay_transcripts(args.input)
    print(json.dumps({"event": "noaa_transcript_replay_complete",
                      "segments": segments, "completed_forecasts": forecasts,
                      "output": str(args.output) if args.output else None}))


if __name__ == "__main__":
    main()
