# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""RDS uncertainty provenance across chunk boundaries."""
import unittest
import numpy as np
from sdrforge.protocols.rds.rds_block_sync import RdsBlockSynchronizer, encode_block


class GroupUncertaintyTest(unittest.TestCase):
    def test_group_uncertainty_survives_chunking(self):
        words = [encode_block(0x5BDB, "A"), encode_block(0x20C1, "B"),
                 encode_block(0x4F4E, "C"), encode_block(0x202D, "D")]
        bits = np.asarray([int(c) for w in words for c in f"{w:026b}"] * 2,
                          dtype=np.uint8)
        uncertain = np.zeros(len(bits), dtype=np.bool_)
        uncertain[[2, 26, 103, 104, 207]] = True
        decoder = RdsBlockSynchronizer()
        groups = []
        for i in range(0, len(bits), 37):
            groups.extend(decoder.process(bits[i:i + 37],
                                          uncertain=uncertain[i:i + 37]))
        self.assertEqual([(g.start_bit, g.uncertain_bits) for g in groups],
                         [(0, 3), (104, 2)])

    def test_uncertainty_length_validation(self):
        with self.assertRaises(ValueError):
            RdsBlockSynchronizer().process(np.zeros(10, dtype=np.uint8),
                                           uncertain=np.zeros(9, dtype=np.bool_))


if __name__ == "__main__":
    unittest.main()
