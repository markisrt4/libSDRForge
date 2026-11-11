# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Compare RDS extraction cutoff and Costas bandwidth on identical recorded IQ."""
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


def run(path: Path, seconds: float, cutoffs: list[float], bandwidths: list[float]) -> None:
    meta = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if meta.get("format") != "rtl_u8_interleaved_iq" or meta.get("sample_rate_hz") != 2_400_000:
        raise ValueError("expected 2.4 MSPS RTL unsigned IQ")
    if meta.get("gaps"):
        raise ValueError("cannot sweep across recorded IQ gaps")
    center = int(meta["center_frequency_hz"])
    ddc, fm = DigitalDownconverter(), FmMultiplexDiscriminator()
    tracks = []
    for cutoff in cutoffs:
        group = {"cutoff_hz": cutoff, "extractor": RdsSubcarrierExtractor(cutoff_hz=cutoff),
                 "variants": []}
        for bandwidth in bandwidths:
            group["variants"].append({
                "bandwidth": bandwidth,
                "carrier": RdsCarrierRecovery(loop_bandwidth=bandwidth),
                "timing": RdsSymbolTimingRecovery(symbol_rate_hz=2375.0),
                "decoders": [RdsBiphaseDecoder(pair_phase=i) for i in (0, 1)],
                "collected": [([], []) for _ in (0, 1)],
            })
        tracks.append(group)
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
            multiplex = fm.process(ddc.process(block, center))
            for group in tracks:
                extracted = group["extractor"].process(multiplex)
                for track in group["variants"]:
                    halves = track["timing"].process(track["carrier"].process(extracted))
                    for decoder, (bits_out, valid_out) in zip(track["decoders"], track["collected"]):
                        bits, valid = decoder.process(halves)
                        bits_out.extend(bits.tolist())
                        valid_out.extend(valid.tolist())
            processed += len(raw) // 2
    results = []
    for group in tracks:
        for track in group["variants"]:
            phases = []
            for phase, (decoder, (bits, valid)) in enumerate(zip(track["decoders"], track["collected"])):
                phases.append({
                    "phase": phase,
                    "invalid_pair_fraction": (decoder.invalid_pairs / decoder.total_pairs
                                              if decoder.total_pairs else None),
                    **score(bits, valid),
                })
            results.append({
                "cutoff_hz": group["cutoff_hz"],
                "loop_bandwidth": track["bandwidth"],
                "carrier_offset_hz": track["carrier"].frequency_offset_hz,
                "final_samples_per_half_bit": track["timing"].samples_per_symbol,
                "phases": phases,
            })
    print(json.dumps({
        "file": str(path), "rf_seconds": round(processed / 2_400_000, 3),
        "results": results,
        "note": "CRC-clean blocks and repeated PI are the primary scores; Manchester invalid-pair fraction is not BER.",
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--cutoffs", type=float, nargs="+",
                        default=[1500, 2000, 2500, 3000, 4000])
    parser.add_argument("--bandwidths", type=float, nargs="+",
                        default=[0.003, 0.015])
    args = parser.parse_args()
    if (args.seconds <= 0 or
            any(not 500 <= value <= 5500 for value in args.cutoffs) or
            any(not 0 < value < 0.2 for value in args.bandwidths)):
        parser.error("invalid seconds, cutoffs, or bandwidths")
    run(args.input.expanduser(), args.seconds, args.cutoffs, args.bandwidths)


if __name__ == "__main__":
    main()
