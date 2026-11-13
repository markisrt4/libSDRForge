# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Offline Costas bandwidth sweep using one shared RF and RDS extraction pass."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rds_timing_sweep import score
from sdrforge.dsp.digital_downconverter import DigitalDownconverter
from sdrforge.dsp.fm_multiplex_discriminator import FmMultiplexDiscriminator
from sdrforge.models.iq import IqBlock
from sdrforge.protocols.rds.rds_biphase_decoder import RdsBiphaseDecoder
from sdrforge.protocols.rds.rds_carrier_recovery import RdsCarrierRecovery
from sdrforge.protocols.rds.rds_subcarrier_extractor import RdsSubcarrierExtractor
from sdrforge.protocols.rds.rds_symbol_timing_recovery import RdsSymbolTimingRecovery


def run(path: Path, seconds: float, bandwidths: list[float]) -> None:
    meta = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if meta.get("format") != "rtl_u8_interleaved_iq" or meta.get("sample_rate_hz") != 2_400_000:
        raise ValueError("expected 2.4 MSPS RTL unsigned IQ")
    if meta.get("gaps"):
        raise ValueError("cannot sweep across recorded IQ gaps")
    center = int(meta["center_frequency_hz"])
    ddc, fm, extractor = DigitalDownconverter(), FmMultiplexDiscriminator(), RdsSubcarrierExtractor()
    tracks = []
    for bandwidth in bandwidths:
        tracks.append({
            "bandwidth": bandwidth,
            "carrier": RdsCarrierRecovery(loop_bandwidth=bandwidth),
            "timing": RdsSymbolTimingRecovery(symbol_rate_hz=2375.0),
            "decoders": [RdsBiphaseDecoder(pair_phase=i) for i in (0, 1)],
            "collected": [([], []) for _ in (0, 1)],
        })
    processed = 0
    limit = round(seconds * 2_400_000)
    with path.open("rb") as stream:
        while processed < limit:
            raw = stream.read(min(262144, 2 * (limit - processed)))
            if not raw:
                break
            if len(raw) % 2:
                raise ValueError("incomplete IQ pair")
            block = IqBlock(samples=raw, center_frequency_hz=center,
                            sample_rate_hz=2_400_000, timestamp_ns=0)
            extracted = extractor.process(fm.process(ddc.process(block, center)))
            for track in tracks:
                corrected = track["carrier"].process(extracted)
                halves = track["timing"].process(corrected)
                for decoder, (bits_out, valid_out) in zip(track["decoders"], track["collected"]):
                    bits, valid = decoder.process(halves)
                    bits_out.extend(bits.tolist())
                    valid_out.extend(valid.tolist())
            processed += len(raw) // 2
    results = []
    for track in tracks:
        phases = []
        for phase, (decoder, (bits, valid)) in enumerate(zip(track["decoders"], track["collected"])):
            phases.append({
                "phase": phase,
                "invalid_pair_fraction": (decoder.invalid_pairs / decoder.total_pairs
                                          if decoder.total_pairs else None),
                **score(bits, valid),
            })
        results.append({
            "loop_bandwidth": track["bandwidth"],
            "carrier_offset_hz": track["carrier"].frequency_offset_hz,
            "final_samples_per_half_bit": track["timing"].samples_per_symbol,
            "phases": phases,
        })
    print(json.dumps({
        "file": str(path), "rf_seconds": round(processed / 2_400_000, 3),
        "results": results,
        "note": "Compare CRC-clean blocks and repeated PI; Manchester invalid-pair fraction is not BER.",
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--bandwidths", type=float, nargs="+",
                        default=[0.003, 0.0075, 0.015, 0.03, 0.06])
    args = parser.parse_args()
    if args.seconds <= 0 or any(not 0 < bandwidth < 0.2 for bandwidth in args.bandwidths):
        parser.error("seconds must be positive and bandwidths must be between 0 and 0.2")
    run(args.input.expanduser(), args.seconds, args.bandwidths)


if __name__ == "__main__":
    main()
