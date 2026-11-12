# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Streaming synchronization must acquire cleanly before erasure recovery."""
import numpy as np
import pytest

from sdrforge.protocols.rds.rds_block_sync import (
    RdsBlockSynchronizer,
    encode_block,
)


def group_bits():
    words = [encode_block(data, offset) for data, offset in (
        (0x5BDB, "A"), (0x20C3, "B"),
        (0x7279, "C"), (0x2052, "D"))]
    return np.array([
        (word >> shift) & 1 for word in words
        for shift in range(25, -1, -1)
    ], dtype=np.uint8)


def test_default_strict_and_explicit_recovery():
    clean = group_bits()
    damaged = clean.copy()
    valid = np.ones(104, dtype=np.bool_)
    valid[3:5] = False
    damaged[3:5] = 0
    strict = RdsBlockSynchronizer()
    assert len(strict.process(clean)) == 1
    assert strict.process(damaged, valid) == []
    optional = RdsBlockSynchronizer(max_erasures=2)
    assert len(optional.process(clean)) == 1
    result = optional.process(damaged, valid)
    assert len(result) == 1
    assert result[0].pi == 0x5BDB
    assert result[0].corrected_bits == 2
    assert result[0].corrected_positions[0] == (3, 4)


def test_damaged_group_cannot_acquire_lock():
    bits = group_bits()
    valid = np.ones(104, dtype=np.bool_)
    valid[3] = False
    assert RdsBlockSynchronizer(max_erasures=2).process(bits, valid) == []


def test_streaming_chunks_preserve_alignment():
    bits = group_bits()
    sync = RdsBlockSynchronizer(max_erasures=2)
    assert sync.process(bits[:47]) == []
    assert len(sync.process(bits[47:])) == 1
    assert len(sync.process(bits)) == 1


@pytest.mark.parametrize("budget", [-1, 3])
def test_invalid_budget(budget):
    with pytest.raises(ValueError):
        RdsBlockSynchronizer(max_erasures=budget)
