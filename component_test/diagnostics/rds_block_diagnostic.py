# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Offline RDS 26-bit block syndrome and per-second quality diagnostic.

Reads raw IQ recordings made by rds_iq_replay.py. Runs the production
downconverter, FM discriminator, RDS extractor, Costas loop, timing recovery,
and both biphase decoders. Counts independently valid 26-bit RDS blocks
without requiring four consecutive blocks to form a group.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from sdrforge.dsp.digital_downconverter import DigitalDownconverter
from sdrforge.dsp.fm_multiplex_discriminator import FmMultiplexDiscriminator
from sdrforge.models.iq import IqBlock
from sdrforge.protocols.rds.rds_biphase_decoder import RdsBiphaseDecoder
from sdrforge.protocols.rds.rds_block_sync import (
    OFFSET_WORDS,
    RdsBlockSynchronizer,
    syndrome,
)
from sdrforge.protocols.rds.rds_carrier_recovery import RdsCarrierRecovery
from sdrforge.protocols.rds.rds_subcarrier_extractor import RdsSubcarrierExtractor
from sdrforge.protocols.rds.rds_symbol_timing_recovery import RdsSymbolTimingRecovery


class BitInspector:
    def __init__(self) -> None:
        self.word = 0
        self.valid_window = 0
        self.bits_seen = 0
        self.offset_counts: Counter[str] = Counter()
        self.events: list[dict] = []
        self.groups = RdsBlockSynchronizer()

    def process(self, bits: np.ndarray, flags: np.ndarray, time_s: float) -> None:
        self.groups.process(bits, flags)
        for bit, valid in zip(bits, flags):
            self.word = ((self.word << 1) | int(bit)) & ((1 << 26) - 1)
            self.valid_window = ((self.valid_window << 1) | int(valid)) & ((1 << 26) - 1)
            self.bits_seen += 1
            if self.bits_seen < 26 or self.valid_window != (1 << 26) - 1:
                continue
            rem = syndrome(self.word)
            for name, offset in OFFSET_WORDS.items():
                if rem == offset:
                    self.offset_counts[name] += 1
                    if len(self.events) < 30:
                        self.events.append({"time_s": round(time_s, 2), "offset": name,
                                            "data": f"0x{self.word >> 10:04X}"})
                    break


def run(path: Path, seconds: float) -> None:
    meta = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if meta.get("format") != "rtl_u8_interleaved_iq" or meta.get("sample_rate_hz") != 2_400_000:
        raise ValueError("Expected a 2.4 MSPS unsigned 8-bit RTL IQ recording")
    center = int(meta["center_frequency_hz"])
    ddc = DigitalDownconverter()
    fm = FmMultiplexDiscriminator()
    extractor = RdsSubcarrierExtractor()
    carrier = RdsCarrierRecovery()
    timing = RdsSymbolTimingRecovery(symbol_rate_hz=2375.0)
    decoders = [RdsBiphaseDecoder(pair_phase=i) for i in (0, 1)]
    inspectors = [BitInspector(), BitInspector()]
    snapshots = []
    processed = 0
    next_report = 2_400_000
    limit = round(seconds * 2_400_000)
    gaps = iter(sorted(meta.get("gaps", []), key=lambda g: g["sample_offset"]))
    next_gap = next(gaps, None)
    resets = 0
    with path.open("rb") as stream:
        while processed < limit:
            if next_gap is not None and processed == next_gap["sample_offset"]:
                ddc.reset()
                fm.reset()
                extractor.reset()
                carrier.reset()
                timing.reset()
                for decoder in decoders:
                    decoder.reset()
                for inspector in inspectors:
                    inspector.word = 0
                    inspector.valid_window = 0
                    inspector.bits_seen = 0
                    inspector.groups.reset()
                resets += 1
                next_gap = next(gaps, None)
            count = min(262144, 2 * (limit - processed))
            if next_gap is not None:
                count = min(count, 2 * (next_gap["sample_offset"] - processed))
            raw = stream.read(count)
            if not raw:
                break
            if len(raw) % 2:
                raise ValueError("Incomplete I/Q pair")
            iq = IqBlock(samples=raw, center_frequency_hz=center,
                         sample_rate_hz=2_400_000, timestamp_ns=0)
            multiplex = fm.process(ddc.process(iq, center))
            halves = timing.process(carrier.process(extractor.process(multiplex)))
            processed += len(raw) // 2
            now = processed / 2_400_000
            for decoder, inspector in zip(decoders, inspectors):
                bits, valid = decoder.process(halves)
                inspector.process(bits, valid, now)
            if processed >= next_report:
                snapshots.append({
                    "second": round(now, 2),
                    "phase": [
                        {"pairs": d.total_pairs, "invalid_pairs": d.invalid_pairs,
                         "recent_invalid_fraction": d.recent_invalid_pair_fraction,
                         "crc_blocks": sum(i.offset_counts.values()),
                         "groups": i.groups.groups_found}
                        for d, i in zip(decoders, inspectors)
                    ],
                    "carrier_offset_hz": round(carrier.frequency_offset_hz, 2),
                    "half_bit_samples": round(timing.samples_per_symbol, 5),
                })
                next_report += 2_400_000
    print(json.dumps({
        "file": str(path), "seconds": round(processed / 2_400_000, 3),
        "gap_resets": resets,
        "phases": [
            {"phase": phase, "total_pairs": d.total_pairs,
             "invalid_pairs": d.invalid_pairs,
             "crc_blocks_by_offset": dict(i.offset_counts),
             "crc_blocks_total": sum(i.offset_counts.values()),
             "validated_groups": i.groups.groups_found,
             "first_block_matches": i.events}
            for phase, (d, i) in enumerate(zip(decoders, inspectors))
        ],
        "timeline": snapshots,
        "warning": "Single 26-bit CRC matches can occur by chance; repeated correctly spaced A/B/C/D blocks or full groups are stronger evidence.",
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", type=Path, nargs="+")
    parser.add_argument("--seconds", type=float, default=20)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    for recording in args.recordings:
        run(recording.expanduser(), args.seconds)


if __name__ == "__main__":
    main()
