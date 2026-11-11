# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Synthetic offline framing consensus regression tests."""
import unittest

from examples.rds_framing_consensus import analyze_framing
from sdrforge.protocols.rds.rds_block_sync import encode_block


def bits_for(data, offset):
    word = encode_block(data, offset)
    return [(word >> shift) & 1 for shift in range(25, -1, -1)]


class FramingConsensusTest(unittest.TestCase):
    def setUp(self):
        group = sum((bits_for(value, offset) for value, offset in (
            (0x5BDB, "A"), (0x20C3, "B"), (0x7279, "C"),
            (0x2052, "D"))), [])
        self.bits = group * 4
        self.valid = [True] * len(self.bits)

    def test_clean_alignment(self):
        result = analyze_framing(self.bits, self.valid)
        self.assertEqual(result["status"], "consensus_candidate")
        self.assertEqual(result["pi"], "0x5BDB")
        self.assertEqual(result["summary"]["strict_groups"], 4)

    def test_missing_block_does_not_destroy_alignment(self):
        valid = self.valid.copy()
        valid[26 + 2] = False
        valid[26 + 3] = False
        result = analyze_framing(self.bits, valid)
        self.assertEqual(result["alignment_residue"], 0)
        self.assertEqual(result["summary"]["strict_groups"], 3)
        self.assertGreaterEqual(result["summary"]["missing"], 1)

    def test_one_erasure_is_separately_counted(self):
        valid = self.valid.copy()
        valid[26 + 2] = False
        result = analyze_framing(self.bits, valid)
        self.assertEqual(result["summary"]["strict_groups"], 3)
        self.assertEqual(result["summary"]["groups_with_erasures"], 1)

    def test_no_consensus_from_single_anchor(self):
        result = analyze_framing(self.bits[:104], self.valid[:104])
        self.assertEqual(result["status"], "no_consensus")


if __name__ == "__main__":
    unittest.main()
