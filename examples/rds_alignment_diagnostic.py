# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Conservative offline RDS group alignment and single-erasure diagnostics.

This is deliberately separate from the production RDS synchronizer. A
reconstructed block is labeled corrected, never called unmodified CRC-valid.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from sdrforge.protocols.rds.rds_block_sync import decode_block
from sdrforge.dsp.digital_downconverter import DigitalDownconverter
from sdrforge.dsp.fm_multiplex_discriminator import FmMultiplexDiscriminator
from sdrforge.models.iq import IqBlock
from sdrforge.protocols.rds.rds_biphase_decoder import RdsBiphaseDecoder
from sdrforge.protocols.rds.rds_carrier_recovery import RdsCarrierRecovery
from sdrforge.protocols.rds.rds_subcarrier_extractor import RdsSubcarrierExtractor
from sdrforge.protocols.rds.rds_symbol_timing_recovery import RdsSymbolTimingRecovery

MASK = (1 << 26) - 1


def inspect_block(bits: list[int], valid: list[bool], offset: str):
    """Return unique payload and erasure count; never flip trusted bits."""
    if len(bits) != 26 or len(valid) != 26:
        raise ValueError("expected 26 bits")
    erased = [i for i, ok in enumerate(valid) if not ok]
    if len(erased) > 1:
        return None
    word = 0
    for bit in bits:
        word = (word << 1) | int(bit)
    if not erased:
        match = decode_block(word, offset)
        return (match[1], 0) if match else None
    mask = 1 << (25 - erased[0])
    matches = []
    for value in (word & ~mask, word | mask):
        match = decode_block(value, offset)
        if match:
            matches.append(match[1])
    return (matches[0], 1) if len(matches) == 1 else None


def analyze_bits(bits: list[int], valid: list[bool]) -> dict:
    """Find group-aligned A anchors and score the following 3 blocks."""
    counts = Counter()
    candidates = []
    for start in range(0, len(bits) - 25):
        a = inspect_block(bits[start:start + 26], valid[start:start + 26], "A")
        if a is None or a[1] != 0:
            continue  # Only uncorrected A blocks can anchor a candidate.
        blocks = [{"offset": "A", "data": f"0x{a[0]:04X}", "erasures": 0}]
        matched = 1
        corrected = 0
        for index, names in enumerate((("B",), ("C", "C_prime"), ("D",)), start=1):
            pos = start + index * 26
            if pos + 26 > len(bits):
                break
            result = next(((name, match) for name in names
                           if (match := inspect_block(bits[pos:pos + 26],
                                                     valid[pos:pos + 26], name))
                           is not None), None)
            if result is None:
                blocks.append({"offset": "/".join(names), "status": "missing"})
            else:
                name, (data, erasures) = result
                blocks.append({"offset": name, "data": f"0x{data:04X}",
                               "erasures": erasures})
                matched += 1
                corrected += erasures
        counts[f"anchors_with_{matched}_matching_blocks"] += 1
        if matched >= 2:
            candidates.append({"start_bit": start, "pi": f"0x{a[0]:04X}",
                               "matched_blocks": matched,
                               "corrected_blocks": corrected, "blocks": blocks})
    candidates.sort(key=lambda item: (-item["matched_blocks"],
                                      item["corrected_blocks"], item["start_bit"]))
    return {"anchor_counts": dict(counts), "top_candidates": candidates[:25],
            "complete_groups_strict": sum(c["matched_blocks"] == 4 and
                                          c["corrected_blocks"] == 0 for c in candidates),
            "complete_groups_with_single_erasures": sum(
                c["matched_blocks"] == 4 and c["corrected_blocks"] > 0 for c in candidates)}


def run(path: Path, seconds: float) -> None:
    meta = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if meta.get("format") != "rtl_u8_interleaved_iq" or meta.get("sample_rate_hz") != 2_400_000:
        raise ValueError("expected RTL 2.4 MSPS U8 recording")
    center = int(meta["center_frequency_hz"])
    ddc, fm = DigitalDownconverter(), FmMultiplexDiscriminator()
    extractor, carrier = RdsSubcarrierExtractor(), RdsCarrierRecovery()
    timing = RdsSymbolTimingRecovery(symbol_rate_hz=2375.0)
    decoders = [RdsBiphaseDecoder(pair_phase=i) for i in (0, 1)]
    collected = [([], []) for _ in range(2)]
    processed = 0
    limit = round(seconds * 2_400_000)
    gaps = sorted(meta.get("gaps", []), key=lambda g: g["sample_offset"])
    if gaps:
        raise ValueError("recorded gaps require segmented analysis; refusing to bridge discontinuities")
    with path.open("rb") as stream:
        while processed < limit:
            raw = stream.read(min(262144, 2 * (limit - processed)))
            if not raw:
                break
            if len(raw) % 2:
                raise ValueError("incomplete IQ pair")
            iq = IqBlock(samples=raw, center_frequency_hz=center,
                         sample_rate_hz=2_400_000, timestamp_ns=0)
            multiplex = fm.process(ddc.process(iq, center))
            halves = timing.process(carrier.process(extractor.process(multiplex)))
            for decoder, (bits_out, valid_out) in zip(decoders, collected):
                bits, valid = decoder.process(halves)
                bits_out.extend(int(b) for b in bits)
                valid_out.extend(bool(v) for v in valid)
            processed += len(raw) // 2
    print(json.dumps({
        "file": str(path), "seconds": round(processed / 2_400_000, 3),
        "phases": [{"phase": phase, **analyze_bits(bits, valid)}
                   for phase, (bits, valid) in enumerate(collected)],
        "caution": "One-erasure corrections are diagnostic only. Require repeated PI and coherent block sequences before trusting recovered groups.",
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", type=Path, nargs="+")
    parser.add_argument("--seconds", type=float, default=20)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    for path in args.recordings:
        run(path.expanduser(), args.seconds)


if __name__ == "__main__":
    main()
