# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Observe live RDS groups and possible TMC broadcasts with an RTL-SDR."""

from __future__ import annotations

import argparse
import curses
import json
import os
import shutil
import sys
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from sdrforge.adapters import RtlSdrSource
from sdrforge.protocols.rds.rds_radiotext_assembler import RdsRadioTextAssembler
from sdrforge.protocols.rds.tmc_discovery import TmcDiscovery
from sdrforge.receivers import WbfmReceiver


def draw_dashboard(screen, frequency, rf_seconds, target_seconds, stats, receiver,
                   found, decode_ratio, audio_enabled, message="", radiotext=None,
                   corrected_groups=0):
    """Render a responsive color curses dashboard without extra dependencies."""
    screen.erase()
    height, width = screen.getmaxyx()
    status = receiver.rds_status
    ps = status.metadata.program_service if status else None
    colored = curses.has_colors()
    if colored:
        curses.start_color()
        try:
            curses.use_default_colors()
        except curses.error:
            pass
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)

    def line(y, value, color=0, bold=False):
        if not 0 <= y < height or width < 2:
            return
        attr = curses.color_pair(color) if colored and color else 0
        if bold:
            attr |= curses.A_BOLD
        try:
            screen.addnstr(y, 0, str(value), width - 1, attr)
        except curses.error:
            pass

    line(0, "  libSDRForge  /  RDS SIGNAL MONITOR", 1, True)
    line(1, "=" * min(width - 1, 72), 1)
    line(2, f"  {frequency:7.3f} MHz    {'STEREO' if receiver.stereo_locked else 'MONO'}"
         f"    AUDIO {'ON' if audio_enabled else 'OFF'}", 2, True)
    progress = min(1.0, rf_seconds / max(target_seconds, 0.001))
    bar_width = max(0, min(width - 22, 38))
    filled = round(progress * bar_width)
    line(3, f"  RF [{('#' * filled).ljust(bar_width, '-')}] {rf_seconds:.1f}s", 1)
    line(5, f"  STATION  {ps or 'SEARCHING'}    PI: "
         f"{hex(found.pi).upper() if found.pi is not None else '--'}", 2, True)
    line(7, "  RADIO TEXT", 1, True)
    if radiotext is not None:
        line(8, "  " + radiotext.preview, 2 if radiotext.complete else 3, True)
        line(9, f"  Segments received: {16 - len(radiotext.missing_segments)}/16"
             f"  Observations: {radiotext.observations}"
             f"  Conflicts: {len(radiotext.conflicting_segments)}")
        line(10, f"  Message: {'COMPLETE' if radiotext.complete else 'ASSEMBLING'}"
             f"  Corrected observations: {radiotext.corrected_observations}", 2)
    else:
        line(8, "  Waiting for RDS RadioText...", 3)
    line(12, "  SIGNAL / DECODER", 1, True)
    line(13, f"  Groups: {found.total_groups}  Corrected: {corrected_groups}"
         f"  Sync confidence: {status.sync_confidence if status else '-'}/10")
    line(14, f"  RDS RMS: {status.rds_baseband_rms:.5f}" if status else "  RDS RMS: --")
    line(15, f"  Carrier: {status.carrier_offset_hz:+.1f} Hz" if status else "  Carrier: --")
    line(16, f"  Pair phase: {status.locked_pair_phase if status and status.locked_pair_phase is not None else 'SEARCHING'}"
         f"  Phase groups: {status.phase_groups_found if status else '--'}")
    line(17, f"  DSP load: {decode_ratio:.2f}x  "
         f"IQ dropped: {stats.get('dropped_blocks', 0)}"
         f"  Queue: {stats.get('queued_blocks', 0)}/{stats.get('queue_capacity_blocks', 0)}")
    line(19, f"  TMC 8A: {found.group_8a_count}    ODA 3A: {found.group_3a_count}")
    if message:
        line(20, "  " + message, 3)
    line(height - 1, "  [Q] Quit   |   RDS/TMC experimental monitor", 1)
    screen.refresh()


def open_dashboard():
    """Attach curses to /dev/tty even when termux-usb redirects stdio."""
    tty_fd = os.open("/dev/tty", os.O_RDWR)
    saved_stdin = os.dup(0)
    saved_stdout = os.dup(1)
    try:
        sys.stdout.flush()
        os.dup2(tty_fd, 0)
        os.dup2(tty_fd, 1)
        screen = curses.initscr()
        curses.noecho()
        curses.cbreak()
        screen.keypad(True)
        screen.nodelay(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        return screen, tty_fd, saved_stdin, saved_stdout
    except BaseException:
        os.dup2(saved_stdin, 0)
        os.dup2(saved_stdout, 1)
        os.close(saved_stdin)
        os.close(saved_stdout)
        os.close(tty_fd)
        raise


def close_dashboard(screen, tty_fd, saved_stdin, saved_stdout):
    try:
        screen.keypad(False)
        curses.nocbreak()
        curses.echo()
        curses.endwin()
    finally:
        sys.stdout.flush()
        os.dup2(saved_stdin, 0)
        os.dup2(saved_stdout, 1)
        os.close(saved_stdin)
        os.close(saved_stdout)
        os.close(tty_fd)


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
    radiotext_assembler = RdsRadioTextAssembler()
    corrected_groups = 0
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
                radiotext_assembler.reset()
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
                radiotext_assembler.process(group)
                corrected_groups += int(group.corrected_bits > 0)
                if output is not None:
                    output.write(json.dumps(asdict(group)) + "\n")
            now = time.monotonic()
            if dashboard is not None and now - last_dashboard >= 0.2:
                draw_dashboard(dashboard, args.frequency, rf_samples / source.get_sample_rate(),
                               args.seconds, stats, receiver, scanner.status,
                               processing_seconds / max(processed_audio_seconds, 0.001), args.audio,
                               radiotext=radiotext_assembler.snapshot(),
                               corrected_groups=corrected_groups)
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
