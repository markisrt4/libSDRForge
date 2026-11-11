# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Record RTL-SDR unsigned 8-bit IQ and replay it through the production WBFM/RDS receiver.

Capture on Termux (via scripts/run_rtlsdr_termux.sh):
    examples/rds_iq_replay.py capture --frequency 94.7 --seconds 10 --output ~/rds_947.iq --acquisition-mode async
Replay on Termux or Linux:
    python examples/rds_iq_replay.py replay --input ~/rds_947.iq
The adjacent .json file stores metadata and drop counts. Never concatenate
samples across missing blocks without resetting the decoder at those gaps.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sdrforge.adapters import RtlSdrSource
from sdrforge.models.iq import IqBlock
from sdrforge.receivers import WbfmReceiver

BLOCK_BYTES = 262_144


def capture(args: argparse.Namespace) -> None:
    path = args.output.expanduser()
    if path.exists() or path.with_suffix(path.suffix + ".json").exists():
        raise SystemExit("Output already exists; choose a new --output path")
    frequency = round(args.frequency * 1_000_000)
    source = RtlSdrSource(device_index=args.device_index, acquisition_mode=args.acquisition_mode)
    sample_count = 0
    gaps = []
    previous_drops = 0
    meta_path = path.with_suffix(path.suffix + ".json")
    try:
        source.open()
        source.set_center_frequency(frequency)
        source.set_gain(None if args.auto_gain else args.gain)
        source.start()
        with path.open("xb") as output:
            while sample_count < args.seconds * source.get_sample_rate():
                block = source.read_iq()
                dropped = source.get_acquisition_stats()["dropped_blocks"]
                if dropped > previous_drops:
                    gaps.append({"sample_offset": sample_count, "dropped_blocks": dropped - previous_drops})
                previous_drops = dropped
                output.write(block.samples)
                sample_count += len(block.samples) // 2
        print(f"Saved {sample_count/source.get_sample_rate():.2f}s to {path}")
    finally:
        stats = source.get_acquisition_stats()
        try:
            source.close()
        finally:
            if path.exists():
                meta = {"format": "rtl_u8_interleaved_iq", "center_frequency_hz": frequency,
                        "sample_rate_hz": source.get_sample_rate(), "iq_samples": sample_count,
                        "gain_db": None if args.auto_gain else args.gain,
                        "gaps": gaps, "acquisition_stats": stats}
                meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
                print(f"Metadata: {meta_path}")
                print(f"Dropped blocks: {stats['dropped_blocks']}; recorded gaps: {len(gaps)}")


def replay(args: argparse.Namespace) -> None:
    path = args.input.expanduser()
    meta = json.loads(path.with_suffix(path.suffix + ".json").read_text(encoding="utf-8"))
    if meta["format"] != "rtl_u8_interleaved_iq":
        raise SystemExit("Unsupported IQ format")
    frequency = int(meta["center_frequency_hz"])
    rate = int(meta["sample_rate_hz"])
    receiver = WbfmReceiver(channel_frequency_hz=frequency, mode="stereo", rds_enabled=True)
    gaps = iter(sorted(meta.get("gaps", []), key=lambda x: x["sample_offset"]))
    next_gap = next(gaps, None)
    processed = 0
    groups = 0
    found_pi = set()
    with path.open("rb") as stream:
        while True:
            # Split at a recorded discontinuity, so the decoder cannot falsely
            # assume that missing IQ samples were contiguous.
            length = BLOCK_BYTES
            if next_gap is not None:
                if processed == next_gap["sample_offset"]:
                    receiver.reset(preserve_metadata=True)
                    next_gap = next(gaps, None)
                elif processed < next_gap["sample_offset"]:
                    length = min(length, (next_gap["sample_offset"] - processed) * 2)
            data = stream.read(length)
            if not data:
                break
            if len(data) % 2:
                raise SystemExit("Truncated IQ file: incomplete I/Q pair")
            block = IqBlock(samples=data, center_frequency_hz=frequency,
                            sample_rate_hz=rate, timestamp_ns=0)
            receiver.process(block)
            processed += len(data) // 2
            for group in receiver.last_rds_groups:
                groups += 1
                found_pi.add(group.pi)
    status = receiver.rds_status
    print(json.dumps({
        "rf_seconds": round(processed / rate, 3),
        "validated_groups": groups,
        "pi_values": [f"0x{pi:04X}" for pi in sorted(found_pi)],
        "stereo_locked": receiver.stereo_locked,
        "rds_rms": status.rds_baseband_rms if status else None,
        "rds_band_excess_db": status.rds_band_excess_db if status else None,
        "phase_invalid_fraction": status.phase_recent_invalid_pair_fraction if status else None,
        "phase_groups": status.phase_groups_found if status else None,
        "carrier_offset_hz": status.carrier_offset_hz if status else None,
        "half_bit_samples": status.half_bit_samples_per_symbol if status else None,
        "recorded_gaps": len(meta.get("gaps", [])),
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("capture")
    record.add_argument("--frequency", type=float, default=94.7)
    record.add_argument("--seconds", type=float, default=10)
    record.add_argument("--output", type=Path, required=True)
    record.add_argument("--gain", type=float, default=30)
    record.add_argument("--auto-gain", action="store_true")
    record.add_argument("--device-index", type=int, default=0)
    record.add_argument("--acquisition-mode", choices=("async", "sync", "auto"), default="async")
    play = sub.add_parser("replay")
    play.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "capture":
        if not 76 <= args.frequency <= 108 or args.seconds <= 0:
            parser.error("frequency must be 76–108 MHz and seconds positive")
        capture(args)
    else:
        replay(args)


if __name__ == "__main__":
    main()
