# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Full-chain RDS robustness characterization using reproducible synthetic RF.

These are diagnostic sweeps, not guaranteed reception thresholds. A failing
baseline or non-finite DSP diagnostic is a regression; degraded reception at
high noise is reported rather than incorrectly asserted to succeed.
"""

import unittest

import numpy as np
from test_rds_end_to_end_waveform import waveform

from sdrforge.protocols.rds.receiver_controller import RdsReceiverController


def run_case(samples: np.ndarray, chunk_size: int) -> dict:
    receiver = RdsReceiverController()
    accepted = 0
    for start in range(0, len(samples), chunk_size):
        accepted += len(receiver.process_multiplex(samples[start:start + chunk_size]))
    status = receiver.status
    return {
        "accepted_groups": accepted,
        "phase_groups": status.phase_groups_found,
        "invalid_pairs": status.invalid_pairs,
        "locked_phase": status.locked_pair_phase,
        "carrier_offset_hz": status.carrier_offset_hz,
        "half_bit_samples_per_symbol": status.half_bit_samples_per_symbol,
        "pi": status.metadata.pi,
        "ps": status.metadata.program_service,
    }


class RdsRobustnessTest(unittest.TestCase):
    def test_noise_sweep_diagnostics(self):
        results = {}
        for noise in (0.0, 0.01, 0.03, 0.06):
            result = run_case(waveform(noise=noise), 8191)
            results[noise] = result
            with self.subTest(noise=noise):
                self.assertTrue(np.isfinite(result["carrier_offset_hz"]))
                self.assertTrue(np.isfinite(result["half_bit_samples_per_symbol"]))
                self.assertGreaterEqual(result["accepted_groups"], 0)
        print("RDS noise sweep:", results)
        self.assertEqual(results[0.0]["ps"], "ORC FM")

    def test_carrier_offset_sweep_diagnostics(self):
        results = {}
        for offset in (-35.0, -10.0, 0.0, 10.0, 35.0):
            result = run_case(waveform(carrier_offset_hz=offset), 8191)
            results[offset] = result
            with self.subTest(offset_hz=offset):
                self.assertTrue(np.isfinite(result["carrier_offset_hz"]))
                self.assertGreaterEqual(result["accepted_groups"], 0)
        print("RDS carrier offset sweep:", results)
        self.assertEqual(results[0.0]["ps"], "ORC FM")

    def test_irregular_buffer_sizes(self):
        samples = waveform()
        baseline = run_case(samples, len(samples))
        print("RDS baseline:", baseline)
        self.assertEqual(baseline["ps"], "ORC FM")
        for chunk in (127, 1237, 8191, 24000):
            with self.subTest(chunk=chunk):
                result = run_case(samples, chunk)
                self.assertEqual(result["ps"], baseline["ps"])
                self.assertEqual(result["accepted_groups"], baseline["accepted_groups"])
                self.assertEqual(result["phase_groups"], baseline["phase_groups"])

    def test_interruption_and_recovery_diagnostics(self):
        samples = waveform(cycles=8)
        damaged = samples.copy()
        midpoint = len(damaged) // 2
        damaged[midpoint:midpoint + 48_000] = 0.0
        result = run_case(damaged, 8191)
        print("RDS interruption:", result)
        self.assertTrue(np.isfinite(result["carrier_offset_hz"]))
        self.assertGreaterEqual(result["accepted_groups"], 0)


if __name__ == "__main__":
    unittest.main()
