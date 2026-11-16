"""Hardware-free ADS-B receiver diagnostics.

Usage: python -m sdrforge.adsb.receiver_cli --source synthetic
"""
import argparse
import json
import time

from .receiver_session import AdsbReceiverSession

SYNTHETIC_FRAMES = (
    "8D40621D58C382D690C8AC2863A7",
    "8D40621D58C386435CC412692AD6",
    "8D4840D6202CC371C32CE0576098",
    "8D485020994409940838175B284F",
)


def run_synthetic(*, cycles=1, interval=0.0, verbose=False, emit=print, sleep=time.sleep):
    """Run known CRC-valid frames through the real decoder and tracker."""
    if cycles < 1 or interval < 0:
        raise ValueError("cycles must be >= 1 and interval must be >= 0")
    session = AdsbReceiverSession()
    start = time.monotonic()
    for cycle in range(cycles):
        for frame in SYNTHETIC_FRAMES:
            now = time.monotonic() - start
            aircraft = session.accept(frame, now)
            if verbose and aircraft is not None:
                emit(f"icao={aircraft.icao} callsign={aircraft.callsign or '-'} "
                     f"lat={aircraft.latitude} lon={aircraft.longitude}")
        if cycle + 1 < cycles and interval:
            sleep(interval)
    stats = session.statistics(time.monotonic() - start)
    emit(json.dumps(stats.__dict__, sort_keys=True))
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description="SDRForge ADS-B frame receiver diagnostics")
    parser.add_argument("--source", choices=("synthetic",), default="synthetic",
                        help="IQ replay and live RTL-SDR will be added with the demodulator")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--interval", type=float, default=0.0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.cycles < 1 or args.interval < 0:
        parser.error("cycles must be >= 1 and interval must be >= 0")
    run_synthetic(cycles=args.cycles, interval=args.interval, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
