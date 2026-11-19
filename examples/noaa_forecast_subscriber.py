"""Inspect NOAA forecast events from a dedicated SDRForge ZeroMQ publisher.

Install the optional transport dependency with: pip install 'libsdrforge[zmq]'
Start this subscriber before starting the live NOAA probe (PUB/SUB slow joiner).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import textwrap


def decode_forecast_message(message: bytes) -> dict:
    """Validate a versioned SDRForge telemetry envelope for NOAA forecasts."""
    topic, separator, body = message.partition(b" ")
    if not separator or topic != b"noaa.forecast":
        raise ValueError("expected noaa.forecast topic and JSON envelope")
    envelope = json.loads(body)
    if not isinstance(envelope, dict) or envelope.get("schema_version") != 1:
        raise ValueError("unsupported telemetry envelope")
    payload = envelope.get("payload")
    if not isinstance(payload, dict) or payload.get("event") != "noaa_forecast_completed":
        raise ValueError("invalid NOAA forecast payload")
    return payload


def format_forecast(event: dict, width: int = 80) -> list[str]:
    """Produce readable forecast lines without assuming optional fields exist."""
    forecast = event.get("completed_forecast", {}).get("forecast", {})
    period = str(forecast.get("period") or "Unknown period").title()
    conditions = str(forecast.get("conditions") or "Unknown conditions").title()
    area = event.get("forecast_area") or "UNSCOPED"
    parts = [period, conditions]
    for key, label in (("high_f", "High"), ("low_f", "Low"),
                       ("precipitation_chance_percent", "Rain")):
        value = forecast.get(key)
        if value is not None:
            parts.append(f"{label} {value}{'%' if label == 'Rain' else 'F'}")
    if forecast.get("high_description"):
        parts.append(str(forecast["high_description"]))
    if forecast.get("low_description"):
        parts.append(str(forecast["low_description"]))
    line = " | ".join(parts)
    prefix = f"[{area}] "
    return textwrap.wrap(prefix + line, width=max(25, width), subsequent_indent="  ") or [prefix]


def render_dashboard(events: list[dict], *, endpoint: str, errors: int = 0,
                     width: int = 80, height: int = 24) -> str:
    """Build a compact ANSI-independent dashboard, newest forecasts first."""
    width = max(30, width)
    height = max(8, height)
    scoped = sum(bool(e.get("forecast_areas")) for e in events)
    lines = [
        "SDRForge | NOAA Forecast Monitor",
        f"ZMQ {endpoint}",
        f"Received: {len(events)}  Scoped: {scoped}  Unscoped: {len(events)-scoped}  Errors: {errors}",
        "UNSCOPED forecasts are NOT verified as local weather",
        "-" * min(width, 72),
    ]
    for event in reversed(events):
        frequency = event.get("source_frequency_hz")
        mhz = f"{frequency / 1e6:.3f} MHz" if isinstance(frequency, (int, float)) else "? MHz"
        meta = (f"Cycle {event.get('forecast_cycle', '?')} | {mhz} | "
                f"{event.get('deduplication_status', '?')}")
        if event.get("cycle_boundary_suspected"):
            meta += " | CYCLE RESTART SUSPECTED"
        block = [meta] + format_forecast(event, width=width - 2)
        if len(lines) + len(block) + 1 > height - 2:
            break
        lines.extend(block)
        lines.append("")
    lines.append("Ctrl+C to exit")
    return "\n".join(line[:width] for line in lines[:height])


def redraw(events: list[dict], endpoint: str, errors: int) -> None:
    size = shutil.get_terminal_size((80, 24))
    screen = render_dashboard(events, endpoint=endpoint, errors=errors,
                              width=size.columns, height=size.lines)
    sys.stdout.write("\x1b[H\x1b[2J" + screen + "\x1b[J")
    sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="tcp://127.0.0.1:5573")
    parser.add_argument("--count", type=int, default=0, help="Exit after N events; 0 means continuous")
    parser.add_argument("--json", action="store_true", help="Print raw JSONL instead of the TUI")
    args = parser.parse_args()
    if args.count < 0:
        parser.error("--count must be nonnegative")
    try:
        import zmq
    except ImportError as exc:
        parser.error("pyzmq is required; install libsdrforge[zmq]")
        raise AssertionError("unreachable") from exc
    context = zmq.Context.instance()
    socket = context.socket(zmq.SUB)
    socket.setsockopt(zmq.SUBSCRIBE, b"noaa.forecast")
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect(args.endpoint)
    received = 0
    errors = 0
    events: list[dict] = []
    if not args.json:
        sys.stdout.write("\x1b[?1049h\\x1b[?25l")
        redraw(events, args.endpoint, errors)
    try:
        while args.count == 0 or received < args.count:
            try:
                message = socket.recv()
                payload = decode_forecast_message(message)
            except (ValueError, json.JSONDecodeError) as exc:
                errors += 1
                if args.json:
                    print(json.dumps({"event": "noaa_forecast_decode_error", "error": str(exc)}), flush=True)
                else:
                    redraw(events, args.endpoint, errors)
                continue
            received += 1
            if args.json:
                print(json.dumps(payload), flush=True)
            else:
                events.append(payload)
                redraw(events, args.endpoint, errors)
    except KeyboardInterrupt:
        pass
    finally:
        socket.close()
        if not args.json:
            sys.stdout.write("\x1b[?25h\\x1b[?1049l")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
