# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Parallel experimental RDS receiver must not affect trusted metadata."""
import unittest

import numpy as np

from sdrforge.protocols.rds.receiver_controller import RdsReceiverController


class RdsReceiverSoftPathTest(unittest.TestCase):
    def test_default_does_not_enable_soft_path(self):
        receiver = RdsReceiverController(pair_phase=0)
        self.assertEqual(receiver.experimental_soft_last_groups, ())
        self.assertEqual(receiver._soft_biphases, [])
        self.assertEqual(receiver._erasure_blocks, [])
        self.assertEqual(receiver.status.diagnostic_erasure_groups, (0, 0))

    def test_extractor_cutoff_is_configurable_and_validated(self):
        receiver = RdsReceiverController(extractor_cutoff_hz=2100.0)
        self.assertEqual(receiver._extractor.cutoff_hz, 2100.0)
        with self.assertRaises(ValueError):
            RdsReceiverController(extractor_cutoff_hz=100.0)

    def test_persistent_sync_is_explicit_and_preserves_soft_path_isolation(self):\n        receiver = RdsReceiverController(persistent_sync=True, experimental_soft_pairs=True)\n        self.assertTrue(receiver.status.persistent_sync_enabled)\n        self.assertEqual(len(receiver._soft_biphases), 2)\n        self.assertEqual(receiver.status.diagnostic_erasure_groups, (0, 0))\n        receiver.reset()\n        self.assertTrue(receiver.status.persistent_sync_enabled)\n\n    def test_soft_path_is_independent_and_resettable(self):
        receiver = RdsReceiverController(pair_phase=0, experimental_soft_pairs=True)
        self.assertEqual(len(receiver._soft_biphases), 2)
        self.assertEqual(len(receiver._erasure_blocks), 2)
        halves = np.asarray([1, -1, -1, 1, 1, 1, -1, 1], dtype=np.float32)
        receiver.process_half_bits(halves)
        self.assertEqual(receiver._soft_biphases[0].soft_pair_guesses, 1)
        self.assertEqual(receiver._biphases[0].soft_pair_guesses, 0)
        self.assertEqual(receiver.status.groups_found, 0)
        self.assertIsNone(receiver.status.metadata.pi)
        receiver.reset()
        self.assertEqual(receiver._soft_biphases[0].soft_pair_guesses, 0)
        self.assertEqual(receiver.experimental_soft_last_groups, ())
        self.assertEqual(receiver.status.diagnostic_erasure_groups, (0, 0))


if __name__ == "__main__":
    unittest.main()
