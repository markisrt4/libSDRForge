"""!
@brief Hardware-free ADS-B receiver diagnostics.
Usage: python -m sdrforge.adsb.receiver_cli --source synthetic
"""

import argparse
import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from .iq_stream import StreamingAdsbDemodulator
from .receiver_session import AdsbReceiverSession, ReceiverStatistics

SYNTHETIC_FRAMES = (
    "8D40621D58C382D690C8AC2863A7",
    "8D40621D58C386435CC412692AD6",
    "8D4840D6202CC371C32CE0576098",
    "8D485020994409940838175B284F",
)


def run_synthetic(
    *,
    cycles: int = 1,
    interval: float = 0.0,
    verbose: bool = False,
    emit: Callable[[str], object] = print,
    sleep: Callable[[float], object] = time.sleep,
) -> ReceiverStatistics:
    """!
    @brief Run known CRC-valid frames through the real decoder and tracker.
    @param cycles The cycles value.
    @param interval The interval value.
    @param verbose The verbose value.
    @param emit The emit value.
    @param sleep The sleep value.
    @return Receiver statistics for the synthetic run.
    """
    if cycles < 1 or interval < 0:
        raise ValueError("cycles must be >= 1 and interval must be >= 0")
    session = AdsbReceiverSession()
    start = time.monotonic()
    for cycle in range(cycles):
        for frame in SYNTHETIC_FRAMES:
            now = time.monotonic() - start
            aircraft = session.accept(frame, now)
            if verbose and aircraft is not None:
                emit(
                    f"icao={aircraft.icao} callsign={aircraft.callsign or '-'} "
                    f"lat={aircraft.latitude} lon={aircraft.longitude}"
                )
        if cycle + 1 < cycles and interval:
            sleep(interval)
    stats = session.statistics(time.monotonic() - start)
    emit(json.dumps(stats.__dict__, sort_keys=True))
    return stats


def run_iq_replay(
    *,
    path: str | Path,
    sample_rate: float = 2e6,
    chunk_samples: int = 16384,
    verbose: bool = False,
    emit: Callable[[str], object] = print,
) -> ReceiverStatistics:
    """!
    @brief Replay raw interleaved unsigned 8-bit RTL-SDR I/Q samples.
    Each pair of bytes is I,Q centered at 127.5. The final odd byte, if
    present, is discarded; no SDR hardware or background service is used.
    @param path The path value.
    @param sample_rate The sample rate value.
    @param chunk_samples The chunk samples value.
    @param verbose The verbose value.
    @param emit The emit value.
    @return Receiver statistics for the replay.
    """
    if chunk_samples < 1:
        raise ValueError("chunk_samples must be >= 1")
    receiver = StreamingAdsbDemodulator(sample_rate)
    session = AdsbReceiverSession()
    sample_count = 0
    start = time.monotonic()
    with Path(path).open("rb") as stream:
        while data := stream.read(chunk_samples * 2):
            pairs = np.frombuffer(data[: len(data) // 2 * 2], dtype=np.uint8)
            if len(pairs) == 0:
                continue
            iq = (
                (pairs[::2].astype(np.float32) - 127.5)
                + 1j * (pairs[1::2].astype(np.float32) - 127.5)
            ) / 127.5
            for frame in receiver.feed(iq):
                aircraft = session.accept(frame, sample_count / sample_rate)
                if verbose and aircraft is not None:
                    emit(
                        f"icao={aircraft.icao} callsign={aircraft.callsign or '-'} "
                        f"lat={aircraft.latitude} lon={aircraft.longitude}"
                    )
            sample_count += len(iq)
    stats = session.statistics(sample_count / sample_rate)
    result = dict(stats.__dict__)
    result.update(
        samples_processed=sample_count,
        sample_rate=sample_rate,
        elapsed_seconds=round(time.monotonic() - start, 3),
    )
    emit(json.dumps(result, sort_keys=True))
    return stats


def main(argv: Sequence[str] | None = None) -> int:
    """!
    @brief Handle main.
    @param argv The argv value.
    @return Process exit status.
    """
    parser = argparse.ArgumentParser(
        description="SDRForge ADS-B frame receiver diagnostics"
    )
    parser.add_argument(
        "--source",
        choices=("synthetic", "iq-replay"),
        default="synthetic",
        help="synthetic decoded frames or raw RTL-SDR unsigned 8-bit IQ replay",
    )
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--interval", type=float, default=0.0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--iq-file", type=Path, help="raw interleaved unsigned 8-bit I/Q file"
    )
    parser.add_argument("--sample-rate", type=float, default=2e6)
    parser.add_argument("--chunk-samples", type=int, default=16384)
    args = parser.parse_args(argv)
    if args.cycles < 1 or args.interval < 0:
        parser.error("cycles must be >= 1 and interval must be >= 0")
    if args.source == "iq-replay":
        if args.iq_file is None:
            parser.error("--iq-file is required for iq-replay")
        if (
            args.chunk_samples < 1
            or not np.isfinite(args.sample_rate)
            or args.sample_rate < 2e6
        ):
            parser.error("--chunk-samples must be positive and --sample-rate >= 2e6")
        run_iq_replay(
            path=args.iq_file,
            sample_rate=args.sample_rate,
            chunk_samples=args.chunk_samples,
            verbose=args.verbose,
        )
    else:
        run_synthetic(cycles=args.cycles, interval=args.interval, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
