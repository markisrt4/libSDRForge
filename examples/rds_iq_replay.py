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
import base64
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sdrforge.adapters import RtlSdrSource
from sdrforge.models.iq import IqBlock
from sdrforge.receivers import WbfmReceiver

BLOCK_BYTES = 262_144


def capture_location() -> dict:
    """Collect a best-effort Android GPS fix before USB capture."""
    if not shutil.which("termux-location"):
        return {"status": "unavailable", "reason": "termux-location not installed"}
    try:
        result = subprocess.run(
            ["termux-location", "-p", "gps", "-r", "once"],
            capture_output=True, text=True, timeout=8, check=False,
        )
        if result.returncode or not result.stdout.strip():
            return {"status": "unavailable", "reason": "no GPS fix"}
        fix = json.loads(result.stdout)
        latitude, longitude = float(fix["latitude"]), float(fix["longitude"])
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("invalid coordinates")
        location = {
            "status": "valid", "provider": fix.get("provider", "gps"),
            "latitude": latitude, "longitude": longitude,
            "coordinate_reference": "WGS84",
            "altitude_reference": "WGS84 ellipsoid",
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        for source, dest in (("altitude", "altitude_m"),
                             ("accuracy", "horizontal_accuracy_m"),
                             ("vertical_accuracy", "vertical_accuracy_m")):
            if fix.get(source) is not None:
                location[dest] = float(fix[source])
        return location
    except (subprocess.TimeoutExpired, OSError, ValueError, TypeError, KeyError):
        return {"status": "unavailable", "reason": "GPS lookup failed"}


def capture(args: argparse.Namespace) -> None:
    path = args.output.expanduser()
    if path.exists() or path.with_suffix(path.suffix + ".json").exists():
        raise SystemExit("Output already exists; choose a new --output path")
    if args.no_location:
        location = {"status": "disabled"}
    elif "SDRFORGE_CAPTURE_LOCATION_B64" in os.environ:
        try:
            location = json.loads(base64.b64decode(os.environ["SDRFORGE_CAPTURE_LOCATION_B64"], validate=True).decode("utf-8"))
            if not isinstance(location, dict):
                raise ValueError("expected object")
        except (ValueError, TypeError, UnicodeError, base64.binascii.Error):
            location = {"status": "unavailable", "reason": "invalid launcher GPS metadata"}
    else:
        location = capture_location()
    capture_started_at_utc = datetime.now(timezone.utc).isoformat()
    frequency = round(args.frequency * 1_000_000)
    source = RtlSdrSource(device_index=args.device_index, acquisition_mode=args.acquisition_mode)
    sample_count = 0
    gaps = []
    previous_drops = 0
    hardware_configuration = None
    meta_path = path.with_suffix(path.suffix + ".json")
    try:
        print("TUNER_STAGE: opening device", flush=True)
        source.open()
        print("TUNER_STAGE: device opened; setting requested center frequency", flush=True)
        source.set_center_frequency(frequency)
        print("TUNER_STAGE: center frequency configured; setting gain", flush=True)
        source.set_gain(None if args.auto_gain else args.gain)
        print("TUNER_STAGE: gain configured", flush=True)
        hardware_configuration = source.get_hardware_configuration()
        print("Hardware readback:", json.dumps(hardware_configuration, sort_keys=True), flush=True)
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
                        "hardware_configuration": hardware_configuration,
                        "capture_started_at_utc": capture_started_at_utc,
                        "location": location, "antenna": args.antenna,
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
    compare = getattr(args, "compare_sync", False)
    receivers = {"strict": WbfmReceiver(channel_frequency_hz=frequency, mode="stereo", rds_enabled=True)}
    if compare:
        receivers["persistent"] = WbfmReceiver(
            channel_frequency_hz=frequency, mode="stereo", rds_enabled=True,
            rds_persistent_sync=True)
    receiver = receivers["strict"]
    gaps = iter(sorted(meta.get("gaps", []), key=lambda x: x["sample_offset"]))
    next_gap = next(gaps, None)
    processed = 0
    groups = 0
    found_pi = set()
    metrics = {name: {"validated_groups": 0, "pi_values": set()}
               for name in receivers}
    with path.open("rb") as stream:
        while True:
            # Split at a recorded discontinuity, so the decoder cannot falsely
            # assume that missing IQ samples were contiguous.
            length = BLOCK_BYTES
            if next_gap is not None:
                if processed == next_gap["sample_offset"]:
                    for candidate in receivers.values():
                        candidate.reset(preserve_metadata=True)
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
            for name, candidate in receivers.items():
                candidate.process(block)
                for group in candidate.last_rds_groups:
                    metrics[name]["validated_groups"] += 1
                    metrics[name]["pi_values"].add(group.pi)
                    if name == "strict":
                        groups += 1
                        found_pi.add(group.pi)
            processed += len(data) // 2
    status = receiver.rds_status
    comparison = {}
    if compare:
        for name, candidate in receivers.items():
            state = candidate.rds_status
            comparison[name] = {
                "validated_groups": metrics[name]["validated_groups"],
                "pi_values": [f"0x{pi:04X}" for pi in sorted(metrics[name]["pi_values"])],
                "locked_pair_phase": state.locked_pair_phase if state else None,
                "phase_groups": state.phase_groups_found if state else None,
                "clean_blocks": state.clean_blocks if state else None,
                "missing_blocks": state.missing_blocks if state else None,
                "partial_groups": state.partial_groups if state else None,
                "loss_events": state.loss_events if state else None,
                "phase_framing_diagnostics": state.phase_framing_diagnostics if state else None,
                "phase_invalid_fraction": state.phase_recent_invalid_pair_fraction if state else None,
            }
    # Summarize the framing state without treating isolated CRC-clean blocks
    # as complete RDS groups. This is intentionally diagnostic, not a repair.
    framing_summary = {}
    if compare:
        for name, entry in comparison.items():
            clean = entry["clean_blocks"] or 0
            missing = entry["missing_blocks"] or 0
            diagnostics = entry["phase_framing_diagnostics"] or []
            framing_summary[name] = {
                "clean_block_fraction": round(clean / (clean + missing), 4)
                    if clean + missing else None,
                "complete_groups": entry["validated_groups"],
                "partial_groups": entry["partial_groups"],
                "locked_phase": entry["locked_pair_phase"],
                "per_phase": [
                    {
                        "phase": phase,
                        "locked": bool(info.get("locked")),
                        "alignment_residue": info.get("last_alignment"),
                        "last_pi": info.get("last_pi"),
                        "aligned_block_counts": info.get("aligned_blocks", {}),
                        "acquisition_count": len(info.get("acquisitions", [])),
                        "loss_count": len(info.get("loss_positions", [])),
                    }
                    for phase, info in enumerate(diagnostics)
                ],
            }
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
        **({"sync_comparison": comparison, "framing_summary": framing_summary} if compare else {}),
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
    record.add_argument("--antenna", help="Optional antenna label")
    record.add_argument("--no-location", action="store_true", help="Skip GPS lookup")
    record.add_argument("--device-index", type=int, default=0)
    record.add_argument("--acquisition-mode", choices=("async", "sync", "auto"), default="async")
    play = sub.add_parser("replay")
    play.add_argument("--input", type=Path, required=True)
    play.add_argument("--compare-sync", action="store_true",
                      help="Replay strict and experimental persistent RDS synchronizers side by side")
    args = parser.parse_args()
    if args.command == "capture":
        if not 76 <= args.frequency <= 108 or args.seconds <= 0:
            parser.error("frequency must be 76–108 MHz and seconds positive")
        capture(args)
    else:
        replay(args)


if __name__ == "__main__":
    main()
