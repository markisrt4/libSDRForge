# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Offline RDS framing consensus, without changing the live receiver.

A clean A block votes for a 104-bit group alignment. A consensus alignment
is only reported when at least two clean A blocks share the same PI and
104-bit residue. Missing blocks remain missing; one-erasure reconstructions
are explicitly marked and never treated as clean.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from sdrforge.protocols.rds.rds_block_sync import decode_block

MASK = (1 << 26) - 1


def check_block(bits, valid, offset, *, allow_erasure=False):
    if len(bits) != 26 or len(valid) != 26:
        return None
    missing = [i for i, ok in enumerate(valid) if not ok]
    if len(missing) > (1 if allow_erasure else 0):
        return None
    word = 0
    for bit in bits:
        word = (word << 1) | int(bit)
    if not missing:
        result = decode_block(word, offset)
        return {"data": result[1], "quality": "clean"} if result else None
    mask = 1 << (25 - missing[0])
    options = []
    for candidate in (word & ~mask, word | mask):
        result = decode_block(candidate, offset)
        if result:
            options.append(result[1])
    if len(options) == 1:
        return {"data": options[0], "quality": "one_erasure"}
    return None


def analyze_framing(bits, valid, *, min_anchors=2, max_groups=30):
    if len(bits) != len(valid):
        raise ValueError("bit and validity lengths differ")
    votes = defaultdict(list)
    for pos in range(len(bits) - 25):
        result = check_block(bits[pos:pos + 26], valid[pos:pos + 26], "A")
        if result:
            votes[(pos % 104, result["data"])].append(pos)
    rankings = sorted(votes.items(), key=lambda item: (-len(item[1]), item[0]))
    if not rankings or len(rankings[0][1]) < min_anchors:
        return {"status": "no_consensus", "top_votes": [
            {"residue": residue, "pi": f"0x{pi:04X}", "anchors": len(positions)}
            for (residue, pi), positions in rankings[:8]]}
    (residue, pi), positions = rankings[0]
    groups = []
    summary = Counter()
    # Examine group starts across the full recording, not just near clean A anchors.
    for start in range(residue, len(bits) - 103, 104):
        blocks = []
        for index, offsets in enumerate((("A",), ("B",), ("C", "C_prime"), ("D",))):
            offset_start = start + index * 26
            matches = [(offset, result) for offset in offsets
                       if (result := check_block(
                           bits[offset_start:offset_start + 26],
                           valid[offset_start:offset_start + 26],
                           offset, allow_erasure=True)) is not None]
            if len(matches) != 1:
                blocks.append({"offset": "/".join(offsets), "quality": "missing"})
                summary["missing"] += 1
                continue
            offset, result = matches[0]
            blocks.append({"offset": offset, "data": f"0x{result['data']:04X}",
                           "quality": result["quality"]})
            summary[result["quality"]] += 1
        a = blocks[0]
        if a.get("quality") == "clean" and a.get("data") != f"0x{pi:04X}":
            summary["conflicting_pi"] += 1
        clean = sum(b["quality"] == "clean" for b in blocks)
        complete = all(b["quality"] != "missing" for b in blocks)
        if complete:
            summary["complete_aligned_groups"] += 1
            if clean == 4:
                summary["strict_groups"] += 1
            else:
                summary["groups_with_erasures"] += 1
        if any(b["quality"] != "missing" for b in blocks):
            summary["groups_with_any_blocks"] += 1
            if len(groups) < max_groups:
                groups.append({"start_bit": start, "blocks": blocks,
                               "complete": complete, "clean_blocks": clean})
    return {
        "status": "consensus_candidate",
        "alignment_residue": residue, "pi": f"0x{pi:04X}",
        "clean_a_anchors": len(positions),
        "anchor_positions": positions[:30],
        "top_votes": [{"residue": r, "pi": f"0x{p:04X}", "anchors": len(v)}
                      for (r, p), v in rankings[:8]],
        "summary": dict(summary), "sample_groups": groups,
        "warning": "Framing consensus is diagnostic, not proof that missing blocks were recovered.",
    }
