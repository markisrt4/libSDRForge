# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""PI-assisted acquisition requires two corroborating clean PI anchors."""
import numpy as np

from sdrforge.protocols.rds.rds_block_sync import RdsBlockSynchronizer, encode_block


def group(pi=0x5BDB):
    words = [encode_block(value, offset) for value, offset in (
        (pi, "A"), (0x20C3, "B"), (0x7279, "C"), (0x2052, "D"))]
    return np.array([(word >> shift) & 1 for word in words
                     for shift in range(25, -1, -1)], dtype=np.uint8)


def test_correlated_anchors_acquire_recovered_group_across_chunks():
    bits = np.concatenate((group(), group()))
    valid = np.ones(len(bits), dtype=np.bool_)
    valid[30] = False
    sync = RdsBlockSynchronizer(max_erasures=2, pi_anchor_sync=True)
    assert sync.process(bits[:115], valid[:115]) == []
    found = sync.process(bits[115:], valid[115:])
    assert len(found) == 2
    assert found[0].synchronization == "pi_anchors"
    assert found[0].corrected_bits == 1
    assert found[1].corrected_bits == 0


def test_different_pi_does_not_acquire():
    bits = np.concatenate((group(), group(0x1234)))
    valid = np.ones(len(bits), dtype=np.bool_)
    valid[30] = False
    sync = RdsBlockSynchronizer(max_erasures=2, pi_anchor_sync=True)
    assert sync.process(bits, valid) == []


def test_anchor_mode_is_opt_in():
    bits = np.concatenate((group(), group()))
    valid = np.ones(len(bits), dtype=np.bool_)
    valid[30] = False
    assert RdsBlockSynchronizer(max_erasures=2).process(bits, valid) != []
    sync = RdsBlockSynchronizer(max_erasures=2)
    assert sync.process(bits[:104], valid[:104]) == []
