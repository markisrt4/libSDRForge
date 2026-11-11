# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Offline RDS initial symbol-timing sweep on a single shared IQ replay.

Scores only CRC-clean blocks at a repeated-PI 104-bit alignment. This is a
diagnostic, not a change to the production receiver's timing loop.
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
from sdrforge.protocols.rds.rds_block_sync import decode_block
from sdrforge.protocols.rds.rds_carrier_recovery import RdsCarrierRecovery
from sdrforge.protocols.rds.rds_subcarrier_extractor import RdsSubcarrierExtractor
from sdrforge.protocols.rds.rds_symbol_timing_recovery import RdsSymbolTimingRecovery



def decode_one_erasure(bits, valid, start, names):
    """Recover exactly one invalid bit only when CRC yields a unique candidate."""
    if start + 26 > len(bits):
        return None
    erased = [i for i, flag in enumerate(valid[start:start + 26]) if not flag]
    if len(erased) != 1:
        return None
    candidates = []
    for value in (0, 1):
        word = 0
        for i, bit in enumerate(bits[start:start + 26]):
            word = (word << 1) | (value if i == erased[0] else int(bit))
        for name in names:
            decoded = decode_block(word, name)
            if decoded is not None:
                candidates.append((decoded, erased[0], value))
    return candidates[0] if len(candidates) == 1 else None

def score(bits, valid, *, min_anchors=2):
    """Find repeated clean A blocks; score CRC-clean B/C/D at that residue."""
    votes = Counter()
    words = []
    for pos in range(len(bits) - 25):
        if not all(valid[pos:pos + 26]):
            continue
        word = 0
        for bit in bits[pos:pos + 26]:
            word = (word << 1) | int(bit)
        words.append((pos, word))
        match = decode_block(word, "A")
        if match:
            votes[(pos % 104, match[1])] += 1
    if not votes:
        return {"status": "no_consensus", "anchors": 0, "clean_blocks": 0,
                "complete_groups": 0}
    (residue, pi), anchors = votes.most_common(1)[0]
    if anchors < min_anchors:
        return {"status": "no_consensus", "anchors": anchors,
                "clean_blocks": 0, "complete_groups": 0}
    word_map = dict(words)
    counts = Counter()
    complete_group_details = []
    recovered_group_details = []
    recovered_blocks = 0
    for start in range(residue, len(bits) - 103, 104):
        offsets = (("A",), ("B",), ("C", "C_prime"), ("D",))
        matches = []
        recovered_matches = []
        corrections = []
        for index, names in enumerate(offsets):
            word = word_map.get(start + 26 * index)
            decoded = (next((result for name in names
                             if (result := decode_block(word, name)) is not None), None)
                       if word is not None else None)
            matches.append(decoded)
            recovered = (decode_one_erasure(bits, valid, start + 26 * index, names)
                         if decoded is None else None)
            recovered_matches.append(decoded if decoded is not None else
                                     (recovered[0] if recovered else None))
            if recovered is not None:
                recovered_blocks += 1
                corrections.append({"block": ("A", "B", "C", "D")[index],
                                    "bit_index": recovered[1],
                                    "recovered_value": recovered[2]})
            if decoded is not None:
                counts["clean_blocks"] += 1
        if all(match is not None for match in matches) and matches[0][1] == pi:
            counts["complete_groups"] += 1
            complete_group_details.append({
                "start_bit": start,
                "pi": f"0x{matches[0][1]:04X}",
                "block_b": f"0x{matches[1][1]:04X}",
                "block_c": f"0x{matches[2][1]:04X}",
                "block_d": f"0x{matches[3][1]:04X}",
                "group_type": (matches[1][1] >> 12) & 0xF,
                "version": "B" if matches[1][1] & 0x0800 else "A",
                "c_prime": decode_block(word_map[start + 52], "C_prime") is not None,
            })
        if (corrections and all(match is not None for match in recovered_matches)
                and recovered_matches[0][1] == pi):
            b = recovered_matches[1][1]
            recovered_group_details.append({
                "start_bit": start,
                "pi": f"0x{pi:04X}",
                "block_b": f"0x{b:04X}",
                "block_c": f"0x{recovered_matches[2][1]:04X}",
                "block_d": f"0x{recovered_matches[3][1]:04X}",
                "group_type": (b >> 12) & 0xF,
                "version": "B" if b & 0x0800 else "A",
                "corrections": corrections,
                "status": "experimental_single_erasure_recovery",
            })
    return {"status": "consensus", "residue": residue, "pi": f"0x{pi:04X}",
            "anchors": anchors, "clean_blocks": counts["clean_blocks"],
            "complete_groups": counts["complete_groups"],
            "complete_group_details": complete_group_details[:20],
            "single_erasure_recovered_blocks": recovered_blocks,
            "single_erasure_complete_groups": len(recovered_group_details),
            "single_erasure_group_details": recovered_group_details[:20]}


def run(path, seconds, offsets):
    meta = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if meta.get("format") != "rtl_u8_interleaved_iq" or meta.get("sample_rate_hz") != 2_400_000:
        raise ValueError("expected 2.4 MSPS RTL unsigned IQ")
    if meta.get("gaps"):
        raise ValueError("cannot sweep across recorded IQ gaps")
    center = int(meta["center_frequency_hz"])
    ddc, fm, extractor, carrier = (DigitalDownconverter(), FmMultiplexDiscriminator(),
                                   RdsSubcarrierExtractor(), RdsCarrierRecovery())
    tracks = []
    for offset in offsets:
        timing = RdsSymbolTimingRecovery(symbol_rate_hz=2375.0,
                                         initial_phase_samples=offset)
        tracks.append((offset, timing, [RdsBiphaseDecoder(pair_phase=i) for i in (0, 1)],
                       [([], []) for _ in (0, 1)]))
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
            baseband = carrier.process(extractor.process(fm.process(ddc.process(block, center))))
            for _, timing, decoders, collected in tracks:
                halves = timing.process(baseband)
                for decoder, (bits_out, valid_out) in zip(decoders, collected):
                    bits, valid = decoder.process(halves)
                    bits_out.extend(bits.tolist())
                    valid_out.extend(valid.tolist())
            processed += len(raw) // 2
    results = []
    for offset, timing, decoders, collected in tracks:
        phases = []
        for index, ((bits, valid), decoder) in enumerate(zip(collected, decoders)):
            phases.append({"phase": index,
                           "invalid_pair_fraction": (decoder.invalid_pairs / decoder.total_pairs
                                                     if decoder.total_pairs else None),
                           **score(bits, valid)})
        results.append({"initial_phase_samples": offset,
                        "final_samples_per_half_bit": timing.samples_per_symbol,
                        "phases": phases})
    print(json.dumps({"file": str(path), "rf_seconds": round(processed / 2_400_000, 3),
                      "results": results,
                      "note": "CRC-clean counts are diagnostic; do not infer BER or metadata validity from Manchester pair fractions."},
                     indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--offsets", type=float, nargs="+",
                        default=[0.0, 1.0, 2.0, 3.0, 4.0])
    args = parser.parse_args()
    period = 12_000 / 2375
    if args.seconds <= 0 or any(not 0 <= offset < period for offset in args.offsets):
        parser.error("seconds must be positive and offsets within one half-bit period")
    run(args.input.expanduser(), args.seconds, args.offsets)


if __name__ == "__main__":
    main()
