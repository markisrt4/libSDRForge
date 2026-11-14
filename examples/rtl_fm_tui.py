# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Minimal curses FM radio with keyboard tuning and live diagnostics.

Run via scripts/test_rtlsdr_termux.sh on Android so TERMUX_USB_FD is supplied.
"""

from __future__ import annotations

import argparse
import curses
import os
import sys
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field

import numpy as np

from sdrforge.adapters import RtlSdrSource
from sdrforge.session import RadioSession


@dataclass
class RadioState:
    frequency: float = 104.3
    mono: bool = True
    playing: bool = True
    error: str = ""
    stats: dict = field(default_factory=dict)
    discontinuities: int = 0
    stereo_locked: bool = False
    audio_seconds: float = 0.0


def audio_worker(state: RadioState, commands: queue.Queue, stopped: threading.Event) -> None:
    """Only this thread owns SDR and player lifecycle; UI never touches hardware."""
    while not stopped.is_set():
        if not state.playing:
            try:
                command = commands.get(timeout=0.15)
            except queue.Empty:
                continue
            if command == "quit":
                return
            continue

        frequency, mono = state.frequency, state.mono
        source = RtlSdrSource(acquisition_mode="async", queue_blocks=64)
        player = None
        try:
            with RadioSession(frequency_hz=round(frequency * 1_000_000),
                              mode="mono" if mono else "stereo",
                              gain_db=None, source=source) as radio:
                player = subprocess.Popen(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error",
                     "-f", "s16le", "-ar", "48000", "-ch_layout",
                     "mono" if mono else "stereo", "-i", "pipe:0"],
                    stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
                )
                state.error = ""
                state.audio_seconds = 0
                while not stopped.is_set() and state.playing:
                    try:
                        command = commands.get_nowait()
                    except queue.Empty:
                        command = None
                    if command == "quit":
                        stopped.set()
                        break
                    if command == "restart":
                        break
                    if player.poll() is not None:
                        raise RuntimeError(f"ffplay exited ({player.returncode})")
                    pcm = radio.read().audio
                    payload = (np.clip(pcm, -1, 1) * 32767).astype("<i2").tobytes()
                    if player.stdin is None:
                        raise RuntimeError("ffplay input unavailable")
                    player.stdin.write(payload)
                    state.audio_seconds += len(pcm) / 48_000
                    state.stats = source.get_acquisition_stats()
                    status = radio.status
                    state.discontinuities = status.discontinuities
                    state.stereo_locked = status.stereo_locked
        except Exception as exc:  # noqa: BLE001 - surface worker failure in UI
            state.error = str(exc)
            state.playing = False
        finally:
            if player is not None:
                if player.stdin is not None:
                    try:
                        player.stdin.close()
                    except OSError:
                        pass
                try:
                    player.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    player.terminate()
                    try:
                        player.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        player.kill()
                        player.wait()


def draw(screen, state: RadioState) -> None:
    screen.erase()
    height, width = screen.getmaxyx()
    lines = [
        "SDRForge FM Radio",
        "",
        f"  {state.frequency:6.1f} MHz   {'MONO' if state.mono else 'STEREO'}",
        f"  {'PLAYING' if state.playing else 'STOPPED'}",
        "",
        "  Gain          AUTO",
        (f"  IQ queue      {state.stats.get('queued_blocks', 0)} / "
         f"{state.stats.get('queue_capacity_blocks', 64)}"),
        f"  Dropped IQ    {state.stats.get('dropped_blocks', 0)}",
        f"  Gaps          {state.discontinuities}",
        f"  Stereo lock   {'YES' if state.stereo_locked else 'NO'}",
        f"  Audio         {state.audio_seconds:.1f}s",
        "",
        "  Left/Right: tune 0.1 MHz",
        "  Up/Down: tune 1 MHz",
        "  M: mono/stereo   Space: play/stop",
        "  Q: quit",
    ]
    if state.error:
        lines.extend(["", "Error: " + state.error])
    for y, line in enumerate(lines[:height]):
        try:
            screen.addnstr(y, 0, line, max(0, width - 1))
        except curses.error:
            pass
    screen.refresh()


def tui(screen, state: RadioState, commands: queue.Queue,
        stopped: threading.Event) -> None:
    curses.curs_set(0)
    screen.nodelay(True)
    screen.keypad(True)
    while not stopped.is_set():
        draw(screen, state)
        key = screen.getch()
        if key in (ord("q"), ord("Q")):
            stopped.set()
            commands.put("quit")
            break
        if key in (curses.KEY_LEFT, curses.KEY_RIGHT, curses.KEY_UP, curses.KEY_DOWN):
            step = {curses.KEY_LEFT: -0.1, curses.KEY_RIGHT: 0.1,
                    curses.KEY_UP: 1.0, curses.KEY_DOWN: -1.0}[key]
            state.frequency = round(min(108.0, max(87.5, state.frequency + step)), 1)
            state.playing = True
            commands.put("restart")
        elif key in (ord("m"), ord("M")):
            state.mono = not state.mono
            state.playing = True
            commands.put("restart")
        elif key == ord(" "):
            state.playing = not state.playing
            commands.put("restart")
        time.sleep(0.1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frequency", type=float, default=104.3)
    parser.add_argument("--stereo", action="store_true")
    args = parser.parse_args()
    if not 87.5 <= args.frequency <= 108.0:
        parser.error("FM frequency must be between 87.5 and 108.0 MHz")
    if not shutil.which("ffplay"):
        parser.error("ffplay not found")
    state = RadioState(frequency=args.frequency, mono=not args.stereo)
    commands: queue.Queue = queue.Queue()
    stopped = threading.Event()
    worker = threading.Thread(target=audio_worker, args=(state, commands, stopped),
                              name="fm-audio", daemon=True)
    worker.start()
    try:
        # termux-usb -E may launch us with stdin redirected away from the TTY.
        # Open the controlling terminal explicitly for curses input/output.
        try:
            tty_fd = os.open("/dev/tty", os.O_RDWR)
        except OSError as exc:
            raise RuntimeError(
                "No controlling terminal available to USB-launched TUI; "
                "run the frontend in an interactive Termux terminal"
            ) from exc
        try:
            with os.fdopen(tty_fd, "r+", buffering=1, closefd=True) as tty:
                old_stdin, old_stdout = sys.stdin, sys.stdout
                try:
                    sys.stdin = tty
                    sys.stdout = tty
                    curses.wrapper(tui, state, commands, stopped)
                finally:
                    sys.stdin, sys.stdout = old_stdin, old_stdout
        except curses.error as exc:
            raise RuntimeError(
                "Unable to initialize curses on the controlling terminal"
            ) from exc
    finally:
        stopped.set()
        commands.put("quit")
        worker.join(timeout=8)
        if worker.is_alive():
            print("Warning: radio shutdown is still in progress")


if __name__ == "__main__":
    main()
