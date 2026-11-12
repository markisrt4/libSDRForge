# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Regression tests for opt-in RDS erasure recovery."""
import pytest

from sdrforge.protocols.rds.rds_block_sync import encode_block
from sdrforge.protocols.rds.rds_erasure_recovery import recover_block


def word_bits(word):
    return [(word >> shift) & 1 for shift in range(25, -1, -1)]


@pytest.mark.parametrize("offset,data", [
    ("A", 0x5BDB), ("B", 0x20C3), ("C", 0x7279),
    ("C_prime", 0x7279), ("D", 0x2052),
])
def test_clean_block_is_strictly_decodable(offset, data):
    bits = word_bits(encode_block(data, offset))
    result = recover_block(bits, [True] * 26, [offset])
    assert result is not None
    assert (result.offset, result.data, result.corrected_bits) == (offset, data, 0)


@pytest.mark.parametrize("positions", [(3,), (3, 4), (22, 23)])
def test_erasure_recovery_requires_explicit_budget(positions):
    bits = word_bits(encode_block(0x5BDB, "A"))
    valid = [True] * 26
    for position in positions:
        valid[position] = False
        bits[position] = 0
    assert recover_block(bits, valid, ["A"]) is None
    if len(positions) == 2:
        assert recover_block(bits, valid, ["A"], max_erasures=1) is None
    result = recover_block(bits, valid, ["A"], max_erasures=len(positions))
    assert result is not None
    assert result.data == 0x5BDB
    assert result.corrected_positions == positions
    assert result.corrected_values == tuple(
        word_bits(encode_block(0x5BDB, "A"))[p] for p in positions
    )


def test_wrong_offset_does_not_pass_crc():
    bits = word_bits(encode_block(0x5BDB, "A"))
    assert recover_block(bits, [True] * 26, ["B"]) is None


@pytest.mark.parametrize("budget", [-1, 3])
def test_unsupported_budget_rejected(budget):
    with pytest.raises(ValueError):
        recover_block([0] * 26, [True] * 26, ["A"], max_erasures=budget)


def test_invalid_bit_length_rejected():
    with pytest.raises(ValueError):
        recover_block([0] * 25, [True] * 25, ["A"])


def test_nonbinary_input_rejected():
    with pytest.raises(ValueError):
        recover_block([2] + [0] * 25, [True] * 26, ["A"])
