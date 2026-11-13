# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Tests for streaming biphase and differential RDS bit decisions."""

import unittest

import numpy as np

from sdrforge.protocols.rds.rds_biphase_decoder import RdsBiphaseDecoder


def encoded_halves(bits, initial=0):
    previous = initial
    halves = []
    for bit in bits:
        previous ^= int(bit)
        halves.extend((previous, previous ^ 1))
    return np.asarray(halves, dtype=np.int8) * 2 - 1


class RdsBiphaseDecoderTest(unittest.TestCase):
    def test_round_trip_and_polarity_ambiguity(self):
        rng = np.random.default_rng(57)
        expected = rng.integers(0, 2, size=500, dtype=np.uint8)
        halves = encoded_halves(expected)
        for polarity in (1, -1):
            decoder = RdsBiphaseDecoder()
            actual, valid = decoder.process(halves * polarity)
            np.testing.assert_array_equal(actual[1:], expected[1:])
            self.assertFalse(valid[0])
            self.assertTrue(np.all(valid[1:]))
            self.assertEqual(decoder.invalid_pairs, 0)

    def test_irregular_chunk_boundaries(self):
        bits = np.random.default_rng(4961).integers(0, 2, size=257)
        halves = encoded_halves(bits)
        expected = RdsBiphaseDecoder().process(halves)
        decoder = RdsBiphaseDecoder()
        results = [decoder.process(halves[i:i + 7])
                   for i in range(0, len(halves), 7)]
        np.testing.assert_array_equal(np.concatenate([r[0] for r in results]), expected[0])
        np.testing.assert_array_equal(np.concatenate([r[1] for r in results]), expected[1])

    def test_pair_phase_with_leading_half_bit(self):
        bits = np.random.default_rng(20).integers(0, 2, size=100)
        halves = np.concatenate(([1], encoded_halves(bits)))
        decoded, valid = RdsBiphaseDecoder(pair_phase=1).process(halves)
        np.testing.assert_array_equal(decoded[1:], bits[1:])
        self.assertTrue(np.all(valid[1:]))

    def test_invalid_pair_marks_erasure_and_resets_history(self):
        halves = encoded_halves([0, 1, 0, 1, 1])
        halves[4:6] = 1
        decoder = RdsBiphaseDecoder()
        decoded, valid = decoder.process(halves)
        self.assertEqual(decoder.invalid_pairs, 1)
        np.testing.assert_array_equal(valid, [False, True, False, False, True])
        self.assertEqual(decoded[-1], 1)

    def test_experimental_soft_pair_uses_stronger_half_and_keeps_history(self):
        # Encoded halves for [0, 1, 0, 1, 1] with one damaged pair.
        halves = encoded_halves([0, 1, 0, 1, 1]).astype(float)
        halves[4] = 0.2
        halves[5] = 1.0  # Both signs positive; stronger second half wins.
        decoder = RdsBiphaseDecoder(experimental_soft_pairs=True)
        bits, valid = decoder.process(halves)
        self.assertEqual(decoder.invalid_pairs, 1)
        self.assertEqual(decoder.soft_pair_guesses, 1)
        self.assertFalse(valid[0])
        self.assertTrue(np.all(valid[1:]))
        self.assertEqual(len(bits), 5)

    def test_soft_pair_streaming_continuity(self):
        halves = encoded_halves([0, 1, 0, 1, 1, 0]).astype(float)
        halves[4:6] = [0.2, 1.0]
        expected = RdsBiphaseDecoder(experimental_soft_pairs=True).process(halves)
        decoder = RdsBiphaseDecoder(experimental_soft_pairs=True)
        chunks = [decoder.process(halves[i:i + 3]) for i in range(0, len(halves), 3)]
        np.testing.assert_array_equal(np.concatenate([x[0] for x in chunks]), expected[0])
        np.testing.assert_array_equal(np.concatenate([x[1] for x in chunks]), expected[1])
        self.assertEqual(decoder.soft_pair_guesses, 1)

    def test_soft_pair_uncertainty_propagates_to_next_differential_bit(self):
        halves = encoded_halves([0, 1, 0, 1, 1]).astype(float)
        halves[4:6] = [0.2, 1.0]
        decoder = RdsBiphaseDecoder(experimental_soft_pairs=True)
        decoder.process(halves)
        np.testing.assert_array_equal(
            decoder.last_uncertain_mask, [True, False, True, True, False])
        decoder.reset()
        self.assertEqual(len(decoder.last_uncertain_mask), 0)

    def test_validation_and_reset(self):
        with self.assertRaises(ValueError):
            RdsBiphaseDecoder(pair_phase=2)
        decoder = RdsBiphaseDecoder()
        for bad in (np.ones((2, 2)), np.array([np.nan])):
            with self.assertRaises(ValueError):
                decoder.process(bad)
        decoder.process(np.array([1, 1]))
        self.assertEqual(decoder.invalid_pairs, 1)
        decoder.reset()
        self.assertEqual(decoder.invalid_pairs, 0)


if __name__ == "__main__":
    unittest.main()
