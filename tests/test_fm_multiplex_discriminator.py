# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Synthetic multiplex tests independent of SDR hardware."""

import unittest

import numpy as np

from sdrforge.dsp.fm_multiplex_discriminator import FmMultiplexDiscriminator


class FmMultiplexDiscriminatorTest(unittest.TestCase):
    def test_preserves_stereo_pilot_and_rds_components(self):
        rate = 240_000
        count = 48_000
        t = np.arange(count) / rate
        multiplex = (0.18 * np.sin(2 * np.pi * 1_000 * t)
                     + 0.08 * np.sin(2 * np.pi * 19_000 * t)
                     + 0.10 * np.sin(2 * np.pi * 38_000 * t)
                     + 0.04 * np.sin(2 * np.pi * 57_000 * t))
        phase = np.cumsum(multiplex) * (2 * np.pi * 75_000 / rate)
        iq = np.exp(1j * phase).astype(np.complex64)
        result = FmMultiplexDiscriminator().process(iq)
        self.assertEqual(len(result), count)
        frequencies = np.fft.rfftfreq(count, 1 / rate)
        spectrum = np.abs(np.fft.rfft(result))
        for frequency in (1_000, 19_000, 38_000, 57_000):
            index = np.argmin(np.abs(frequencies - frequency))
            self.assertGreater(spectrum[index], 100)

    def test_streaming_matches_whole_block(self):
        rate = 240_000
        t = np.arange(48_000) / rate
        phase = np.cumsum(0.2 * np.sin(2 * np.pi * 1_000 * t)) * (2 * np.pi * 75_000 / rate)
        iq = np.exp(1j * phase).astype(np.complex64)
        expected = FmMultiplexDiscriminator().process(iq)
        decoder = FmMultiplexDiscriminator()
        chunks = [decoder.process(iq[i:i + 1237]) for i in range(0, len(iq), 1237)]
        np.testing.assert_allclose(np.concatenate(chunks), expected, atol=1e-5)

    def test_rejects_real_samples(self):
        with self.assertRaises(ValueError):
            FmMultiplexDiscriminator().process(np.zeros(100))


if __name__ == "__main__":
    unittest.main()
