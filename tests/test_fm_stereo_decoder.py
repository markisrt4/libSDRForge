# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Synthetic FM stereo tests; no SDR or sound device required."""

import unittest

import numpy as np

from sdrforge.dsp.fm_stereo_decoder import FmStereoDecoder

RATE = 240_000


def stereo_multiplex(count=120_000, pilot=0.1):
    t = np.arange(count) / RATE
    left = 0.25 * np.sin(2 * np.pi * 1_000 * t)
    right = 0.25 * np.sin(2 * np.pi * 2_000 * t)
    return ((left + right) + (left - right) * np.cos(2 * np.pi * 38_000 * t)
            + pilot * np.sin(2 * np.pi * 19_000 * t)).astype(np.float32)


class FmStereoDecoderTest(unittest.TestCase):
    def test_recovers_separate_channels(self):
        decoder = FmStereoDecoder()
        pcm = decoder.process(stereo_multiplex())
        self.assertEqual(pcm.shape, (24_000, 2))
        self.assertTrue(decoder.stereo_locked)
        for channel, expected in ((0, 1_000), (1, 2_000)):
            audio = pcm[8_000:, channel]
            spectrum = np.abs(np.fft.rfft(audio))
            frequencies = np.fft.rfftfreq(len(audio), 1 / 48_000)
            self.assertLess(abs(frequencies[np.argmax(spectrum)] - expected), 10)

    def test_missing_pilot_falls_back_to_mono(self):
        decoder = FmStereoDecoder()
        pcm = decoder.process(stereo_multiplex(pilot=0))
        self.assertFalse(decoder.stereo_locked)
        np.testing.assert_allclose(pcm[:, 0], pcm[:, 1], atol=1e-6)

    def test_chunked_matches_whole_after_pilot_acquisition(self):
        samples = stereo_multiplex(count=120_000)
        warmup, payload = samples[:48_000], samples[48_000:]
        whole, chunked = FmStereoDecoder(), FmStereoDecoder()
        whole.process(warmup)
        chunked.process(warmup)
        self.assertTrue(whole.stereo_locked)
        expected = whole.process(payload)
        pieces = [chunked.process(payload[i:i + 1237])
                  for i in range(0, len(payload), 1237)]
        np.testing.assert_allclose(np.concatenate(pieces), expected, atol=1e-5)

    def test_pilot_loss_returns_to_dual_mono(self):
        decoder = FmStereoDecoder()
        decoder.process(stereo_multiplex(count=48_000))
        self.assertTrue(decoder.stereo_locked)
        pcm = decoder.process(stereo_multiplex(count=240_000, pilot=0))
        self.assertFalse(decoder.stereo_locked)
        np.testing.assert_allclose(pcm[-4800:, 0], pcm[-4800:, 1], atol=1e-6)

    def test_stereo_separation_in_decibels(self):
        pcm = FmStereoDecoder().process(stereo_multiplex(count=240_000))
        steady = pcm[12_000:]
        frequencies = np.fft.rfftfreq(len(steady), 1 / 48_000)
        left = np.abs(np.fft.rfft(steady[:, 0]))
        right = np.abs(np.fft.rfft(steady[:, 1]))
        for hz, wanted, unwanted in ((1_000, left, right),
                                      (2_000, right, left)):
            index = np.argmin(np.abs(frequencies - hz))
            separation_db = 20 * np.log10(
                max(float(wanted[index]), 1e-12)
                / max(float(unwanted[index]), 1e-12))
            self.assertGreater(separation_db, 6.0,
                               f"{hz} Hz stereo separation: {separation_db:.1f} dB")

    def test_rejects_non_vector(self):
        with self.assertRaises(ValueError):
            FmStereoDecoder().process(np.zeros((10, 2)))


if __name__ == "__main__":
    unittest.main()
