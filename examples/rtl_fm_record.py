# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Record stereo FM radio to a WAV file using a connected RTL-SDR dongle."""

from __future__ import annotations

import argparse
import time
import wave
from pathlib import Path

import numpy as np

from sdrforge.adapters import RtlSdrSource
from sdrforge.receivers import WbfmReceiver


def record(*, frequency_hz: int, seconds: float, output: Path,
           gain_db: float | None, mono: bool, rds: bool,
           device_index: int, acquisition_mode: str,
           rf_warmup_seconds: float) -> None:
    if rf_warmup_seconds < 0:
        raise ValueError("rf_warmup_seconds must be non-negative")
    if seconds <= 0:
        raise ValueError("seconds must be positive")
    if rds and mono:
        raise ValueError("RDS requires stereo decoding")
    source = RtlSdrSource(device_index=device_index, acquisition_mode=acquisition_mode)
    receiver = WbfmReceiver(
        channel_frequency_hz=frequency_hz,
        mode="mono" if mono else "stereo",
        rds_enabled=rds,
    )
    channels = 1 if mono else 2
    frames_written = 0
    started = time.monotonic()
    previous_report = started
    previous_dropped = 0
    try:
        source.open()
        source.set_center_frequency(frequency_hz)
        source.set_gain(gain_db)
        source.start()
        # Match ORC NativeRadioService: discard raw RF IQ while the tuner
        # settles, then reset receiver state before recording begins.
        warmup_samples = 0
        target_samples = round(rf_warmup_seconds * source.get_sample_rate())
        while warmup_samples < target_samples:
            block = source.read_iq()
            if (block.sample_rate_hz != source.get_sample_rate()
                    or block.center_frequency_hz != frequency_hz):
                raise RuntimeError("unexpected SDR format during RF warmup")
            warmup_samples += len(block.samples) // 2
        if target_samples:
            receiver.reset()
            print(f"RF warmup complete: {warmup_samples / source.get_sample_rate():.2f}s",
                  flush=True)
        started = time.monotonic()
        previous_report = started
        previous_dropped = source.get_acquisition_stats()["dropped_blocks"]
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)
            wav.setframerate(48_000)
            while frames_written < int(seconds * 48_000):
                block = source.read_iq()
                stats = source.get_acquisition_stats()
                dropped = stats["dropped_blocks"]
                if dropped > previous_dropped:
                    receiver.reset(preserve_metadata=True)
                previous_dropped = dropped
                pcm = receiver.process(block)
                remaining = int(seconds * 48_000) - frames_written
                pcm = pcm[:remaining]
                samples = np.clip(pcm, -1.0, 1.0)
                wav.writeframesraw((samples * 32767).astype("<i2").tobytes())
                frames_written += len(samples)
                now = time.monotonic()
                if now - previous_report >= 5:
                    status = receiver.rds_status
                    station = status.metadata if status is not None else None
                    print(
                        f"audio={frames_written / 48_000:.1f}s "
                        f"elapsed={now - started:.1f}s "
                        f"dropped={dropped} "
                        f"PI={hex(station.pi) if station and station.pi is not None else '-'} "
                        f"PS={station.program_service if station else '-'}",
                        flush=True,
                    )
                    previous_report = now
    finally:
        source.close()
    print(f"Saved {frames_written / 48_000:.2f}s of audio to {output}")
    print(f"Acquisition: {source.get_acquisition_stats()}")
    status = receiver.rds_status
    if status is not None:
        print(f"RDS: {status.metadata}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frequency", type=float, default=104.3, help="FM MHz")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=Path("fm-recording.wav"))
    parser.add_argument("--gain", type=float, default=30.0, help="Tuner gain dB")
    parser.add_argument("--auto-gain", action="store_true")
    parser.add_argument("--rf-warmup-seconds", type=float, default=2.0)\n    parser.add_argument("--mono", action="store_true")
    parser.add_argument("--rds", action="store_true")
    parser.add_argument("--device-index", type=int, default=0)
    parser.add_argument("--acquisition-mode", choices=("auto", "sync", "async"),
                        default="auto")
    args = parser.parse_args()
    record(
        frequency_hz=round(args.frequency * 1_000_000),
        seconds=args.seconds,
        output=args.output,
        gain_db=None if args.auto_gain else args.gain,
        mono=args.mono,
        rds=args.rds,
        device_index=args.device_index,
        acquisition_mode=args.acquisition_mode,\n        rf_warmup_seconds=args.rf_warmup_seconds,
    )


if __name__ == "__main__":
    main()
