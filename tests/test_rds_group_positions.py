# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Absolute group positions survive chunking and receiver resets."""
import unittest
import numpy as np

from sdrforge.protocols.rds.rds_block_sync import RdsBlockSynchronizer, encode_block


def stream():
    words = [encode_block(0x5BDB, "A"), encode_block(0x20C1, "B"),
             encode_block(0x4F4E, "C"), encode_block(0x202D, "D")]
    bits = [int(bit) for word in words for bit in f"{word:026b}"]
    return np.asarray(bits * 3, dtype=np.uint8)


class GroupPositionTest(unittest.TestCase):
    def test_positions_match_across_chunk_boundaries(self):
        values = stream()
        whole = RdsBlockSynchronizer().process(values)
        self.assertEqual([g.start_bit for g in whole], [0, 104, 208])
        decoder = RdsBlockSynchronizer()
        chunked = []
        for i in range(0, len(values), 37):
            chunked.extend(decoder.process(values[i:i + 37]))
        self.assertEqual([g.start_bit for g in chunked], [0, 104, 208])

    def test_reset_restarts_absolute_positions(self):
        decoder = RdsBlockSynchronizer()
        decoder.process(stream())
        decoder.reset()
        self.assertEqual([g.start_bit for g in decoder.process(stream())],
                         [0, 104, 208])


if __name__ == "__main__":
    unittest.main()
