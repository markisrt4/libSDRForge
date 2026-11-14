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

from sdrforge.dsp.digital_downconverter import DigitalDownconverter
from sdrforge.dsp.fm_multiplex_discriminator import FmMultiplexDiscriminator
from sdrforge.models.iq import IqBlock
from sdrforge.protocols.rds.rds_biphase_decoder import RdsBiphaseDecoder
from sdrforge.protocols.rds.rds_block_sync import decode_block
from sdrforge.protocols.rds.rds_carrier_recovery import RdsCarrierRecovery
from sdrforge.protocols.rds.rds_subcarrier_extractor import RdsSubcarrierExtractor
from sdrforge.protocols.rds.rds_symbol_timing_recovery import RdsSymbolTimingRecovery


def decode_erasures(bits, valid, start, names, count):
    """Resolve exactly count erased bits only if CRC yields one candidate."""
    if start + 26 > len(bits):
        return None
    erased = [i for i, flag in enumerate(valid[start:start + 26]) if not flag]
    if len(erased) != count:
        return None
    candidates = []
    for mask in range(1 << count):
        replacements = [(mask >> (count - 1 - i)) & 1 for i in range(count)]
        values = list(bits[start:start + 26])
        for index, value in zip(erased, replacements):
            values[index] = value
        word = 0
        for bit in values:
            word = (word << 1) | int(bit)
        for name in names:
            decoded = decode_block(word, name)
            if decoded is not None:
                candidates.append((decoded, [
                    {"bit_index": i, "recovered_value": v}
                    for i, v in zip(erased, replacements)]))
    return candidates[0] if len(candidates) == 1 else None

def decode_one_erasure(bits, valid, start, names):
    result = decode_erasures(bits, valid, start, names, 1)
    if result is None:
        return None
    return result[0], result[1][0]["bit_index"], result[1][0]["recovered_value"]

def group_detail(start, matches, corrections=None):
    b = matches[1][1]
    result = {
        "start_bit": start,
        "pi": f"0x{matches[0][1]:04X}",
        "block_b": f"0x{b:04X}",
        "block_c": f"0x{matches[2][1]:04X}",
        "block_d": f"0x{matches[3][1]:04X}",
        "group_type": (b >> 12) & 15,
        "version": "B" if b & 0x0800 else "A",
        "c_prime": matches[2][0] == "C_prime",
    }
    if (b >> 12) & 15 == 2:
        result["radiotext_ab"] = (b >> 4) & 1
        result["radiotext_segment"] = b & 15
        if not b & 0x0800:
            data = (matches[2][1], matches[3][1])
            result["radiotext_fragment"] = bytes([data[0] >> 8, data[0] & 255,
                                                   data[1] >> 8, data[1] & 255]).decode("latin-1")
    if corrections is not None:
        result["corrections"] = corrections
        result["status"] = "experimental_erasure_recovery"
    return result

def assemble_radiotext(clean, single, double):
    """Build conservative RadioText previews from independent group observations.

    A/B transitions start new epochs. Conflicting segments within an epoch are
    unresolved, not majority-voted. Erasure-corrected text is diagnostic only.
    """
    by_position = {}
    for tier, groups in (("two_erasure", double), ("one_erasure", single),
                         ("clean", clean)):
        for group in groups:
            if group.get("group_type") != 2 or group.get("version") != "A":
                continue
            if "radiotext_fragment" not in group:
                continue
            pos = group["start_bit"]
            # One RF group can appear in only one confidence tier.
            old = by_position.get(pos)
            rank = {"two_erasure": 0, "one_erasure": 1, "clean": 2}
            if old is None or rank[tier] > rank[old[0]]:
                by_position[pos] = (tier, group)
    observations = sorted(by_position.items())
    epochs = []
    current = None
    for pos, (tier, group) in observations:
        key = (group["pi"], group["radiotext_ab"])
        if current is None or current["key"] != key:
            current = {"key": key, "first_bit": pos, "last_bit": pos,
                       "segments": {}}
            epochs.append(current)
        current["last_bit"] = pos
        address = group["radiotext_segment"]
        fragment = group["radiotext_fragment"]
        variants = current["segments"].setdefault(address, {})
        record = variants.setdefault(fragment, {
            "clean": 0, "one_erasure": 0, "two_erasure": 0,
            "start_bits": [], "max_corrected_bits": 0})
        record[tier] += 1
        record["start_bits"].append(pos)
        corrected = sum(len(item["bits"]) for item in group.get("corrections", []))
        record["max_corrected_bits"] = max(record["max_corrected_bits"], corrected)
    output = []
    for epoch_index, epoch in enumerate(epochs):
        details = []
        chars = ["?"] * 64
        for address, variants in sorted(epoch["segments"].items()):
            ranked = sorted(variants.items(),
                key=lambda item: (-item[1]["clean"], -item[1]["one_erasure"],
                                  -item[1]["two_erasure"], item[0]))
            conflict = len(ranked) > 1
            if not conflict:
                chars[address * 4:address * 4 + 4] = list(ranked[0][0])
            details.append({"segment": address, "conflict": conflict,
                "variants": [{"text": fragment, **counts}
                             for fragment, counts in ranked]})
        terminators = [i for i, char in enumerate(chars) if char == "\r"]
        terminated = bool(terminators)
        if terminated:
            chars = chars[:terminators[0]]
        unresolved = "?" in chars
        conflicts = any(item["conflict"] for item in details)
        # Completeness is structural, not proof that erasure recovery was correct.
        complete = terminated and not unresolved and not conflicts
        output.append({
            "pi": epoch["key"][0], "radiotext_ab": epoch["key"][1],
            "epoch": epoch_index, "first_bit": epoch["first_bit"],
            "last_bit": epoch["last_bit"],
            "independent_observations": sum(
                sum(v["clean"] + v["one_erasure"] + v["two_erasure"]
                    for v in variants.values())
                for variants in epoch["segments"].values()),
            "preview": "".join(chars).rstrip("?"),
            "terminator_seen": terminated,
            "complete": complete,
            "contains_unresolved_characters": unresolved,
            "has_conflicts": conflicts,
            "experimental_only": True, "segments": details,
        })
    return output


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
    two_erasure_blocks = 0
    two_erasure_group_details = []
    for start in range(residue, len(bits) - 103, 104):
        offsets = (("A",), ("B",), ("C", "C_prime"), ("D",))
        matches = []
        recovered_matches = []
        corrections = []
        two_matches = []
        two_corrections = []
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
            two_recovered = (decode_erasures(bits, valid, start + 26 * index, names, 2)
                             if decoded is None and recovered is None else None)
            two_matches.append(decoded if decoded is not None else
                               (recovered[0] if recovered else
                                (two_recovered[0] if two_recovered else None)))
            if recovered is not None:
                two_corrections.append({"block": ("A", "B", "C", "D")[index],
                                        "bits": [{"bit_index": recovered[1],
                                                  "recovered_value": recovered[2]}]})
            if two_recovered is not None:
                two_erasure_blocks += 1
                two_corrections.append({"block": ("A", "B", "C", "D")[index],
                                        "bits": two_recovered[1]})
            if decoded is not None:
                counts["clean_blocks"] += 1
        if all(match is not None for match in matches) and matches[0][1] == pi:
            counts["complete_groups"] += 1
            complete_group_details.append(group_detail(start, matches))
        if (corrections and all(match is not None for match in recovered_matches)
                and recovered_matches[0][1] == pi):
            recovered_group_details.append(group_detail(
                start, recovered_matches, [
                    {"block": item["block"],
                     "bits": [{"bit_index": item["bit_index"],
                               "recovered_value": item["recovered_value"]}]}
                    for item in corrections]))
        if (two_corrections and all(match is not None for match in two_matches)
                and two_matches[0][1] == pi
                and any(len(item["bits"]) == 2 for item in two_corrections)):
            two_erasure_group_details.append(
                group_detail(start, two_matches, two_corrections))
    return {"status": "consensus", "residue": residue, "pi": f"0x{pi:04X}",
            "anchors": anchors, "clean_blocks": counts["clean_blocks"],
            "complete_groups": counts["complete_groups"],
            "complete_group_details": complete_group_details[:20],
            "single_erasure_recovered_blocks": recovered_blocks,
            "single_erasure_complete_groups": len(recovered_group_details),
            "single_erasure_group_details": recovered_group_details[:20],
            "two_erasure_recovered_blocks": two_erasure_blocks,
            "two_erasure_complete_groups": len(two_erasure_group_details),
            "two_erasure_group_details": two_erasure_group_details[:20],
            "radiotext_assemblies": assemble_radiotext(
                complete_group_details, recovered_group_details,
                two_erasure_group_details)}


def run(path, seconds, offsets, experimental_soft_pairs=False):
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
                       [([], []) for _ in (0, 1)],
                       [RdsBiphaseDecoder(pair_phase=i, experimental_soft_pairs=True)
                        for i in (0, 1)] if experimental_soft_pairs else [],
                       [([], [], []) for _ in (0, 1)] if experimental_soft_pairs else []))
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
            for _, timing, decoders, collected, soft_decoders, soft_collected in tracks:
                halves = timing.process(baseband)
                for decoder, (bits_out, valid_out) in zip(decoders, collected):
                    bits, valid = decoder.process(halves)
                    bits_out.extend(bits.tolist())
                    valid_out.extend(valid.tolist())
                for decoder, (bits_out, valid_out, uncertain_out) in zip(soft_decoders, soft_collected):
                    bits, valid = decoder.process(halves)
                    bits_out.extend(bits.tolist())
                    valid_out.extend(valid.tolist())
                    uncertain_out.extend(decoder.last_uncertain_mask.tolist())
            processed += len(raw) // 2
    results = []
    for offset, timing, decoders, collected, soft_decoders, soft_collected in tracks:
        phases = []
        for index, ((bits, valid), decoder) in enumerate(zip(collected, decoders)):
            phases.append({"phase": index,
                           "invalid_pair_fraction": (decoder.invalid_pairs / decoder.total_pairs
                                                     if decoder.total_pairs else None),
                           **score(bits, valid)})
        soft_phases = []
        for index, ((bits, valid, uncertain), decoder) in enumerate(zip(soft_collected, soft_decoders)):
            hypothesis = score(bits, valid)
            # CRC-passing candidate blocks that contain no guessed decisions
            # are independently observed, not soft-decision recoveries.
            details = hypothesis.get("complete_group_details", [])
            for group in details:
                start = group["start_bit"]
                group["guessed_decision_count"] = sum(uncertain[start:start + 104])
                group["status"] = ("observed" if not group["guessed_decision_count"]
                                   else "experimental_soft_pair")
            # Count all groups, not just the 20 examples retained in JSON.
            # score() currently truncates detail lists; avoid implying the
            # detail count covers every group.
            soft_phases.append({"phase": index, "guessed_pairs": decoder.soft_pair_guesses,
                                "displayed_group_guess_counts": [
                                    item["guessed_decision_count"] for item in details],
                                **hypothesis})
        results.append({"initial_phase_samples": offset,
                        "final_samples_per_half_bit": timing.samples_per_symbol,
                        "phases": phases,
                        "experimental_soft_phases": soft_phases})
    print(json.dumps({"file": str(path), "rf_seconds": round(processed / 2_400_000, 3),
                      "results": results,
                      "note": "Experimental soft-pair CRC matches contain guessed bits and are NOT strictly CRC-clean or trusted metadata."},
                     indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--offsets", type=float, nargs="+",
                        default=[0.0, 1.0, 2.0, 3.0, 4.0])
    parser.add_argument("--experimental-soft-pairs", action="store_true",
                        help="Compare untrusted soft-pair hypotheses with strict decoding")
    args = parser.parse_args()
    period = 12_000 / 2375
    if args.seconds <= 0 or any(not 0 <= offset < period for offset in args.offsets):
        parser.error("seconds must be positive and offsets within one half-bit period")
    run(args.input.expanduser(), args.seconds, args.offsets, args.experimental_soft_pairs)


if __name__ == "__main__":
    main()
