# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Observe live RDS groups and possible TMC broadcasts with an RTL-SDR."""

from __future__ import annotations

import argparse
import curses
import os
import sys
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


def draw_dashboard(screen, frequency, rf_seconds, target_seconds, stats, receiver,
                   found, decode_ratio, audio_enabled, message=""):
    screen.erase()
    height, width = screen.getmaxyx()
    status = receiver.rds_status
    ps = status.metadata.program_service if status else None
    lines = [
        "libSDRForge | Live RDS / TMC",
        f"Station: {frequency:.1f} MHz  Audio: {'ON' if audio_enabled else 'OFF'}",
        f"RF captured: {rf_seconds:.1f} / {target_seconds:.1f} seconds",
        "",
        f"IQ received: {stats.get('received_blocks', 0)} blocks",
        f"IQ queue: {stats.get('queued_blocks', 0)}/{stats.get('queue_capacity_blocks', 0)}",
        f"IQ dropped: {stats.get('dropped_blocks', 0)}",
        f"Stereo pilot locked: {'YES' if receiver.stereo_locked else 'NO'}",
        f"DSP decode ratio: {decode_ratio:.2f} (below 1 preferred)",
        "",
        f"RDS PI: {hex(found.pi) if found.pi is not None else '-'}",
        f"Program service: {ps or '-'}",
        f"Validated RDS groups: {found.total_groups}",
        f"TMC 8A groups: {found.group_8a_count}",
        f"ODA 3A groups: {found.group_3a_count}",
        "",
        "Q: quit | Ctrl+C: quit",
    ]
    if message:
        lines.append("Status: " + message)
    for y, line in enumerate(lines[:height]):
        try:
            screen.addnstr(y, 0, line, max(0, width - 1))
        except curses.error:
            pass
    screen.refresh()


def open_dashboard():
    """Use the controlling terminal; Termux USB launch may redirect stdin."""
    fd = os.open("/dev/tty", os.O_RDWR)
    tty = os.fdopen(fd, "r+", buffering=1)
    old_stdin, old_stdout = sys.stdin, sys.stdout
    try:
        sys.stdin = tty
        sys.stdout = tty
        screen = curses.initscr()
        curses.noecho()
        curses.cbreak()
        screen.keypad(True)
        screen.nodelay(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        return screen, tty, old_stdin, old_stdout
    except BaseException:
        sys.stdin, sys.stdout = old_stdin, old_stdout
        tty.close()
        raise


def close_dashboard(screen, tty, old_stdin, old_stdout):
    try:
        screen.keypad(False)
        curses.nocbreak()
        curses.echo()
        curses.endwin()
    finally:
        sys.stdin, sys.stdout = old_stdin, old_stdout
        tty.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frequency", type=float, default=104.3, help="FM MHz")
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--gain", type=float, default=30.0)
    parser.add_argument("--auto-gain", action="store_true")
    parser.add_argument("--device-index", type=int, default=0)
    parser.add_argument("--acquisition-mode", choices=("auto", "sync", "async"), default="auto")
    parser.add_argument("--tui", action="store_true", help="Live curses RDS/TMC dashboard")
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
    processing_seconds = 0.0
    processed_audio_seconds = 0.0
    output = None
    player = None
    failed = False
    dashboard = None
    dashboard_context = None
    last_dashboard = 0.0
    try:
        if args.jsonl is not None:
            output = args.jsonl.open("w", encoding="utf-8")
        if args.tui:
            dashboard_context = open_dashboard()
            dashboard = dashboard_context[0]
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
        if not args.tui:
            print(f"Listening {args.frequency:.3f} MHz for {args.seconds:.0f}s RF; Ctrl+C to stop", flush=True)
        while rf_samples < args.seconds * source.get_sample_rate():
            if dashboard is not None and dashboard.getch() in (ord("q"), ord("Q")):
                break
            block = source.read_iq()
            stats = source.get_acquisition_stats()
            dropped = stats["dropped_blocks"]
            if dropped > previous_dropped:
                receiver.reset(preserve_metadata=True)
                scanner.reset()
            previous_dropped = dropped
            decode_start = time.monotonic()
            pcm = receiver.process(block)
            processing_seconds += time.monotonic() - decode_start
            processed_audio_seconds += len(pcm) / 48000.0
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
            if dashboard is not None and now - last_dashboard >= 0.2:
                draw_dashboard(dashboard, args.frequency, rf_samples / source.get_sample_rate(),
                               args.seconds, stats, receiver, scanner.status,
                               processing_seconds / max(processed_audio_seconds, 0.001), args.audio)
                last_dashboard = now
            if dashboard is None and now - last_report >= 5:
                status = receiver.rds_status
                found = scanner.status
                print(
                    f"RF={rf_samples / source.get_sample_rate():.1f}s "
                    f"PI={hex(found.pi) if found.pi is not None else '-'} "
                    f"PS={status.metadata.program_service if status else '-'} "
                    f"groups={found.total_groups} 8A={found.group_8a_count} "
                    f"3A={found.group_3a_count} dropped={dropped} "
                    f"decode_ratio={processing_seconds / max(processed_audio_seconds, 0.001):.2f} "
                    f"stereo_locked={receiver.stereo_locked}",
                    flush=True,
                )
                last_report = now
    except KeyboardInterrupt:
        print("Interrupted; reporting received groups.", flush=True)
    except (RuntimeError, OSError) as exc:
        failed = True
        print(f"Capture stopped (check USB connection if IQ read failed): {exc}", flush=True)
    finally:
        if dashboard_context is not None:
            close_dashboard(*dashboard_context)
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
