"""Compact, scrollable NOAA forecast monitor over SDRForge ZeroMQ.

Run subscriber before the publisher. Use --json for machine-readable output.
"""

from __future__ import annotations

import argparse
import json
import os
import select
import shutil
import sys
import termios
import textwrap
import tty
from contextlib import contextmanager


def decode_forecast_message(message: bytes) -> dict:
    """Validate the NOAA forecast envelope."""
    topic, separator, body = message.partition(b" ")
    if not separator or topic != b"noaa.forecast":
        raise ValueError("expected noaa.forecast topic and JSON envelope")
    envelope = json.loads(body)
    if not isinstance(envelope, dict) or envelope.get("schema_version") != 1:
        raise ValueError("unsupported telemetry envelope")
    payload = envelope.get("payload")
    if (
        not isinstance(payload, dict)
        or payload.get("event") != "noaa_forecast_completed"
    ):
        raise ValueError("invalid NOAA forecast payload")
    return payload


def forecast_lines(event: dict, width: int) -> list[str]:
    """Format one forecast without claiming an unknown area is local."""
    forecast = event.get("completed_forecast", {}).get("forecast", {})
    period = str(forecast.get("period") or "Unknown").upper()
    conditions = str(forecast.get("conditions") or "Unknown").title()
    area = event.get("forecast_area")
    label = f"{period} | {conditions}"
    details = []
    for key, name, suffix in (
        ("high_f", "High", "F"),
        ("low_f", "Low", "F"),
        ("precipitation_chance_percent", "Rain", "%"),
    ):
        if forecast.get(key) is not None:
            details.append(f"{name} {forecast[key]}{suffix}")
    for key in ("high_description", "low_description"):
        if forecast.get(key):
            details.append(str(forecast[key]))
    if area:
        details.append(f"Area: {area}")
    else:
        details.append("Area: unknown")
    if event.get("cycle_boundary_suspected"):
        details.append("Cycle restart suspected")
    result = textwrap.wrap(label, width=max(12, width)) or [label]
    for detail in details:
        result.extend(
            textwrap.wrap(
                detail,
                width=max(12, width),
                initial_indent="  ",
                subsequent_indent="  ",
            )
        )
    return result


def dashboard_lines(events: list[dict], *, width: int, errors: int = 0) -> list[str]:
    """Return all content lines; pagination belongs to the terminal renderer."""
    width = max(20, width)
    scoped = sum(bool(e.get("forecast_areas")) for e in events)
    frequency = next(
        (
            e.get("source_frequency_hz")
            for e in reversed(events)
            if isinstance(e.get("source_frequency_hz"), (int, float))
        ),
        None,
    )
    mhz = f"{frequency / 1e6:.3f} MHz" if frequency is not None else "Awaiting RF"
    header = [
        f"SDRForge NOAA | {mhz}",
        f"{len(events)} received | {scoped} scoped | {len(events) - scoped} unknown",
    ]
    if errors:
        header.append(f"Decode errors: {errors}")
    return [line[:width] for line in header]


def forecast_body(events: list[dict], width: int) -> list[str]:
    """Newest first; separate records with a single rule."""
    body: list[str] = []
    for event in reversed(events):
        if body:
            body.append("-" * min(width, 48))
        body.extend(forecast_lines(event, width))
    return body


def render_dashboard(
    events: list[dict],
    *,
    endpoint: str,
    errors: int = 0,
    width: int = 80,
    height: int = 24,
    scroll: int = 0,
) -> str:
    """Render a fixed header and footer with a scrollable forecast viewport."""
    width, height = max(20, width), max(7, height)
    header = dashboard_lines(events, width=width, errors=errors)
    footer = "Up/Down scroll | PgUp/PgDn page | Q quit"
    body = forecast_body(events, width)
    available = max(1, height - len(header) - 2)
    maximum = max(0, len(body) - available)
    offset = min(max(0, scroll), maximum)
    visible = body[offset : offset + available]
    if not body:
        visible = ["Waiting for NOAA forecast events..."]
    lines = header + ["=" * min(width, 48)] + visible
    lines += [""] * max(0, height - 1 - len(lines))
    lines.append(footer[:width])
    return "\n".join(line[:width] for line in lines[:height])


@contextmanager
def terminal_mode(enabled: bool):
    """Restore terminal settings even on Ctrl+C or subscriber failures."""
    if not enabled:
        yield
        return
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[?1049h\x1b[?25l")
        sys.stdout.flush()
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


def redraw(events: list[dict], endpoint: str, errors: int, scroll: int) -> None:
    size = shutil.get_terminal_size((80, 24))
    screen = render_dashboard(
        events,
        endpoint=endpoint,
        errors=errors,
        width=size.columns,
        height=size.lines,
        scroll=scroll,
    )
    sys.stdout.write("\x1b[H\x1b[2J" + screen + "\x1b[J")
    sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="tcp://127.0.0.1:5573")
    parser.add_argument(
        "--count", type=int, default=0, help="Exit after N events; 0 means continuous"
    )
    parser.add_argument(
        "--json", action="store_true", help="Print raw JSONL instead of TUI"
    )
    args = parser.parse_args()
    if args.count < 0:
        parser.error("--count must be nonnegative")
    if not args.json and not (sys.stdin.isatty() and sys.stdout.isatty()):
        parser.error("TUI requires a terminal; use --json for redirected output")
    try:
        import zmq
    except ImportError:
        parser.error("pyzmq is required; install libsdrforge[zmq]")
    context = zmq.Context.instance()
    socket = context.socket(zmq.SUB)
    socket.setsockopt(zmq.SUBSCRIBE, b"noaa.forecast")
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect(args.endpoint)
    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)
    received = errors = scroll = 0
    events: list[dict] = []
    pending_keys = b""
    try:
        with terminal_mode(not args.json):
            if not args.json:
                redraw(events, args.endpoint, errors, scroll)
            while args.count == 0 or received < args.count:
                if socket in dict(poller.poll(100)):
                    try:
                        payload = decode_forecast_message(socket.recv())
                    except (ValueError, json.JSONDecodeError) as exc:
                        errors += 1
                        if args.json:
                            print(
                                json.dumps(
                                    {
                                        "event": "noaa_forecast_decode_error",
                                        "error": str(exc),
                                    }
                                ),
                                flush=True,
                            )
                    else:
                        received += 1
                        if args.json:
                            print(json.dumps(payload), flush=True)
                        else:
                            events.append(payload)
                            scroll = 0
                if not args.json:
                    if select.select([sys.stdin], [], [], 0)[0]:
                        pending_keys += os.read(sys.stdin.fileno(), 64)
                    while pending_keys:
                        if pending_keys.startswith(b"\x1b["):
                            if len(pending_keys) < 3:
                                break
                            if pending_keys[2:3] in (b"A", b"B"):
                                scroll += -1 if pending_keys[2:3] == b"A" else 1
                                pending_keys = pending_keys[3:]
                            elif pending_keys.startswith((b"\x1b[5~", b"\x1b[6~")):
                                scroll += -8 if pending_keys[2:3] == b"5" else 8
                                pending_keys = pending_keys[4:]
                            elif len(pending_keys) < 4:
                                break
                            else:
                                pending_keys = pending_keys[1:]
                        elif pending_keys[:1] in (b"q", b"Q", b"\x03"):
                            return
                        elif pending_keys[:1] in (b"k", b"K"):
                            scroll -= 1
                            pending_keys = pending_keys[1:]
                        elif pending_keys[:1] in (b"j", b"J"):
                            scroll += 1
                            pending_keys = pending_keys[1:]
                        else:
                            pending_keys = pending_keys[1:]
                    size = shutil.get_terminal_size((80, 24))
                    body_height = max(
                        1,
                        size.lines
                        - len(
                            dashboard_lines(events, width=size.columns, errors=errors)
                        )
                        - 2,
                    )
                    scroll = min(
                        max(0, scroll),
                        max(0, len(forecast_body(events, size.columns)) - body_height),
                    )
                    redraw(events, args.endpoint, errors, scroll)
    except KeyboardInterrupt:
        pass
    finally:
        socket.close()


if __name__ == "__main__":
    main()
