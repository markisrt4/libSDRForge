# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Compare conventional Costas and pilot-referenced RDS recovery on saved IQ.

Experimental diagnostic only: does not modify production receiver DSP.
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
from sdrforge.protocols.rds.rds_biphase_decoder import RdsBiphaseDecoder
from sdrforge.protocols.rds.rds_block_sync import RdsBlockSynchronizer
from sdrforge.protocols.rds.rds_carrier_recovery import RdsCarrierRecovery
from sdrforge.protocols.rds.rds_subcarrier_extractor import RdsSubcarrierExtractor
from sdrforge.protocols.rds.rds_symbol_timing_recovery import RdsSymbolTimingRecovery

RATE = 240_000


class Decoder:
    def __init__(self, use_costas: bool, rotation: float = 0) -> None:
        self.carrier = RdsCarrierRecovery() if use_costas else None
        self.timing = RdsSymbolTimingRecovery(symbol_rate_hz=2375.0)
        self.biphases = [RdsBiphaseDecoder(pair_phase=i) for i in range(2)]
        self.blocks = [RdsBlockSynchronizer() for _ in range(2)]
        self.rotation = np.exp(1j * rotation)

    def process(self, samples: np.ndarray) -> None:
        if self.carrier is not None:
            samples = self.carrier.process(samples)
        else:
            samples = (samples * self.rotation).astype(np.complex64)
        halves = self.timing.process(samples)
        for decoder, blocks in zip(self.biphases, self.blocks):
            bits, valid = decoder.process(halves)
            blocks.process(bits, valid)

    def result(self) -> dict:
        return {
            "groups": [b.groups_found for b in self.blocks],
            "invalid_pair_fraction": [
                round(b.invalid_pairs / b.total_pairs, 4) if b.total_pairs else None
                for b in self.biphases
            ],
        }


def run(path: Path, seconds: float) -> None:
    meta = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if meta.get("format") != "rtl_u8_interleaved_iq" or meta.get("sample_rate_hz") != 2_400_000:
        raise ValueError("Expected 2.4 MSPS unsigned 8-bit RTL IQ")
    center = int(meta["center_frequency_hz"])
    ddc = DigitalDownconverter()
    fm = FmMultiplexDiscriminator()
    extractor = RdsSubcarrierExtractor()
    pilot_sos = signal.butter(4, [18700, 19300], btype="bandpass",
                              fs=RATE, output="sos")
    pilot_state = np.zeros((len(pilot_sos), 2))
    smooth_state = np.zeros(1, dtype=np.complex128)
    sample_index = 0
    decimation_phase = 0
    costas = Decoder(True)
    # Unknown RDS phase relative to pilot: sweep half a BPSK revolution.
    angles = np.linspace(0, np.pi, 12, endpoint=False)
    candidates = [Decoder(False, float(angle)) for angle in angles]
    processed = 0
    max_samples = round(seconds * 2_400_000)
    gaps = iter(sorted(meta.get("gaps", []), key=lambda g: g["sample_offset"]))
    next_gap = next(gaps, None)
    with path.open("rb") as stream:
        while processed < max_samples:
            if next_gap is not None and processed == next_gap["sample_offset"]:
                ddc.reset()
                fm.reset()
                extractor.reset()
                pilot_state[:] = 0
                smooth_state[:] = 0
                sample_index = 0
                decimation_phase = 0
                costas = Decoder(True)
                candidates = [Decoder(False, float(angle)) for angle in angles]
                next_gap = next(gaps, None)
            count = min(262144, 2 * (max_samples - processed))
            if next_gap is not None:
                count = min(count, 2 * (next_gap["sample_offset"] - processed))
            raw = stream.read(count)
            if not raw:
                break
            block = IqBlock(samples=raw, center_frequency_hz=center,
                            sample_rate_hz=2_400_000, timestamp_ns=0)
            multiplex = fm.process(ddc.process(block, center))
            rds = extractor.process(multiplex)
            pilot, pilot_state = signal.sosfilt(pilot_sos, multiplex, zi=pilot_state)
            indices = np.arange(len(pilot)) + sample_index
            pilot_base = pilot * np.exp(-2j * np.pi * 19000 * indices / RATE)
            smooth, smooth_state = signal.lfilter(
                [0.0005], [1, -0.9995], pilot_base, zi=smooth_state)
            reference = smooth[decimation_phase::20]
            # Triple the *residual* pilot phase, not its 19 kHz oscillation.
            # Multiplying by conjugate removes transmitter clock/phase drift.
            reference /= np.maximum(np.abs(reference), 1e-10)
            corrected = (rds * np.conj(reference ** 3)).astype(np.complex64)
            costas.process(rds)
            for candidate in candidates:
                candidate.process(corrected)
            decimation_phase = (decimation_phase - len(multiplex)) % 20
            sample_index = (sample_index + len(multiplex)) % RATE
            processed += len(raw) // 2
    results = [dict(phase_degrees=round(float(np.degrees(angle)), 1), **c.result())
               for angle, c in zip(angles, candidates)]
    results.sort(key=lambda r: (-max(r["groups"]), min(x for x in r["invalid_pair_fraction"] if x is not None)))
    print(json.dumps({
        "file": str(path), "seconds": round(processed / 2_400_000, 3),
        "costas": costas.result(), "pilot_referenced_best": results[:5],
        "note": "Experimental phase sweep; group counts, not pair validity alone, determine success.",
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", type=Path, nargs="+")
    parser.add_argument("--seconds", type=float, default=5)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    for recording in args.recordings:
        run(recording.expanduser(), args.seconds)


if __name__ == "__main__":
    main()
