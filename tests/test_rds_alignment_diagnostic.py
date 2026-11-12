# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Hardware-free regression checks for offline RDS alignment diagnostics."""
from __future__ import annotations

import unittest

from examples.rds_alignment_diagnostic import analyze_bits, inspect_block
from sdrforge.protocols.rds.rds_block_sync import encode_block


def word_bits(word: int) -> list[int]:
    return [(word >> shift) & 1 for shift in range(25, -1, -1)]


class RdsAlignmentDiagnosticTest(unittest.TestCase):
    def setUp(self) -> None:
        words = [encode_block(0x5BDB, "A"), encode_block(0x20C1, "B"),
                 encode_block(0xE0CD, "C"), encode_block(0x2052, "D")]
        self.bits = [bit for word in words for bit in word_bits(word)]
        self.valid = [True] * 104

    def test_strict_complete_group(self) -> None:
        result = analyze_bits(self.bits, self.valid)
        self.assertGreaterEqual(result["complete_groups_strict"], 1)

    def test_single_erasure_is_labeled_corrected(self) -> None:
        valid = self.valid.copy()
        valid[26 + 8] = False
        result = analyze_bits(self.bits, valid)
        self.assertEqual(result["complete_groups_strict"], 0)
        self.assertGreaterEqual(result["complete_groups_with_single_erasures"], 1)

    def test_two_erasures_in_block_are_rejected(self) -> None:
        valid = self.valid.copy()
        valid[26 + 8] = False
        valid[26 + 9] = False
        result = analyze_bits(self.bits, valid)
        self.assertEqual(result["complete_groups_with_single_erasures"], 0)

    def test_trusted_bit_error_is_not_corrected(self) -> None:
        bits = self.bits.copy()
        bits[26 + 8] ^= 1
        result = analyze_bits(bits, self.valid)
        self.assertEqual(result["complete_groups_strict"], 0)
        self.assertEqual(result["complete_groups_with_single_erasures"], 0)

    def test_known_block(self) -> None:
        self.assertEqual(inspect_block(self.bits[:26], self.valid[:26], "A"),
                         (0x5BDB, 0))


if __name__ == "__main__":
    unittest.main()
