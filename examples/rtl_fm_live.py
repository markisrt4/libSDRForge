# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Stream decoded FM audio to ffplay (or another raw PCM player)."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time

import numpy as np

from sdrforge.adapters import RtlSdrSource
from sdrforge.session import RadioSession


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frequency", type=float, default=104.3, help="FM MHz")
    parser.add_argument("--mono", action="store_true")
    parser.add_argument("--gain", type=float, default=30.0)
    parser.add_argument("--auto-gain", action="store_true")
    parser.add_argument("--seconds", type=float, default=0, help="0 = play until Ctrl+C")
    parser.add_argument("--player", default="ffplay", help="Raw PCM player executable")
    parser.add_argument("--acquisition-mode", choices=("auto", "async", "sync"),
                        default="async")
    parser.add_argument("--queue-blocks", type=int, default=64)
    args = parser.parse_args()
    if args.seconds < 0:
        parser.error("--seconds must be nonnegative")
    if args.queue_blocks <= 0:
        parser.error("--queue-blocks must be positive")
    if not shutil.which(args.player):
        parser.error(f"{args.player!r} not found; install ffmpeg with ffplay or choose --player")
    channels = 1 if args.mono else 2
    command = [args.player, "-nodisp", "-autoexit", "-loglevel", "warning",
               "-f", "s16le", "-ar", "48000", "-ch_layout",
               "mono" if channels == 1 else "stereo", "-i", "pipe:0"]
    source = RtlSdrSource(acquisition_mode=args.acquisition_mode,
                          queue_blocks=args.queue_blocks)
    radio = RadioSession(frequency_hz=round(args.frequency * 1_000_000),
                         mode="mono" if args.mono else "stereo",
                         gain_db=None if args.auto_gain else args.gain,
                         source=source)
    player = None
    frames = 0
    last_report = time.monotonic()
    try:
        with radio:
            player = subprocess.Popen(command, stdin=subprocess.PIPE)
            print(f"Playing {args.frequency:.1f} MHz ({channels} channel(s)); Ctrl+C to stop",
                  flush=True)
            while args.seconds == 0 or frames < args.seconds * 48_000:
                if player.poll() is not None:
                    raise RuntimeError(f"audio player exited with code {player.returncode}")
                pcm = radio.read().audio
                if args.seconds:
                    pcm = pcm[:max(0, int(args.seconds * 48_000) - frames)]
                samples = np.clip(pcm, -1.0, 1.0)
                payload = (samples * 32767).astype("<i2").tobytes()
                if player.stdin is None:
                    raise RuntimeError("audio player has no stdin")
                player.stdin.write(payload)
                frames += len(samples)
                now = time.monotonic()
                if now - last_report >= 5:
                    stats = source.get_acquisition_stats()
                    status = radio.status
                    print(f"audio={frames / 48_000:.1f}s "
                          f"dropped={stats['dropped_blocks']} "
                          f"queued={stats['queued_blocks']}/{stats['queue_capacity_blocks']} "
                          f"discontinuities={status.discontinuities} "
                          f"stereo_locked={status.stereo_locked}", flush=True)
                    last_report = now
    except KeyboardInterrupt:
        print("\nStopping radio...", flush=True)
    except BrokenPipeError as exc:
        raise RuntimeError("audio player closed its input") from exc
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
        print(f"Decoded {frames / 48_000:.2f}s of audio", flush=True)
        print(f"Acquisition: {source.get_acquisition_stats()}", flush=True)


if __name__ == "__main__":
    main()
