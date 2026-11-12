# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""RDS 26-bit checkwords, offset words, and streaming group synchronization."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

POLYNOMIAL = 0x5B9  # x^10 + x^8 + x^7 + x^5 + x^4 + x^3 + 1
OFFSET_WORDS = {"A": 0x0FC, "B": 0x198, "C": 0x168,
                "C_prime": 0x350, "D": 0x1B4}
BLOCK_BITS = 26
GROUP_BITS = 104


def syndrome(word: int) -> int:
    """Compute the 10-bit remainder of an MSB-first 26-bit RDS word."""
    if not 0 <= word < (1 << BLOCK_BITS):
        raise ValueError("RDS block must be 26 bits")
    remainder = word
    for shift in range(15, -1, -1):
        if remainder & (1 << (shift + 10)):
            remainder ^= POLYNOMIAL << shift
    return remainder & 0x3FF


def encode_block(data: int, offset: str) -> int:
    """Construct an RDS block with the standard offset-masked checkword."""
    if not 0 <= data <= 0xFFFF or offset not in OFFSET_WORDS:
        raise ValueError("invalid RDS data or block offset")
    message = data << 10
    return message | (syndrome(message) ^ OFFSET_WORDS[offset])


def decode_block(word: int, expected: str | None = None) -> tuple[str, int] | None:
    """Return (offset_name, 16-bit payload) if the checkword is valid."""
    remainder = syndrome(word)
    if expected is not None:
        if expected not in OFFSET_WORDS:
            raise ValueError("unknown RDS offset")
        return (expected, word >> 10) if remainder == OFFSET_WORDS[expected] else None
    for name, offset in OFFSET_WORDS.items():
        if remainder == offset:
            return name, word >> 10
    return None


@dataclass(frozen=True)
class RdsGroup:
    pi: int
    block_b: int
    block_c: int
    block_d: int
    c_prime: bool
    corrected_bits: int = 0
    corrected_positions: tuple[tuple[int, ...], ...] = ((), (), (), ())
    synchronization: str = "strict"


class RdsBlockSynchronizer:
    """Stream RDS groups with strict acquisition and optional erasure recovery.

    Recovery is permitted only after a complete CRC-clean group establishes
    alignment. After three missed aligned groups, reacquire strictly.
    """

    def __init__(self, *, max_erasures: int = 0, pi_anchor_sync: bool = False) -> None:
        if max_erasures not in (0, 1, 2):
            raise ValueError("max_erasures must be 0, 1 or 2")
        self.max_erasures = max_erasures
        self.pi_anchor_sync = bool(pi_anchor_sync)
        self.reset()

    def reset(self) -> None:
        self._bits: list[int] = []
        self._valid: list[bool] = []
        self.groups_found = 0
        self._locked = False
        self._misses = 0

    @staticmethod
    def _word(bits: list[int]) -> int:
        result = 0
        for bit in bits:
            result = (result << 1) | bit
        return result

    def _decode_group(self, cursor: int, *, allow_recovery: bool) -> RdsGroup | None:
        # Imported lazily to avoid a module cycle with rds_erasure_recovery.
        from sdrforge.protocols.rds.rds_erasure_recovery import recover_block

        names = (("A",), ("B",), ("C", "C_prime"), ("D",))
        decoded = []
        for index, offsets in enumerate(names):
            start = cursor + index * BLOCK_BITS
            block = recover_block(
                self._bits[start:start + BLOCK_BITS],
                self._valid[start:start + BLOCK_BITS],
                offsets,
                max_erasures=self.max_erasures if allow_recovery else 0,
            )
            if block is None:
                return None
            decoded.append(block)
        a, b, c, d = decoded
        return RdsGroup(a.data, b.data, c.data, d.data,
                        c.offset == "C_prime",
                        sum(block.corrected_bits for block in decoded),
                        tuple(block.corrected_positions for block in decoded))

    def _clean_pi(self, start: int) -> int | None:
        if not all(self._valid[start:start + BLOCK_BITS]):
            return None
        result = decode_block(self._word(self._bits[start:start + BLOCK_BITS]), "A")
        return result[1] if result is not None else None

    def process(self, bits: np.ndarray, valid: np.ndarray | None = None) -> list[RdsGroup]:
        values = np.asarray(bits)
        if values.ndim != 1 or not np.all((values == 0) | (values == 1)):
            raise ValueError("expected one-dimensional binary bits")
        if valid is None:
            flags = np.ones(len(values), dtype=np.bool_)
        else:
            flags = np.asarray(valid)
            if flags.ndim != 1 or len(flags) != len(values):
                raise ValueError("valid mask must match bits")
        self._bits.extend(int(bit) for bit in values)
        self._valid.extend(bool(flag) for flag in flags)
        found: list[RdsGroup] = []
        cursor = 0
        while len(self._bits) - cursor >= GROUP_BITS:
            group = self._decode_group(cursor, allow_recovery=self._locked)
            if group is None and not self._locked and self.pi_anchor_sync:
                pi = self._clean_pi(cursor)
                if pi is not None:
                    if len(self._bits) - cursor < GROUP_BITS + BLOCK_BITS:
                        break
                    if self._clean_pi(cursor + GROUP_BITS) == pi:
                        recovered = self._decode_group(cursor, allow_recovery=True)
                        if recovered is not None and recovered.pi == pi:
                            from dataclasses import replace
                            group = replace(recovered, synchronization="pi_anchors")
            if group is not None:
                found.append(group)
                self.groups_found += 1
                self._locked = True
                self._misses = 0
                cursor += GROUP_BITS
            elif self._locked:
                self._misses += 1
                if self._misses >= 3:
                    self._locked = False
                    self._misses = 0
                    # Scan the missed region for a new strict alignment.
                    cursor = max(0, cursor - 2 * GROUP_BITS + 1)
                else:
                    cursor += GROUP_BITS
            else:
                cursor += 1
        if cursor:
            del self._bits[:cursor]
            del self._valid[:cursor]
        return found
