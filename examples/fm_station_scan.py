# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Single-USB-session FM survey for Termux and Linux.

Termux: bash scripts/run_rtlsdr_termux_logged.sh examples/fm_station_scan.py \
    --start 88.1 --stop 107.9 --step 0.8 --dwell 0.3 --top 8
This is a relative RF survey, not proof that a station transmits RDS.
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
from scipy.signal import periodogram

from sdrforge.adapters import RtlSdrSource

RATE = 2_400_000
NFFT = 16384
EPS = 1e-30


def power_db(value: float) -> float:
    return round(float(10 * np.log10(max(value, EPS))), 2)


def evaluate(raw: bytes) -> dict:
    """Measure a center channel against off-channel shoulders; reject DC."""
    data = np.frombuffer(raw, dtype=np.uint8)
    if len(data) < NFFT * 2:
        raise ValueError("insufficient IQ for spectrum")
    pairs = data[: len(data) // 2 * 2].reshape(-1, 2)
    clip = float(np.mean(np.any((pairs <= 1) | (pairs >= 254), axis=1)))
    iq = ((pairs[:, 0].astype(np.float32) - 127.5) +
          1j * (pairs[:, 1].astype(np.float32) - 127.5)) / 128
    bins = np.zeros(NFFT, dtype=np.float64)
    count = 0
    for start in range(0, len(iq) - NFFT + 1, NFFT):
        freq, spectrum = periodogram(iq[start:start + NFFT], fs=RATE,
                                     nfft=NFFT, window="hann",
                                     return_onesided=False, scaling="density")
        bins += spectrum
        count += 1
    bins /= count

    def density(low: float, high: float) -> float:
        mask = (np.abs(freq) >= low) & (np.abs(freq) < high)
        return float(np.mean(bins[mask]))

    center = density(10_000, 90_000)
    shoulders = (density(140_000, 220_000) + density(300_000, 450_000)) / 2
    return {
        "channel_contrast_db": power_db(center / max(shoulders, EPS)),
        "channel_density_db": power_db(center),
        "reference_density_db": power_db(shoulders),
        "iq_rms_dbfs_relative": power_db(float(np.mean(np.abs(iq) ** 2))),
        "near_adc_rail_fraction": round(clip, 6),
    }


def frequencies(start: float, stop: float, step: float) -> list[int]:
    """Produce integer-Hz frequencies without accumulating float drift."""
    first, last, stride = (round(v * 1e6) for v in (start, stop, step))
    if stride <= 0 or first > last:
        raise ValueError("invalid frequency range")
    return list(range(first, last + 1, stride))


def scan(source: RtlSdrSource, center_hz: int, dwell: float, settle: float) -> dict:
    # Stopping the asynchronous reader before retuning prevents stale queued
    # blocks and avoids changing tuner state while librtlsdr is reading.
    source.stop()
    source.set_center_frequency(center_hz)
    time.sleep(settle)
    source.start()
    raw = bytearray()
    samples_needed = round(dwell * RATE)
    samples = 0
    try:
        while samples < samples_needed:
            block = source.read_iq()
            raw.extend(block.samples)
            samples += len(block.samples) // 2
        stats = source.get_acquisition_stats()
    finally:
        source.stop()
    result = {"frequency_mhz": round(center_hz / 1e6, 4),
              "dropped_blocks": stats["dropped_blocks"],
              "received_seconds": round(samples / RATE, 3)}
    if stats["dropped_blocks"]:
        result["error"] = "IQ blocks dropped; ranking invalid"
    else:
        result.update(evaluate(bytes(raw)))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=float, default=88.1)
    parser.add_argument("--stop", type=float, default=107.9)
    parser.add_argument("--step", type=float, default=0.8)
    parser.add_argument("--dwell", type=float, default=0.3)
    parser.add_argument("--settle", type=float, default=0.08)
    parser.add_argument("--gain", type=float, default=30)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--output", help="Optional JSON report file")
    args = parser.parse_args()
    if not (88 <= args.start <= args.stop <= 108):
        parser.error("FM range must be within 88–108 MHz")
    if args.dwell < 0.1 or args.settle < 0 or args.top < 1 or args.step <= 0:
        parser.error("dwell >= 0.1, settle >= 0, step > 0, top >= 1 required")
    centers = frequencies(args.start, args.stop, args.step)
    if len(centers) > 250:
        parser.error("limit scan to 250 tuning points")
    source = RtlSdrSource(acquisition_mode="async")
    results = []
    try:
        source.open()
        source.set_gain(args.gain)
        for index, center in enumerate(centers, 1):
            print(f"Scanning {index}/{len(centers)}: {center / 1e6:.3f} MHz", flush=True)
            try:
                results.append(scan(source, center, args.dwell, args.settle))
            except Exception as exc:
                results.append({"frequency_mhz": center / 1e6, "error": str(exc)})
                # USB failure is not recoverable by blindly retuning.
                if not source.is_connected():
                    break
    finally:
        source.close()
    valid = [r for r in results if "channel_contrast_db" in r]
    valid.sort(key=lambda r: r["channel_contrast_db"], reverse=True)
    report = {
        "method": "relative centered-channel contrast; not calibrated SNR or RDS confirmation",
        "sample_rate_hz": RATE, "gain_db": args.gain,
        "scan_points": len(results), "successful_points": len(valid),
        "ranked_candidates": valid[:args.top],
        "all_measurements": results,
    }
    output = json.dumps(report, indent=2)
    print(output)
    if args.output:
        from pathlib import Path
        destination = Path(args.output).expanduser()
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(output + "\n")


if __name__ == "__main__":
    main()
