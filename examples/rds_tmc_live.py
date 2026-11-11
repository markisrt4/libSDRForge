# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Observe live RDS groups and possible TMC broadcasts with an RTL-SDR."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from sdrforge.adapters import RtlSdrSource
from sdrforge.protocols.rds.tmc_discovery import TmcDiscovery
from sdrforge.receivers import WbfmReceiver


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frequency", type=float, default=104.3, help="FM MHz")
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--gain", type=float, default=30.0)
    parser.add_argument("--auto-gain", action="store_true")
    parser.add_argument("--device-index", type=int, default=0)
    parser.add_argument("--acquisition-mode", choices=("auto", "sync", "async"), default="auto")
    parser.add_argument("--audio", action="store_true", help="Play stereo FM audio while decoding RDS")
    parser.add_argument("--player", default="ffplay", help="PCM player executable")
    parser.add_argument("--jsonl", type=Path, help="Save CRC-validated groups for offline inspection")
    args = parser.parse_args()
    if not 76 <= args.frequency <= 108:
        parser.error("frequency must be between 76 and 108 MHz")
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    if args.audio and not shutil.which(args.player):
        parser.error(f"{args.player!r} not found; install ffmpeg or choose --player")
    frequency_hz = round(args.frequency * 1_000_000)
    source = RtlSdrSource(device_index=args.device_index, acquisition_mode=args.acquisition_mode)
    receiver = WbfmReceiver(channel_frequency_hz=frequency_hz, mode="stereo", rds_enabled=True)
    scanner = TmcDiscovery()
    previous_dropped = 0
    rf_samples = 0
    last_report = time.monotonic()
    output = None
    player = None
    failed = False
    try:
        if args.jsonl is not None:
            output = args.jsonl.open("w", encoding="utf-8")
        source.open()
        source.set_center_frequency(frequency_hz)
        source.set_gain(None if args.auto_gain else args.gain)
        source.start()
        if args.audio:
            player = subprocess.Popen(
                [args.player, "-nodisp", "-autoexit", "-loglevel", "warning",
                 "-f", "s16le", "-ar", "48000", "-ch_layout", "stereo", "-i", "pipe:0"],
                stdin=subprocess.PIPE,
            )
        print(f"Listening {args.frequency:.3f} MHz for {args.seconds:.0f}s RF; Ctrl+C to stop", flush=True)
        while rf_samples < args.seconds * source.get_sample_rate():
            block = source.read_iq()
            stats = source.get_acquisition_stats()
            dropped = stats["dropped_blocks"]
            if dropped > previous_dropped:
                receiver.reset(preserve_metadata=True)
                scanner.reset()
            previous_dropped = dropped
            pcm = receiver.process(block)
            if player is not None:
                if player.poll() is not None:
                    raise RuntimeError(f"audio player exited: {player.returncode}")
                if player.stdin is None:
                    raise RuntimeError("audio player stdin unavailable")
                player.stdin.write((np.clip(pcm, -1.0, 1.0) * 32767).astype("<i2").tobytes())
            rf_samples += len(block.samples) // 2
            for group in receiver.last_rds_groups:
                scanner.process(group)
                if output is not None:
                    output.write(json.dumps(asdict(group)) + "\n")
            now = time.monotonic()
            if now - last_report >= 5:
                status = receiver.rds_status
                found = scanner.status
                print(
                    f"RF={rf_samples / source.get_sample_rate():.1f}s "
                    f"PI={hex(found.pi) if found.pi is not None else '-'} "
                    f"PS={status.metadata.program_service if status else '-'} "
                    f"groups={found.total_groups} 8A={found.group_8a_count} "
                    f"3A={found.group_3a_count} dropped={dropped}",
                    flush=True,
                )
                last_report = now
    except KeyboardInterrupt:
        print("Interrupted; reporting received groups.", flush=True)
    except (RuntimeError, OSError) as exc:
        failed = True
        print(f"Capture stopped (check USB connection if IQ read failed): {exc}", flush=True)
    finally:
        if player is not None:
            if player.stdin is not None:
                try:
                    player.stdin.close()
                except OSError:
                    pass
            try:
                player.wait(timeout=2)
            except subprocess.TimeoutExpired:
                player.terminate()
                try:
                    player.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    player.kill()
                    player.wait()
        try:
            source.close()
        except (RuntimeError, OSError) as exc:
            print(f"Cleanup warning: {exc}", flush=True)
        if output is not None:
            output.close()
    print(json.dumps(asdict(scanner.status), indent=2))
    print("Candidate 8A groups do not establish usable TMC traffic data.")
    if failed:
        print("Capture ended early; partial RDS results shown above.")


if __name__ == "__main__":
    main()
