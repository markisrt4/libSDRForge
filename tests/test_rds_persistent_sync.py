# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Hardware-free persistent RDS synchronizer tests."""
import unittest

import numpy as np

from sdrforge.protocols.rds.rds_block_sync import encode_block
from sdrforge.protocols.rds.rds_persistent_sync import RdsPersistentSynchronizer


def group():
    words = (("A", 0x5BDB), ("B", 0x20C3), ("C", 0x7279), ("D", 0x2052))
    return np.asarray([(encode_block(value, offset) >> shift) & 1
                       for offset, value in words
                       for shift in range(25, -1, -1)], dtype=np.uint8)


class PersistentSyncTest(unittest.TestCase):
    def test_acquires_and_emits_strict_groups(self):
        sync = RdsPersistentSynchronizer()
        bits = np.tile(group(), 5)
        found = []
        for chunk in np.array_split(bits, 13):
            found.extend(sync.process(chunk))
        self.assertTrue(sync.locked)
        self.assertEqual(sync.pi, 0x5BDB)
        self.assertGreaterEqual(len(found), 3)
        self.assertTrue(all(item.pi == 0x5BDB for item in found))

    def test_missing_block_does_not_shift_frame(self):
        sync = RdsPersistentSynchronizer()
        bits = np.tile(group(), 6)
        valid = np.ones(len(bits), dtype=np.bool_)
        valid[3 * 104 + 52:3 * 104 + 54] = False
        found = sync.process(bits, valid)
        self.assertTrue(sync.locked)
        self.assertGreater(sync.missing_blocks, 0)
        self.assertGreater(sync.partial_groups, 0)
        self.assertTrue(all(item.pi == 0x5BDB for item in found))

    def test_reacquires_after_lost_anchors(self):
        sync = RdsPersistentSynchronizer(loss_groups=3)
        bits = np.tile(group(), 12)
        valid = np.ones(len(bits), dtype=np.bool_)
        for index in range(3, 8):
            valid[index * 104:index * 104 + 26] = False
        sync.process(bits, valid)
        self.assertGreaterEqual(sync.loss_events, 1)
        self.assertTrue(sync.locked)

    def test_single_anchor_does_not_lock(self):
        sync = RdsPersistentSynchronizer()
        sync.process(group())
        self.assertFalse(sync.locked)


if __name__ == "__main__":
    unittest.main()
