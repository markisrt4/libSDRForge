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


class RdsBlockSynchronizer:
    """Search an MSB-first bitstream for CRC-validated A/B/C-or-C'/D groups.

    Scans every bit for acquisition and requires four consecutive valid
    blocks. Invalid/erased bits prevent a candidate group from matching.
    No CRC correction is attempted. Retains 103 bits between calls.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._bits: list[int] = []
        self._valid: list[bool] = []
        self.groups_found = 0

    @staticmethod
    def _word(bits: list[int]) -> int:
        result = 0
        for bit in bits:
            result = (result << 1) | bit
        return result

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
            if not all(self._valid[cursor:cursor + GROUP_BITS]):
                cursor += 1
                continue
            words = [self._word(self._bits[cursor + i * BLOCK_BITS:
                                          cursor + (i + 1) * BLOCK_BITS])
                     for i in range(4)]
            a = decode_block(words[0], "A")
            b = decode_block(words[1], "B")
            c = decode_block(words[2], "C") or decode_block(words[2], "C_prime")
            d = decode_block(words[3], "D")
            if a and b and c and d:
                found.append(RdsGroup(a[1], b[1], c[1], d[1],
                                      c[0] == "C_prime"))
                self.groups_found += 1
                cursor += GROUP_BITS
            else:
                cursor += 1
        if cursor:
            del self._bits[:cursor]
            del self._valid[:cursor]
        return found
