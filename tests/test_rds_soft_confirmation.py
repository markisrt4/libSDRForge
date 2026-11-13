# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Tests for quarantined experimental RDS RadioText observations."""
import unittest

from sdrforge.protocols.rds.rds_block_sync import RdsGroup
from sdrforge.protocols.rds.rds_soft_confirmation import RdsSoftConfirmation


def group(text="ON -", *, pi=0x5BDB, segment=1, ab=0, kind=2):
    data = text.encode("latin-1")
    return RdsGroup(pi, (kind << 12) | (ab << 4) | segment,
                    (data[0] << 8) | data[1], (data[2] << 8) | data[3], False)


class SoftConfirmationTest(unittest.TestCase):
    def test_repetition_requires_distinct_positions(self):
        tracker = RdsSoftConfirmation()
        value = group()
        self.assertIsNone(tracker.observe(value, start_bit=100, uncertain_bits=6))
        self.assertIsNone(tracker.observe(value, start_bit=100, uncertain_bits=6))
        confirmed = tracker.observe(value, start_bit=204, uncertain_bits=17)
        self.assertEqual(confirmed.text, "ON -")
        self.assertEqual(confirmed.observations, 2)

    def test_conflicting_fragment_quarantines_segment(self):
        tracker = RdsSoftConfirmation()
        self.assertIsNone(tracker.observe(group(), start_bit=100, uncertain_bits=6))
        self.assertIsNone(tracker.observe(group("NO -"), start_bit=204, uncertain_bits=6))
        self.assertIsNone(tracker.observe(group(), start_bit=308, uncertain_bits=6))

    def test_station_or_ab_change_clears_evidence(self):
        tracker = RdsSoftConfirmation()
        tracker.observe(group(), start_bit=100, uncertain_bits=6)
        self.assertIsNone(tracker.observe(group(ab=1), start_bit=204, uncertain_bits=6))
        self.assertIsNone(tracker.observe(group(pi=0x1234), start_bit=308, uncertain_bits=6))

    def test_tmc_is_never_promoted(self):
        tracker = RdsSoftConfirmation()
        self.assertIsNone(tracker.observe(group(kind=8), start_bit=100, uncertain_bits=0))
        self.assertIsNone(tracker.observe(group(kind=8), start_bit=204, uncertain_bits=0))

    def test_rejects_invalid_provenance(self):
        tracker = RdsSoftConfirmation()
        with self.assertRaises(ValueError):
            tracker.observe(group(), start_bit=-1, uncertain_bits=1)
        with self.assertRaises(ValueError):
            tracker.observe(group(), start_bit=1, uncertain_bits=105)


if __name__ == "__main__":
    unittest.main()
