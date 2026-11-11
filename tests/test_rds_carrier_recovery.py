# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Hardware-free BPSK carrier loop tests."""

import unittest

import numpy as np

from sdrforge.protocols.rds.rds_carrier_recovery import RdsCarrierRecovery


def synthetic_bpsk(count=12_000, offset_hz=35.0):
    rng = np.random.default_rng(4961)
    # Approximately 10.105 samples per RDS bit at 12 kSPS.
    symbols = rng.choice([-1.0, 1.0], size=2_000)
    indices = np.floor(np.arange(count) * 1187.5 / 12_000).astype(int)
    phase = 0.8 + 2 * np.pi * offset_hz * np.arange(count) / 12_000
    return (symbols[indices] * np.exp(1j * phase)).astype(np.complex64)


class RdsCarrierRecoveryTest(unittest.TestCase):
    def test_recovers_frequency_and_bpsk_axis(self):
        recovered = RdsCarrierRecovery()
        result = recovered.process(synthetic_bpsk())
        self.assertAlmostEqual(recovered.frequency_offset_hz, 35, delta=3)
        steady = result[4_000:]
        self.assertLess(np.mean(np.abs(steady.imag)), 0.15)

    def test_irregular_streaming_matches_whole_block(self):
        samples = synthetic_bpsk(count=9_127, offset_hz=-22)
        expected = RdsCarrierRecovery().process(samples)
        decoder = RdsCarrierRecovery()
        chunks = [decoder.process(samples[i:i + 137])
                  for i in range(0, len(samples), 137)]
        np.testing.assert_allclose(np.concatenate(chunks), expected, atol=1e-6)

    def test_reset_restarts_loop(self):
        samples = synthetic_bpsk(count=2_000)
        decoder = RdsCarrierRecovery()
        expected = decoder.process(samples)
        decoder.reset()
        np.testing.assert_allclose(decoder.process(samples), expected, atol=1e-6)

    def test_validation(self):
        decoder = RdsCarrierRecovery()
        with self.assertRaises(ValueError):
            decoder.process(np.ones(10))
        with self.assertRaises(ValueError):
            decoder.process(np.array([complex(np.nan, 0)]))
        with self.assertRaises(ValueError):
            RdsCarrierRecovery(loop_bandwidth=0)
        self.assertEqual(decoder.process(np.array([], dtype=np.complex64)).size, 0)


if __name__ == "__main__":
    unittest.main()
