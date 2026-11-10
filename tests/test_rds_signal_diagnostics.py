# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Synthetic, hardware-free checks for FM multiplex spectrum diagnostics."""

import unittest
import numpy as np

from sdrforge.diagnostics.rds_signal_diagnostics import RdsSignalDiagnostics


class RdsSignalDiagnosticsTest(unittest.TestCase):
    def test_pilot_and_rds_band_detected(self):
        fs = 240_000
        t = np.arange(32768) / fs
        signal = (0.15 * np.sin(2 * np.pi * 19_000 * t)
                  + 0.08 * np.cos(2 * np.pi * 57_000 * t)
                  + 0.002 * np.sin(2 * np.pi * 50_000 * t))
        monitor = RdsSignalDiagnostics()
        for chunk in np.array_split(signal, 9):
            monitor.update(chunk)
        result = monitor.snapshot()
        self.assertIsNotNone(result)
        self.assertGreater(result.rds_to_adjacent_db, 10)
        self.assertGreater(result.pilot_19khz_dbfs, result.rds_57khz_band_dbfs)

    def test_insufficient_data_and_reset(self):
        monitor = RdsSignalDiagnostics()
        self.assertIsNone(monitor.snapshot())
        monitor.update(np.zeros(16384))
        self.assertIsNotNone(monitor.snapshot())
        monitor.reset()
        self.assertIsNone(monitor.snapshot())

    def test_rejects_invalid_shape(self):
        monitor = RdsSignalDiagnostics()
        with self.assertRaises(ValueError):
            monitor.update(np.zeros((2, 2)))


if __name__ == "__main__":
    unittest.main()
