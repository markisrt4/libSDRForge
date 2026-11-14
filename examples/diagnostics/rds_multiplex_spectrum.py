# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Offline FM multiplex spectral analysis of saved RTL-SDR IQ recordings.

Usage: python examples/rds_multiplex_spectrum.py ~/rds_947_good.iq
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import signal

from sdrforge.dsp.digital_downconverter import DigitalDownconverter
from sdrforge.dsp.fm_multiplex_discriminator import FmMultiplexDiscriminator
from sdrforge.models.iq import IqBlock

RATE = 240_000
NFFT = 16384
BLOCK_BYTES = 262144


def inspect(path: Path, seconds: float) -> None:
    metadata = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if metadata.get("format") != "rtl_u8_interleaved_iq" or metadata.get("sample_rate_hz") != 2_400_000:
        raise ValueError("Expected a 2.4 MSPS RTL unsigned 8-bit IQ recording")
    center = int(metadata["center_frequency_hz"])
    ddc = DigitalDownconverter()
    discriminator = FmMultiplexDiscriminator()
    accumulated = np.zeros(NFFT // 2 + 1, dtype=np.float64)
    windows = 0
    processed = 0
    max_samples = round(seconds * 2_400_000)
    pending = np.empty(0, dtype=np.float32)
    gaps = iter(sorted(metadata.get("gaps", []), key=lambda item: item["sample_offset"]))
    next_gap = next(gaps, None)
    with path.open("rb") as stream:
        while processed < max_samples:
            if next_gap is not None and processed == next_gap["sample_offset"]:
                ddc.reset()
                discriminator.reset()
                pending = np.empty(0, dtype=np.float32)
                next_gap = next(gaps, None)
            size = min(BLOCK_BYTES, 2 * (max_samples - processed))
            if next_gap is not None and processed < next_gap["sample_offset"]:
                size = min(size, 2 * (next_gap["sample_offset"] - processed))
            raw = stream.read(size)
            if not raw:
                break
            if len(raw) % 2:
                raise ValueError("Incomplete IQ sample at end of file")
            block = IqBlock(samples=raw, center_frequency_hz=center,
                            sample_rate_hz=2_400_000, timestamp_ns=0)
            multiplex = discriminator.process(ddc.process(block, center))
            processed += len(raw) // 2
            pending = np.concatenate((pending, multiplex))
            while len(pending) >= NFFT:
                frame = pending[:NFFT]
                pending = pending[NFFT // 2:]
                _, power = signal.periodogram(frame, fs=RATE, window="hann",
                                              nfft=NFFT, scaling="spectrum")
                accumulated += power
                windows += 1
    if not windows:
        raise ValueError("Recording too short for spectral analysis")
    power = accumulated / windows
    freqs = np.fft.rfftfreq(NFFT, 1 / RATE)
    def band(lo: float, hi: float) -> float:
        return float(np.sum(power[(freqs >= lo) & (freqs < hi)]))
    def db(value: float) -> float:
        return float(10 * np.log10(max(value, 1e-30)))
    def excess(target: tuple[float, float], neighbors: list[tuple[float, float]]) -> float:
        target_width = target[1] - target[0]
        noise_density = sum(band(*r) for r in neighbors) / sum(b-a for a,b in neighbors)
        return db(band(*target) / (noise_density * target_width + 1e-30))
    # Broadband RDS is BPSK: its center may be suppressed. Compare total band
    # energy to equal-width neighboring regions, not only the 57kHz FFT bin.
    metrics = {
        "file": str(path),
        "analyzed_rf_seconds": round(processed / 2_400_000, 3),
        "spectrum_windows": windows,
        "pilot_19khz_db": round(db(band(18900, 19100)), 2),
        "stereo_38khz_db": round(db(band(37000, 39000)), 2),
        "rds_54_60khz_db": round(db(band(54000, 60000)), 2),
        "rds_54_60khz_excess_db": round(excess((54000, 60000),
                 [(47000, 53000), (61000, 67000)]), 2),
        "rds_55_59khz_excess_db": round(excess((55000, 59000),
                 [(49000, 53000), (61000, 65000)]), 2),
        "rds_center_57khz_db": round(db(band(56900, 57100)), 2),
        "recorded_gaps": len(metadata.get("gaps", [])),
    }
    print(json.dumps(metrics, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", type=Path, nargs="+")
    parser.add_argument("--seconds", type=float, default=5,
                        help="Analyze this many seconds per file (default: 5)")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    for path in args.recordings:
        inspect(path.expanduser(), args.seconds)


if __name__ == "__main__":
    main()
