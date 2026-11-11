# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Hardware-independent fractional RDS timing recovery tests."""

import unittest

import numpy as np

from sdrforge.protocols.rds.rds_symbol_timing_recovery import RdsSymbolTimingRecovery


def synthetic_symbols(count=36_000):
    rng = np.random.default_rng(4961)
    bits = rng.choice([-1.0, 1.0], size=5_000)
    t = np.arange(count) * 1187.5 / 12_000
    # Smooth symbol boundaries, as expected after an RDS matched filter.
    centers = np.arange(len(bits)) + 0.5
    return np.interp(t, centers, bits, left=bits[0], right=bits[-1]).astype(np.complex64)


class RdsSymbolTimingRecoveryTest(unittest.TestCase):
    def test_fractional_output_rate(self):
        recovered = RdsSymbolTimingRecovery().process(synthetic_symbols())
        self.assertLess(abs(len(recovered) - 3562), 4)
        self.assertTrue(np.all(np.isfinite(recovered)))
        self.assertTrue(np.iscomplexobj(recovered))

    def test_irregular_streaming_matches_whole_block(self):
        samples = synthetic_symbols(32_137)
        expected = RdsSymbolTimingRecovery().process(samples)
        recovery = RdsSymbolTimingRecovery()
        chunks = [recovery.process(samples[i:i + 137])
                  for i in range(0, len(samples), 137)]
        np.testing.assert_allclose(np.concatenate(chunks), expected, atol=1e-6)


    def test_symbol_decisions_with_fractional_offset_and_noise(self):
        """Measure actual decisions, not merely the recovered sample count."""
        rng = np.random.default_rng(2026)
        reference = rng.choice([-1.0, 1.0], size=5_000)
        count = 36_000
        # Symbol centers occur at half-integer symbol times. Offset the
        # sampling clock and add deterministic complex receiver noise.
        times = np.arange(count) * 1187.5 / 12_000 + 0.23
        samples = np.interp(times, np.arange(len(reference)) + 0.5,
                            reference, left=reference[0],
                            right=reference[-1]).astype(np.complex64)
        noise = (rng.normal(size=count) + 1j * rng.normal(size=count)) * 0.06
        samples += noise.astype(np.complex64)
        decisions = np.where(RdsSymbolTimingRecovery().process(samples).real >= 0,
                             1.0, -1.0)
        # Ignore acquisition and tail. Allow a constant integer symbol
        # alignment, but never independently shift individual decisions.
        start = 200
        length = min(2_500, len(decisions) - start - 5)
        self.assertGreater(length, 2_000)
        errors = []
        for shift in range(-3, 4):
            expected = reference[start + shift:start + shift + length]
            errors.append(np.mean(decisions[start:start + length] != expected))
        self.assertLess(min(errors), 0.02)

    def test_rds_half_bit_rate_and_chunk_continuity(self):
        rng = np.random.default_rng(57)
        data = rng.choice([-1.0, 1.0], size=8_000)
        count = 24_000
        # Each biphase data bit occupies two half-bit intervals.
        # A mid-bit polarity transition is guaranteed.
        halves = np.empty(2 * len(data), dtype=np.float64)
        halves[::2] = data
        halves[1::2] = -data
        positions = np.arange(count) * 2375.0 / 12_000
        samples = np.interp(positions, np.arange(len(halves)) + 0.5,
                            halves, left=halves[0], right=halves[-1])
        samples = samples.astype(np.complex64)
        whole = RdsSymbolTimingRecovery(symbol_rate_hz=2375)
        expected = whole.process(samples)
        self.assertLess(abs(len(expected) - 4750), 5)
        self.assertAlmostEqual(whole.samples_per_symbol, 12_000 / 2375,
                               delta=0.11)
        streaming = RdsSymbolTimingRecovery(symbol_rate_hz=2375)
        chunks = [streaming.process(samples[i:i + 113])
                  for i in range(0, len(samples), 113)]
        np.testing.assert_allclose(np.concatenate(chunks), expected, atol=1e-6)

    def test_reset_restarts_symbol_clock(self):
        samples = synthetic_symbols(12_000)
        recovery = RdsSymbolTimingRecovery()
        expected = recovery.process(samples)
        recovery.process(samples)
        recovery.reset()
        np.testing.assert_allclose(recovery.process(samples), expected, atol=1e-6)

    def test_rejects_invalid_input(self):
        recovery = RdsSymbolTimingRecovery()
        for samples in (np.ones(10), np.ones((2, 2), dtype=np.complex64),
                        np.array([complex(np.inf, 0)])):
            with self.assertRaises(ValueError):
                recovery.process(samples)
        with self.assertRaises(ValueError):
            RdsSymbolTimingRecovery(timing_gain=0)
        self.assertEqual(recovery.process(np.array([], dtype=np.complex64)).size, 0)


if __name__ == "__main__":
    unittest.main()
