"""Replay saved NOAA transcript JSONL without Vosk, audio, or SDR hardware."""
from __future__ import annotations

import argparse
import json
import time
from contextlib import nullcontext
from pathlib import Path

from sdrforge.weather.forecast_processor import NoaaForecastProcessor


def replay_transcripts(source: Path, emit=print) -> tuple[int, int]:
    """Emit completed forecast JSONL; return (segments, forecasts)."""
    processor = NoaaForecastProcessor()
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
            for completed_event in processor.feed(
                transcript, frequency_hz=event.get("frequency_hz")
            ):
                emit(json.dumps(completed_event))
                forecasts += 1
    for completed_event in processor.flush():
        emit(json.dumps(completed_event))
        forecasts += 1
    return segments, forecasts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Existing NOAA transcript JSONL")
    parser.add_argument("--output", type=Path, help="Completed forecasts JSONL")
    parser.add_argument("--forecast-zmq-endpoint", help="Optional dedicated ZMQ PUB endpoint")
    parser.add_argument("--publish-interval", type=float, default=0.25,
                        help="Seconds between ZMQ events (default 0.25)")
    parser.add_argument("--subscriber-warmup", type=float, default=1.0,
                        help="Seconds to allow SUB subscriptions to connect")
    args = parser.parse_args()
    if args.output and args.output.resolve() == args.input.resolve():
        parser.error("output must differ from input")
    if args.publish_interval < 0 or args.subscriber_warmup < 0:
        parser.error("publishing delays must be nonnegative")
    stream = None
    if args.forecast_zmq_endpoint:
        from sdrforge.telemetry.stream import TelemetryStream

        stream = TelemetryStream(endpoint=args.forecast_zmq_endpoint)
        stream.start()
    try:
        if stream is not None:
            time.sleep(args.subscriber_warmup)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
        output_context = args.output.open("w", encoding="utf-8") if args.output else nullcontext(None)
        with output_context as output:
            def emit(line: str) -> None:
                if output is not None:
                    output.write(line + "\n")
                else:
                    print(line)
                if stream is not None:
                    event = json.loads(line)
                    if not stream.submit("noaa.forecast", event):
                        raise RuntimeError("NOAA ZMQ telemetry queue rejected forecast")
                    # Give the async publisher time to drain; PUB/SUB is best-effort.
                    time.sleep(args.publish_interval)

            segments, forecasts = replay_transcripts(args.input, emit=emit)
    finally:
        if stream is not None:
            stream.stop()
    print(json.dumps({"event": "noaa_transcript_replay_complete",
                      "segments": segments, "completed_forecasts": forecasts,
                      "output": str(args.output) if args.output else None}))


if __name__ == "__main__":
    main()
