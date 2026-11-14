# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Regression coverage for isolated RDS diagnostic counters."""

import unittest

import numpy as np

from sdrforge.protocols.rds.receiver_controller import RdsReceiverController


class RdsDiagnosticCountersTest(unittest.TestCase):
    def test_disabled_soft_path_reports_zero(self):
        controller = RdsReceiverController()
        controller.process_half_bits(np.array([1.0, 1.0, 1.0, 1.0]))
        status = controller.status
        self.assertEqual(status.phase_total_pairs, (2, 1))
        self.assertEqual(status.phase_invalid_pairs, (2, 1))
        self.assertEqual(status.experimental_soft_pair_guesses, (0, 0))
        self.assertEqual(status.experimental_groups_found, (0, 0))

    def test_soft_guesses_are_isolated_and_reset(self):
        controller = RdsReceiverController(experimental_soft_pairs=True)
        controller.process_half_bits(np.array([1.0, 1.0, 1.0, 1.0]))
        status = controller.status
        self.assertEqual(status.phase_invalid_pairs, (2, 1))
        self.assertEqual(status.experimental_soft_pair_guesses, (2, 1))
        self.assertEqual(status.groups_found, 0)
        controller.reset()
        status = controller.status
        self.assertEqual(status.phase_total_pairs, (0, 0))
        self.assertEqual(status.experimental_soft_pair_guesses, (0, 0))
        self.assertEqual(status.experimental_groups_found, (0, 0))


if __name__ == "__main__":
    unittest.main()
