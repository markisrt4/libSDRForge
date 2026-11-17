"""Reproducible end-to-end NOAA SAME audio impairment benchmark.

Measures exact complete-header recovery; never claims an alert is validated.
Run with python -m sdrforge.weather.same_benchmark --trials 3 --json.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

import numpy as np

from .same_afsk import BAUD, decode_same_audio_diagnostic, synthesize_same_audio

HEADER = b"ZCZC-WXR-RWT-026099+0030-3211200-KDTX/NWS-"
DEFAULT_SNR_DB = (30.0, 20.0, 10.0, 5.0, 0.0)


@dataclass(frozen=True)
class BenchmarkResult:
    snr_db: float
    baud_error: float
    known_clock: bool
    trials: int
    exact_headers: int
    success_rate: float
    mean_byte_errors: float
    mean_prefix_bytes: float
    selected_baud_offsets: tuple[float, ...]


def add_awgn(audio: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Add reproducible white Gaussian noise at signal-power SNR in dB."""
    if not np.isfinite(snr_db):
        raise ValueError("snr_db must be finite")
    samples = np.asarray(audio, dtype=np.float64)
    if samples.ndim != 1 or not np.all(np.isfinite(samples)):
        raise ValueError("audio must be finite mono samples")
    if not len(samples):
        return samples.copy()
    power = float(np.mean(samples ** 2))
    if power == 0:
        return samples.copy()
    noise_std = np.sqrt(power / (10 ** (snr_db / 10)))
    return samples + rng.normal(0, noise_std, size=samples.shape)


def _byte_errors(expected: bytes, decoded: bytes) -> tuple[int, int]:
    """Best contiguous alignment and longest correct prefix for diagnostics.

    A deletion/insertion may inflate the mismatch count. This is a diagnostic
    approximation, not an edit-distance metric or SAME error correction.
    """
    if not decoded:
        return len(expected), 0
    best = (len(expected), 0)
    for start in range(len(decoded)):
        segment = decoded[start:start + len(expected)]
        errors = sum(a != b for a, b in zip(expected, segment))
        errors += len(expected) - len(segment)
        prefix = 0
        for a, b in zip(expected, segment):
            if a != b:
                break
            prefix += 1
        if (errors, -prefix) < (best[0], -best[1]):
            best = (errors, prefix)
    return best


def benchmark(*, snrs: tuple[float, ...] = DEFAULT_SNR_DB,
              baud_errors: tuple[float, ...] = (0.0, 1.0),
              trials: int = 3, seed: int = 2026,
              known_clock: bool = True) -> list[BenchmarkResult]:
    """Measure exact-byte header recovery, including clock-search failures.

    With known_clock=True the correct baud hypothesis is supplied, providing
    a best-case reference, NOT evidence of automatic clock estimation.
    """
    if trials < 1:
        raise ValueError("trials must be positive")
    if not snrs or not baud_errors:
        raise ValueError("snrs and baud_errors must be nonempty")
    if any(not np.isfinite(x) for x in (*snrs, *baud_errors)):
        raise ValueError("impairments must be finite")
    if any(BAUD + error <= 0 for error in baud_errors):
        raise ValueError("baud errors must leave a positive symbol rate")
    results = []
    for error in baud_errors:
        clean = synthesize_same_audio(HEADER, baud=BAUD + error)
        for snr in snrs:
            exact = 0
            total_errors = 0
            total_prefix = 0
            selected_offsets = []
            for trial in range(trials):
                # Stable independent streams per case; no global RNG state.
                rng = np.random.default_rng(np.random.SeedSequence(
                    [seed, trial, int(round((error + 100) * 1000)),
                     int(round((snr + 200) * 1000))]))
                noisy = add_awgn(clean, snr, rng)
                offsets = (error,) if known_clock else (-1.0, 0.0, 1.0)
                result = decode_same_audio_diagnostic(
                    noisy, 24000, baud_offsets=offsets)
                decoded = result.data
                selected_offsets.append(result.baud_offset)
                errors, prefix = _byte_errors(HEADER, decoded)
                total_errors += errors
                total_prefix += prefix
                exact += int(HEADER in decoded)
            results.append(BenchmarkResult(
                float(snr), float(error), known_clock, trials, exact,
                exact / trials, total_errors / trials, total_prefix / trials,
                tuple(selected_offsets)))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--snr", type=float, nargs="+", default=list(DEFAULT_SNR_DB))
    parser.add_argument("--baud-error", type=float, nargs="+", default=[0.0, 1.0])
    parser.add_argument("--unknown-clock", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    rows = benchmark(snrs=tuple(args.snr), baud_errors=tuple(args.baud_error),
                     trials=args.trials, seed=args.seed,
                     known_clock=not args.unknown_clock)
    if args.json:
        print(json.dumps([asdict(row) for row in rows], indent=2))
    else:
        for row in rows:
            print(f"SNR={row.snr_db:5.1f} dB baud_error={row.baud_error:+.2f} "
                  f"exact={row.exact_headers}/{row.trials} "
                  f"({row.success_rate:.0%}) "
                  f"byte_errors={row.mean_byte_errors:.1f} "
                  f"prefix={row.mean_prefix_bytes:.1f} "
                  f"selected_baud={row.selected_baud_offsets}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
