# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Bounded alignment holdover and PI consistency regression tests."""
import numpy as np
import pytest

from sdrforge.protocols.rds.rds_block_sync import RdsBlockSynchronizer, encode_block


def group(pi=0x5BDB):
    words = [encode_block(value, offset) for value, offset in (
        (pi, "A"), (0x20C3, "B"), (0x7279, "C"), (0x2052, "D"))]
    return np.array([(word >> shift) & 1 for word in words
                     for shift in range(25, -1, -1)], dtype=np.uint8)


def test_holdover_recovers_after_multiple_missing_groups():
    clean = group()
    lost = np.zeros(104 * 5, dtype=np.uint8)
    bits = np.concatenate((clean, lost, clean))
    valid = np.concatenate((np.ones(104, dtype=bool),
                            np.zeros(len(lost), dtype=bool),
                            np.ones(104, dtype=bool)))
    sync = RdsBlockSynchronizer(max_erasures=2, max_missed_groups=12)
    found = sync.process(bits, valid)
    assert len(found) == 2
    assert all(item.pi == 0x5BDB for item in found)


def test_wrong_pi_does_not_extend_lock():
    sync = RdsBlockSynchronizer(max_erasures=2, max_missed_groups=12)
    found = sync.process(np.concatenate((group(), group(0x1234))))
    assert len(found) == 1
    assert found[0].pi == 0x5BDB


@pytest.mark.parametrize("value", [0, 33])
def test_invalid_holdover_rejected(value):
    with pytest.raises(ValueError):
        RdsBlockSynchronizer(max_missed_groups=value)
