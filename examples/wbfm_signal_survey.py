# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Measure relative RF quality from existing RTL-SDR U8 IQ recordings.

This is an *uncalibrated* receiver diagnostic. Channel contrast is not an
absolute SNR: adjacent stations, antenna, tuner gain and filter shape matter.

Usage:
  PYTHONPATH="$PWD:$PWD/src" python examples/wbfm_signal_survey.py ~/rds_*.iq --seconds 5
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import signal

RATE = 2_400_000
NFFT = 16384
BLOCK_SAMPLES = 262144
EPS = 1e-30


def db(power: float) -> float:
    return float(10 * np.log10(max(power, EPS)))


def inspect(path: Path, seconds: float) -> dict:
    metadata = json.loads(Path(str(path) + ".json").read_text(encoding="utf-8"))
    if metadata.get("format") != "rtl_u8_interleaved_iq" or metadata.get("sample_rate_hz") != RATE:
        raise ValueError(f"{path}: expected 2.4 MSPS RTL U8 interleaved IQ")
    if metadata.get("gaps"):
        raise ValueError(f"{path}: IQ gaps present; refusing discontinuous survey")
    total = min(round(seconds * RATE), path.stat().st_size // 2)
    accumulated = np.zeros(NFFT, dtype=np.float64)
    windows = 0
    sample_count = 0
    sum_power = 0.0
    clip_count = 0
    pending = np.empty(0, dtype=np.complex64)
    with path.open("rb") as stream:
        while sample_count < total:
            raw = stream.read(min(BLOCK_SAMPLES, total - sample_count) * 2)
            if not raw:
                break
            data = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 2)
            clip_count += int(np.count_nonzero(np.any((data <= 1) | (data >= 254), axis=1)))
            iq = (data[:, 0].astype(np.float32) - 127.5 +
                  1j * (data[:, 1].astype(np.float32) - 127.5)) / 128.0
            sum_power += float(np.sum(np.abs(iq) ** 2))
            sample_count += len(iq)
            pending = np.concatenate((pending, iq))
            while len(pending) >= NFFT:
                frame = pending[:NFFT]
                pending = pending[NFFT // 2:]
                _, psd = signal.periodogram(frame, fs=RATE, window="hann",
                                            nfft=NFFT, return_onesided=False,
                                            scaling="density")
                accumulated += psd
                windows += 1
    if not windows:
        raise ValueError(f"{path}: recording too short (need at least {NFFT} IQ samples)")
    frequencies = np.fft.fftfreq(NFFT, 1 / RATE)
    power = accumulated / windows
    def density(lo: float, hi: float) -> float:
        mask = (np.abs(frequencies) >= lo) & (np.abs(frequencies) < hi)
        return float(np.mean(power[mask]))
    def integrated(lo: float, hi: float) -> float:
        mask = (np.abs(frequencies) >= lo) & (np.abs(frequencies) < hi)
        return float(np.sum(power[mask]) * RATE / NFFT)
    # Exclude the DC spur and compare the WBFM channel to nearby spectrum.
    # Adjacent FM channels can contaminate the reference: this is contrast,
    # deliberately NOT called calibrated SNR.
    channel_density = density(10_000, 100_000)
    reference_density = density(300_000, 500_000)
    # Excluding DC prevents a receiver DC spike from dominating channel power.
    channel_power = integrated(10_000, 100_000)
    return {
        "file": str(path),
        "frequency_mhz": metadata["center_frequency_hz"] / 1e6,
        "seconds": round(sample_count / RATE, 3),
        "gain_db": metadata.get("gain_db"),
        "antenna": metadata.get("antenna"),
        "gps_status": (metadata.get("location") or {}).get("status", "unknown"),
        "iq_rms_dbfs_relative": round(db(sum_power / sample_count), 2),
        "channel_power_dbfs_relative": round(db(channel_power), 2),
        "channel_to_reference_db": round(db(channel_density / max(reference_density, EPS)), 2),
        "reference_density_db": round(db(reference_density), 2),
        "near_adc_rail_fraction": round(clip_count / sample_count, 6),
        "spectral_windows": windows,
        "recorded_gaps": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--seconds", type=float, default=5.0)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    results = [inspect(p.expanduser(), args.seconds) for p in args.recordings]
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
