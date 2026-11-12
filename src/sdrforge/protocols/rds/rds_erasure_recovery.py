# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Optional CRC-guided erasure recovery for a single 26-bit RDS block.

This module does not change strict synchronization or enable correction by
default. A recovered block is experimental and must retain its provenance.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product

from sdrforge.protocols.rds.rds_block_sync import BLOCK_BITS, decode_block


@dataclass(frozen=True)
class RdsRecoveredBlock:
    offset: str
    data: int
    corrected_positions: tuple[int, ...]
    corrected_values: tuple[int, ...]

    @property
    def corrected_bits(self) -> int:
        return len(self.corrected_positions)


def recover_block(
    bits: Sequence[int],
    valid: Sequence[bool],
    expected_offsets: Sequence[str],
    *,
    max_erasures: int = 0,
) -> RdsRecoveredBlock | None:
    """Decode a block only if exactly one CRC-valid assignment exists.

    The default max_erasures=0 preserves strict CRC-only behavior.
    Positions are MSB-first, 0..25. Invalid bits are unknown, not flips.
    Only 0, 1 or 2 erasures are supported to bound false positives.
    """
    if max_erasures not in (0, 1, 2):
        raise ValueError("max_erasures must be 0, 1 or 2")
    if len(bits) != BLOCK_BITS or len(valid) != BLOCK_BITS:
        raise ValueError("RDS block and validity mask must contain 26 bits")
    if not expected_offsets:
        raise ValueError("expected_offsets must not be empty")
    if any(int(bit) not in (0, 1) for bit in bits):
        raise ValueError("RDS bits must be binary")
    erased = tuple(i for i, flag in enumerate(valid) if not flag)
    if len(erased) > max_erasures:
        return None
    matches: list[RdsRecoveredBlock] = []
    for values in product((0, 1), repeat=len(erased)):
        candidate = [int(bit) for bit in bits]
        for position, value in zip(erased, values):
            candidate[position] = value
        word = 0
        for bit in candidate:
            word = (word << 1) | bit
        for offset in dict.fromkeys(expected_offsets):
            decoded = decode_block(word, offset)
            if decoded is not None:
                matches.append(RdsRecoveredBlock(
                    decoded[0], decoded[1], erased, values))
    return matches[0] if len(matches) == 1 else None
