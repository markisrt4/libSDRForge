# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Synthetic RDS extraction tests; no SDR hardware required."""

import unittest

import numpy as np

from sdrforge.protocols.rds.rds_subcarrier_extractor import RdsSubcarrierExtractor

RATE = 240_000


def multiplex(count=48_000):
    t = np.arange(count) / RATE
    return (0.25 * np.sin(2 * np.pi * 1_000 * t)
            + 0.08 * np.sin(2 * np.pi * 19_000 * t)
            + 0.12 * np.cos(2 * np.pi * 38_000 * t)
            + 0.05 * np.cos(2 * np.pi * (57_000 + 1_000) * t)).astype(np.float32)


class RdsSubcarrierExtractorTest(unittest.TestCase):
    def test_rds_sideband_translates_to_one_kilohertz(self):
        pcm = RdsSubcarrierExtractor().process(multiplex())
        self.assertEqual(pcm.shape, (2400,))
        steady = pcm[600:]
        frequencies = np.fft.fftfreq(len(steady), 1 / 12_000)
        spectrum = np.abs(np.fft.fft(steady))
        peak = frequencies[np.argmax(spectrum)]
        self.assertLess(abs(peak - 1_000), 10)
        self.assertGreater(np.max(np.abs(steady)), 0.03)

    def test_streaming_matches_single_block(self):
        samples = multiplex(count=53_217)
        expected = RdsSubcarrierExtractor().process(samples)
        extractor = RdsSubcarrierExtractor()
        pieces = [extractor.process(samples[i:i + 1237])
                  for i in range(0, len(samples), 1237)]
        np.testing.assert_allclose(np.concatenate(pieces), expected, atol=1e-5)

    def test_reset_restores_initial_state(self):
        samples = multiplex()
        extractor = RdsSubcarrierExtractor()
        expected = extractor.process(samples)
        extractor.process(samples)
        extractor.reset()
        np.testing.assert_allclose(extractor.process(samples), expected, atol=1e-6)

    def test_rejects_bad_input(self):
        extractor = RdsSubcarrierExtractor()
        for samples in (np.zeros((10, 2)), np.ones(10, dtype=np.complex64),
                        np.array([np.nan])):
            with self.assertRaises(ValueError):
                extractor.process(samples)
        self.assertEqual(extractor.process(np.array([])).size, 0)


if __name__ == "__main__":
    unittest.main()
