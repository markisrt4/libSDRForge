# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Experimental RadioText preview never silently fills unknown segments."""
import unittest

from sdrforge.protocols.rds.rds_block_sync import RdsGroup
from sdrforge.protocols.rds.rds_soft_confirmation import RdsSoftConfirmation


def group(text, segment=0, pi=0x5BDB, ab=0):
    b = 0x2000 | (ab << 4) | segment
    return RdsGroup(pi, b, (ord(text[0]) << 8) | ord(text[1]),
                    (ord(text[2]) << 8) | ord(text[3]), False)


class PreviewTest(unittest.TestCase):
    def test_repeated_fragments_and_missing_positions(self):
        c = RdsSoftConfirmation()
        for pos, text, seg in [(0, "POIS", 0), (104, "ON -", 1),
                               (208, "POIS", 0), (312, "ON -", 1)]:
            c.observe(group(text, seg), start_bit=pos, uncertain_bits=4)
        preview = c.radio_text
        self.assertTrue(preview.preview.startswith("POISON -????"))
        self.assertEqual(preview.confirmed_segments, 2)
        self.assertFalse(preview.complete)
        self.assertEqual(preview.observations[:3], (2, 2, 0))

    def test_conflict_retracts_previously_confirmed_fragment(self):
        c = RdsSoftConfirmation()
        for pos in (0, 104):
            c.observe(group("POIS"), start_bit=pos, uncertain_bits=1)
        self.assertEqual(c.radio_text.confirmed_segments, 1)
        c.observe(group("NOIS"), start_bit=208, uncertain_bits=1)
        self.assertEqual(c.radio_text.confirmed_segments, 0)
        self.assertEqual(c.radio_text.conflicted_segments, (0,))

    def test_terminator_only_completes_when_prefix_confirmed(self):
        c = RdsSoftConfirmation()
        for pos, seg, text in [(0, 0, "TEST"), (104, 1, " END"),
                               (208, 0, "TEST"), (312, 1, " END"),
                               (416, 2, "\r   "), (520, 2, "\r   ")]:
            c.observe(group(text, seg), start_bit=pos, uncertain_bits=2)
        self.assertTrue(c.radio_text.complete)
        self.assertEqual(c.radio_text.preview, "TEST END")

    def test_pi_change_clears_preview(self):
        c = RdsSoftConfirmation()
        for pos in (0, 104):
            c.observe(group("POIS"), start_bit=pos, uncertain_bits=1)
        c.observe(group("NEXT", pi=0x1234), start_bit=208, uncertain_bits=1)
        self.assertEqual(c.radio_text.pi, 0x1234)
        self.assertEqual(c.radio_text.confirmed_segments, 0)


if __name__ == "__main__":
    unittest.main()
